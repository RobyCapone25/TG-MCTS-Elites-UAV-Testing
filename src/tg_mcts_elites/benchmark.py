from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from aerialist.px4.obstacle import Obstacle

from .models import EvalResult


class BenchmarkRecorder:
    """Append-only recorder shared by every benchmarked search algorithm."""

    SCHEMA_VERSION = 2

    def __init__(
        self,
        output_dir: str | Path,
        algorithm_id: str,
        algorithm_name: str,
        case_study_file: str,
        mission_label: str,
        seed: int,
        budget: int,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.benchmark_dir = self.output_dir / "benchmark"
        self.benchmark_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.benchmark_dir / "events.jsonl"
        self.summary_json_path = self.benchmark_dir / "summary.json"
        self.summary_csv_path = self.benchmark_dir / "summary.csv"

        self.algorithm_id = algorithm_id
        self.algorithm_name = algorithm_name
        self.case_study_file = case_study_file
        self.case_study_basename = Path(case_study_file).name
        self.mission_label = mission_label
        self.seed = int(seed)
        self.budget = int(budget)

        self._started_at = time.perf_counter()
        self._event_sequence = 0
        self._counters: Counter[str] = Counter()
        self._simulation_seconds = 0.0
        self._search_seconds = 0.0
        self._load_existing_events()
        self.record_run_event(
            "run_started",
            resumed=self._event_sequence > 0,
            output_dir=str(self.output_dir.resolve()),
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).astimezone().isoformat()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): BenchmarkRecorder._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [BenchmarkRecorder._json_safe(item) for item in value]
        return str(value)

    @staticmethod
    def _obstacle_dict(obstacle: Obstacle) -> Dict[str, float]:
        return {
            "x": float(obstacle.position.x),
            "y": float(obstacle.position.y),
            "z": float(obstacle.position.z),
            "r": float(obstacle.position.r),
            "l": float(obstacle.size.l),
            "w": float(obstacle.size.w),
            "h": float(obstacle.size.h),
        }

    def _load_existing_events(self) -> None:
        if not self.events_path.exists():
            return
        try:
            with self.events_path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    self._event_sequence = max(
                        self._event_sequence,
                        int(event.get("event_sequence", 0)),
                    )
                    self._update_counters(event)
        except OSError:
            return

    def _update_counters(self, event: Dict[str, Any]) -> None:
        event_type = str(event.get("event_type", "unknown"))
        self._counters[f"event:{event_type}"] += 1
        if event_type == "candidate_proposed":
            status = str(event.get("proposal_status", "unknown"))
            self._counters["candidate_proposals"] += 1
            self._counters[f"candidate_status:{status}"] += 1
        elif event_type == "simulator_attempt":
            status = str(event.get("attempt_status", "unknown"))
            phase = str(event.get("phase", "search"))
            self._counters[f"attempt_status:{status}"] += 1
            self._counters[f"attempt_phase:{phase}"] += 1
            try:
                self._simulation_seconds += max(float(event.get("simulation_seconds", 0.0)), 0.0)
            except (TypeError, ValueError):
                pass
        elif event_type == "search_timing":
            try:
                self._search_seconds += max(float(event.get("search_seconds", 0.0)), 0.0)
            except (TypeError, ValueError):
                pass

    def _write_event(self, event_type: str, **payload: Any) -> None:
        self._event_sequence += 1
        event = self._json_safe(
            {
                "schema_version": self.SCHEMA_VERSION,
                "event_sequence": self._event_sequence,
                "timestamp": self._timestamp(),
                "event_type": event_type,
                "algorithm_id": self.algorithm_id,
                "algorithm_name": self.algorithm_name,
                "case_study_file": self.case_study_file,
                "case_study_basename": self.case_study_basename,
                "mission_label": self.mission_label,
                "seed": self.seed,
                "budget": self.budget,
                **payload,
            }
        )
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._update_counters(event)

    def record_run_event(self, name: str, **payload: Any) -> None:
        self._write_event("run_event", name=name, **payload)

    def record_candidate(
        self,
        *,
        node_id: Optional[int],
        parent_id: Optional[int],
        action: str,
        obstacles: Sequence[Obstacle],
        proposal_status: str,
        rejection_reason: str = "",
        source: str = "",
        signature: Any = None,
    ) -> None:
        self._write_event(
            "candidate_proposed",
            node_id=node_id,
            parent_id=parent_id,
            action=action,
            source=source,
            proposal_status=proposal_status,
            rejection_reason=rejection_reason,
            n_obstacles=len(obstacles),
            obstacles=[self._obstacle_dict(obstacle) for obstacle in obstacles],
            signature=signature,
        )

    def record_search_timing(self, search_seconds: float, phase: str) -> None:
        self._write_event(
            "search_timing",
            phase=phase,
            search_seconds=max(float(search_seconds), 0.0),
        )

    def record_simulator_attempt(
        self,
        *,
        simulation_attempt: int,
        candidate_retry: int,
        node_id: int,
        parent_id: Optional[int],
        action: str,
        attempt_status: str,
        simulation_seconds: float,
        phase: str,
        error_type: str = "",
        error_message: str = "",
        result: Optional[EvalResult] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "simulation_attempt": int(simulation_attempt),
            "candidate_retry": int(candidate_retry),
            "node_id": int(node_id),
            "parent_id": parent_id,
            "action": action,
            "phase": phase,
            "attempt_status": attempt_status,
            "simulation_seconds": max(float(simulation_seconds), 0.0),
            "error_type": error_type,
            "error_message": error_message,
        }
        if result is not None:
            payload.update(
                {
                    "min_distance": result.min_distance,
                    "official_point": result.point,
                    "reward": result.reward,
                    "n_obstacles": len(result.obstacles),
                    "cell": result.cell,
                    "mission_status": result.mission_status,
                    "failure_evidence": result.failure_evidence,
                    "compliance_status": result.compliance_status,
                }
            )
        self._write_event("simulator_attempt", **payload)

    def record_evaluation(self, result: EvalResult, node_id: int, action: str) -> None:
        self._write_event(
            "evaluated_scenario",
            simulation_attempt=result.simulation_attempt,
            node_id=node_id,
            action=action,
            n_obstacles=len(result.obstacles),
            obstacles=[self._obstacle_dict(obstacle) for obstacle in result.obstacles],
            signature=result.signature,
            min_distance=result.min_distance,
            official_point=result.point,
            reward=result.reward,
            elapsed_minutes=result.elapsed_minutes,
            cell=result.cell,
            mission_status=result.mission_status,
            failure_evidence=result.failure_evidence,
            compliance_status=result.compliance_status,
            artifacts_saved=result.artifacts_saved,
            trajectory_points=len(result.trajectory_xy),
        )

    def record_archive_update(
        self,
        *,
        result: EvalResult,
        replaced_existing_elite: bool,
    ) -> None:
        self._write_event(
            "archive_update",
            simulation_attempt=result.simulation_attempt,
            cell=result.cell,
            replaced_existing_elite=replaced_existing_elite,
            min_distance=result.min_distance,
            official_point=result.point,
            reward=result.reward,
            n_obstacles=len(result.obstacles),
        )

    def record_confirmation(
        self,
        *,
        base: EvalResult,
        observed: Optional[EvalResult],
        simulation_attempt: int,
        outcome: str,
    ) -> None:
        self._write_event(
            "confirmation_observation",
            base_simulation_attempt=base.simulation_attempt,
            simulation_attempt=simulation_attempt,
            outcome=outcome,
            observed_point=observed.point if observed is not None else 0,
            observed_min_distance=(observed.min_distance if observed is not None else None),
            observed_mission_status=(observed.mission_status if observed is not None else None),
            total_samples=len(base.point_samples) or 1,
        )

    def record_final_selection(
        self,
        *,
        result: EvalResult,
        rank: int,
        nearest_scenario_distance: Optional[float],
        nearest_trajectory_distance: Optional[float],
    ) -> None:
        self._write_event(
            "final_selected_failure",
            rank=int(rank),
            simulation_attempt=result.simulation_attempt,
            min_distance=result.min_distance,
            official_point=result.point,
            mean_official_point=(sum(result.point_samples) / len(result.point_samples) if result.point_samples else result.point),
            failure_reproducibility=(sum(point > 0 for point in result.point_samples) / len(result.point_samples) if result.point_samples else int(result.point > 0)),
            reward=result.reward,
            n_obstacles=len(result.obstacles),
            cell=result.cell,
            nearest_scenario_distance=nearest_scenario_distance,
            nearest_trajectory_distance=nearest_trajectory_distance,
            signature=result.signature,
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _atomic_write_csv(path: Path, row: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _first_attempt(
        results: Iterable[EvalResult],
        predicate: Callable[[EvalResult], bool],
    ) -> Optional[int]:
        attempts = [
            int(result.simulation_attempt)
            for result in results
            if result.simulation_attempt > 0 and predicate(result)
        ]
        return min(attempts) if attempts else None

    @staticmethod
    def _mean_nearest(
        selected: Sequence[EvalResult],
        distance: Callable[[EvalResult, EvalResult], float],
    ) -> Optional[float]:
        if len(selected) < 2:
            return None
        nearest = []
        for index, left in enumerate(selected):
            values = [
                distance(left, right)
                for other_index, right in enumerate(selected)
                if other_index != index
            ]
            finite = [value for value in values if math.isfinite(value)]
            if finite:
                nearest.append(min(finite))
        return mean(nearest) if nearest else None

    def finalize(
        self,
        *,
        results: Sequence[EvalResult],
        elites: Dict[Any, EvalResult],
        selected_results: Sequence[EvalResult],
        simulator_attempts: int,
        run_status: str,
        nominal_archive_cells: Optional[int],
        is_official_failure: Callable[[EvalResult], bool],
        is_returnable_failure: Callable[[EvalResult], bool],
        mean_official_point: Callable[[EvalResult], float],
        failure_reproducibility: Callable[[EvalResult], float],
        scenario_distance: Callable[[EvalResult, EvalResult], float],
        trajectory_distance: Callable[[EvalResult, EvalResult], float],
    ) -> Dict[str, Any]:
        official = [result for result in results if is_official_failure(result)]
        returnable = [result for result in results if is_returnable_failure(result)]
        attempts = int(simulator_attempts)
        archive_coverage = (
            len(elites) / nominal_archive_cells
            if nominal_archive_cells and nominal_archive_cells > 0
            else None
        )

        recorded_search_attempts = self._counters["attempt_phase:search"]
        recorded_confirmation_attempts = self._counters["attempt_phase:confirmation"]
        recorded_attempts = recorded_search_attempts + recorded_confirmation_attempts

        observed_confirmation_attempts = sum(
            max(int(result.confirmation_attempts), 0) for result in results
        )
        confirmation_attempts = min(
            max(recorded_confirmation_attempts, observed_confirmation_attempts),
            attempts,
        )
        # The strict global counter is authoritative. An abrupt host/container
        # stop may consume an attempt after run_state is fsynced but before the
        # benchmark event is appended; keep the accounting balanced explicitly.
        search_attempts = max(attempts - confirmation_attempts, 0)
        unrecorded_attempts = max(attempts - recorded_attempts, 0)

        if recorded_attempts > 0:
            simulation_seconds = self._simulation_seconds
        else:
            simulation_seconds = sum(
                max(float(value), 0.0) * 60.0
                for result in results
                for value in (result.elapsed_samples or [result.elapsed_minutes])
                if math.isfinite(float(value))
            )

        summary: Dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "generated_at": self._timestamp(),
            "algorithm_id": self.algorithm_id,
            "algorithm_name": self.algorithm_name,
            "case_study_file": self.case_study_file,
            "case_study_basename": self.case_study_basename,
            "mission_label": self.mission_label,
            "seed": self.seed,
            "budget": self.budget,
            "run_status": run_status,
            "simulator_attempts": attempts,
            "search_attempts": search_attempts,
            "confirmation_attempts": confirmation_attempts,
            "successful_evaluations": len(results),
            "official_failures": len(official),
            "returnable_reproducible_failures": len(returnable),
            "diverse_failures_returned": len(selected_results),
            "success_indicator": int(bool(selected_results)),
            "failure_yield_official": len(official) / attempts if attempts else 0.0,
            "failure_yield_returnable": len(returnable) / attempts if attempts else 0.0,
            "initial_official_point_total": sum(result.point for result in results),
            "initial_official_point_yield": sum(result.point for result in results) / attempts if attempts else 0.0,
            "mean_confirmed_point_total": sum(mean_official_point(result) for result in results),
            "diverse_mean_confirmed_point_total": sum(mean_official_point(result) for result in selected_results),
            "best_min_distance": min((result.min_distance for result in results), default=None),
            "time_to_first_official_failure_attempt": self._first_attempt(results, is_official_failure),
            "time_to_first_returnable_failure_attempt": self._first_attempt(results, is_returnable_failure),
            "elite_cells_filled": len(elites),
            "nominal_archive_cells": nominal_archive_cells,
            "archive_coverage": archive_coverage,
            "mean_failure_reproducibility_returnable": (
                mean(failure_reproducibility(result) for result in returnable)
                if returnable
                else None
            ),
            "mean_obstacle_count_returnable": (
                mean(len(result.obstacles) for result in returnable)
                if returnable
                else None
            ),
            "single_obstacle_returnable_fraction": (
                sum(len(result.obstacles) == 1 for result in returnable) / len(returnable)
                if returnable
                else None
            ),
            "mean_nearest_scenario_distance_selected": self._mean_nearest(selected_results, scenario_distance),
            "mean_nearest_trajectory_dtw_selected": self._mean_nearest(selected_results, trajectory_distance),
            "candidate_proposals": self._counters["candidate_proposals"],
            "accepted_candidate_proposals": self._counters["candidate_status:accepted"],
            "invalid_candidate_proposals": self._counters["candidate_status:rejected_invalid"],
            "duplicate_candidate_proposals": (
                self._counters["candidate_status:rejected_duplicate_evaluated"]
                + self._counters["candidate_status:rejected_duplicate_tree"]
            ),
            "system_error_attempts": self._counters["attempt_status:system_error"],
            "noncompliant_attempts": self._counters["attempt_status:noncompliant"],
            "recorded_simulator_attempt_events": recorded_attempts,
            "unrecorded_or_interrupted_attempts": unrecorded_attempts,
            "simulation_seconds_recorded": simulation_seconds,
            "search_seconds_recorded": self._search_seconds,
            "recorder_wall_clock_seconds": max(time.perf_counter() - self._started_at, 0.0),
            "events_file": str(self.events_path.resolve()),
        }
        summary = self._json_safe(summary)

        self._atomic_write_json(self.summary_json_path, summary)
        self._atomic_write_csv(self.summary_csv_path, summary)

        self.record_run_event(
            "run_finished",
            run_status=run_status,
            summary_json=str(self.summary_json_path.resolve()),
            summary_csv=str(self.summary_csv_path.resolve()),
        )
        return summary
