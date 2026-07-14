from __future__ import annotations

import csv
import glob
import json
import os
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from aerialist.px4.obstacle import Obstacle

from .models import (
    EvalResult,
    MCTSNode,
    SavedEvaluatedTestCase,
    SimulationBudgetExhausted,
)


class PersistenceMixin:
    def _initialise_seed(self) -> int:
        env_seed = os.environ.get("TG_SEED", "").strip()
        seed = int(env_seed) if env_seed else random.randint(0, 2**31 - 1)
        random.seed(seed)
        return seed

    def _next_node_id(self) -> int:
        node_id = self._node_counter
        self._node_counter += 1
        return node_id

    def _normalised_case_name(self) -> str:
        return os.path.basename(self.case_study_file)

    def _mission_label(self) -> str:
        """Return a stable human-readable mission label."""
        helper = getattr(self, "_mission_label_from_case_name", None)
        if callable(helper):
            return helper()

        stem = Path(self.case_study_file).stem.lower()
        match = re.search(r"mission[_-]?(\d+)", stem)
        if match:
            return f"mission_{int(match.group(1))}"

        safe = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
        return safe or "mission"

    def _new_run_id(self) -> str:
        """Create a mission-aware unique run identifier."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        return f"{self._mission_label()}_{timestamp}"

    def _mission_label_from_case_name(self) -> str:
        stem = Path(self.case_study_file).stem.lower()
        match = re.search(r"mission\s*_?([0-9]+)", stem)
        if match:
            return f"mission_{int(match.group(1))}"
        safe = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
        return safe or "mission"

    def _configure_run_paths(self) -> None:
        self.checkpoint_dir = os.path.join(self.output_dir, "checkpoint")
        self.failure_cases_dir = os.path.join(self.output_dir, "all_failed_cases")
        self.best_ranked_dir = os.path.join(self.output_dir, "best_ranked_failed_tests")

        self.evaluated_dir = self.failure_cases_dir
        self.scenario_plot_dir = self.failure_cases_dir

        self.pending_path = os.path.join(self.checkpoint_dir, "pending_candidate.json")
        self.results_jsonl_path = os.path.join(self.checkpoint_dir, "results.jsonl")
        self.history_jsonl_path = os.path.join(self.checkpoint_dir, "history.jsonl")
        self.confirmations_jsonl_path = os.path.join(self.checkpoint_dir, "confirmations.jsonl")
        self.tree_state_path = os.path.join(self.checkpoint_dir, "tree_state.json")
        self.system_errors_path = os.path.join(self.checkpoint_dir, "system_errors.csv")
        self.invalid_candidates_path = os.path.join(self.checkpoint_dir, "invalid_candidates.csv")
        self.run_state_path = os.path.join(self.output_dir, "run_state.json")

    def _ensure_output_dirs(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.failure_cases_dir, exist_ok=True)
        os.makedirs(self.best_ranked_dir, exist_ok=True)

    def _find_resume_dir(self, budget: Optional[int] = None) -> Optional[str]:
        if os.environ.get("TG_FORCE_NEW", "0") == "1":
            return None

        namespace = getattr(self, "RESULTS_NAMESPACE", "tg_mcts_elites")
        algorithm_id = getattr(self, "ALGORITHM_ID", "tg_mcts_elites")
        requested_seed = os.environ.get("TG_SEED", "").strip()
        strict_budget = os.environ.get("TG_RESUME_STRICT_BUDGET", "0") == "1"

        candidates = sorted(
            glob.glob(os.path.join("results", namespace, "*")),
            key=os.path.getmtime,
            reverse=True,
        )

        for folder in candidates:
            state_path = os.path.join(folder, "run_state.json")
            if not os.path.exists(state_path):
                continue
            try:
                with open(state_path, "r", encoding="utf-8") as stream:
                    state = json.load(stream)
                same_case = state.get("case_study_basename") == self._normalised_case_name()
                same_algorithm = state.get("algorithm_id", algorithm_id) == algorithm_id
                same_seed = (
                    not requested_seed
                    or int(state.get("seed", -1)) == int(requested_seed)
                )
                same_budget = (
                    not strict_budget
                    or budget is None
                    or int(state.get("budget", -1)) == int(budget)
                )
                incomplete = state.get("status") != "completed"
                if same_case and same_algorithm and same_seed and same_budget and incomplete:
                    return folder
            except (OSError, ValueError, TypeError):
                continue
        return None

    def _setup_run_directory(self, budget: int) -> None:
        resume_dir = self._find_resume_dir(budget)
        previous_state: Dict = {}
        self.mission_label = self._mission_label_from_case_name()

        if resume_dir is not None:
            self.output_dir = resume_dir
            self.run_id = os.path.basename(resume_dir)
            state_path = os.path.join(resume_dir, "run_state.json")
            try:
                with open(state_path, "r", encoding="utf-8") as stream:
                    previous_state = json.load(stream)
            except (OSError, ValueError, TypeError):
                previous_state = {}
            self.mission_label = previous_state.get("mission_label", self.mission_label)
            print(f"\n[resume] Resuming incomplete run: {self.output_dir}")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            self.run_id = f"{self.mission_label}_{timestamp}"
            self.output_dir = os.path.join("results", getattr(self, "RESULTS_NAMESPACE", "tg_mcts_elites"), self.run_id)

        self._configure_run_paths()
        self._ensure_output_dirs()

        self.simulation_attempts = int(
            previous_state.get(
                "simulation_attempts",
                previous_state.get("successful_simulations", 0),
            )
        )
        if "seed" in previous_state:
            self.seed = int(previous_state["seed"])
            random.seed(self.seed)

        previous_budget = previous_state.get("budget")
        if previous_budget is not None and int(previous_budget) != budget:
            print(
                f"[resume] Requested budget changed from {previous_budget} to {budget}. "
                "The new value is interpreted as the total attempt limit."
            )

        self._write_run_state(status="running", budget=budget)

    def _atomic_write_json(self, path: str | Path, payload: Any) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)

    def _write_run_state(self, status: str, budget: int) -> None:
        state = {
            "status": status,
            "algorithm_id": getattr(self, "ALGORITHM_ID", "tg_mcts_elites"),
            "algorithm_name": getattr(self, "ALGORITHM_NAME", "TG-MCTS-Elites"),
            "results_namespace": getattr(self, "RESULTS_NAMESPACE", "tg_mcts_elites"),
            "case_study_file": self.case_study_file,
            "case_study_basename": self._normalised_case_name(),
            "mission_label": getattr(self, "mission_label", self._mission_label_from_case_name()),
            "budget": budget,
            "simulation_attempts": self.simulation_attempts,
            "successful_evaluations": len(self.results),
            "official_failures": sum(result.point > 0 for result in self.results),
            "confirmation_observations": sum(result.confirmation_attempts for result in self.results),
            "seed": self.seed,
            "run_id": self.run_id,
            "output_dir": self.output_dir,
            "mission_plan_path": getattr(self, "mission_plan_path", ""),
            "mission_path_source": getattr(self, "mission_path_source", ""),
            "final_min_scenario_distance": self.FINAL_MIN_SCENARIO_DISTANCE,
            "final_min_trajectory_dtw": self.FINAL_MIN_TRAJECTORY_DTW,
            "updated_at": datetime.now().isoformat(),
        }
        self._atomic_write_json(self.run_state_path, state)

    def _consume_simulation_attempt(self, budget: int) -> int:
        if self.simulation_attempts >= budget:
            raise SimulationBudgetExhausted(
                f"Simulation budget exhausted: {self.simulation_attempts}/{budget} attempts consumed."
            )
        self.simulation_attempts += 1
        self._write_run_state(status="running", budget=budget)
        return self.simulation_attempts

    def _append_jsonl(self, path: str, record: Dict) -> None:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _obstacle_to_dict(self, obstacle: Obstacle) -> Dict:
        return {
            "x": float(obstacle.position.x),
            "y": float(obstacle.position.y),
            "z": float(obstacle.position.z),
            "r": float(obstacle.position.r),
            "l": float(obstacle.size.l),
            "w": float(obstacle.size.w),
            "h": float(obstacle.size.h),
        }

    def _obstacle_from_dict(self, data: Dict) -> Obstacle:
        return Obstacle(
            Obstacle.Size(l=float(data["l"]), w=float(data["w"]), h=float(data["h"])),
            Obstacle.Position(
                x=float(data["x"]),
                y=float(data["y"]),
                z=0.0,
                r=float(data.get("r", 0.0)),
            ),
        )

    def _random_state_to_json(self, value: Any) -> Any:
        if isinstance(value, tuple):
            return [self._random_state_to_json(item) for item in value]
        if isinstance(value, list):
            return [self._random_state_to_json(item) for item in value]
        return value

    def _random_state_from_json(self, value: Any) -> Any:
        if isinstance(value, list):
            return tuple(self._random_state_from_json(item) for item in value)
        return value

    def _tree_nodes(self, root: MCTSNode) -> List[MCTSNode]:
        nodes: List[MCTSNode] = []
        stack = [root]
        seen = set()
        while stack:
            node = stack.pop()
            if node.node_id in seen:
                continue
            seen.add(node.node_id)
            nodes.append(node)
            stack.extend(reversed(node.children))
        return nodes

    def _save_tree_checkpoint(self, root: MCTSNode) -> None:
        records = []
        for node in self._tree_nodes(root):
            records.append(
                {
                    "node_id": node.node_id,
                    "parent_id": node.parent.node_id if node.parent is not None else None,
                    "action": node.action,
                    "obstacles": [self._obstacle_to_dict(obs) for obs in node.obstacles],
                    "visits": node.visits,
                    "total_reward": node.total_reward,
                    "best_reward": node.best_reward,
                    "eval_simulation_attempt": (
                        node.eval_result.simulation_attempt
                        if node.eval_result is not None
                        else None
                    ),
                }
            )
        payload = {
            "algorithm_id": getattr(self, "ALGORITHM_ID", "tg_mcts_elites"),
            "case_study_basename": self._normalised_case_name(),
            "seed": self.seed,
            "root_node_id": root.node_id,
            "random_state": self._random_state_to_json(random.getstate()),
            "nodes": records,
            "saved_at": datetime.now().isoformat(),
        }
        self._atomic_write_json(self.tree_state_path, payload)

    def _load_tree_checkpoint(self) -> Optional[MCTSNode]:
        path = Path(self.tree_state_path)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("case_study_basename") != self._normalised_case_name():
                return None
            if payload.get("algorithm_id") != getattr(self, "ALGORITHM_ID", "tg_mcts_elites"):
                return None
            if int(payload.get("seed", self.seed)) != int(self.seed):
                return None
            records = payload.get("nodes", [])
            if not isinstance(records, list) or not records:
                return None

            results_by_attempt = {
                int(result.simulation_attempt): result
                for result in self.results
                if int(result.simulation_attempt) > 0
            }
            nodes: Dict[int, MCTSNode] = {}
            parent_ids: Dict[int, Optional[int]] = {}
            for record in records:
                node_id = int(record["node_id"])
                obstacles = [
                    self._obstacle_from_dict(item)
                    for item in record.get("obstacles", [])
                ]
                node = MCTSNode(
                    obstacles=obstacles,
                    action=str(record.get("action", "restored")),
                    node_id=node_id,
                    visits=int(record.get("visits", 0)),
                    total_reward=float(record.get("total_reward", 0.0)),
                    best_reward=float(record.get("best_reward", -1e18)),
                )
                attempt = record.get("eval_simulation_attempt")
                if attempt is not None:
                    node.eval_result = results_by_attempt.get(int(attempt))
                nodes[node_id] = node
                parent_raw = record.get("parent_id")
                parent_ids[node_id] = int(parent_raw) if parent_raw is not None else None

            root_id = int(payload.get("root_node_id", min(nodes)))
            root = nodes.get(root_id)
            if root is None:
                return None
            for node_id, node in nodes.items():
                parent_id = parent_ids[node_id]
                if parent_id is None or node_id == root_id:
                    continue
                parent = nodes.get(parent_id, root)
                node.parent = parent
                parent.children.append(node)

            for node in nodes.values():
                if node.obstacles:
                    self.tree_signatures.add(self._scenario_signature(node.obstacles))
            self._node_counter = max(self._node_counter, max(nodes) + 1)
            saved_random_state = payload.get("random_state")
            if saved_random_state is not None:
                random.setstate(self._random_state_from_json(saved_random_state))
            print(f"[resume] Restored search tree with {len(nodes)} node(s).")
            return root
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(f"[resume] Could not restore tree checkpoint: {error}")
            return None

    def _rebuild_tree_from_history(self) -> Optional[MCTSNode]:
        if not self.history:
            return None
        root = MCTSNode(obstacles=[], action="root", node_id=0)
        nodes: Dict[int, MCTSNode] = {root.node_id: root}
        results_by_attempt = {
            int(result.simulation_attempt): result
            for result in self.results
            if int(result.simulation_attempt) > 0
        }
        pending_links = []
        for row in sorted(
            self.history,
            key=lambda item: int(item.get("simulation_attempt", 0) or 0),
        ):
            action = str(row.get("action", "restored"))
            if action.startswith("confirm_attempt_"):
                continue
            try:
                node_id = int(row["node_id"])
                attempt = int(row.get("simulation_attempt", 0))
            except (KeyError, TypeError, ValueError):
                continue
            result = results_by_attempt.get(attempt)
            obstacles = self._clone_obstacles(result.obstacles) if result is not None else []
            node = nodes.get(node_id)
            if node is None:
                node = MCTSNode(obstacles=obstacles, action=action, node_id=node_id)
                nodes[node_id] = node
            node.eval_result = result
            parent_raw = row.get("parent_id")
            try:
                parent_id = int(parent_raw) if parent_raw not in (None, "", "None") else root.node_id
            except (TypeError, ValueError):
                parent_id = root.node_id
            pending_links.append((node_id, parent_id))

        for node_id, parent_id in pending_links:
            node = nodes[node_id]
            parent = nodes.get(parent_id, root)
            if node is root or node.parent is not None:
                continue
            node.parent = parent
            parent.children.append(node)

        for node in nodes.values():
            if node.eval_result is None:
                continue
            current: Optional[MCTSNode] = node
            while current is not None:
                current.visits += 1
                current.total_reward += node.eval_result.reward
                current.best_reward = max(current.best_reward, node.eval_result.reward)
                current = current.parent
            if node.obstacles:
                self.tree_signatures.add(self._scenario_signature(node.obstacles))

        self._node_counter = max(self._node_counter, max(nodes) + 1)
        print(f"[resume] Rebuilt fallback search tree from {len(nodes) - 1} history row(s).")
        return root

    def _find_tree_node(self, root: MCTSNode, node_id: int) -> Optional[MCTSNode]:
        for node in self._tree_nodes(root):
            if node.node_id == node_id:
                return node
        return None

    def _write_pending_candidate(
        self,
        node: MCTSNode,
        simulation_index: int,
        budget: int,
        attempt: int,
    ) -> None:
        record = {
            "case_study_file": self.case_study_file,
            "case_study_basename": self._normalised_case_name(),
            "simulation_index": simulation_index,
            "budget": budget,
            "candidate_retry": attempt,
            "node_id": node.node_id,
            "parent_id": node.parent.node_id if node.parent is not None else None,
            "action": node.action,
            "obstacles": [self._obstacle_to_dict(obs) for obs in node.obstacles],
            "random_state": self._random_state_to_json(random.getstate()),
            "created_at": datetime.now().isoformat(),
        }
        with open(self.pending_path, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())

    def _clear_pending_candidate(self) -> None:
        if os.path.exists(self.pending_path):
            os.remove(self.pending_path)

    def _load_pending_candidate_as_node(self, root: MCTSNode) -> Optional[MCTSNode]:
        if not os.path.exists(self.pending_path):
            return None
        try:
            with open(self.pending_path, "r", encoding="utf-8") as stream:
                record = json.load(stream)
            if record.get("case_study_basename") != self._normalised_case_name():
                return None

            obstacles = [self._obstacle_from_dict(item) for item in record["obstacles"]]
            valid, reasons = self._validate_test_case_rules(obstacles)
            if not valid:
                print("[resume] Pending candidate is no longer valid. Ignoring it.")
                print("[resume] Reasons:", reasons)
                self._clear_pending_candidate()
                return None

            node_id = int(record.get("node_id", self._next_node_id()))
            self._node_counter = max(self._node_counter, node_id + 1)
            parent_id = record.get("parent_id")
            try:
                parent = self._find_tree_node(root, int(parent_id)) if parent_id is not None else root
            except (TypeError, ValueError):
                parent = root
            if parent is None:
                parent = root
            node = MCTSNode(
                obstacles=obstacles,
                parent=parent,
                action="resume_pending_" + str(record.get("action", "unknown")),
                node_id=node_id,
            )
            parent.children.append(node)
            self.tree_signatures.add(self._scenario_signature(obstacles))
            saved_random_state = record.get("random_state")
            if saved_random_state is not None:
                random.setstate(self._random_state_from_json(saved_random_state))
            print(f"[resume] Pending candidate will be recomputed if budget remains: node {node.node_id}")
            return node
        except Exception as error:
            print("[resume] Could not load pending candidate.")
            print(error)
            return None

    def _cleanup_aerialist_runtime_files(self, log_file: str, *, remove_log: bool) -> None:
        if not log_file:
            return
        log_path = Path(log_file)
        runtime_dir = log_path.parent
        if remove_log and log_path.is_file():
            try:
                log_path.unlink()
            except OSError:
                pass
        if runtime_dir.is_dir():
            for pattern in ("*.yaml", "*.yml"):
                for runtime_yaml in runtime_dir.glob(pattern):
                    try:
                        runtime_yaml.unlink()
                    except OSError:
                        pass
            try:
                runtime_dir.rmdir()
            except OSError:
                pass

    def _move_log_to_failure_case(self, source: str, destination: Path) -> str:
        if not source or not os.path.exists(source):
            return ""
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_path = Path(source).resolve()
        destination = destination.resolve()
        if source_path == destination:
            return str(destination)
        if destination.exists():
            destination.unlink()
        shutil.move(str(source_path), str(destination))
        self._cleanup_aerialist_runtime_files(str(source_path), remove_log=False)
        return str(destination)

    def _delete_unselected_log(self, log_file: str) -> None:
        self._cleanup_aerialist_runtime_files(log_file, remove_log=True)

    def _save_result_checkpoint(self, result: EvalResult, simulation_index: int, node: MCTSNode) -> EvalResult:
        save_artifacts = self._should_save_failure_artifacts(result)
        artifact_error = ""

        yaml_path = ""
        log_path = ""
        overview_plot_path = ""
        xy_time_plot_path = ""

        if save_artifacts:
            problem_type = self._problem_label(result.min_distance)
            case_dir = Path(self.failure_cases_dir) / (
                f"failure_attempt_{simulation_index:03d}_node_{node.node_id:03d}_{problem_type}"
            )
            case_dir.mkdir(parents=True, exist_ok=True)
            try:
                yaml_path = str((case_dir / "test.yaml").resolve())
                result.test.save_yaml(yaml_path)

                source_log = getattr(result.test, "log_file", "")
                log_path = self._move_log_to_failure_case(source_log, case_dir / "flight.ulg")

                overview_plot_path = self._save_scenario_plot(
                    test=result.test,
                    obstacles=result.obstacles,
                    index=simulation_index,
                    min_distance=result.min_distance,
                    point=result.point,
                    node_id=node.node_id,
                    mission_status=result.mission_status,
                    output_dir=str(case_dir),
                )
                xy_time_plot_path = self._save_xy_time_plot(
                    test=result.test,
                    obstacles=result.obstacles,
                    index=simulation_index,
                    node_id=node.node_id,
                    output_dir=str(case_dir),
                )

                result.test.log_file = log_path
                result.test.plot_file = overview_plot_path
                result.test.xy_time_plot_file = xy_time_plot_path
                result.artifacts_saved = all(
                    bool(path)
                    for path in (yaml_path, log_path, overview_plot_path, xy_time_plot_path)
                )
            except Exception as error:
                artifact_error = f"{type(error).__name__}: {error}"
                print(f"[artifact-error] Failure metadata kept, but artifacts were incomplete: {artifact_error}")
                result.artifacts_saved = False
        else:
            self._delete_unselected_log(getattr(result.test, "log_file", ""))
            result.test.log_file = ""
            result.test.plot_file = ""
            result.test.xy_time_plot_file = ""
            result.artifacts_saved = False

        result.yaml_file = yaml_path
        result.log_file = log_path
        result.scenario_plot = overview_plot_path
        result.xy_time_plot = xy_time_plot_path
        result.simulation_attempt = simulation_index

        record = {
            "simulation_attempt": simulation_index,
            "node_id": node.node_id,
            "parent_id": node.parent.node_id if node.parent is not None else None,
            "action": node.action,
            "obstacles": [self._obstacle_to_dict(obs) for obs in result.obstacles],
            "min_distance": result.min_distance,
            "problem_type": self._problem_label(result.min_distance),
            "point": result.point,
            "reward": result.reward,
            "elapsed_minutes": result.elapsed_minutes,
            "cell": list(result.cell),
            "signature": [list(item) for item in result.signature],
            "trajectory_xy": [list(point) for point in result.trajectory_xy],
            "point_samples": list(result.point_samples or [result.point]),
            "distance_samples": list(result.distance_samples or [result.min_distance]),
            "elapsed_samples": list(result.elapsed_samples or [result.elapsed_minutes]),
            "artifacts_saved": result.artifacts_saved,
            "scenario_plot": overview_plot_path or None,
            "xy_time_plot": xy_time_plot_path or None,
            "yaml_file": yaml_path or None,
            "log_file": log_path or None,
            "artifact_error": artifact_error or None,
            "mission_status": result.mission_status,
            "failure_evidence": result.failure_evidence,
            "compliance_status": result.compliance_status,
            "saved_at": datetime.now().isoformat(),
        }
        self._append_jsonl(self.results_jsonl_path, record)
        return result

    def _save_confirmation_failure_artifacts(
        self,
        result: EvalResult,
        simulation_index: int,
        node: MCTSNode,
        base_simulation_attempt: int,
    ) -> EvalResult:
        """Retain heavy artifacts for a reproduced official failure.

        Confirmation executions consume the global simulator budget but are not
        inserted as new MCTS search results.  Their heavy artifacts are kept only
        when the confirmation itself is a compliant official failure.
        """
        result.simulation_attempt = simulation_index

        if not self._should_save_failure_artifacts(result):
            self._delete_unselected_log(getattr(result.test, "log_file", ""))
            result.test.log_file = ""
            result.test.plot_file = ""
            result.test.xy_time_plot_file = ""
            result.yaml_file = ""
            result.log_file = ""
            result.scenario_plot = ""
            result.xy_time_plot = ""
            result.artifacts_saved = False
            return result

        problem_type = self._problem_label(result.min_distance)
        case_dir = Path(self.failure_cases_dir) / (
            f"failure_attempt_{simulation_index:03d}_node_{node.node_id:03d}_"
            f"confirmation_of_{base_simulation_attempt:03d}_{problem_type}"
        )
        case_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = ""
        log_path = ""
        overview_path = ""
        xy_time_path = ""

        try:
            yaml_path = str((case_dir / "test.yaml").resolve())
            result.test.save_yaml(yaml_path)

            source_log = getattr(result.test, "log_file", "")
            log_path = self._move_log_to_failure_case(
                source_log,
                case_dir / "flight.ulg",
            )

            overview_path = self._save_scenario_plot(
                test=result.test,
                obstacles=result.obstacles,
                index=simulation_index,
                min_distance=result.min_distance,
                point=result.point,
                node_id=node.node_id,
                mission_status=result.mission_status,
                output_dir=str(case_dir),
            )
            xy_time_path = self._save_xy_time_plot(
                test=result.test,
                obstacles=result.obstacles,
                index=simulation_index,
                node_id=node.node_id,
                output_dir=str(case_dir),
            )

            result.test.log_file = log_path
            result.test.plot_file = overview_path
            result.test.xy_time_plot_file = xy_time_path
            result.yaml_file = yaml_path
            result.log_file = log_path
            result.scenario_plot = overview_path
            result.xy_time_plot = xy_time_path
            result.artifacts_saved = all(
                bool(path)
                for path in (yaml_path, log_path, overview_path, xy_time_path)
            )
        except Exception as error:
            result.yaml_file = yaml_path
            result.log_file = log_path
            result.scenario_plot = overview_path
            result.xy_time_plot = xy_time_path
            result.artifacts_saved = False
            print(
                "[artifact-error] Confirmation failure metadata kept, but "
                f"artifacts were incomplete: {type(error).__name__}: {error}"
            )

        return result

    def _record_confirmation(
        self,
        base: EvalResult,
        observed: Optional[EvalResult],
        simulation_attempt: int,
        retry: int,
        outcome: str,
        error: str = "",
    ) -> None:
        record = {
            "simulation_attempt": simulation_attempt,
            "base_simulation_attempt": base.simulation_attempt,
            "base_signature": [list(item) for item in base.signature],
            "retry": retry,
            "outcome": outcome,
            "point": observed.point if observed is not None else 0,
            "min_distance": observed.min_distance if observed is not None else None,
            "elapsed_minutes": observed.elapsed_minutes if observed is not None else None,
            "mission_status": observed.mission_status if observed is not None else "noncompliant",
            "failure_evidence": observed.failure_evidence if observed is not None else "none",
            "error": error or None,
            "saved_at": datetime.now().isoformat(),
        }
        self._append_jsonl(self.confirmations_jsonl_path, record)

    def _load_previous_confirmations(self) -> None:
        if not os.path.exists(self.confirmations_jsonl_path):
            return

        by_signature = {result.signature: result for result in self.results}
        loaded = 0
        with open(self.confirmations_jsonl_path, "r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    signature = tuple(tuple(item) for item in record["base_signature"])
                    result = by_signature.get(signature)
                    if result is None:
                        continue
                    result.point_samples.append(int(record.get("point", 0)))
                    min_distance = record.get("min_distance")
                    elapsed = record.get("elapsed_minutes")
                    if min_distance is not None:
                        result.distance_samples.append(float(min_distance))
                    if elapsed is not None:
                        result.elapsed_samples.append(float(elapsed))
                    result.confirmation_attempts += 1
                    result.test.mean_official_point = self._mean_official_point(result)
                    result.test.failure_reproducibility = self._failure_reproducibility(result)
                    result.test.confirmation_samples = len(self._result_point_samples(result))
                    result.test.mean_min_distance = self._mean_min_distance(result)
                    loaded += 1
                except Exception:
                    continue
        if loaded:
            print(f"[resume] Loaded {loaded} confirmation observations.")

    def _load_previous_results(self) -> None:
        if not os.path.exists(self.results_jsonl_path):
            return

        loaded = 0
        with open(self.results_jsonl_path, "r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    yaml_file = record.get("yaml_file") or ""
                    log_file = record.get("log_file") or ""
                    plot_file = record.get("scenario_plot") or ""
                    xy_time_plot = record.get("xy_time_plot") or ""
                    artifacts_saved = bool(
                        record.get(
                            "artifacts_saved",
                            bool(yaml_file and log_file and plot_file and xy_time_plot),
                        )
                    )

                    if artifacts_saved and not all(
                        path and os.path.exists(path)
                        for path in (yaml_file, log_file, plot_file, xy_time_plot)
                    ):
                        artifacts_saved = False

                    obstacles = [self._obstacle_from_dict(item) for item in record["obstacles"]]
                    cell = tuple(record["cell"])
                    signature = tuple(tuple(item) for item in record["signature"])
                    trajectory_xy = [
                        (float(point[0]), float(point[1]))
                        for point in record.get("trajectory_xy", [])
                        if isinstance(point, (list, tuple)) and len(point) >= 2
                    ]
                    point_samples = [int(value) for value in record.get("point_samples", [record["point"]])]
                    distance_samples = [float(value) for value in record.get("distance_samples", [record["min_distance"]])]
                    elapsed_samples = [float(value) for value in record.get("elapsed_samples", [record["elapsed_minutes"]])]
                    test = SavedEvaluatedTestCase(
                        yaml_file=yaml_file,
                        log_file=log_file,
                        plot_file=plot_file,
                        xy_time_plot_file=xy_time_plot,
                        failure_evidence=record.get("failure_evidence", "none"),
                        minimum_distance=float(record["min_distance"]),
                        official_point=int(record["point"]),
                        reward=float(record["reward"]),
                        elapsed_minutes=float(record["elapsed_minutes"]),
                        elite_cell=cell,
                        problem_type=record.get("problem_type", self._problem_label(float(record["min_distance"]))),
                        mission_status=record.get("mission_status", "unknown"),
                        compliance_status=record.get("compliance_status", "unknown"),
                        trajectory_xy=trajectory_xy,
                    )
                    result = EvalResult(
                        obstacles=obstacles,
                        test=test,
                        min_distance=float(record["min_distance"]),
                        elapsed_minutes=float(record["elapsed_minutes"]),
                        point=int(record["point"]),
                        reward=float(record["reward"]),
                        cell=cell,
                        signature=signature,
                        scenario_plot=plot_file,
                        xy_time_plot=xy_time_plot,
                        yaml_file=yaml_file,
                        log_file=log_file,
                        mission_status=record.get("mission_status", "unknown"),
                        compliance_status=record.get("compliance_status", "unknown"),
                        artifacts_saved=artifacts_saved,
                        simulation_attempt=int(record.get("simulation_attempt", record.get("simulation", 0))),
                        trajectory_xy=trajectory_xy,
                        point_samples=point_samples,
                        distance_samples=distance_samples,
                        elapsed_samples=elapsed_samples,
                        confirmation_attempts=0,
                        failure_evidence=record.get("failure_evidence", "none"),
                    )
                    test.mean_official_point = self._mean_official_point(result)
                    test.failure_reproducibility = self._failure_reproducibility(result)
                    test.confirmation_samples = len(self._result_point_samples(result))
                    test.mean_min_distance = self._mean_min_distance(result)
                    test.simulation_attempt = result.simulation_attempt
                    self.results.append(result)
                    self.seen_signatures.add(signature)
                    self._update_elites(result)
                    loaded += 1
                except Exception:
                    continue

        if loaded:
            print(f"[resume] Loaded {loaded} previous evaluated simulations.")

    def _load_previous_history(self) -> None:
        if not os.path.exists(self.history_jsonl_path):
            return
        with open(self.history_jsonl_path, "r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    self.history.append(json.loads(line))
                except Exception:
                    pass

    def _log_system_error(self, node: MCTSNode, simulation_index: int, attempt: int, error: Exception) -> None:
        exists = os.path.exists(self.system_errors_path)
        with open(self.system_errors_path, "a", newline="", encoding="utf-8") as stream:
            fieldnames = [
                "time",
                "simulation_attempt",
                "candidate_retry",
                "node_id",
                "action",
                "error_type",
                "error_message",
                "obstacles",
            ]
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": datetime.now().isoformat(),
                    "simulation_attempt": simulation_index,
                    "candidate_retry": attempt,
                    "node_id": node.node_id,
                    "action": node.action,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "obstacles": json.dumps([self._obstacle_to_dict(obs) for obs in node.obstacles]),
                }
            )

    def _log_invalid_candidate(self, node: MCTSNode, simulation_index: int, reason: str) -> None:
        exists = os.path.exists(self.invalid_candidates_path)
        with open(self.invalid_candidates_path, "a", newline="", encoding="utf-8") as stream:
            fieldnames = [
                "time",
                "next_simulation_attempt",
                "node_id",
                "action",
                "reason",
                "obstacles",
            ]
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": datetime.now().isoformat(),
                    "next_simulation_attempt": simulation_index,
                    "node_id": node.node_id,
                    "action": node.action,
                    "reason": reason,
                    "obstacles": json.dumps([self._obstacle_to_dict(obs) for obs in node.obstacles]),
                }
            )
