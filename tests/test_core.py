from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aerialist.px4.obstacle import Obstacle

from tg_mcts_elites.generator import TGMCTSElitesGenerator
from tg_mcts_elites.models import EvalResult


class DummyTest:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.yaml_file = str(root / "test.yaml")
        self.log_file = str(root / "flight.ulg")
        self.plot_file = str(root / "trajectory_overview.png")
        self.xy_time_plot_file = str(root / "trajectory_xy_time.png")
        for artifact in (
            self.yaml_file,
            self.log_file,
            self.plot_file,
            self.xy_time_plot_file,
        ):
            Path(artifact).write_bytes(b"test")

    def save_yaml(self, path: str) -> None:
        Path(path).write_bytes(Path(self.yaml_file).read_bytes())


def obstacle(x: float, y: float, rotation: float = 0.0) -> Obstacle:
    return Obstacle(
        Obstacle.Size(l=5.0, w=5.0, h=15.0),
        Obstacle.Position(x=x, y=y, z=0.0, r=rotation),
    )


class CorePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = object.__new__(TGMCTSElitesGenerator)
        self.generator.simulation_attempts = 10
        self.generator.elites = {}

    def result(
        self,
        root: Path,
        x: float,
        y: float,
        distance: float,
        point: int,
        signature: tuple,
        mission_status: str = "completed",
        trajectory_xy: list[tuple[float, float]] | None = None,
    ) -> EvalResult:
        test = DummyTest(root)
        return EvalResult(
            obstacles=[obstacle(x, y)],
            test=test,
            min_distance=distance,
            elapsed_minutes=1.0,
            point=point,
            reward=100.0 - distance,
            cell=(1, 0, 0, 0, 0),
            signature=signature,
            scenario_plot=test.plot_file,
            xy_time_plot=test.xy_time_plot_file,
            yaml_file=test.yaml_file,
            log_file=test.log_file,
            mission_status=mission_status,
            compliance_status="compliant",
            artifacts_saved=True,
            simulation_attempt=1,
            trajectory_xy=list(trajectory_xy or []),
            point_samples=[point],
            distance_samples=[distance],
            elapsed_samples=[1.0],
            failure_evidence=self.generator._failure_evidence(distance, mission_status),
        )

    def test_official_point_boundaries(self) -> None:
        self.assertEqual(self.generator._official_point(0.10), 5)
        self.assertEqual(self.generator._official_point(0.50), 2)
        self.assertEqual(self.generator._official_point(1.20), 1)
        self.assertEqual(self.generator._official_point(1.50), 0)

    def test_noncompleted_official_failure_is_returnable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.result(
                Path(directory) / "noncompleted",
                0.0,
                20.0,
                0.10,
                5,
                ((0,),),
                mission_status="not_completed",
            )
            self.assertEqual(
                result.failure_evidence,
                "noncompleted_critical_proximity",
            )
            self.assertTrue(self.generator._is_returnable_failure(result))

    def test_noncompleted_without_official_proximity_is_not_returnable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.result(
                Path(directory) / "noncompleted_safe",
                0.0,
                20.0,
                2.5,
                0,
                ((0,),),
                mission_status="not_completed",
            )
            self.assertEqual(
                result.failure_evidence,
                "noncompleted_without_official_proximity",
            )
            self.assertFalse(self.generator._is_returnable_failure(result))

    def test_near_duplicate_scenarios_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.result(root / "a", 0.0, 20.0, 0.2, 5, ((0,),))
            second = self.result(root / "b", 0.1, 20.1, 0.3, 2, ((1,),))
            distant = self.result(root / "c", 20.0, 35.0, 0.4, 2, ((2,),))
            self.assertTrue(self.generator._scenarios_too_similar(first, second))
            self.assertFalse(self.generator._scenarios_too_similar(first, distant))

    def test_identical_trajectories_are_rejected_even_with_different_obstacles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = [(0.0, float(y)) for y in range(0, 51, 5)]
            first = self.result(
                root / "a", -20.0, 15.0, 0.2, 5, ((0,),), trajectory_xy=path
            )
            second = self.result(
                root / "b", 20.0, 35.0, 0.3, 2, ((1,),), trajectory_xy=path
            )
            self.assertGreater(
                self.generator._scenario_distance(first, second),
                self.generator.FINAL_MIN_SCENARIO_DISTANCE,
            )
            self.assertLess(
                self.generator._trajectory_distance(first, second),
                self.generator.FINAL_MIN_TRAJECTORY_DTW,
            )
            self.assertTrue(self.generator._scenarios_too_similar(first, second))

    def test_confirmation_statistics_affect_final_rank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unstable = self.result(root / "unstable", -20.0, 15.0, 0.2, 5, ((0,),))
            unstable.point_samples.extend([0, 0, 0, 0])
            unstable.distance_samples.extend([3.0, 3.0, 3.0, 3.0])
            stable = self.result(root / "stable", 20.0, 35.0, 0.8, 2, ((1,),))
            stable.point_samples.extend([2, 2, 2, 2])
            stable.distance_samples.extend([0.8, 0.8, 0.8, 0.8])
            self.assertGreater(
                self.generator._final_rank_key(stable),
                self.generator._final_rank_key(unstable),
            )
            self.assertLess(
                self.generator._failure_reproducibility(unstable),
                self.generator.MIN_FAILURE_REPRODUCIBILITY,
            )

    def test_final_suite_contains_only_diverse_returnable_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failure = self.result(root / "failure", 0.0, 20.0, 0.2, 5, ((0,),))
            duplicate = self.result(root / "duplicate", 0.1, 20.1, 0.3, 2, ((1,),))
            safe = self.result(root / "safe", 20.0, 35.0, 4.0, 0, ((2,),))
            incomplete = self.result(
                root / "incomplete",
                25.0,
                35.0,
                0.4,
                2,
                ((3,),),
                mission_status="unknown",
            )
            self.generator.results = [failure, duplicate, safe, incomplete]
            selected = self.generator._final_suite()
            self.assertEqual(selected, [failure.test])

    def test_qgroundcontrol_plan_is_converted_to_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_dir = root / "case_studies"
            case_dir.mkdir()
            latitude = 45.0
            longitude = 9.0
            north_50m = latitude + math.degrees(50.0 / self.generator.EARTH_RADIUS_M)

            plan_path = case_dir / "unseen_mission.plan"
            plan_path.write_text(
                json.dumps(
                    {
                        "fileType": "Plan",
                        "plannedHomePosition": [latitude, longitude, 0.0],
                        "mission": {
                            "items": [
                                {
                                    "type": "SimpleItem",
                                    "command": 16,
                                    "params": [0, 0, 0, None, north_50m, longitude, 10],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            yaml_path = case_dir / "unseen_case.yaml"
            yaml_path.write_text(
                "robot:\n  mission_file: case_studies/unseen_mission.plan\n"
                "simulation:\n  simulator: ros\n",
                encoding="utf-8",
            )

            generator = object.__new__(TGMCTSElitesGenerator)
            generator.case_study_file = str(yaml_path)
            generator._mission_reference_cache = None
            generator._reference_pose_cache = None

            old_cwd = Path.cwd()
            try:
                # Exercise repository-root-relative mission paths.
                import os

                os.chdir(root)
                path = generator._mission_reference_path()
            finally:
                os.chdir(old_cwd)

            self.assertEqual(path[0], (0.0, 0.0))
            self.assertAlmostEqual(path[-1][0], 0.0, delta=0.2)
            self.assertAlmostEqual(path[-1][1], 50.0, delta=0.5)
            poses = generator._reference_pose_samples()
            self.assertTrue(any(10.0 <= y <= 40.0 for _, y, _ in poses))


    def test_southward_geographic_path_is_mapped_into_simulator_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_dir = root / "case_studies"
            case_dir.mkdir()
            latitude = 45.0
            longitude = 9.0
            south_50m = latitude - math.degrees(50.0 / self.generator.EARTH_RADIUS_M)

            plan_path = case_dir / "southward.plan"
            plan_path.write_text(
                json.dumps(
                    {
                        "fileType": "Plan",
                        "plannedHomePosition": [latitude, longitude, 0.0],
                        "mission": {
                            "items": [
                                {
                                    "type": "SimpleItem",
                                    "command": 16,
                                    "params": [0, 0, 0, None, south_50m, longitude, 10],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            yaml_path = case_dir / "southward.yaml"
            yaml_path.write_text(
                "robot:\n  mission_file: case_studies/southward.plan\n"
                "simulation:\n  simulator: ros\n",
                encoding="utf-8",
            )

            generator = object.__new__(TGMCTSElitesGenerator)
            generator.case_study_file = str(yaml_path)
            generator._mission_reference_cache = None
            generator._reference_pose_cache = None

            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                path_points = generator._mission_reference_path()
                poses = generator._reference_pose_samples()
            finally:
                os.chdir(old_cwd)

            self.assertAlmostEqual(path_points[-1][0], 0.0, delta=0.2)
            self.assertAlmostEqual(path_points[-1][1], 50.0, delta=0.5)
            self.assertEqual(generator.mission_frame_transform, "east_south")
            self.assertTrue(any(10.0 <= y <= 40.0 for _, y, _ in poses))


if __name__ == "__main__":
    unittest.main()
