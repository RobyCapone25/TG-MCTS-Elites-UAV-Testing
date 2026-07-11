#!/usr/bin/python3
"""
CLI for TG-MCTS-Elites with harmonized final artifacts and a clean output layout.

Search logic is NOT changed. random_generator.py and testcase.py stay untouched.

Final layout:
generated_tests/<timestamp>/
├── test_0.yaml
├── test_0.ulg
├── rank01_d01.234_obs1.yaml
├── rank01_d01.234_obs1.ulg
├── manifest.csv
├── checkpoint.json
├── debug.txt
└── plots/
    ├── test_0_native.png
    ├── test_0_official.png
    ├── rank01_d01.234_obs1_plot.png
    ├── progress_final.png
    ├── tree_final.png
    └── scenario_sim_...png

All plots are collected in the same folder: <output>/plots/
"""
from __future__ import annotations

from argparse import ArgumentParser
import contextlib
import csv
from datetime import datetime
import io
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, TextIO

import yaml
from decouple import config

from plot_official import plot_one
from random_generator import RandomGenerator


TESTS_FOLDER = Path(config("TESTS_FOLDER", default="./generated_tests/"))
logger = logging.getLogger(__name__)


class Tee:
    def __init__(self, *streams: TextIO) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        return any(getattr(stream, "isatty", lambda: False)() for stream in self.streams)


def arg_parse():
    main_parser = ArgumentParser(description="UAV Test Generator")
    subparsers = main_parser.add_subparsers(dest="command", required=True)
    parser = subparsers.add_parser(name="generate", description="generate tests")
    parser.add_argument("test", help="initial test description file address")
    parser.add_argument(
        "budget",
        type=int,
        help="test generation budget (total number of simulations allowed)",
    )
    return main_parser.parse_args()


def config_loggers() -> None:
    os.makedirs("logs/", exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    debug_handler = logging.FileHandler("logs/debug.txt", mode="a", encoding="utf-8")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root.addHandler(debug_handler)

    terminal_handler = logging.StreamHandler()
    terminal_handler.setLevel(logging.INFO)
    terminal_handler.setFormatter(
        logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    )
    root.addHandler(terminal_handler)

    info_handler = logging.FileHandler("logs/info.txt", mode="a", encoding="utf-8")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root.addHandler(info_handler)


def _new_output_folder() -> Path:
    TESTS_FOLDER.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
    folder = TESTS_FOLDER / stamp
    folder.mkdir(parents=False, exist_ok=False)
    (folder / "plots").mkdir(parents=False, exist_ok=False)
    return folder.resolve()


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _obstacle_count(yaml_path: Path) -> int:
    try:
        with yaml_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        obstacles = (data.get("simulation") or {}).get("obstacles") or []
        return len(obstacles)
    except Exception as exc:
        logger.warning("Could not count obstacles in %s: %s", yaml_path, exc)
        return 0


def _copy_existing(source: Any, destination: Path) -> bool:
    if not source:
        return False
    source_path = Path(str(source))
    if not source_path.is_file():
        logger.warning("Artifact not found and not copied: %s", source_path)
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    return True


def _rank_base(rank: int, minimum_distance: Optional[float], obstacle_count: int) -> str:
    distance = "unknown" if minimum_distance is None else f"{minimum_distance:06.3f}"
    return f"rank{rank:02d}_d{distance}_obs{obstacle_count}"


def _generate_official_plot(
    ulg_path: Path,
    yaml_path: Path,
    output_path: Path,
    title: str,
) -> str:
    if not ulg_path.is_file():
        return "missing_ulg"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            plot_one(str(ulg_path), str(yaml_path), str(output_path), title=title)
        return "official"
    except Exception as exc:
        logger.warning("Official plot failed for %s: %s", yaml_path.name, exc)
        return f"failed:{type(exc).__name__}"


def _copy_global_algorithm_plots(generator: Any, plots_dir: Path) -> Dict[str, str]:
    """
    Copy the main TG-MCTS-Elites plots into the common plots folder.
    We keep the original results/... files untouched and only create clean copies.
    """
    copied = {}

    for attr_name, out_name in (
        ("progress_plot_path", "progress_final.png"),
        ("tree_plot_path", "tree_final.png"),
    ):
        src = getattr(generator, attr_name, None)
        if src and Path(src).is_file():
            dst = plots_dir / out_name
            shutil.copy2(src, dst)
            copied[attr_name] = dst.name

    return copied


def _copy_selected_scenario_plots(generator: Any, records: List[Dict[str, Any]], plots_dir: Path) -> List[str]:
    """
    Copy only the scenario plots corresponding to the returned ranking, if available.
    This avoids flooding the final folder with every internal scenario image while
    still collecting the relevant native plots in one place.
    """
    copied = []
    ranking = getattr(generator, "last_final_selection", None) or []
    if not ranking:
        return copied

    for idx, item in enumerate(ranking):
        src = item.get("plot")
        if not src:
            continue
        src_path = Path(str(src))
        if not src_path.is_file():
            continue
        dst = plots_dir / f"rank{idx+1:02d}_scenario_native.png"
        shutil.copy2(src_path, dst)
        copied.append(dst.name)
        if idx < len(records):
            records[idx]["scenario_native_plot"] = dst.name
    return copied


def _export_one(test_case: Any, index: int, output_folder: Path) -> Dict[str, Any]:
    rank = index + 1
    plots_dir = output_folder / "plots"
    test_stem = f"test_{index}"

    yaml_path = output_folder / f"{test_stem}.yaml"
    ulg_path = output_folder / f"{test_stem}.ulg"

    native_plot_path = plots_dir / f"{test_stem}_native.png"
    official_plot_path = plots_dir / f"{test_stem}_official.png"

    test_case.save_yaml(str(yaml_path))
    log_copied = _copy_existing(getattr(test_case, "log_file", None), ulg_path)
    native_plot_copied = _copy_existing(getattr(test_case, "plot_file", None), native_plot_path)

    plot_status = _generate_official_plot(
        ulg_path=ulg_path,
        yaml_path=yaml_path,
        output_path=official_plot_path,
        title=test_stem,
    )

    obstacle_count = _obstacle_count(yaml_path)
    minimum_distance = _safe_float(getattr(test_case, "minimum_distance", None))
    rank_base = _rank_base(rank, minimum_distance, obstacle_count)

    rank_yaml = output_folder / f"{rank_base}.yaml"
    rank_ulg = output_folder / f"{rank_base}.ulg"
    rank_plot = plots_dir / f"{rank_base}_plot.png"

    shutil.copy2(yaml_path, rank_yaml)
    if log_copied:
        shutil.copy2(ulg_path, rank_ulg)

    if official_plot_path.is_file():
        shutil.copy2(official_plot_path, rank_plot)
    elif native_plot_copied:
        shutil.copy2(native_plot_path, rank_plot)
        plot_status = plot_status + "+native_fallback"

    return {
        "rank": rank,
        "minimum_distance": minimum_distance,
        "obstacle_count": obstacle_count,
        "plot_status": plot_status,
        "original_yaml": yaml_path.name,
        "original_ulg": ulg_path.name if ulg_path.is_file() else "",
        "native_plot": str(native_plot_path.relative_to(output_folder)) if native_plot_path.is_file() else "",
        "official_plot": str(official_plot_path.relative_to(output_folder)) if official_plot_path.is_file() else "",
        "rank_yaml": rank_yaml.name,
        "rank_ulg": rank_ulg.name if rank_ulg.is_file() else "",
        "rank_plot": str(rank_plot.relative_to(output_folder)) if rank_plot.is_file() else "",
        "scenario_native_plot": "",
    }


def _write_manifest(output_folder: Path, records: List[Dict[str, Any]]) -> None:
    fields = [
        "rank",
        "minimum_distance",
        "obstacle_count",
        "plot_status",
        "original_yaml",
        "original_ulg",
        "native_plot",
        "official_plot",
        "scenario_native_plot",
        "rank_yaml",
        "rank_ulg",
        "rank_plot",
    ]
    with (output_folder / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def _write_export_checkpoint(
    output_folder: Path,
    args: Any,
    generator: Any,
    records: List[Dict[str, Any]],
    status: str,
    error: str = "",
) -> None:
    payload = {
        "kind": "harmonized-output-index",
        "schema_version": 2,
        "native_search_untouched": True,
        "status": status,
        "algorithm": "tg_mcts_elites",
        "case_study_file": str(Path(args.test).resolve()),
        "budget": int(args.budget),
        "algorithm_run_id": getattr(generator, "run_id", None),
        "algorithm_output_dir": getattr(generator, "output_dir", None),
        "generated_test_count": len(records),
        "plots_folder": "plots",
        "created_at": datetime.now().isoformat(),
        "error": error,
        "tests": records,
    }
    with (output_folder / "checkpoint.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def main() -> int:
    args = arg_parse()
    mission_path = Path(args.test)
    if not mission_path.is_file():
        print(f"ERROR: mission file not found: {mission_path.resolve()}", file=sys.stderr)
        return 2
    if args.budget <= 0:
        print("ERROR: budget must be strictly positive.", file=sys.stderr)
        return 2

    output_folder = _new_output_folder()
    plots_dir = output_folder / "plots"
    transcript_path = output_folder / "debug.txt"

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    generator = None
    records: List[Dict[str, Any]] = []

    with transcript_path.open("a", encoding="utf-8", buffering=1) as transcript:
        sys.stdout = Tee(original_stdout, transcript)
        sys.stderr = Tee(original_stderr, transcript)

        try:
            config_loggers()
            generator = RandomGenerator(case_study_file=args.test)
            test_cases = generator.generate(args.budget)

            for index, test_case in enumerate(test_cases):
                records.append(_export_one(test_case, index, output_folder))

            global_plot_info = _copy_global_algorithm_plots(generator, plots_dir)
            selected_scenarios = _copy_selected_scenario_plots(generator, records, plots_dir)

            _write_manifest(output_folder, records)
            _write_export_checkpoint(
                output_folder=output_folder,
                args=args,
                generator=generator,
                records=records,
                status="completed",
            )

            print(f"{len(test_cases)} test cases generated")
            print(f"output folder: {output_folder}/")
            return 0

        except Exception as exc:
            logger.exception("program terminated: %s", exc, exc_info=True)
            _write_manifest(output_folder, records)
            _write_export_checkpoint(
                output_folder=output_folder,
                args=args,
                generator=generator,
                records=records,
                status="failed",
                error=str(exc),
            )
            return 1

        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

            root = logging.getLogger()
            for handler in root.handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    try:
                        handler.setStream(original_stderr)
                    except Exception:
                        handler.stream = original_stderr


if __name__ == "__main__":
    raise SystemExit(main())
