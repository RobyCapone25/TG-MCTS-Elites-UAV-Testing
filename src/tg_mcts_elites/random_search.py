from __future__ import annotations

import random
import time
from typing import Any, List, Optional

from .generator import TGMCTSElitesGenerator
from .models import EvalResult, MCTSNode


class RandomSearchGenerator(TGMCTSElitesGenerator):
    """Operator-matched random-search baseline without UCB or MCTS backup."""

    ALGORITHM_ID = "operator_random_search"
    ALGORITHM_NAME = "Operator-Matched Random Search"
    RESULTS_NAMESPACE = "random_search"
    RANDOM_RESTART_PROBABILITY = 0.30
    MAX_RANDOM_PROPOSALS_PER_SELECTION = 60

    def _random_candidate(self, root: MCTSNode) -> Optional[MCTSNode]:
        benchmark = getattr(self, "benchmark", None)
        for _ in range(self.MAX_RANDOM_PROPOSALS_PER_SELECTION):
            if not self.results or random.random() < self.RANDOM_RESTART_PROBABILITY:
                source = "random_restart"
                source_obstacles = []
                parent_id = root.node_id
            else:
                source = "uniform_evaluated_parent"
                source_result = random.choice(self.results)
                source_obstacles = source_result.obstacles
                parent_id = root.node_id

            temporary_parent = MCTSNode(obstacles=source_obstacles, node_id=-1)
            action = random.choice(self._available_actions(temporary_parent))
            child_obstacles = self._apply_action(source_obstacles, action)
            signature = self._scenario_signature(child_obstacles)
            valid, reasons = self._validate_test_case_rules(child_obstacles)

            if not valid:
                if benchmark is not None:
                    benchmark.record_candidate(
                        node_id=None,
                        parent_id=parent_id,
                        action=action,
                        obstacles=child_obstacles,
                        proposal_status="rejected_invalid",
                        rejection_reason="; ".join(reasons),
                        source=source,
                        signature=signature,
                    )
                continue
            if signature in self.seen_signatures:
                if benchmark is not None:
                    benchmark.record_candidate(
                        node_id=None,
                        parent_id=parent_id,
                        action=action,
                        obstacles=child_obstacles,
                        proposal_status="rejected_duplicate_evaluated",
                        source=source,
                        signature=signature,
                    )
                continue
            if signature in self.tree_signatures:
                if benchmark is not None:
                    benchmark.record_candidate(
                        node_id=None,
                        parent_id=parent_id,
                        action=action,
                        obstacles=child_obstacles,
                        proposal_status="rejected_duplicate_tree",
                        source=source,
                        signature=signature,
                    )
                continue

            child = MCTSNode(
                obstacles=child_obstacles,
                parent=root,
                action=f"random:{action}",
                node_id=self._next_node_id(),
            )
            root.children.append(child)
            self.tree_signatures.add(signature)
            if benchmark is not None:
                benchmark.record_candidate(
                    node_id=child.node_id,
                    parent_id=root.node_id,
                    action=action,
                    obstacles=child_obstacles,
                    proposal_status="accepted",
                    source=source,
                    signature=signature,
                )
            return child

        if benchmark is not None:
            benchmark.record_run_event(
                "candidate_batch_exhausted",
                source="random_search",
                parent_id=root.node_id,
                maximum_proposals=self.MAX_RANDOM_PROPOSALS_PER_SELECTION,
            )
        return None

    def _process_evaluated_node(self, node: MCTSNode, result: EvalResult, budget: int) -> None:
        node.eval_result = result
        self._record_history(result.simulation_attempt, node, result)
        # Deliberately no reward backup: future random choices cannot use fitness.
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
        failed_proposals = 0
        max_failed_proposals = max(50, total_budget * 15)
        while (
            self.simulation_attempts < attempt_limit
            and self.simulation_attempts < total_budget
            and failed_proposals < max_failed_proposals
        ):
            started = time.perf_counter()
            node = self._random_candidate(root)
            if self.benchmark is not None:
                self.benchmark.record_search_timing(
                    time.perf_counter() - started,
                    "uniform_random_candidate_selection",
                )
            if node is None:
                failed_proposals += 1
                continue
            result = self._evaluate_with_retries(node=node, budget=total_budget)
            if result is None:
                failed_proposals += 1
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
        self._start_benchmark_recorder(budget)
        root = self._load_tree_checkpoint()
        if root is None:
            root = self._rebuild_tree_from_history()
        if root is None:
            root = MCTSNode(obstacles=[], node_id=self._next_node_id())

        print("\n======================================================")
        print("Rule-compliant Operator-Matched Random UAV Test Generator")
        print(f"Case study: {self.case_study_file}")
        print(f"Simulator-attempt budget: {budget}")
        print(f"Seed: {self.seed}")
        print(f"Output directory: {self.output_dir}")
        print(f"Reference waypoints: {len(reference_path)}")
        print("Parent selection: uniform over evaluated scenarios")
        print("Action selection: uniform over the same scenario operators")
        print("UCB, progressive-widening control, and MCTS backup: disabled")
        print("MAP-Elites archive: measurement only; never used for generation")
        print("Confirmation, validation, scoring, persistence, and final filtering: shared")
        print("======================================================")

        confirmation_reserve = self._confirmation_reserve(budget)
        exploration_limit = max(1, budget - confirmation_reserve)

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


__all__ = ["RandomSearchGenerator"]
