from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tg_mcts_elites.generator import RandomGenerator
from tg_mcts_elites.models import MCTSNode


class OutputLayoutTests(unittest.TestCase):
    def test_save_all_outputs_creates_tree_and_named_progress(self) -> None:
        generator = object.__new__(RandomGenerator)

        with tempfile.TemporaryDirectory() as directory:
            generator.output_dir = directory
            generator.history = [
                {"simulation_attempt": 1, "node_id": 1, "min_distance": 3.4, "reward": 5.0, "point": 0},
                {"simulation_attempt": 2, "node_id": 2, "min_distance": 1.1, "reward": 40.0, "point": 1},
            ]
            generator.CRITICAL_PROXIMITY_THRESHOLD = 0.25
            generator.FAILURE_THRESHOLD = 1.5
            generator.NEAR_MISS_THRESHOLD = 3.0
            generator.history_jsonl_path = str(Path(directory) / "history.jsonl")
            root = MCTSNode(obstacles=[], node_id=0)
            child = MCTSNode(obstacles=[], parent=root, action="init", node_id=1)
            root.children.append(child)

            generator._save_all_outputs(root)

            for filename in (
                "history.csv",
                "mcts_tree.png",
                "tree_final.png",
                "progress_min_distance.png",
                "progress_reward.png",
                "progress_reward_vs_distance.png",
            ):
                path = Path(directory) / filename
                self.assertTrue(path.is_file(), filename)
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
