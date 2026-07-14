#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find or prepare one exact benchmark run for safe restart."
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--algorithm-id", required=True)
    parser.add_argument("--case-study", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help=(
            "repair a completed run_state whose benchmark summary was not fully "
            "finalized, making that run resumable"
        ),
    )
    return parser.parse_args()


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _matching_states(args: argparse.Namespace) -> Iterable[tuple[Path, Dict[str, Any]]]:
    root = args.results_dir / args.namespace
    case_name = args.case_study.name
    candidates = sorted(
        root.glob("*/run_state.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )
    for state_path in candidates:
        state = _load_json(state_path)
        if state is None:
            continue
        try:
            matches = (
                state.get("algorithm_id") == args.algorithm_id
                and state.get("case_study_basename") == case_name
                and int(state.get("seed", -1)) == args.seed
                and int(state.get("budget", -1)) == args.budget
            )
        except (TypeError, ValueError):
            matches = False
        if matches:
            yield state_path, state


def _valid_completed_summary(
    summary_path: Path,
    state: Dict[str, Any],
    args: argparse.Namespace,
) -> bool:
    summary = _load_json(summary_path)
    if summary is None:
        return False
    try:
        return (
            state.get("status") == "completed"
            and summary.get("run_status") == "completed"
            and summary.get("algorithm_id") == args.algorithm_id
            and summary.get("case_study_basename") == args.case_study.name
            and int(summary.get("seed", -1)) == args.seed
            and int(summary.get("budget", -1)) == args.budget
            and int(summary.get("simulator_attempts", -1)) >= args.budget
        )
    except (TypeError, ValueError):
        return False


def determine_status(args: argparse.Namespace) -> tuple[str, Optional[Path]]:
    matches = list(_matching_states(args))
    for state_path, state in matches:
        summary_path = state_path.parent / "benchmark" / "summary.json"
        if _valid_completed_summary(summary_path, state, args):
            return "completed", state_path.parent

    if not matches:
        return "new", None

    state_path, state = matches[0]
    if state.get("status") == "completed" and args.prepare:
        state["status"] = "running"
        state["recovery_note"] = (
            "Reopened because run_state was completed before a valid benchmark "
            "summary was available."
        )
        state["updated_at"] = datetime.now().isoformat()
        _atomic_write_json(state_path, state)
        print(
            f"Reopened incomplete benchmark finalization: {state_path.parent}",
            file=sys.stderr,
        )
    return "resume", state_path.parent


def main() -> int:
    args = parse_args()
    if args.seed < 0 or args.budget <= 0:
        print("seed must be non-negative and budget must be positive", file=sys.stderr)
        return 2
    status, path = determine_status(args)
    print(status)
    if path is not None:
        print(path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
