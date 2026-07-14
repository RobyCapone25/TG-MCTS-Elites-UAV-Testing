from __future__ import annotations

import time
from typing import Optional

from testcase import TestCase

from .models import (
    EvalResult,
    MCTSNode,
    NonCompliantCandidateError,
    SimulationBudgetExhausted,
)


class SimulationMixin:
    def _run_simulation_once(
        self,
        node: MCTSNode,
        simulation_attempt: int,
        budget: int,
    ) -> EvalResult:
        obstacles = node.obstacles
        valid, reasons = self._validate_test_case_rules(obstacles)
        if not valid:
            raise NonCompliantCandidateError("; ".join(reasons))

        test = TestCase(self.case_study, obstacles)

        print(f"\n[TG-MCTS-Elites] Simulator attempt {simulation_attempt}/{budget}")
        print(f"Action: {node.action}")
        print(f"Scenario with {len(obstacles)} obstacle(s)")
        for index, obstacle in enumerate(obstacles, start=1):
            print(
                f"  obstacle {index}: "
                f"x={float(obstacle.position.x):.2f}, "
                f"y={float(obstacle.position.y):.2f}, "
                f"l={float(obstacle.size.l):.2f}, "
                f"w={float(obstacle.size.w):.2f}, "
                f"h={float(obstacle.size.h):.2f}, "
                f"r={float(obstacle.position.r):.2f}"
            )

        start = time.time()
        test.execute()
        elapsed_minutes = max((time.time() - start) / 60.0, 1e-6)

        try:
            distances = test.get_distances()
            if not distances:
                raise RuntimeError("Simulation completed but returned no obstacle distances.")

            min_distance = min(distances)
            print(f"minimum_distance:{min_distance:.4f}")

            point = self._official_point(min_distance)
            trajectory_xy, trajectory_actual = self._extract_trajectory_xy(test)
            mission_status = self._mission_completion_status(test)

            # A distance threshold is not collision evidence. Until a reliable
            # collision signal is available, every explicitly non-completed mission
            # is rejected from the compliant result set.
            if mission_status == "not_completed":
                raise NonCompliantCandidateError(
                    "mission did not complete and no independent collision signal is available"
                )

            reward = self._reward(
                min_distance=min_distance,
                n_obstacles=len(obstacles),
                elapsed_minutes=elapsed_minutes,
                mission_status=mission_status,
            )
            cell = self._elite_cell(obstacles)
        except Exception:
            self._delete_unselected_log(getattr(test, "log_file", ""))
            raise

        test.minimum_distance = min_distance
        test.official_point = point
        test.reward = reward
        test.elapsed_minutes = elapsed_minutes
        test.elite_cell = cell
        test.problem_type = self._problem_label(min_distance)
        test.mission_status = mission_status
        test.compliance_status = "compliant"
        test.plot_file = ""
        test.trajectory_xy = list(trajectory_xy) if trajectory_actual else []

        return EvalResult(
            obstacles=obstacles,
            test=test,
            min_distance=min_distance,
            elapsed_minutes=elapsed_minutes,
            point=point,
            reward=reward,
            cell=cell,
            signature=self._scenario_signature(obstacles),
            scenario_plot="",
            mission_status=mission_status,
            compliance_status="compliant",
            simulation_attempt=simulation_attempt,
            trajectory_xy=list(trajectory_xy) if trajectory_actual else [],
            point_samples=[point],
            distance_samples=[min_distance],
            elapsed_samples=[elapsed_minutes],
            confirmation_attempts=0,
        )

    def _evaluate_with_retries(
        self,
        node: MCTSNode,
        budget: int,
    ) -> Optional[EvalResult]:
        signature = self._scenario_signature(node.obstacles)
        if signature in self.seen_signatures:
            return None

        valid, reasons = self._validate_test_case_rules(node.obstacles)
        if not valid:
            self._log_invalid_candidate(
                node=node,
                simulation_index=self.simulation_attempts + 1,
                reason="; ".join(reasons),
            )
            self.seen_signatures.add(signature)
            return None

        for candidate_retry in range(1, self.MAX_SYSTEM_RETRIES + 2):
            next_attempt = self.simulation_attempts + 1
            if next_attempt > budget:
                return None

            self._write_pending_candidate(
                node=node,
                simulation_index=next_attempt,
                budget=budget,
                attempt=candidate_retry,
            )

            try:
                simulation_attempt = self._consume_simulation_attempt(budget)
                result = self._run_simulation_once(
                    node=node,
                    simulation_attempt=simulation_attempt,
                    budget=budget,
                )
                result = self._save_result_checkpoint(
                    result=result,
                    simulation_index=simulation_attempt,
                    node=node,
                )

                self.results.append(result)
                self.seen_signatures.add(signature)
                self._update_elites(result)
                self._clear_pending_candidate()
                return result

            except SimulationBudgetExhausted:
                return None

            except NonCompliantCandidateError as error:
                print("[invalid-candidate] Candidate violates execution constraints.")
                print(error)
                self._log_invalid_candidate(
                    node=node,
                    simulation_index=self.simulation_attempts,
                    reason=str(error),
                )
                self.seen_signatures.add(signature)
                self._clear_pending_candidate()
                return None

            except Exception as error:
                self._log_system_error(
                    node=node,
                    simulation_index=self.simulation_attempts,
                    attempt=candidate_retry,
                    error=error,
                )
                print(
                    f"[system-error] Candidate retry {candidate_retry}/"
                    f"{self.MAX_SYSTEM_RETRIES + 1} failed."
                )
                print(error)

                if (
                    candidate_retry <= self.MAX_SYSTEM_RETRIES
                    and self.simulation_attempts < budget
                ):
                    print("[system-error] Recomputing the same candidate with a new budget unit.")
                    time.sleep(2.0)
                else:
                    print(
                        "[system-error] Candidate stopped after retries or budget exhaustion. "
                        "It is not counted as a UAV failure."
                    )
                    self._clear_pending_candidate()
                    return None

        return None
