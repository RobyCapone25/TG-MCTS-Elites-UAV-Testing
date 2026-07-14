from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from aerialist.px4.aerialist_test import AerialistTest

from .archive import ArchiveMixin
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


class RandomGenerator(
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

    def __init__(self, case_study_file: str) -> None:
        self.case_study_file = case_study_file
        self.case_study = AerialistTest.from_yaml(case_study_file)

        self.results: List[EvalResult] = []
        self.elites: Dict[Tuple, EvalResult] = {}
        self.seen_signatures = set()
        self.tree_signatures = set()
        self.history: List[Dict[str, Any]] = []
        self.selected_results: List[EvalResult] = []
        self._node_counter = 0
        self._mission_reference_cache = None
        self._reference_pose_cache = None
        self.simulation_attempts = 0
        self.seed = self._initialise_seed()

        self.run_id = self._new_run_id()
        self.output_dir = os.path.join("results", "tg_mcts_elites", self.run_id)
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

    def _process_evaluated_node(self, node: MCTSNode, result: EvalResult, budget: int) -> None:
        node.eval_result = result
        self._record_history(result.simulation_attempt, node, result)
        self._backup(node, result.reward)
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
            node = self._tree_policy(root)
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
        print("Final suite: completed, compliant, diverse official failures only")
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

        self._run_search_phase(
            root=root,
            attempt_limit=exploration_limit,
            total_budget=budget,
        )

        if self.simulation_attempts < budget and confirmation_reserve > 0:
            self._confirm_top_failures(budget)

        # If no candidate could be confirmed, or the selected candidates reached
        # their target sample count early, return any remaining budget to search.
        if self.simulation_attempts < budget:
            self._run_search_phase(
                root=root,
                attempt_limit=budget,
                total_budget=budget,
            )

        final_tests = self._final_suite() if self.results else []
        self._save_all_outputs(root)

        if self.simulation_attempts >= budget:
            status = "completed"
        elif not self.results:
            status = "failed_no_successful_evaluations"
        else:
            status = "stopped_before_budget"
        self._write_run_state(status=status, budget=budget)

        return final_tests
