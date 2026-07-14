from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from aerialist.px4.obstacle import Obstacle

from tg_mcts_elites.benchmark import BenchmarkRecorder
from tg_mcts_elites.generator import TGMCTSElitesGenerator
from tg_mcts_elites.models import EvalResult, MCTSNode
from tg_mcts_elites.random_search import RandomSearchGenerator


def obstacle() -> Obstacle:
    return Obstacle(
        Obstacle.Size(l=5.0, w=5.0, h=15.0),
        Obstacle.Position(x=0.0, y=20.0, z=0.0, r=0.0),
    )


class BenchmarkTests(unittest.TestCase):
    def test_random_search_is_a_distinct_generator(self) -> None:
        self.assertIsNot(RandomSearchGenerator, TGMCTSElitesGenerator)
        self.assertEqual(RandomSearchGenerator.RESULTS_NAMESPACE, "random_search")
        self.assertNotIn("_backup", RandomSearchGenerator._process_evaluated_node.__code__.co_names)

    def test_recorder_writes_events_and_current_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = BenchmarkRecorder(
                output_dir=directory,
                algorithm_id="operator_random_search",
                algorithm_name="Operator-Matched Random Search",
                case_study_file="case_studies/mission1.yaml",
                mission_label="mission_1",
                seed=123,
                budget=10,
            )
            result = EvalResult(
                obstacles=[obstacle()],
                test=object(),
                min_distance=0.2,
                elapsed_minutes=1.0,
                point=5,
                reward=100.0,
                cell=(1, 0, 0, 0, 0),
                signature=((0.0,),),
                mission_status="not_completed",
                compliance_status="compliant",
                artifacts_saved=True,
                simulation_attempt=3,
                trajectory_xy=[(0.0, 0.0), (0.0, 50.0)],
                point_samples=[5, 5, 0],
                distance_samples=[0.2, 0.2, 3.0],
                elapsed_samples=[1.0, 1.0, 1.0],
                failure_evidence="noncompleted_critical_proximity",
            )
            recorder.record_candidate(
                node_id=1,
                parent_id=0,
                action="init_single",
                obstacles=result.obstacles,
                proposal_status="accepted",
            )
            recorder.record_simulator_attempt(
                simulation_attempt=3,
                candidate_retry=1,
                node_id=1,
                parent_id=0,
                action="init_single",
                attempt_status="evaluated",
                simulation_seconds=2.0,
                phase="search",
                result=result,
            )
            summary = recorder.finalize(
                results=[result],
                elites={result.cell: result},
                selected_results=[result],
                simulator_attempts=10,
                run_status="completed",
                nominal_archive_cells=700,
                is_official_failure=lambda item: item.point > 0,
                is_returnable_failure=lambda item: True,
                mean_official_point=lambda item: sum(item.point_samples) / len(item.point_samples),
                failure_reproducibility=lambda item: sum(p > 0 for p in item.point_samples) / len(item.point_samples),
                scenario_distance=lambda left, right: 0.5,
                trajectory_distance=lambda left, right: 0.5,
            )
            self.assertEqual(summary["official_failures"], 1)
            self.assertEqual(summary["returnable_reproducible_failures"], 1)
            self.assertEqual(summary["time_to_first_official_failure_attempt"], 3)
            self.assertAlmostEqual(summary["archive_coverage"], 1 / 700)
            self.assertEqual(summary["search_attempts"], 10)
            self.assertEqual(summary["recorded_simulator_attempt_events"], 1)
            self.assertEqual(summary["unrecorded_or_interrupted_attempts"], 9)
            self.assertTrue((Path(directory) / "benchmark" / "summary.csv").is_file())
            events = [
                json.loads(line)
                for line in (Path(directory) / "benchmark" / "events.jsonl").read_text().splitlines()
            ]
            self.assertTrue(any(event["event_type"] == "candidate_proposed" for event in events))
            self.assertTrue(any(event["event_type"] == "simulator_attempt" for event in events))

    def test_tree_checkpoint_round_trip_preserves_search_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            generator = object.__new__(TGMCTSElitesGenerator)
            generator.case_study_file = "case_studies/mission1.yaml"
            generator.seed = 123
            generator.tree_state_path = str(root_path / "tree_state.json")
            generator.tree_signatures = set()
            generator._node_counter = 2

            result = EvalResult(
                obstacles=[obstacle()],
                test=object(),
                min_distance=0.4,
                elapsed_minutes=1.0,
                point=2,
                reward=60.0,
                cell=(1, 0, 0, 0, 0),
                signature=((0.0,),),
                simulation_attempt=1,
            )
            generator.results = [result]
            root = MCTSNode(
                obstacles=[],
                action="root",
                node_id=0,
                visits=1,
                total_reward=60.0,
                best_reward=60.0,
            )
            child = MCTSNode(
                obstacles=[obstacle()],
                parent=root,
                action="init_single",
                node_id=1,
                visits=1,
                total_reward=60.0,
                best_reward=60.0,
                eval_result=result,
            )
            root.children.append(child)
            random.seed(777)
            generator._save_tree_checkpoint(root)
            expected_next_random = random.random()
            random.seed(1)

            restored = object.__new__(TGMCTSElitesGenerator)
            restored.case_study_file = generator.case_study_file
            restored.seed = generator.seed
            restored.tree_state_path = generator.tree_state_path
            restored.tree_signatures = set()
            restored._node_counter = 0
            restored.results = [result]

            restored_root = restored._load_tree_checkpoint()
            self.assertIsNotNone(restored_root)
            assert restored_root is not None
            self.assertEqual(restored_root.visits, 1)
            self.assertEqual(len(restored_root.children), 1)
            restored_child = restored_root.children[0]
            self.assertEqual(restored_child.node_id, 1)
            self.assertEqual(restored_child.action, "init_single")
            self.assertIs(restored_child.eval_result, result)
            self.assertEqual(restored_child.total_reward, 60.0)
            self.assertEqual(random.random(), expected_next_random)



if __name__ == "__main__":
    unittest.main()
