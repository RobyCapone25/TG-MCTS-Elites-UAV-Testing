#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


METRICS = [
    "success_indicator",
    "failure_yield_official",
    "failure_yield_returnable",
    "initial_official_point_yield",
    "mean_confirmed_point_total",
    "diverse_mean_confirmed_point_total",
    "best_min_distance",
    "time_to_first_official_failure_attempt",
    "time_to_first_returnable_failure_attempt",
    "archive_coverage",
    "elite_cells_filled",
    "diverse_failures_returned",
    "mean_failure_reproducibility_returnable",
    "mean_obstacle_count_returnable",
    "single_obstacle_returnable_fraction",
    "mean_nearest_scenario_distance_selected",
    "mean_nearest_trajectory_dtw_selected",
    "candidate_proposals",
    "invalid_candidate_proposals",
    "duplicate_candidate_proposals",
    "system_error_attempts",
    "unrecorded_or_interrupted_attempts",
    "simulation_seconds_recorded",
    "search_seconds_recorded",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate finalized BenchmarkRecorder summaries across algorithms "
            "and paired seeds. Incomplete/interrupted runs are ignored."
        )
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/benchmark_comparison"),
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="write CSV/JSON aggregates without generating paired comparison plots",
    )
    return parser.parse_args()


def _load_json(path: Path) -> Dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _valid_finalized_summary(path: Path, summary: Mapping[str, Any]) -> bool:
    state_path = path.parents[1] / "run_state.json"
    state = _load_json(state_path)
    if state is None:
        return False
    try:
        budget = int(summary.get("budget", -1))
        return (
            summary.get("run_status") == "completed"
            and state.get("status") == "completed"
            and summary.get("algorithm_id") == state.get("algorithm_id")
            and summary.get("case_study_basename") == state.get("case_study_basename")
            and int(summary.get("seed", -1)) == int(state.get("seed", -2))
            and budget == int(state.get("budget", -2))
            and int(summary.get("simulator_attempts", -1)) >= budget > 0
        )
    except (TypeError, ValueError):
        return False


def _newer(left: Mapping[str, Any], right: Mapping[str, Any]) -> Mapping[str, Any]:
    left_key = (str(left.get("generated_at", "")), str(left.get("summary_file", "")))
    right_key = (str(right.get("generated_at", "")), str(right.get("summary_file", "")))
    return right if right_key >= left_key else left


def load_summaries(results_dir: Path) -> List[Dict[str, Any]]:
    latest: Dict[Tuple[str, str, int, int], Mapping[str, Any]] = {}
    for path in sorted(results_dir.glob("*/*/benchmark/summary.json")):
        data = _load_json(path)
        if data is None or not _valid_finalized_summary(path, data):
            continue
        row = dict(data)
        row["summary_file"] = str(path.resolve())
        row["run_state_file"] = str((path.parents[1] / "run_state.json").resolve())
        try:
            key = (
                str(row.get("mission_label", "unknown")),
                str(row.get("algorithm_id", "unknown")),
                int(row.get("seed")),
                int(row.get("budget")),
            )
        except (TypeError, ValueError):
            continue
        latest[key] = _newer(latest[key], row) if key in latest else row
    return [dict(latest[key]) for key in sorted(latest)]


def numeric(values: Iterable[Any]) -> List[float]:
    output: List[float] = []
    for value in values:
        if value is None or value == "":
            continue
        try:
            output.append(float(value))
        except (TypeError, ValueError):
            continue
    return output


def describe(values: Sequence[float]) -> Dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "q1": None,
            "q3": None,
            "minimum": None,
            "maximum": None,
        }
    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "q1": q1,
        "q3": q3,
        "minimum": min(values),
        "maximum": max(values),
    }


def _atomic_write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _atomic_write_json(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(list(rows), stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def aggregate(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        try:
            budget = int(row.get("budget"))
        except (TypeError, ValueError):
            continue
        groups[
            (
                str(row.get("mission_label", "unknown")),
                str(row.get("algorithm_id", "unknown")),
                budget,
            )
        ].append(row)

    output: List[Dict[str, Any]] = []
    for (mission, algorithm, budget), group in sorted(groups.items()):
        successes = numeric(row.get("success_indicator") for row in group)
        record: Dict[str, Any] = {
            "mission_label": mission,
            "algorithm_id": algorithm,
            "algorithm_name": group[0].get("algorithm_name", algorithm),
            "budget": budget,
            "runs": len(group),
            "seeds": "|".join(str(row.get("seed")) for row in sorted(group, key=lambda item: int(item.get("seed", 0)))),
            "success_rate": statistics.fmean(successes) if successes else None,
        }
        for metric in METRICS:
            for name, value in describe(numeric(row.get(metric) for row in group)).items():
                record[f"{metric}_{name}"] = value
        output.append(record)
    return output


def main() -> int:
    args = parse_args()
    summaries = load_summaries(args.results_dir)
    if not summaries:
        print(f"No finalized benchmark summaries found below: {args.results_dir}")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / "raw_runs.csv"
    aggregate_csv = args.output_dir / "aggregate.csv"
    aggregate_json = args.output_dir / "aggregate.json"
    _atomic_write_csv(summaries, raw_path)
    rows = aggregate(summaries)
    _atomic_write_csv(rows, aggregate_csv)
    _atomic_write_json(rows, aggregate_json)
    print(f"Finalized runs loaded: {len(summaries)}")
    print(f"Raw runs: {raw_path}")
    print(f"Aggregate CSV: {aggregate_csv}")
    print(f"Aggregate JSON: {aggregate_json}")

    if not args.no_plots:
        try:
            from plot_benchmarks import generate_benchmark_plots

            manifest = generate_benchmark_plots(
                raw_runs_path=raw_path,
                output_dir=args.output_dir / "plots",
            )
        except (ImportError, OSError, ValueError) as error:
            print(f"Benchmark plots were not generated: {error}")
        else:
            print(f"Paired comparison plots: {len(manifest)}")
            print(f"Plot directory: {args.output_dir / 'plots'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
