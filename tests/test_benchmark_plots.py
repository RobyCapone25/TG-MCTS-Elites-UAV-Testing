from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from plot_benchmarks import PRIMARY_METRICS, generate_benchmark_plots


class BenchmarkPlotTests(unittest.TestCase):
    def test_two_seed_pairs_generate_explicit_metric_plots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_path = root / "raw_runs.csv"
            output_dir = root / "plots"
            rows = []
            for seed in (1001, 1002):
                rows.extend(
                    [
                        {
                            "generated_at": f"2026-07-14T12:00:0{seed - 1000}+02:00",
                            "mission_label": "mission_1",
                            "algorithm_id": "operator_random_search",
                            "algorithm_name": "Operator-Matched Random Search",
                            "seed": seed,
                            "budget": 50,
                            "failure_yield_returnable": 0.04,
                            "diverse_failures_returned": 1,
                            "best_min_distance": 0.9,
                            "time_to_first_official_failure_attempt": 30,
                            "archive_coverage": 0.02,
                            "mean_failure_reproducibility_returnable": 0.6,
                        },
                        {
                            "generated_at": f"2026-07-14T12:01:0{seed - 1000}+02:00",
                            "mission_label": "mission_1",
                            "algorithm_id": "tg_mcts_elites",
                            "algorithm_name": "TG-MCTS-Elites",
                            "seed": seed,
                            "budget": 50,
                            "failure_yield_returnable": 0.10,
                            "diverse_failures_returned": 3,
                            "best_min_distance": 0.3,
                            "time_to_first_official_failure_attempt": 12,
                            "archive_coverage": 0.06,
                            "mean_failure_reproducibility_returnable": 0.9,
                        },
                    ]
                )

            with raw_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            manifest = generate_benchmark_plots(raw_path, output_dir)

            self.assertEqual(len(manifest), len(PRIMARY_METRICS))
            for item in manifest:
                plot = Path(item["plot_file"])
                self.assertTrue(plot.is_file(), plot)
                self.assertGreater(plot.stat().st_size, 0)
                self.assertEqual(item["paired_seed_count"], 2)

            self.assertTrue((output_dir / "plot_manifest.csv").is_file())
            self.assertTrue((output_dir / "paired_differences.csv").is_file())
            self.assertTrue((output_dir / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
