from __future__ import annotations

import time
from typing import List

from .models import (
    EvalResult,
    MCTSNode,
    NonCompliantCandidateError,
    SimulationBudgetExhausted,
)


class ConfirmationMixin:
    def _confirmation_reserve(self, budget: int) -> int:
        if budget < self.CONFIRMATION_MIN_BUDGET:
            return 0
        reserve = max(1, int(round(budget * self.CONFIRMATION_BUDGET_FRACTION)))
        return min(reserve, max(0, budget - 1))

    def _confirmation_candidates(self) -> List[EvalResult]:
        unique = {}
        for result in self.results:
            if not self._is_returnable_failure(result):
                continue
            old = unique.get(result.signature)
            if old is None or self._final_rank_key(result) > self._final_rank_key(old):
                unique[result.signature] = result
        ranked = sorted(unique.values(), key=self._final_rank_key, reverse=True)
        return ranked[: self.CONFIRMATION_MAX_CANDIDATES]

    def _append_confirmation_observation(
        self,
        base: EvalResult,
        *,
        point: int,
        min_distance: float | None,
        elapsed_minutes: float | None,
    ) -> None:
        base.point_samples.append(int(point))
        if min_distance is not None:
            base.distance_samples.append(float(min_distance))
        if elapsed_minutes is not None:
            base.elapsed_samples.append(float(elapsed_minutes))
        base.confirmation_attempts += 1
        base.test.mean_official_point = self._mean_official_point(base)
        base.test.failure_reproducibility = self._failure_reproducibility(base)
        base.test.confirmation_samples = len(self._result_point_samples(base))
        base.test.mean_min_distance = self._mean_min_distance(base)

    def _confirm_candidate_once(self, base: EvalResult, budget: int) -> bool:
        node = MCTSNode(
            obstacles=self._clone_obstacles(base.obstacles),
            parent=None,
            action=f"confirm_attempt_{base.simulation_attempt}",
            node_id=self._next_node_id(),
        )

        for retry in range(1, self.MAX_SYSTEM_RETRIES + 2):
            if self.simulation_attempts >= budget:
                return False

            started = time.perf_counter()
            try:
                attempt = self._consume_simulation_attempt(budget)
                observed = self._run_simulation_once(
                    node=node,
                    simulation_attempt=attempt,
                    budget=budget,
                )
                observed = self._save_confirmation_failure_artifacts(
                    result=observed,
                    simulation_index=attempt,
                    node=node,
                    base_simulation_attempt=base.simulation_attempt,
                )

                self._record_attempt(
                    node=node,
                    simulation_attempt=attempt,
                    candidate_retry=retry,
                    attempt_status="evaluated",
                    simulation_seconds=time.perf_counter() - started,
                    phase="confirmation",
                    result=observed,
                )

                # Confirmation executions consume real attempts and belong in
                # progress diagnostics even though they are not MCTS children.
                self._record_history(attempt, node, observed)

                self._append_confirmation_observation(
                    base,
                    point=observed.point,
                    min_distance=observed.min_distance,
                    elapsed_minutes=observed.elapsed_minutes,
                )
                self._record_confirmation(
                    base=base,
                    observed=observed,
                    simulation_attempt=attempt,
                    retry=retry,
                    outcome="evaluated",
                )
                if getattr(self, "benchmark", None) is not None:
                    self.benchmark.record_confirmation(
                        base=base,
                        observed=observed,
                        simulation_attempt=attempt,
                        outcome="evaluated",
                    )
                print(
                    "[confirmation] "
                    f"base attempt {base.simulation_attempt}: "
                    f"point={observed.point}, "
                    f"min_distance={observed.min_distance:.4f}, "
                    f"failure_rate={self._failure_reproducibility(base):.3f}"
                )
                return True

            except SimulationBudgetExhausted:
                return False

            except NonCompliantCandidateError as error:
                self._record_attempt(
                    node=node,
                    simulation_attempt=self.simulation_attempts,
                    candidate_retry=retry,
                    attempt_status="noncompliant",
                    simulation_seconds=time.perf_counter() - started,
                    phase="confirmation",
                    error=error,
                )
                self._append_confirmation_observation(
                    base,
                    point=0,
                    min_distance=None,
                    elapsed_minutes=None,
                )
                self._record_confirmation(
                    base=base,
                    observed=None,
                    simulation_attempt=self.simulation_attempts,
                    retry=retry,
                    outcome="noncompliant",
                    error=str(error),
                )
                if getattr(self, "benchmark", None) is not None:
                    self.benchmark.record_confirmation(
                        base=base,
                        observed=None,
                        simulation_attempt=self.simulation_attempts,
                        outcome="noncompliant",
                    )
                print(
                    "[confirmation] Candidate did not reproduce as a compliant "
                    f"failure: {error}"
                )
                return True

            except Exception as error:
                self._record_attempt(
                    node=node,
                    simulation_attempt=self.simulation_attempts,
                    candidate_retry=retry,
                    attempt_status="system_error",
                    simulation_seconds=time.perf_counter() - started,
                    phase="confirmation",
                    error=error,
                )
                self._log_system_error(
                    node=node,
                    simulation_index=self.simulation_attempts,
                    attempt=retry,
                    error=error,
                )
                print(
                    f"[confirmation-system-error] retry {retry}/"
                    f"{self.MAX_SYSTEM_RETRIES + 1} failed: {error}"
                )
                if retry <= self.MAX_SYSTEM_RETRIES and self.simulation_attempts < budget:
                    time.sleep(2.0)
                    continue
                return False

        return False

    def _confirm_top_failures(self, budget: int) -> bool:
        candidates = self._confirmation_candidates()
        if not candidates:
            print("[confirmation] No failure is available; reserved attempts return to exploration.")
            return False

        print(
            "[confirmation] Rerunning up to "
            f"{len(candidates)} leading failures within the strict total budget."
        )
        while self.simulation_attempts < budget:
            active = [
                result
                for result in candidates
                if len(self._result_point_samples(result))
                < self.CONFIRMATION_TARGET_TOTAL_SAMPLES
            ]
            if not active:
                break

            progress = False
            for result in active:
                if self.simulation_attempts >= budget:
                    break
                progress = self._confirm_candidate_once(result, budget) or progress
            if not progress:
                break

        return True
