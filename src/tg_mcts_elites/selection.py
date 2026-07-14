from __future__ import annotations

import math
import os
from itertools import permutations
from typing import Any, List, Sequence, Tuple

from aerialist.px4.obstacle import Obstacle

from .models import EvalResult


class SelectionMixin:
    def _normalised_obstacle_vector(self, obstacle: Obstacle) -> Tuple[float, ...]:
        def normalise(value: float, low: float, high: float) -> float:
            if high <= low:
                return 0.0
            return (value - low) / (high - low)

        return (
            normalise(float(obstacle.position.x), self.X_MIN, self.X_MAX),
            normalise(float(obstacle.position.y), self.Y_MIN, self.Y_MAX),
            normalise(float(obstacle.size.l), self.MIN_L, self.MAX_L),
            normalise(float(obstacle.size.w), self.MIN_W, self.MAX_W),
            normalise(float(obstacle.size.h), self.MIN_H, self.MAX_H),
            normalise(float(obstacle.position.r), self.MIN_R, self.MAX_R),
        )

    def _vector_distance(self, first: Sequence[float], second: Sequence[float]) -> float:
        return math.sqrt(
            sum((a - b) ** 2 for a, b in zip(first, second)) / max(len(first), 1)
        )

    def _scenario_distance(self, first: EvalResult, second: EvalResult) -> float:
        """Permutation-invariant distance between two obstacle configurations."""
        if len(first.obstacles) != len(second.obstacles):
            return float("inf")
        if not first.obstacles:
            return 0.0

        first_vectors = [self._normalised_obstacle_vector(obs) for obs in first.obstacles]
        second_vectors = [self._normalised_obstacle_vector(obs) for obs in second.obstacles]

        best = float("inf")
        for assignment in permutations(second_vectors):
            squared = 0.0
            for left, right in zip(first_vectors, assignment):
                distance = self._vector_distance(left, right)
                squared += distance * distance
            best = min(best, math.sqrt(squared / len(first_vectors)))
        return best

    def _downsample_trajectory(
        self,
        points: Sequence[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        cleaned = [
            (float(x), float(y))
            for x, y in points
            if math.isfinite(float(x)) and math.isfinite(float(y))
        ]
        limit = max(2, int(self.MAX_DTW_TRAJECTORY_POINTS))
        if len(cleaned) <= limit:
            return cleaned

        output: List[Tuple[float, float]] = []
        for index in range(limit):
            source_index = round(index * (len(cleaned) - 1) / (limit - 1))
            output.append(cleaned[source_index])
        return output

    def _trajectory_distance(self, first: EvalResult, second: EvalResult) -> float:
        """Normalised Dynamic Time Warping distance between realised XY paths.

        ``inf`` means that at least one result has no extracted trajectory, in
        which case final-suite diversity falls back to obstacle geometry only.
        """
        left = self._downsample_trajectory(first.trajectory_xy)
        right = self._downsample_trajectory(second.trajectory_xy)
        if len(left) < 2 or len(right) < 2:
            return float("inf")

        scale = max(float(self.TRAJECTORY_DISTANCE_SCALE_M), 1e-9)
        previous = [float("inf")] * (len(right) + 1)
        previous[0] = 0.0

        for left_point in left:
            current = [float("inf")] * (len(right) + 1)
            for j, right_point in enumerate(right, start=1):
                local_cost = math.hypot(
                    left_point[0] - right_point[0],
                    left_point[1] - right_point[1],
                ) / scale
                current[j] = local_cost + min(
                    previous[j],      # insertion
                    current[j - 1],   # deletion
                    previous[j - 1],  # match
                )
            previous = current

        return previous[-1] / max(len(left), len(right), 1)

    def _scenarios_too_similar(self, first: EvalResult, second: EvalResult) -> bool:
        geometry_too_close = (
            self._scenario_distance(first, second)
            < self.FINAL_MIN_SCENARIO_DISTANCE
        )
        trajectory_distance = self._trajectory_distance(first, second)
        trajectory_too_close = (
            not math.isinf(trajectory_distance)
            and trajectory_distance < self.FINAL_MIN_TRAJECTORY_DTW
        )
        return geometry_too_close or trajectory_too_close

    def _has_complete_failure_artifacts(self, result: EvalResult) -> bool:
        return all(
            path and os.path.exists(path)
            for path in (
                result.yaml_file,
                result.log_file,
                result.scenario_plot,
                result.xy_time_plot,
            )
        )

    def _final_suite(self) -> List[Any]:
        unique_candidates: List[EvalResult] = []
        exact_signatures = set()

        for result in self.results:
            if result.signature in exact_signatures:
                continue
            exact_signatures.add(result.signature)

            if not self._is_returnable_failure(result):
                continue
            if not self._has_complete_failure_artifacts(result):
                continue
            unique_candidates.append(result)

        ranked = sorted(unique_candidates, key=self._final_rank_key, reverse=True)
        selected: List[EvalResult] = []

        for candidate in ranked:
            if len(selected) >= self.RETURN_LIMIT:
                break
            if any(self._scenarios_too_similar(candidate, previous) for previous in selected):
                continue
            selected.append(candidate)

        print("\n===== TG-MCTS-Elites Summary =====")
        print(f"Simulator attempts consumed: {self.simulation_attempts}")
        print(f"Successful evaluated simulations: {len(self.results)}")
        print(f"Official failures found: {sum(self._is_official_failure(r) for r in self.results)}")
        print(f"Confirmation observations: {sum(r.confirmation_attempts for r in self.results)}")
        print(f"Elite cells filled: {len(self.elites)}")
        print(f"Diverse failures returned: {len(selected)}")
        print(
            "Minimum normalised obstacle distance: "
            f"{self.FINAL_MIN_SCENARIO_DISTANCE:.3f}"
        )
        print(
            "Minimum normalised trajectory DTW: "
            f"{self.FINAL_MIN_TRAJECTORY_DTW:.3f}"
        )

        if selected:
            best = selected[0]
            print(
                f"Best returned test: min_distance={best.min_distance:.4f}, "
                f"initial_point={best.point}, mean_point={self._mean_official_point(best):.3f}, "
                f"failure_rate={self._failure_reproducibility(best):.3f}, "
                f"samples={len(self._result_point_samples(best))}, reward={best.reward:.4f}, "
                f"cell={best.cell}, obstacles={len(best.obstacles)}, "
                f"mission_status={best.mission_status}"
            )
        else:
            print("No compliant, completed, artifact-backed official failure was found.")

        print("\nReturned ranking:")
        for index, result in enumerate(selected, start=1):
            nearest_geometry = float("inf")
            nearest_trajectory = float("inf")
            if index > 1:
                nearest_geometry = min(
                    self._scenario_distance(result, previous)
                    for previous in selected[: index - 1]
                )
                trajectory_values = [
                    self._trajectory_distance(result, previous)
                    for previous in selected[: index - 1]
                ]
                finite_values = [value for value in trajectory_values if not math.isinf(value)]
                if finite_values:
                    nearest_trajectory = min(finite_values)

            geometry_text = (
                "n/a" if math.isinf(nearest_geometry) else f"{nearest_geometry:.4f}"
            )
            trajectory_text = (
                "n/a" if math.isinf(nearest_trajectory) else f"{nearest_trajectory:.4f}"
            )
            print(
                f"  rank {index}: min_distance={result.min_distance:.4f}, "
                f"problem_type={self._problem_label(result.min_distance)}, "
                f"initial_point={result.point}, mean_point={self._mean_official_point(result):.3f}, "
                f"failure_rate={self._failure_reproducibility(result):.3f}, "
                f"samples={len(self._result_point_samples(result))}, reward={result.reward:.4f}, "
                f"cell={result.cell}, obstacles={len(result.obstacles)}, "
                f"nearest_obstacle_distance={geometry_text}, "
                f"nearest_trajectory_dtw={trajectory_text}, "
                f"plot={result.scenario_plot}"
            )

        for result in selected:
            result.test.mean_official_point = self._mean_official_point(result)
            result.test.failure_reproducibility = self._failure_reproducibility(result)
            result.test.confirmation_samples = len(self._result_point_samples(result))
            result.test.mean_min_distance = self._mean_min_distance(result)
            result.test.simulation_attempt = result.simulation_attempt
            result.test.xy_time_plot_file = result.xy_time_plot

        self.selected_results = list(selected)
        return [result.test for result in selected]
