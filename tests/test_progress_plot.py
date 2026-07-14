from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tg_mcts_elites.generator import RandomGenerator


class ProgressPlotTests(unittest.TestCase):
    def test_progress_plots_are_created_from_all_successful_evaluations(self) -> None:
        generator = object.__new__(RandomGenerator)

        with tempfile.TemporaryDirectory() as directory:
            generator.output_dir = directory
            generator.history = [
                {"simulation_attempt": 1, "min_distance": 4.2, "reward": 8.0, "point": 0},
                {"simulation_attempt": 3, "min_distance": 1.4, "reward": 34.0, "point": 1},
                {"simulation_attempt": 4, "min_distance": 2.1, "reward": 20.0, "point": 0},
                {"simulation_attempt": 7, "min_distance": 0.8, "reward": 58.0, "point": 2},
            ]
            generator.CRITICAL_PROXIMITY_THRESHOLD = 0.25
            generator.FAILURE_THRESHOLD = 1.5
            generator.NEAR_MISS_THRESHOLD = 3.0

            generator._save_progress_plots()

            for filename in (
                "progress_min_distance.png",
                "progress_reward.png",
                "progress_reward_vs_distance.png",
            ):
                path = Path(directory) / filename
                self.assertTrue(path.is_file(), filename)
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
