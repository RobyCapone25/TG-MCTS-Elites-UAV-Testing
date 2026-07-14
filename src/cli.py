#!/usr/bin/env python3
from __future__ import annotations

import csv
import logging
import shutil
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from pathlib import Path

from decouple import config

from tg_mcts_elites import RandomSearchGenerator, TGMCTSElitesGenerator

TESTS_FOLDER = Path(config("TESTS_FOLDER", default="./generated_tests/")).expanduser()
logger = logging.getLogger(__name__)

ALGORITHMS = {
    "tg-mcts-elites": TGMCTSElitesGenerator,
    "random-search": RandomSearchGenerator,
}


def positive_budget(value: str) -> int:
    budget = int(value)
    if budget <= 0:
        raise ArgumentTypeError("budget must be a positive integer")
    return budget


def arg_parse() -> Namespace:
    parser = ArgumentParser(description="TG-MCTS-Elites UAV Test Generator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", help="generate UAV tests")
    generate_parser.add_argument("test", type=Path, help="case-study YAML path")
    generate_parser.add_argument(
        "budget",
        type=positive_budget,
        help="maximum number of real simulator executions, including retries",
    )
    generate_parser.add_argument(
        "--algorithm",
        choices=sorted(ALGORITHMS),
        default="tg-mcts-elites",
        help="search algorithm; the default preserves the historical command",
    )
    return parser.parse_args()


def config_loggers() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    debug_handler = logging.FileHandler(logs_dir / "debug.txt")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    info_handler = logging.FileHandler(logs_dir / "info.txt")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

    root.addHandler(debug_handler)
    root.addHandler(info_handler)
    root.addHandler(console_handler)


def create_ranking_directory(run_name: str, algorithm_id: str) -> Path:
    TESTS_FOLDER.mkdir(parents=True, exist_ok=True)
    # Preserve the historical TG-MCTS-Elites output path. Keep the baseline in
    # a separate namespace so paired runs cannot be confused.
    if algorithm_id == "tg_mcts_elites":
        ranking_dir = TESTS_FOLDER / run_name
    else:
        ranking_dir = TESTS_FOLDER / algorithm_id / run_name
    ranking_dir.mkdir(parents=True, exist_ok=True)
    return ranking_dir.resolve()


def export_ranking(test_cases: list, ranking_dir: Path) -> None:
    rows = []
    for zero_index, test_case in enumerate(test_cases):
        rank = zero_index + 1
        stem = f"test_{zero_index}"
        yaml_path = ranking_dir / f"{stem}.yaml"
        log_path = ranking_dir / f"{stem}.ulg"
        overview_path = ranking_dir / f"{stem}_overview.png"
        xy_time_path = ranking_dir / f"{stem}_xy_time.png"

        source_log = Path(test_case.log_file)
        source_plot = Path(test_case.plot_file)
        if not source_log.is_file() or not source_plot.is_file():
            raise FileNotFoundError(f"Rank {rank} is missing its persisted ULG or overview plot artifact.")

        test_case.save_yaml(yaml_path)
        shutil.copy2(source_log, log_path)
        shutil.copy2(source_plot, overview_path)

        xy_time_source = Path(getattr(test_case, "xy_time_plot_file", ""))
        xy_time_name = ""
        if xy_time_source.is_file():
            shutil.copy2(xy_time_source, xy_time_path)
            xy_time_name = xy_time_path.name

        rows.append(
            {
                "algorithm_id": getattr(test_case, "algorithm_id", ""),
                "algorithm_name": getattr(test_case, "algorithm_name", ""),
                "rank": rank,
                "minimum_distance": getattr(test_case, "minimum_distance", ""),
                "official_point": getattr(test_case, "official_point", ""),
                "mean_official_point": getattr(test_case, "mean_official_point", ""),
                "failure_reproducibility": getattr(test_case, "failure_reproducibility", ""),
                "evaluation_samples": getattr(test_case, "confirmation_samples", 1),
                "mean_minimum_distance": getattr(test_case, "mean_min_distance", ""),
                "reward": getattr(test_case, "reward", ""),
                "problem_type": getattr(test_case, "problem_type", ""),
                "mission_status": getattr(test_case, "mission_status", ""),
                "failure_evidence": getattr(test_case, "failure_evidence", ""),
                "yaml_file": yaml_path.name,
                "log_file": log_path.name,
                "overview_plot_file": overview_path.name,
                "xy_time_plot_file": xy_time_name,
            }
        )

    with open(ranking_dir / "ranking.csv", "w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "algorithm_id",
            "algorithm_name",
            "rank",
            "minimum_distance",
            "official_point",
            "mean_official_point",
            "failure_reproducibility",
            "evaluation_samples",
            "mean_minimum_distance",
            "reward",
            "problem_type",
            "mission_status",
            "failure_evidence",
            "yaml_file",
            "log_file",
            "overview_plot_file",
            "xy_time_plot_file",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    config_loggers()
    args = arg_parse()
    if not args.test.is_file():
        logger.error("Case-study file not found: %s", args.test)
        return 1

    generator_class = ALGORITHMS[args.algorithm]
    generator = generator_class(case_study_file=str(args.test))

    try:
        test_cases = generator.generate(args.budget)
        for test_case in test_cases:
            test_case.algorithm_id = generator.ALGORITHM_ID
            test_case.algorithm_name = generator.ALGORITHM_NAME
        ranking_dir = create_ranking_directory(generator.run_id, generator.ALGORITHM_ID)
        export_ranking(test_cases, ranking_dir)
        if hasattr(generator, "_export_best_ranked_summary"):
            generator._export_best_ranked_summary(test_cases)

        print(f"algorithm: {generator.ALGORITHM_NAME}")
        print(f"{len(test_cases)} diverse official failure test cases generated")
        print(f"output folder: {ranking_dir}")
        print(f"complete run data: {Path(generator.output_dir).resolve()}")
        print(f"all failed cases: {Path(generator.failure_cases_dir).resolve()}")
        print(f"best ranked failed tests: {Path(generator.best_ranked_dir).resolve()}")
        return 0
    except Exception as error:
        logger.exception("program terminated: %s", error)
        if getattr(generator, "output_dir", ""):
            print(f"complete run data: {Path(generator.output_dir).resolve()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
