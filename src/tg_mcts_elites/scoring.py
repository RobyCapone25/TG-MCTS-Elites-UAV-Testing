from __future__ import annotations

import math
from typing import Tuple

from .models import EvalResult


class ScoringMixin:
    def _official_point(self, min_distance: float) -> int:
        if min_distance < self.CRITICAL_PROXIMITY_THRESHOLD:
            return 5
        if min_distance < 1.0:
            return 2
        if min_distance < self.FAILURE_THRESHOLD:
            return 1
        return 0

    def _failure_evidence(self, min_distance: float, mission_status: str) -> str:
        """Describe the available evidence without claiming an unobserved collision.

        The competition score is distance based.  Mission non-completion is kept
        as a separate execution outcome because it may indicate a crash, an
        avoidance deadlock, or another system-under-test failure.  In the absence
        of an independent PX4/Gazebo collision flag, none of these labels claims
        that a collision is confirmed.
        """
        if min_distance < self.CRITICAL_PROXIMITY_THRESHOLD:
            if mission_status == "not_completed":
                return "noncompleted_critical_proximity"
            return "critical_proximity"
        if min_distance < self.FAILURE_THRESHOLD:
            if mission_status == "not_completed":
                return "noncompleted_official_proximity"
            return "official_proximity"
        if mission_status == "not_completed":
            return "noncompleted_without_official_proximity"
        if mission_status == "unknown":
            return "unknown_completion"
        return "none"

    def _reward(
        self,
        min_distance: float,
        n_obstacles: int,
        elapsed_minutes: float,
        mission_status: str,
    ) -> float:
        point = self._official_point(min_distance)

        closeness_reward = 5.0 / (0.2 + min_distance)
        failure_bonus = 25.0 * point
        simplicity_bonus = 4.0 / n_obstacles
        time_penalty = 0.05 * elapsed_minutes

        mission_bonus = 0.0
        if mission_status == "completed":
            mission_bonus = 3.0
        elif mission_status == "unknown":
            mission_bonus = 0.5

        return failure_bonus + closeness_reward + simplicity_bonus + mission_bonus - time_penalty

    def _result_point_samples(self, result: EvalResult) -> Tuple[int, ...]:
        samples = tuple(int(value) for value in result.point_samples)
        return samples or (int(result.point),)

    def _mean_official_point(self, result: EvalResult) -> float:
        samples = self._result_point_samples(result)
        return sum(samples) / len(samples)

    def _failure_reproducibility(self, result: EvalResult) -> float:
        samples = self._result_point_samples(result)
        return sum(value > 0 for value in samples) / len(samples)

    def _mean_min_distance(self, result: EvalResult) -> float:
        samples = [float(value) for value in result.distance_samples if math.isfinite(float(value))]
        if not samples:
            return float(result.min_distance)
        return sum(samples) / len(samples)

    def _mean_elapsed_minutes(self, result: EvalResult) -> float:
        samples = [float(value) for value in result.elapsed_samples if math.isfinite(float(value))]
        if not samples:
            return float(result.elapsed_minutes)
        return sum(samples) / len(samples)

    def _sort_key(self, result: EvalResult) -> Tuple:
        """Quality key used inside MAP-Elites during the search."""
        observed_outcome_priority = (
            1 if result.mission_status in {"completed", "not_completed"} else 0
        )
        return (
            result.point,
            observed_outcome_priority,
            -result.min_distance,
            result.reward,
            -len(result.obstacles),
        )

    def _final_rank_key(self, result: EvalResult) -> Tuple:
        """Robust ranking using observed mean score and reproducibility."""
        samples = self._result_point_samples(result)
        return (
            self._mean_official_point(result),
            self._failure_reproducibility(result),
            len(samples),
            -self._mean_min_distance(result),
            -len(result.obstacles),
            -self._mean_elapsed_minutes(result),
            result.reward,
        )

    def _problem_label(self, min_distance: float) -> str:
        """Distance-based label; it does not claim that a collision occurred."""
        if min_distance < self.CRITICAL_PROXIMITY_THRESHOLD:
            return "critical_proximity"
        if min_distance < self.FAILURE_THRESHOLD:
            return "official_failure"
        if min_distance < self.NEAR_MISS_THRESHOLD:
            return "near_miss"
        return "safe"

    def _is_official_failure(self, result: EvalResult) -> bool:
        return result.point > 0 and result.min_distance < self.FAILURE_THRESHOLD

    def _should_save_failure_artifacts(self, result: EvalResult) -> bool:
        return self._is_official_failure(result) and result.compliance_status == "compliant"

    def _is_returnable_failure(self, result: EvalResult) -> bool:
        """Return completed and non-completed official proximity failures.

        A non-completed mission is not automatically a collision.  It is eligible
        only when the execution itself produced an official distance failure and
        retained complete evidence.  Unknown completion remains excluded.
        """
        return (
            self._is_official_failure(result)
            and result.compliance_status == "compliant"
            and result.mission_status in {"completed", "not_completed"}
            and result.artifacts_saved
            and self._failure_reproducibility(result) >= self.MIN_FAILURE_REPRODUCIBILITY
        )
