from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Tuple

from aerialist.px4.aerialist_test import AerialistTest

from .archive import ArchiveMixin
from .benchmark import BenchmarkRecorder
from .config import GeneratorConstants
from .confirmation import ConfirmationMixin
from .geometry import GeometryMixin
from .mcts import MCTSMixin
from .mission import MissionPlanMixin
from .models import EvalResult, MCTSNode
from .persistence import PersistenceMixin
from .plotting import PlottingMixin
from .scenarios import ScenarioMixin
from .scoring import ScoringMixin
from .selection import SelectionMixin
from .simulation import SimulationMixin
from .trajectory import TrajectoryMixin
from .validation import ValidationMixin


class TGMCTSElitesGenerator(
    GeneratorConstants,
    PersistenceMixin,
    GeometryMixin,
    MissionPlanMixin,
    ValidationMixin,
    ScenarioMixin,
    ArchiveMixin,
    ScoringMixin,
    MCTSMixin,
    TrajectoryMixin,
    PlottingMixin,
    SimulationMixin,
    ConfirmationMixin,
    SelectionMixin,
):
    """High-level TG-MCTS-Elites orchestration class."""

    ALGORITHM_ID = "tg_mcts_elites"
    ALGORITHM_NAME = "TG-MCTS-Elites"
    RESULTS_NAMESPACE = "tg_mcts_elites"
    NOMINAL_ARCHIVE_CELLS = 700

    def __init__(self, case_study_file: str) -> None:
        self.case_study_file = case_study_file
        self.case_study = AerialistTest.from_yaml(case_study_file)
        self.results: List[EvalResult] = []
        self.elites: Dict[Tuple, EvalResult] = {}
        self.seen_signatures = set()
        self.tree_signatures = set()
        self.history: List[Dict[str, Any]] = []
        self.selected_results: List[EvalResult] = []
        self.benchmark: BenchmarkRecorder | None = None
        self._node_counter = 0
        self._mission_reference_cache = None
        self._reference_pose_cache = None
        self.simulation_attempts = 0
        self.seed = self._initialise_seed()

        self.run_id = self._new_run_id()
        self.output_dir = os.path.join("results", self.RESULTS_NAMESPACE, self.run_id)
        self._configure_run_paths()

    def _reset_search_state(self) -> None:
        self.results = []
        self.elites = {}
        self.seen_signatures = set()
        self.tree_signatures = set()
        self.history = []
        self.selected_results = []

    def _tree_root(self, node: MCTSNode) -> MCTSNode:
        while node.parent is not None:
            node = node.parent
        return node

    def _start_benchmark_recorder(self, budget: int) -> None:
        self.benchmark = BenchmarkRecorder(
            output_dir=self.output_dir,
            algorithm_id=self.ALGORITHM_ID,
            algorithm_name=self.ALGORITHM_NAME,
            case_study_file=self.case_study_file,
            mission_label=getattr(self, "mission_label", self._mission_label_from_case_name()),
            seed=self.seed,
            budget=budget,
        )

    def _process_evaluated_node(self, node: MCTSNode, result: EvalResult, budget: int) -> None:
        node.eval_result = result
        self._record_history(result.simulation_attempt, node, result)
        self._backup(node, result.reward)
        self._save_tree_checkpoint(self._tree_root(node))
        self._write_run_state(status="running", budget=budget)

        interval = max(1, int(self.OUTPUT_SNAPSHOT_INTERVAL))
        if result.simulation_attempt % interval == 0:
            self._save_history_csv()
            self._save_progress_plots()
            self._save_tree_plot(self._tree_root(node))

    def _run_search_phase(
        self,
        root: MCTSNode,
        attempt_limit: int,
        total_budget: int,
    ) -> None:
        failed_expansions = 0
        max_failed_expansions = max(50, total_budget * 15)

        while (
            self.simulation_attempts < attempt_limit
            and self.simulation_attempts < total_budget
            and failed_expansions < max_failed_expansions
        ):
            started = time.perf_counter()
            node = self._tree_policy(root)
            if self.benchmark is not None:
                self.benchmark.record_search_timing(
                    time.perf_counter() - started,
                    "mcts_tree_policy",
                )
            if node is None:
                failed_expansions += 1
                continue

            valid, reasons = self._validate_test_case_rules(node.obstacles)
            if not valid:
                self._log_invalid_candidate(
                    node=node,
                    simulation_index=self.simulation_attempts + 1,
                    reason="; ".join(reasons),
                )
                failed_expansions += 1
                continue

            result = self._evaluate_with_retries(node=node, budget=total_budget)
            if result is None:
                failed_expansions += 1
                continue
            self._process_evaluated_node(node, result, total_budget)

    def _finish_run(self, root: MCTSNode, budget: int, final_tests: List[Any]) -> List[Any]:
        # Older/current selection revisions may return test objects without
        # storing the corresponding EvalResult objects. Recover that mapping so
        # benchmark summaries remain complete without rewriting selection.py.
        if final_tests and not self.selected_results:
            selected_ids = {id(test) for test in final_tests}
            self.selected_results = [
                result for result in self.results if id(result.test) in selected_ids
            ]

        if self.benchmark is not None and self.selected_results:
            for rank, result in enumerate(self.selected_results, start=1):
                previous = self.selected_results[: rank - 1]
                nearest_scenario = (
                    min(self._scenario_distance(result, item) for item in previous)
                    if previous
                    else None
                )
                nearest_trajectory = (
                    min(self._trajectory_distance(result, item) for item in previous)
                    if previous
                    else None
                )
                self.benchmark.record_final_selection(
                    result=result,
                    rank=rank,
                    nearest_scenario_distance=nearest_scenario,
                    nearest_trajectory_distance=nearest_trajectory,
                )

        self._save_tree_checkpoint(root)
        self._save_all_outputs(root)
        if self.simulation_attempts >= budget:
            status = "completed"
        elif not self.results:
            status = "failed_no_successful_evaluations"
        else:
            status = "stopped_before_budget"

        # The benchmark summary is finalized before run_state is marked completed.
        # If the process stops during finalization, the same run remains resumable
        # and can regenerate the summary and plots without consuming a new attempt.
        if self.benchmark is not None:
            self.benchmark.finalize(
                results=self.results,
                elites=self.elites,
                selected_results=self.selected_results,
                simulator_attempts=self.simulation_attempts,
                run_status=status,
                nominal_archive_cells=self.NOMINAL_ARCHIVE_CELLS,
                is_official_failure=self._is_official_failure,
                is_returnable_failure=self._is_returnable_failure,
                mean_official_point=self._mean_official_point,
                failure_reproducibility=self._failure_reproducibility,
                scenario_distance=self._scenario_distance,
                trajectory_distance=self._trajectory_distance,
            )
        self._write_run_state(status=status, budget=budget)
        return final_tests

    def generate(self, budget: int) -> List[Any]:
        if budget <= 0:
            raise ValueError("budget must be a positive integer")

        self._reset_search_state()
        self._setup_run_directory(budget=budget)
        reference_path = self._mission_reference_path()
        self._load_previous_results()
        self._load_previous_confirmations()
        self._load_previous_history()
        if self.results:
            self.simulation_attempts = max(
                self.simulation_attempts,
                max(result.simulation_attempt for result in self.results),
            )

        self._node_counter = max(self._node_counter, len(self.history) + 1)
        self._start_benchmark_recorder(budget)
        root = self._load_tree_checkpoint()
        if root is None:
            root = self._rebuild_tree_from_history()
        if root is None:
            root = MCTSNode(obstacles=[], node_id=self._next_node_id())

        print("\n======================================================")
        print("Rule-compliant Robust TG-MCTS-Elites UAV Test Generator")
        print(f"Case study: {self.case_study_file}")
        print(f"Simulator-attempt budget: {budget}")
        print(f"Attempts already consumed: {self.simulation_attempts}")
        print(f"Evaluations restored from checkpoint: {len(self.results)}")
        print(f"Seed: {self.seed}")
        print(f"Output directory: {self.output_dir}")
        print(f"Mission plan: {getattr(self, 'mission_plan_path', 'unknown')}")
        print(f"Reference waypoints: {len(reference_path)}")
        print("Heavy artifacts: retained only for official failures (d < 1.5 m)")
        print("Final suite: compliant, artifact-backed, reproducible proximity failures")
        print("Diversity: obstacle geometry plus realised-trajectory DTW")
        print("Crash handling: pending candidate may be retried if budget remains")
        print("======================================================")

        confirmation_reserve = self._confirmation_reserve(budget)
        exploration_limit = max(1, budget - confirmation_reserve)
        print(
            f"Exploration target: {exploration_limit} attempts | "
            f"confirmation reserve: {confirmation_reserve}"
        )

        pending_node = self._load_pending_candidate_as_node(root)
        if pending_node is not None and self.simulation_attempts < budget:
            result = self._evaluate_with_retries(node=pending_node, budget=budget)
            if result is not None:
                self._process_evaluated_node(pending_node, result, budget)

        self._run_search_phase(root, exploration_limit, budget)
        if self.simulation_attempts < budget and confirmation_reserve > 0:
            self._confirm_top_failures(budget)
        if self.simulation_attempts < budget:
            self._run_search_phase(root, budget, budget)

        final_tests = self._final_suite() if self.results else []
        return self._finish_run(root, budget, final_tests)


# Backward compatibility for existing imports and external scripts.
RandomGenerator = TGMCTSElitesGenerator

__all__ = ["TGMCTSElitesGenerator", "RandomGenerator"]
