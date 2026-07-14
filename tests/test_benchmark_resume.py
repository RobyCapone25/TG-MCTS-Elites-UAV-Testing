from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from aggregate_benchmarks import load_summaries
from benchmark_status import determine_status


class BenchmarkResumeTests(unittest.TestCase):
    def _args(self, root: Path, prepare: bool = False) -> Namespace:
        return Namespace(
            results_dir=root / "results",
            namespace="tg_mcts_elites",
            algorithm_id="tg_mcts_elites",
            case_study=Path("case_studies/mission1.yaml"),
            seed=1001,
            budget=50,
            prepare=prepare,
        )

    def _write_state(self, root: Path, status: str) -> Path:
        run_dir = root / "results" / "tg_mcts_elites" / "mission_1_run"
        run_dir.mkdir(parents=True)
        state = {
            "status": status,
            "algorithm_id": "tg_mcts_elites",
            "case_study_basename": "mission1.yaml",
            "seed": 1001,
            "budget": 50,
            "simulation_attempts": 50,
        }
        (run_dir / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
        return run_dir

    def test_completed_requires_a_valid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self._write_state(root, "completed")
            status, _ = determine_status(self._args(root))
            self.assertEqual(status, "resume")

            benchmark_dir = run_dir / "benchmark"
            benchmark_dir.mkdir()
            summary = {
                "run_status": "completed",
                "algorithm_id": "tg_mcts_elites",
                "case_study_basename": "mission1.yaml",
                "mission_label": "mission_1",
                "seed": 1001,
                "budget": 50,
                "simulator_attempts": 50,
                "generated_at": "2026-07-14T12:00:00+02:00",
            }
            (benchmark_dir / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            status, _ = determine_status(self._args(root))
            self.assertEqual(status, "completed")

    def test_prepare_reopens_incompletely_finalized_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self._write_state(root, "completed")
            status, _ = determine_status(self._args(root, prepare=True))
            self.assertEqual(status, "resume")
            state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "running")
            self.assertIn("recovery_note", state)

    def test_aggregator_ignores_incomplete_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = self._write_state(root, "completed")
            benchmark_dir = completed / "benchmark"
            benchmark_dir.mkdir()
            summary = {
                "run_status": "completed",
                "algorithm_id": "tg_mcts_elites",
                "case_study_basename": "mission1.yaml",
                "mission_label": "mission_1",
                "seed": 1001,
                "budget": 50,
                "simulator_attempts": 50,
                "generated_at": "2026-07-14T12:00:00+02:00",
            }
            (benchmark_dir / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            incomplete = root / "results" / "random_search" / "mission_1_run"
            (incomplete / "benchmark").mkdir(parents=True)
            (incomplete / "run_state.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "algorithm_id": "operator_random_search",
                        "case_study_basename": "mission1.yaml",
                        "seed": 1001,
                        "budget": 50,
                    }
                ),
                encoding="utf-8",
            )
            (incomplete / "benchmark" / "summary.json").write_text(
                json.dumps(
                    {
                        "run_status": "stopped_before_budget",
                        "algorithm_id": "operator_random_search",
                        "case_study_basename": "mission1.yaml",
                        "mission_label": "mission_1",
                        "seed": 1001,
                        "budget": 50,
                        "simulator_attempts": 12,
                    }
                ),
                encoding="utf-8",
            )

            rows = load_summaries(root / "results")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["algorithm_id"], "tg_mcts_elites")


if __name__ == "__main__":
    unittest.main()
