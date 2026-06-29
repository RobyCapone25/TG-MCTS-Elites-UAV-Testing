import csv
import glob
import json
import math
import os
import random
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

from aerialist.px4.aerialist_test import AerialistTest
from aerialist.px4.obstacle import Obstacle

from testcase import TestCase


class NonCompliantCandidateError(Exception):
    pass


class SavedEvaluatedTestCase:
    def __init__(
        self,
        yaml_file: str,
        log_file: str,
        plot_file: str,
        minimum_distance: float,
        official_point: int,
        reward: float,
        elapsed_minutes: float,
        elite_cell: Tuple,
        problem_type: str,
        mission_status: str,
        compliance_status: str,
    ) -> None:
        self.yaml_file = yaml_file
        self.log_file = log_file
        self.plot_file = plot_file
        self.minimum_distance = minimum_distance
        self.official_point = official_point
        self.reward = reward
        self.elapsed_minutes = elapsed_minutes
        self.elite_cell = elite_cell
        self.problem_type = problem_type
        self.mission_status = mission_status
        self.compliance_status = compliance_status

    def save_yaml(self, path: str) -> None:
        shutil.copyfile(self.yaml_file, path)


@dataclass
class EvalResult:
    obstacles: List[Obstacle]
    test: Any
    min_distance: float
    elapsed_minutes: float
    point: int
    reward: float
    cell: Tuple
    signature: Tuple
    scenario_plot: str
    yaml_file: str = ""
    log_file: str = ""
    mission_status: str = "unknown"
    compliance_status: str = "unknown"


@dataclass
class MCTSNode:
    obstacles: List[Obstacle]
    parent: Optional["MCTSNode"] = None
    action: str = "root"
    node_id: int = -1
    children: List["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0
    best_reward: float = -1e18
    eval_result: Optional[EvalResult] = None

    def mean_reward(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.total_reward / self.visits


class RandomGenerator(object):
    """
    Rule-compliant Robust TG-MCTS-Elites generator.

    Implements:
    - only obstacle manipulation;
    - max 3 obstacles;
    - x in [-40, 30], y in [10, 40];
    - z = 0;
    - l,w in [2,20];
    - 10 < h <= 25;
    - r in [0,90];
    - rotated obstacle fitting;
    - rotated overlap checking;
    - physical-feasibility grid check;
    - simulator/system retry;
    - PC crash resume with pending_candidate.json;
    - MAP-Elites diversity;
    - MCTS tree search;
    - trajectory/obstacle plots;
    - no per-run UML generation.
    """

    X_MIN = -40.0
    X_MAX = 30.0
    Y_MIN = 10.0
    Y_MAX = 40.0

    MIN_L = 2.0
    MAX_L = 20.0
    MIN_W = 2.0
    MAX_W = 20.0
    MIN_H = 10.1
    MAX_H = 25.0

    MIN_R = 0.0
    MAX_R = 90.0

    MAX_OBSTACLES = 3
    RETURN_LIMIT = 20

    OVERLAP_MARGIN = 0.10
    FEASIBILITY_GRID_STEP = 1.0
    MISSION_COMPLETION_RADIUS = 10.0

    HARD_FAIL_THRESHOLD = 0.25
    FAILURE_THRESHOLD = 1.5
    NEAR_MISS_THRESHOLD = 3.0

    UCB_C = 1.4
    PW_C = 2.0
    PW_ALPHA = 0.55

    MAX_SYSTEM_RETRIES = 2

    def __init__(self, case_study_file: str) -> None:
        self.case_study_file = case_study_file
        self.case_study = AerialistTest.from_yaml(case_study_file)

        self.results: List[EvalResult] = []
        self.elites: Dict[Tuple, EvalResult] = {}
        self.seen_signatures = set()
        self.tree_signatures = set()

        self.history = []
        self._node_counter = 0
        self.seed = self._initialise_seed()

        self.run_id = datetime.now().strftime("%d-%m-%H-%M-%S")
        self.output_dir = os.path.join("results", "tg_mcts_elites", self.run_id)
        self.checkpoint_dir = os.path.join(self.output_dir, "checkpoint")
        self.evaluated_dir = os.path.join(self.output_dir, "evaluated_tests")
        self.scenario_plot_dir = os.path.join(self.output_dir, "scenario_plots")

        self.pending_path = os.path.join(self.checkpoint_dir, "pending_candidate.json")
        self.results_jsonl_path = os.path.join(self.checkpoint_dir, "results.jsonl")
        self.history_jsonl_path = os.path.join(self.checkpoint_dir, "history.jsonl")
        self.system_errors_path = os.path.join(self.checkpoint_dir, "system_errors.csv")
        self.invalid_candidates_path = os.path.join(self.checkpoint_dir, "invalid_candidates.csv")
        self.run_state_path = os.path.join(self.output_dir, "run_state.json")

    # ==============================================================
    # Setup
    # ==============================================================

    def _initialise_seed(self) -> int:
        env_seed = os.environ.get("TG_SEED", "").strip()
        if env_seed:
            seed = int(env_seed)
        else:
            seed = random.randint(0, 2**31 - 1)
        random.seed(seed)
        return seed

    def _next_node_id(self) -> int:
        node_id = self._node_counter
        self._node_counter += 1
        return node_id

    def _ensure_output_dirs(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.makedirs(self.evaluated_dir, exist_ok=True)
        os.makedirs(self.scenario_plot_dir, exist_ok=True)

    def _normalised_case_name(self) -> str:
        return os.path.basename(self.case_study_file)

    def _find_resume_dir(self) -> Optional[str]:
        if os.environ.get("TG_FORCE_NEW", "0") == "1":
            return None

        candidates = sorted(
            glob.glob(os.path.join("results", "tg_mcts_elites", "*")),
            key=os.path.getmtime,
            reverse=True,
        )

        for folder in candidates:
            state_path = os.path.join(folder, "run_state.json")
            if not os.path.exists(state_path):
                continue

            try:
                with open(state_path, "r") as f:
                    state = json.load(f)

                same_case = state.get("case_study_basename") == self._normalised_case_name()
                incomplete = state.get("status") != "completed"

                if same_case and incomplete:
                    return folder
            except Exception:
                continue

        return None

    def _setup_run_directory(self, budget: int) -> None:
        resume_dir = self._find_resume_dir()

        if resume_dir is not None:
            self.output_dir = resume_dir
            self.run_id = os.path.basename(resume_dir)
            print(f"\n[resume] Resuming incomplete run: {self.output_dir}")
        else:
            self.run_id = datetime.now().strftime("%d-%m-%H-%M-%S")
            self.output_dir = os.path.join("results", "tg_mcts_elites", self.run_id)

        self.checkpoint_dir = os.path.join(self.output_dir, "checkpoint")
        self.evaluated_dir = os.path.join(self.output_dir, "evaluated_tests")
        self.scenario_plot_dir = os.path.join(self.output_dir, "scenario_plots")

        self.pending_path = os.path.join(self.checkpoint_dir, "pending_candidate.json")
        self.results_jsonl_path = os.path.join(self.checkpoint_dir, "results.jsonl")
        self.history_jsonl_path = os.path.join(self.checkpoint_dir, "history.jsonl")
        self.system_errors_path = os.path.join(self.checkpoint_dir, "system_errors.csv")
        self.invalid_candidates_path = os.path.join(self.checkpoint_dir, "invalid_candidates.csv")
        self.run_state_path = os.path.join(self.output_dir, "run_state.json")

        self._ensure_output_dirs()
        self._write_run_state(status="running", budget=budget)

    def _write_run_state(self, status: str, budget: int) -> None:
        state = {
            "status": status,
            "case_study_file": self.case_study_file,
            "case_study_basename": self._normalised_case_name(),
            "budget": budget,
            "successful_simulations": len(self.results),
            "seed": self.seed,
            "run_id": self.run_id,
            "output_dir": self.output_dir,
            "updated_at": datetime.now().isoformat(),
        }

        with open(self.run_state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _append_jsonl(self, path: str, record: Dict) -> None:
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())

    # ==============================================================
    # Serialization and checkpoints
    # ==============================================================

    def _obstacle_to_dict(self, obs: Obstacle) -> Dict:
        return {
            "x": float(obs.position.x),
            "y": float(obs.position.y),
            "z": float(obs.position.z),
            "r": float(obs.position.r),
            "l": float(obs.size.l),
            "w": float(obs.size.w),
            "h": float(obs.size.h),
        }

    def _obstacle_from_dict(self, data: Dict) -> Obstacle:
        return Obstacle(
            Obstacle.Size(
                l=float(data["l"]),
                w=float(data["w"]),
                h=float(data["h"]),
            ),
            Obstacle.Position(
                x=float(data["x"]),
                y=float(data["y"]),
                z=0.0,
                r=float(data.get("r", 0.0)),
            ),
        )

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
            "attempt": attempt,
            "node_id": node.node_id,
            "parent_id": node.parent.node_id if node.parent is not None else None,
            "action": node.action,
            "obstacles": [self._obstacle_to_dict(obs) for obs in node.obstacles],
            "created_at": datetime.now().isoformat(),
        }

        with open(self.pending_path, "w") as f:
            json.dump(record, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    def _clear_pending_candidate(self) -> None:
        if os.path.exists(self.pending_path):
            os.remove(self.pending_path)

    def _load_pending_candidate_as_node(self, root: MCTSNode) -> Optional[MCTSNode]:
        if not os.path.exists(self.pending_path):
            return None

        try:
            with open(self.pending_path, "r") as f:
                record = json.load(f)

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

            node = MCTSNode(
                obstacles=obstacles,
                parent=root,
                action="resume_pending_" + str(record.get("action", "unknown")),
                node_id=node_id,
            )

            root.children.append(node)
            self.tree_signatures.add(self._scenario_signature(obstacles))

            print(f"[resume] Pending candidate found and will be recomputed first: node {node.node_id}")
            return node

        except Exception as e:
            print("[resume] Could not load pending candidate.")
            print(e)
            return None

    def _save_result_checkpoint(
        self,
        result: EvalResult,
        simulation_index: int,
        node: MCTSNode,
    ) -> EvalResult:
        yaml_path = os.path.join(
            self.evaluated_dir,
            f"eval_{simulation_index:03d}_node_{node.node_id:03d}.yaml",
        )

        result.test.save_yaml(yaml_path)

        log_file = getattr(result.test, "log_file", "")
        plot_file = getattr(result.test, "plot_file", result.scenario_plot)

        if log_file:
            log_file = os.path.abspath(log_file)

        plot_file = os.path.abspath(plot_file)
        yaml_path = os.path.abspath(yaml_path)

        result.yaml_file = yaml_path
        result.log_file = log_file

        record = {
            "simulation": simulation_index,
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
            "signature": [list(x) for x in result.signature],
            "scenario_plot": plot_file,
            "yaml_file": yaml_path,
            "log_file": log_file,
            "mission_status": result.mission_status,
            "compliance_status": result.compliance_status,
            "saved_at": datetime.now().isoformat(),
        }

        self._append_jsonl(self.results_jsonl_path, record)
        return result

    def _load_previous_results(self) -> None:
        if not os.path.exists(self.results_jsonl_path):
            return

        loaded = 0

        with open(self.results_jsonl_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                    yaml_file = record["yaml_file"]
                    log_file = record.get("log_file", "")
                    plot_file = record["scenario_plot"]

                    if not os.path.exists(yaml_file):
                        continue
                    if plot_file and not os.path.exists(plot_file):
                        continue
                    if log_file and not os.path.exists(log_file):
                        continue

                    obstacles = [self._obstacle_from_dict(item) for item in record["obstacles"]]
                    cell = tuple(record["cell"])
                    signature = tuple(tuple(x) for x in record["signature"])

                    test = SavedEvaluatedTestCase(
                        yaml_file=yaml_file,
                        log_file=log_file,
                        plot_file=plot_file,
                        minimum_distance=float(record["min_distance"]),
                        official_point=int(record["point"]),
                        reward=float(record["reward"]),
                        elapsed_minutes=float(record["elapsed_minutes"]),
                        elite_cell=cell,
                        problem_type=record["problem_type"],
                        mission_status=record.get("mission_status", "unknown"),
                        compliance_status=record.get("compliance_status", "unknown"),
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
                        yaml_file=yaml_file,
                        log_file=log_file,
                        mission_status=record.get("mission_status", "unknown"),
                        compliance_status=record.get("compliance_status", "unknown"),
                    )

                    self.results.append(result)
                    self.seen_signatures.add(signature)
                    self._update_elites(result)

                    loaded += 1

                except Exception:
                    continue

        if loaded > 0:
            print(f"[resume] Loaded {loaded} previous successful simulations.")

    def _load_previous_history(self) -> None:
        if not os.path.exists(self.history_jsonl_path):
            return

        with open(self.history_jsonl_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    self.history.append(json.loads(line))
                except Exception:
                    pass

    def _log_system_error(
        self,
        node: MCTSNode,
        simulation_index: int,
        attempt: int,
        error: Exception,
    ) -> None:
        exists = os.path.exists(self.system_errors_path)

        with open(self.system_errors_path, "a", newline="") as f:
            fieldnames = [
                "time",
                "simulation",
                "attempt",
                "node_id",
                "action",
                "error_type",
                "error_message",
                "obstacles",
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not exists:
                writer.writeheader()

            writer.writerow(
                {
                    "time": datetime.now().isoformat(),
                    "simulation": simulation_index,
                    "attempt": attempt,
                    "node_id": node.node_id,
                    "action": node.action,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "obstacles": json.dumps([self._obstacle_to_dict(obs) for obs in node.obstacles]),
                }
            )

    def _log_invalid_candidate(
        self,
        node: MCTSNode,
        simulation_index: int,
        reason: str,
    ) -> None:
        exists = os.path.exists(self.invalid_candidates_path)

        with open(self.invalid_candidates_path, "a", newline="") as f:
            fieldnames = [
                "time",
                "simulation",
                "node_id",
                "action",
                "reason",
                "obstacles",
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not exists:
                writer.writeheader()

            writer.writerow(
                {
                    "time": datetime.now().isoformat(),
                    "simulation": simulation_index,
                    "node_id": node.node_id,
                    "action": node.action,
                    "reason": reason,
                    "obstacles": json.dumps([self._obstacle_to_dict(obs) for obs in node.obstacles]),
                }
            )

    # ==============================================================
    # Rotated geometry
    # ==============================================================

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(value, high))

    def _deg_to_rad(self, angle_deg: float) -> float:
        return angle_deg * math.pi / 180.0

    def _rotated_half_extents(self, l: float, w: float, r: float) -> Tuple[float, float]:
        theta = self._deg_to_rad(r)
        c = abs(math.cos(theta))
        s = abs(math.sin(theta))
        hx = c * l / 2.0 + s * w / 2.0
        hy = s * l / 2.0 + c * w / 2.0
        return hx, hy

    def _rotated_corners(self, obs: Obstacle) -> List[Tuple[float, float]]:
        x = float(obs.position.x)
        y = float(obs.position.y)
        l = float(obs.size.l)
        w = float(obs.size.w)
        r = float(obs.position.r)

        theta = self._deg_to_rad(r)
        c = math.cos(theta)
        s = math.sin(theta)

        local = [
            (-l / 2.0, -w / 2.0),
            (l / 2.0, -w / 2.0),
            (l / 2.0, w / 2.0),
            (-l / 2.0, w / 2.0),
        ]

        corners = []
        for lx, ly in local:
            gx = x + c * lx - s * ly
            gy = y + s * lx + c * ly
            corners.append((gx, gy))

        return corners

    def _polygon_axes(self, corners: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        axes = []

        for i in range(len(corners)):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % len(corners)]

            edge_x = x2 - x1
            edge_y = y2 - y1

            axis_x = -edge_y
            axis_y = edge_x

            norm = math.sqrt(axis_x * axis_x + axis_y * axis_y)

            if norm > 1e-12:
                axes.append((axis_x / norm, axis_y / norm))

        return axes

    def _project_polygon(
        self,
        corners: List[Tuple[float, float]],
        axis: Tuple[float, float],
    ) -> Tuple[float, float]:
        ax, ay = axis
        values = [x * ax + y * ay for x, y in corners]
        return min(values), max(values)

    def _rotated_boxes_overlap(self, obs1: Obstacle, obs2: Obstacle) -> bool:
        c1 = self._rotated_corners(obs1)
        c2 = self._rotated_corners(obs2)

        axes = self._polygon_axes(c1) + self._polygon_axes(c2)

        for axis in axes:
            min1, max1 = self._project_polygon(c1, axis)
            min2, max2 = self._project_polygon(c2, axis)

            if max1 + self.OVERLAP_MARGIN < min2:
                return False

            if max2 + self.OVERLAP_MARGIN < min1:
                return False

        return True

    def _point_inside_rotated_obstacle(self, x: float, y: float, obs: Obstacle) -> bool:
        cx = float(obs.position.x)
        cy = float(obs.position.y)
        l = float(obs.size.l)
        w = float(obs.size.w)
        r = float(obs.position.r)

        theta = -self._deg_to_rad(r)
        c = math.cos(theta)
        s = math.sin(theta)

        dx = x - cx
        dy = y - cy

        local_x = c * dx - s * dy
        local_y = s * dx + c * dy

        return abs(local_x) <= l / 2.0 and abs(local_y) <= w / 2.0

    # ==============================================================
    # Mission reference
    # ==============================================================

    def _mission_corridors(self) -> List[float]:
        name = self.case_study_file.lower()

        if "mission1" in name:
            return [-4.0, 0.0, 4.0]

        if "mission2" in name:
            return [-15.0, -10.0, -5.0, 0.0, 5.0]

        if "mission3" in name:
            return [-25.0, -20.0, -15.0, -10.0, -5.0, 0.0]

        return [-25.0, -20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0]

    def _fallback_reference_path(self) -> List[Tuple[float, float]]:
        name = self.case_study_file.lower()

        if "mission1" in name:
            return [(0.0, 0.0), (0.0, 50.0)]

        if "mission2" in name:
            return [(0.0, 0.0), (0.0, 50.0), (-10.0, 0.0)]

        if "mission3" in name:
            return [(0.0, 0.0), (0.0, 50.0), (-20.0, 50.0), (-20.0, 0.0)]

        return [(0.0, 0.0), (0.0, 50.0)]

    # ==============================================================
    # Obstacle generation and validation
    # ==============================================================

    def _clone_obstacle(self, obs: Obstacle) -> Obstacle:
        return Obstacle(
            Obstacle.Size(
                l=float(obs.size.l),
                w=float(obs.size.w),
                h=float(obs.size.h),
            ),
            Obstacle.Position(
                x=float(obs.position.x),
                y=float(obs.position.y),
                z=0.0,
                r=float(obs.position.r),
            ),
        )

    def _clone_obstacles(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        return [self._clone_obstacle(obs) for obs in obstacles]

    def _make_obstacle(
        self,
        x: float,
        y: float,
        l: float,
        w: float,
        h: float,
        r: Optional[float] = None,
    ) -> Obstacle:
        l = self._clamp(l, self.MIN_L, self.MAX_L)
        w = self._clamp(w, self.MIN_W, self.MAX_W)
        h = self._clamp(h, self.MIN_H, self.MAX_H)

        if r is None:
            r = random.uniform(self.MIN_R, self.MAX_R)

        r = self._clamp(r, self.MIN_R, self.MAX_R)

        hx, hy = self._rotated_half_extents(l, w, r)

        x = self._clamp(x, self.X_MIN + hx, self.X_MAX - hx)
        y = self._clamp(y, self.Y_MIN + hy, self.Y_MAX - hy)

        return Obstacle(
            Obstacle.Size(l=l, w=w, h=h),
            Obstacle.Position(x=x, y=y, z=0.0, r=r),
        )

    def _is_inside_area(self, obs: Obstacle) -> bool:
        if abs(float(obs.position.z)) > 1e-9:
            return False

        if not (self.MIN_R <= float(obs.position.r) <= self.MAX_R):
            return False

        if not (self.MIN_L <= float(obs.size.l) <= self.MAX_L):
            return False

        if not (self.MIN_W <= float(obs.size.w) <= self.MAX_W):
            return False

        if not (10.0 < float(obs.size.h) <= self.MAX_H):
            return False

        for x, y in self._rotated_corners(obs):
            if x < self.X_MIN - 1e-9 or x > self.X_MAX + 1e-9:
                return False

            if y < self.Y_MIN - 1e-9 or y > self.Y_MAX + 1e-9:
                return False

        return True

    def _is_point_blocked(self, x: float, y: float, obstacles: List[Obstacle]) -> bool:
        for obs in obstacles:
            if self._point_inside_rotated_obstacle(x, y, obs):
                return True
        return False

    def _inside_valid_area_point(self, x: float, y: float) -> bool:
        return self.X_MIN <= x <= self.X_MAX and self.Y_MIN <= y <= self.Y_MAX

    def _grid_point(self, x: float, y: float) -> Tuple[int, int]:
        step = self.FEASIBILITY_GRID_STEP
        gx = int(round((x - self.X_MIN) / step))
        gy = int(round((y - self.Y_MIN) / step))
        return gx, gy

    def _world_point(self, gx: int, gy: int) -> Tuple[float, float]:
        step = self.FEASIBILITY_GRID_STEP
        x = self.X_MIN + gx * step
        y = self.Y_MIN + gy * step
        return x, y

    def _nearest_free_grid_point(
        self,
        x: float,
        y: float,
        obstacles: List[Obstacle],
    ) -> Optional[Tuple[int, int]]:
        start = self._grid_point(x, y)

        max_gx = int(round((self.X_MAX - self.X_MIN) / self.FEASIBILITY_GRID_STEP))
        max_gy = int(round((self.Y_MAX - self.Y_MIN) / self.FEASIBILITY_GRID_STEP))

        q = deque([start])
        seen = {start}

        while q:
            gx, gy = q.popleft()

            if 0 <= gx <= max_gx and 0 <= gy <= max_gy:
                wx, wy = self._world_point(gx, gy)

                if self._inside_valid_area_point(wx, wy) and not self._is_point_blocked(wx, wy, obstacles):
                    return gx, gy

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nxt = (gx + dx, gy + dy)

                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)

            if len(seen) > 500:
                break

        return None

    def _free_space_connected(
        self,
        start_world: Tuple[float, float],
        goal_world: Tuple[float, float],
        obstacles: List[Obstacle],
    ) -> bool:
        start = self._nearest_free_grid_point(start_world[0], start_world[1], obstacles)
        goal = self._nearest_free_grid_point(goal_world[0], goal_world[1], obstacles)

        if start is None or goal is None:
            return False

        max_gx = int(round((self.X_MAX - self.X_MIN) / self.FEASIBILITY_GRID_STEP))
        max_gy = int(round((self.Y_MAX - self.Y_MIN) / self.FEASIBILITY_GRID_STEP))

        q = deque([start])
        seen = {start}

        while q:
            gx, gy = q.popleft()

            if (gx, gy) == goal:
                return True

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx = gx + dx
                ny = gy + dy

                if not (0 <= nx <= max_gx and 0 <= ny <= max_gy):
                    continue

                if (nx, ny) in seen:
                    continue

                wx, wy = self._world_point(nx, ny)

                if self._is_point_blocked(wx, wy, obstacles):
                    continue

                seen.add((nx, ny))
                q.append((nx, ny))

        return False

    def _sample_segment_inside_area(
        self,
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        samples: int = 300,
    ) -> List[Tuple[float, float]]:
        x0, y0 = p0
        x1, y1 = p1
        inside = []

        for k in range(samples + 1):
            t = k / samples
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)

            if self._inside_valid_area_point(x, y):
                inside.append((x, y))

        return inside

    def _has_physical_feasible_corridor(self, obstacles: List[Obstacle]) -> bool:
        reference = self._fallback_reference_path()
        checked_any_segment = False

        for i in range(len(reference) - 1):
            inside_points = self._sample_segment_inside_area(reference[i], reference[i + 1])

            if len(inside_points) < 2:
                continue

            checked_any_segment = True
            start = inside_points[0]
            goal = inside_points[-1]

            if not self._free_space_connected(start, goal, obstacles):
                return False

        if not checked_any_segment:
            return True

        return True

    def _validate_test_case_rules(self, obstacles: List[Obstacle]) -> Tuple[bool, List[str]]:
        reasons = []

        if len(obstacles) == 0:
            reasons.append("no obstacles generated")

        if len(obstacles) > self.MAX_OBSTACLES:
            reasons.append("more than 3 obstacles")

        for i, obs in enumerate(obstacles):
            if not (self.X_MIN <= float(obs.position.x) <= self.X_MAX):
                reasons.append(f"obstacle {i + 1}: x center out of range")

            if not (self.Y_MIN <= float(obs.position.y) <= self.Y_MAX):
                reasons.append(f"obstacle {i + 1}: y center out of range")

            if abs(float(obs.position.z)) > 1e-9:
                reasons.append(f"obstacle {i + 1}: z is not zero")

            if not (self.MIN_R <= float(obs.position.r) <= self.MAX_R):
                reasons.append(f"obstacle {i + 1}: rotation r out of range")

            if not (self.MIN_L <= float(obs.size.l) <= self.MAX_L):
                reasons.append(f"obstacle {i + 1}: length l out of range")

            if not (self.MIN_W <= float(obs.size.w) <= self.MAX_W):
                reasons.append(f"obstacle {i + 1}: width w out of range")

            if not (10.0 < float(obs.size.h) <= self.MAX_H):
                reasons.append(f"obstacle {i + 1}: height h must satisfy 10 < h <= 25")

            if not self._is_inside_area(obs):
                reasons.append(f"obstacle {i + 1}: rotated box does not fit inside valid area")

        for i in range(len(obstacles)):
            for j in range(i + 1, len(obstacles)):
                if self._rotated_boxes_overlap(obstacles[i], obstacles[j]):
                    reasons.append(f"obstacles {i + 1} and {j + 1} overlap")

        if len(obstacles) > 0 and not self._has_physical_feasible_corridor(obstacles):
            reasons.append("physical feasibility check failed: free-space corridor is blocked")

        return len(reasons) == 0, reasons

    def _is_valid_scenario(self, obstacles: List[Obstacle]) -> bool:
        valid, _ = self._validate_test_case_rules(obstacles)
        return valid

    def _repair_scenario(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        repaired = []

        for obs in obstacles[: self.MAX_OBSTACLES]:
            new_obs = self._make_obstacle(
                x=float(obs.position.x),
                y=float(obs.position.y),
                l=float(obs.size.l),
                w=float(obs.size.w),
                h=float(obs.size.h),
                r=float(obs.position.r),
            )

            if all(not self._rotated_boxes_overlap(new_obs, other) for other in repaired):
                repaired.append(new_obs)

        if len(repaired) > 0 and not self._has_physical_feasible_corridor(repaired):
            return repaired[:1]

        return repaired

    # ==============================================================
    # Scenario creation
    # ==============================================================

    def _single_blocker(self) -> List[Obstacle]:
        x = random.choice(self._mission_corridors()) + random.gauss(0.0, 2.0)
        y = random.uniform(12.0, 38.0)

        l = random.uniform(5.0, 17.0)
        w = random.uniform(5.0, 17.0)
        h = random.uniform(self.MIN_H, self.MAX_H)
        r = random.uniform(self.MIN_R, self.MAX_R)

        return [self._make_obstacle(x, y, l, w, h, r)]

    def _gate_scenario(self) -> List[Obstacle]:
        center_x = random.choice(self._mission_corridors())
        y = random.uniform(15.0, 35.0)

        gap = random.uniform(2.2, 5.0)

        l1 = random.uniform(4.0, 9.0)
        l2 = random.uniform(4.0, 9.0)

        w1 = random.uniform(8.0, 16.0)
        w2 = random.uniform(8.0, 16.0)

        h1 = random.uniform(self.MIN_H, self.MAX_H)
        h2 = random.uniform(self.MIN_H, self.MAX_H)

        r1 = random.uniform(0.0, 25.0)
        r2 = random.uniform(0.0, 25.0)

        left = self._make_obstacle(
            x=center_x - gap / 2.0 - l1 / 2.0,
            y=y,
            l=l1,
            w=w1,
            h=h1,
            r=r1,
        )

        right = self._make_obstacle(
            x=center_x + gap / 2.0 + l2 / 2.0,
            y=y,
            l=l2,
            w=w2,
            h=h2,
            r=r2,
        )

        obstacles = self._repair_scenario([left, right])

        if self._is_valid_scenario(obstacles):
            return obstacles

        return self._single_blocker()

    def _staggered_scenario(self) -> List[Obstacle]:
        center_x = random.choice(self._mission_corridors())
        n = random.choices([2, 3], weights=[0.80, 0.20], k=1)[0]

        base_y = random.uniform(13.0, 22.0)
        obstacles = []

        for i in range(n):
            x = center_x + random.gauss(0.0, 3.0)
            y = base_y + i * random.uniform(7.0, 10.0)

            l = random.uniform(4.0, 13.0)
            w = random.uniform(4.0, 13.0)
            h = random.uniform(self.MIN_H, self.MAX_H)
            r = random.uniform(self.MIN_R, self.MAX_R)

            obstacles.append(self._make_obstacle(x, y, l, w, h, r))

        obstacles = self._repair_scenario(obstacles)

        if self._is_valid_scenario(obstacles):
            return obstacles

        return self._gate_scenario()

    def _random_tg_scenario(self) -> List[Obstacle]:
        r = random.random()

        if r < 0.35:
            return self._single_blocker()

        if r < 0.75:
            return self._gate_scenario()

        return self._staggered_scenario()

    # ==============================================================
    # MCTS actions
    # ==============================================================

    def _mutate_obstacle(self, obs: Obstacle, sigma: float) -> Obstacle:
        x = float(obs.position.x) + random.gauss(0.0, 2.2 * sigma)
        y = float(obs.position.y) + random.gauss(0.0, 2.8 * sigma)

        l = float(obs.size.l) + random.gauss(0.0, 1.5 * sigma)
        w = float(obs.size.w) + random.gauss(0.0, 1.5 * sigma)
        h = float(obs.size.h) + random.gauss(0.0, 1.0)

        r = float(obs.position.r) + random.gauss(0.0, 8.0 * sigma)

        return self._make_obstacle(x, y, l, w, h, r)

    def _tighten_gate(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        if len(obstacles) != 2:
            return obstacles

        obs1, obs2 = self._clone_obstacles(obstacles)

        if obs1.position.x < obs2.position.x:
            left, right = obs1, obs2
        else:
            left, right = obs2, obs1

        shift = random.uniform(0.20, 0.60)

        left = self._make_obstacle(
            x=float(left.position.x) + shift,
            y=float(left.position.y) + random.gauss(0.0, 0.8),
            l=float(left.size.l) + random.gauss(0.0, 0.5),
            w=float(left.size.w) + random.gauss(0.0, 0.7),
            h=float(left.size.h),
            r=float(left.position.r) + random.gauss(0.0, 4.0),
        )

        right = self._make_obstacle(
            x=float(right.position.x) - shift,
            y=float(right.position.y) + random.gauss(0.0, 0.8),
            l=float(right.size.l) + random.gauss(0.0, 0.5),
            w=float(right.size.w) + random.gauss(0.0, 0.7),
            h=float(right.size.h),
            r=float(right.position.r) + random.gauss(0.0, 4.0),
        )

        repaired = self._repair_scenario([left, right])

        if self._is_valid_scenario(repaired):
            return repaired

        return obstacles

    def _slide_along_path(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        idx = random.randrange(len(child))
        obs = child[idx]

        child[idx] = self._make_obstacle(
            x=float(obs.position.x) + random.gauss(0.0, 1.0),
            y=float(obs.position.y) + random.gauss(0.0, 4.0),
            l=float(obs.size.l),
            w=float(obs.size.w),
            h=float(obs.size.h),
            r=float(obs.position.r),
        )

        child = self._repair_scenario(child)

        if self._is_valid_scenario(child):
            return child

        return obstacles

    def _resize_obstacle(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        idx = random.randrange(len(child))
        obs = child[idx]

        child[idx] = self._make_obstacle(
            x=float(obs.position.x),
            y=float(obs.position.y),
            l=float(obs.size.l) + random.gauss(0.5, 1.2),
            w=float(obs.size.w) + random.gauss(0.5, 1.2),
            h=float(obs.size.h),
            r=float(obs.position.r),
        )

        child = self._repair_scenario(child)

        if self._is_valid_scenario(child):
            return child

        return obstacles

    def _rotate_obstacle(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        idx = random.randrange(len(child))
        obs = child[idx]

        child[idx] = self._make_obstacle(
            x=float(obs.position.x),
            y=float(obs.position.y),
            l=float(obs.size.l),
            w=float(obs.size.w),
            h=float(obs.size.h),
            r=float(obs.position.r) + random.gauss(0.0, 15.0),
        )

        child = self._repair_scenario(child)

        if self._is_valid_scenario(child):
            return child

        return obstacles

    def _apply_action(self, obstacles: List[Obstacle], action: str) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)

        if action == "init_single":
            return self._single_blocker()

        if action == "init_gate":
            return self._gate_scenario()

        if action == "init_staggered":
            return self._staggered_scenario()

        if action == "add_blocker" and len(child) < self.MAX_OBSTACLES:
            child.append(self._single_blocker()[0])
            child = self._repair_scenario(child)
            if self._is_valid_scenario(child):
                return child

        if action == "mutate_local" and len(child) > 0:
            idx = random.randrange(len(child))
            child[idx] = self._mutate_obstacle(child[idx], sigma=1.0)
            child = self._repair_scenario(child)
            if self._is_valid_scenario(child):
                return child

        if action == "mutate_strong" and len(child) > 0:
            idx = random.randrange(len(child))
            child[idx] = self._mutate_obstacle(child[idx], sigma=2.0)
            child = self._repair_scenario(child)
            if self._is_valid_scenario(child):
                return child

        if action == "tighten_gate":
            return self._tighten_gate(child)

        if action == "slide_y" and len(child) > 0:
            return self._slide_along_path(child)

        if action == "resize" and len(child) > 0:
            return self._resize_obstacle(child)

        if action == "rotate" and len(child) > 0:
            return self._rotate_obstacle(child)

        return self._random_tg_scenario()

    def _available_actions(self, node: MCTSNode) -> List[str]:
        if len(node.obstacles) == 0:
            return ["init_single", "init_gate", "init_staggered"]

        actions = [
            "mutate_local",
            "mutate_strong",
            "slide_y",
            "resize",
            "rotate",
            "tighten_gate",
        ]

        if len(node.obstacles) < self.MAX_OBSTACLES:
            actions.append("add_blocker")

        return actions

    # ==============================================================
    # MAP-Elites
    # ==============================================================

    def _scenario_signature(self, obstacles: List[Obstacle]) -> Tuple:
        values = []

        for obs in obstacles:
            values.append(
                (
                    round(float(obs.position.x), 1),
                    round(float(obs.position.y), 1),
                    round(float(obs.size.l), 1),
                    round(float(obs.size.w), 1),
                    round(float(obs.size.h), 1),
                    round(float(obs.position.r), 1),
                )
            )

        values.sort()
        return tuple(values)

    def _mean_xy(self, obstacles: List[Obstacle]) -> Tuple[float, float]:
        mx = sum(float(obs.position.x) for obs in obstacles) / len(obstacles)
        my = sum(float(obs.position.y) for obs in obstacles) / len(obstacles)
        return mx, my

    def _compactness(self, obstacles: List[Obstacle]) -> float:
        if len(obstacles) <= 1:
            return 0.0

        dists = []

        for i in range(len(obstacles)):
            for j in range(i + 1, len(obstacles)):
                dx = float(obstacles[i].position.x) - float(obstacles[j].position.x)
                dy = float(obstacles[i].position.y) - float(obstacles[j].position.y)
                dists.append(math.sqrt(dx * dx + dy * dy))

        return sum(dists) / len(dists)

    def _mean_rotation(self, obstacles: List[Obstacle]) -> float:
        return sum(float(obs.position.r) for obs in obstacles) / len(obstacles)

    def _bin_value(self, value: float, low: float, high: float, bins: int) -> int:
        if value <= low:
            return 0

        if value >= high:
            return bins - 1

        ratio = (value - low) / (high - low)
        return int(ratio * bins)

    def _elite_cell(self, obstacles: List[Obstacle]) -> Tuple:
        mean_x, mean_y = self._mean_xy(obstacles)
        compactness = self._compactness(obstacles)
        mean_r = self._mean_rotation(obstacles)

        n_bin = len(obstacles)
        x_bin = self._bin_value(mean_x, self.X_MIN, self.X_MAX, 5)
        y_bin = self._bin_value(mean_y, self.Y_MIN, self.Y_MAX, 5)
        r_bin = self._bin_value(mean_r, self.MIN_R, self.MAX_R, 4)

        if compactness < 6.0:
            c_bin = 0
        elif compactness < 14.0:
            c_bin = 1
        else:
            c_bin = 2

        return (n_bin, x_bin, y_bin, c_bin, r_bin)

    def _update_elites(self, result: EvalResult) -> None:
        old = self.elites.get(result.cell)

        if old is None or self._sort_key(result) > self._sort_key(old):
            self.elites[result.cell] = result

    # ==============================================================
    # Scoring
    # ==============================================================

    def _official_point(self, min_distance: float) -> int:
        if min_distance < 0.25:
            return 5
        if min_distance < 1.0:
            return 2
        if min_distance < 1.5:
            return 1
        return 0

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

    def _sort_key(self, result: EvalResult) -> Tuple:
        completion_priority = 1 if result.mission_status == "completed" else 0

        return (
            result.point,
            completion_priority,
            -result.min_distance,
            result.reward,
            -len(result.obstacles),
        )

    def _problem_label(self, min_distance: float) -> str:
        if min_distance < self.HARD_FAIL_THRESHOLD:
            return "hard_fail"
        if min_distance < self.FAILURE_THRESHOLD:
            return "soft_fail"
        if min_distance < self.NEAR_MISS_THRESHOLD:
            return "near_miss"
        return "safe"

    # ==============================================================
    # MCTS
    # ==============================================================

    def _ucb_score(self, parent: MCTSNode, child: MCTSNode) -> float:
        if child.visits == 0:
            return float("inf")

        exploitation = child.total_reward / child.visits
        exploration = self.UCB_C * math.sqrt(
            math.log(parent.visits + 1.0) / child.visits
        )

        return exploitation + exploration

    def _progressive_widening_limit(self, node: MCTSNode) -> int:
        return max(1, int(self.PW_C * ((node.visits + 1) ** self.PW_ALPHA)))

    def _can_expand(self, node: MCTSNode) -> bool:
        return len(node.children) < self._progressive_widening_limit(node)

    def _expand(self, node: MCTSNode) -> Optional[MCTSNode]:
        actions = self._available_actions(node)

        for _ in range(60):
            action = random.choice(actions)
            child_obstacles = self._apply_action(node.obstacles, action)

            valid, _ = self._validate_test_case_rules(child_obstacles)
            if not valid:
                continue

            signature = self._scenario_signature(child_obstacles)

            if signature in self.seen_signatures:
                continue

            if signature in self.tree_signatures:
                continue

            child = MCTSNode(
                obstacles=child_obstacles,
                parent=node,
                action=action,
                node_id=self._next_node_id(),
            )

            node.children.append(child)
            self.tree_signatures.add(signature)
            return child

        return None

    def _tree_policy(self, root: MCTSNode) -> Optional[MCTSNode]:
        node = root

        for _ in range(20):
            if self._can_expand(node):
                expanded = self._expand(node)
                if expanded is not None:
                    return expanded

            if len(node.children) == 0:
                return self._expand(node)

            node = max(node.children, key=lambda child: self._ucb_score(node, child))

        return node

    def _backup(self, node: MCTSNode, reward: float) -> None:
        while node is not None:
            node.visits += 1
            node.total_reward += reward
            node.best_reward = max(node.best_reward, reward)
            node = node.parent

    # ==============================================================
    # Trajectory extraction and mission completion
    # ==============================================================

    def _try_float(self, value: Any) -> Optional[float]:
        try:
            x = float(value)
            if math.isfinite(x):
                return x
        except Exception:
            return None
        return None

    def _point_from_object(self, obj: Any) -> Optional[Tuple[float, float]]:
        if obj is None:
            return None

        if isinstance(obj, dict):
            key_pairs = [
                ("x", "y"),
                ("X", "Y"),
                ("local_x", "local_y"),
                ("position_x", "position_y"),
                ("east", "north"),
                ("lon", "lat"),
                ("longitude", "latitude"),
            ]

            for kx, ky in key_pairs:
                if kx in obj and ky in obj:
                    x = self._try_float(obj[kx])
                    y = self._try_float(obj[ky])
                    if x is not None and y is not None:
                        return (x, y)

        attr_pairs = [
            ("x", "y"),
            ("X", "Y"),
            ("local_x", "local_y"),
            ("position_x", "position_y"),
            ("east", "north"),
            ("lon", "lat"),
            ("longitude", "latitude"),
        ]

        for ax, ay in attr_pairs:
            if hasattr(obj, ax) and hasattr(obj, ay):
                x = self._try_float(getattr(obj, ax))
                y = self._try_float(getattr(obj, ay))
                if x is not None and y is not None:
                    return (x, y)

        if isinstance(obj, (list, tuple)) and len(obj) >= 2:
            x = self._try_float(obj[0])
            y = self._try_float(obj[1])
            if x is not None and y is not None:
                return (x, y)

        return None

    def _extract_xy_sequence(self, obj: Any) -> List[Tuple[float, float]]:
        if obj is None:
            return []

        if hasattr(obj, "columns"):
            try:
                columns = list(obj.columns)
                lower_to_original = {str(c).lower(): c for c in columns}

                candidate_pairs = [
                    ("x", "y"),
                    ("local_x", "local_y"),
                    ("position_x", "position_y"),
                    ("east", "north"),
                    ("lon", "lat"),
                    ("longitude", "latitude"),
                ]

                for x_name, y_name in candidate_pairs:
                    if x_name in lower_to_original and y_name in lower_to_original:
                        xs = list(obj[lower_to_original[x_name]])
                        ys = list(obj[lower_to_original[y_name]])

                        points = []

                        for x_raw, y_raw in zip(xs, ys):
                            x = self._try_float(x_raw)
                            y = self._try_float(y_raw)

                            if x is not None and y is not None:
                                points.append((x, y))

                        if len(points) >= 2:
                            return points
            except Exception:
                pass

        if isinstance(obj, dict):
            key_pairs = [
                ("x", "y"),
                ("X", "Y"),
                ("local_x", "local_y"),
                ("position_x", "position_y"),
                ("east", "north"),
                ("lon", "lat"),
                ("longitude", "latitude"),
            ]

            for kx, ky in key_pairs:
                if kx in obj and ky in obj:
                    try:
                        xs = list(obj[kx])
                        ys = list(obj[ky])
                        points = []

                        for x_raw, y_raw in zip(xs, ys):
                            x = self._try_float(x_raw)
                            y = self._try_float(y_raw)

                            if x is not None and y is not None:
                                points.append((x, y))

                        if len(points) >= 2:
                            return points
                    except Exception:
                        pass

        attr_pairs = [
            ("x", "y"),
            ("X", "Y"),
            ("local_x", "local_y"),
            ("position_x", "position_y"),
            ("east", "north"),
            ("lon", "lat"),
            ("longitude", "latitude"),
        ]

        for ax, ay in attr_pairs:
            if hasattr(obj, ax) and hasattr(obj, ay):
                try:
                    xs = list(getattr(obj, ax))
                    ys = list(getattr(obj, ay))
                    points = []

                    for x_raw, y_raw in zip(xs, ys):
                        x = self._try_float(x_raw)
                        y = self._try_float(y_raw)

                        if x is not None and y is not None:
                            points.append((x, y))

                    if len(points) >= 2:
                        return points
                except Exception:
                    pass

        if isinstance(obj, (list, tuple)):
            points = []

            for item in obj:
                point = self._point_from_object(item)

                if point is not None:
                    points.append(point)

            if len(points) >= 2:
                return points

        return []

    def _clean_trajectory_points(self, points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        clean = []

        for x, y in points:
            if not math.isfinite(x) or not math.isfinite(y):
                continue

            if abs(x) > 10000 or abs(y) > 10000:
                continue

            clean.append((x, y))

        if len(clean) >= 2:
            return clean

        return self._fallback_reference_path()

    def _extract_trajectory_xy(self, test: Any) -> Tuple[List[Tuple[float, float]], bool]:
        trajectory = getattr(test, "trajectory", None)

        if trajectory is None:
            return self._fallback_reference_path(), False

        direct = self._extract_xy_sequence(trajectory)
        if len(direct) >= 2:
            return self._clean_trajectory_points(direct), True

        candidate_attrs = [
            "positions",
            "points",
            "path",
            "trajectory",
            "records",
            "record",
            "data",
            "df",
            "dataframe",
            "log",
            "values",
            "_data",
            "_df",
            "_record",
        ]

        for attr in candidate_attrs:
            if hasattr(trajectory, attr):
                try:
                    candidate = getattr(trajectory, attr)
                    points = self._extract_xy_sequence(candidate)

                    if len(points) >= 2:
                        return self._clean_trajectory_points(points), True
                except Exception:
                    pass

        if hasattr(trajectory, "__dict__"):
            for _, value in vars(trajectory).items():
                points = self._extract_xy_sequence(value)

                if len(points) >= 2:
                    return self._clean_trajectory_points(points), True

        return self._fallback_reference_path(), False

    def _mission_completion_status(self, test: Any) -> str:
        points, actual = self._extract_trajectory_xy(test)

        if not actual or len(points) < 2:
            return "unknown"

        goal = self._fallback_reference_path()[-1]
        last = points[-1]

        dx = last[0] - goal[0]
        dy = last[1] - goal[1]
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= self.MISSION_COMPLETION_RADIUS:
            return "completed"

        return "not_completed"

    # ==============================================================
    # Plotting
    # ==============================================================

    def _save_scenario_plot(
        self,
        test: Any,
        obstacles: List[Obstacle],
        index: int,
        min_distance: float,
        point: int,
        node_id: int,
        mission_status: str,
    ) -> str:
        points, actual = self._extract_trajectory_xy(test)

        os.makedirs(self.scenario_plot_dir, exist_ok=True)

        problem_type = self._problem_label(min_distance)
        path = os.path.join(
            self.scenario_plot_dir,
            f"scenario_sim_{index:03d}_node_{node_id:03d}_{problem_type}.png",
        )

        fig, ax = plt.subplots(figsize=(9, 7))

        area = Rectangle(
            (self.X_MIN, self.Y_MIN),
            self.X_MAX - self.X_MIN,
            self.Y_MAX - self.Y_MIN,
            fill=False,
            linestyle="--",
            linewidth=1.5,
            edgecolor="black",
            label="Valid obstacle area",
        )
        ax.add_patch(area)

        for i, obs in enumerate(obstacles):
            corners = self._rotated_corners(obs)
            poly = Polygon(
                corners,
                closed=True,
                alpha=0.45,
                edgecolor="black",
                facecolor="tab:gray",
            )
            ax.add_patch(poly)

            ax.text(
                float(obs.position.x),
                float(obs.position.y),
                f"O{i + 1}\nr={float(obs.position.r):.0f}°",
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
            )

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]

        if actual:
            ax.plot(xs, ys, linewidth=2.2, marker=".", markersize=2.5, label="Extracted UAV trajectory")
        else:
            ax.plot(xs, ys, linewidth=2.0, linestyle=":", marker="o", label="Reference path fallback")

        if len(points) >= 1:
            ax.scatter(xs[0], ys[0], marker="s", s=80, label="Start")
            ax.scatter(xs[-1], ys[-1], marker="*", s=130, label="End")

        if min_distance < self.HARD_FAIL_THRESHOLD:
            title_color = "red"
            status = "HARD FAIL"
        elif min_distance < self.FAILURE_THRESHOLD:
            title_color = "red"
            status = "SOFT FAIL"
        elif min_distance < self.NEAR_MISS_THRESHOLD:
            title_color = "orange"
            status = "NEAR MISS"
        else:
            title_color = "green"
            status = "SAFE"

        ax.set_title(
            f"TG-MCTS-Elites scenario {index} | node {node_id} | {status}\n"
            f"min_distance = {min_distance:.3f} m | point = {point} | "
            f"trajectory = {actual} | mission = {mission_status}",
            color=title_color,
        )

        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.grid(True, alpha=0.3)
        ax.axis("equal")

        min_x = min([self.X_MIN] + xs) - 5.0
        max_x = max([self.X_MAX] + xs) + 5.0
        min_y = min([0.0, self.Y_MIN] + ys) - 5.0
        max_y = max([self.Y_MAX] + ys) + 5.0

        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)

        ax.legend(loc="best", fontsize=8)
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close(fig)

        test.plot_file = path

        return path

    # ==============================================================
    # Simulation
    # ==============================================================

    def _run_simulation_once(self, node: MCTSNode, index: int, budget: int) -> EvalResult:
        obstacles = node.obstacles

        valid, reasons = self._validate_test_case_rules(obstacles)

        if not valid:
            raise NonCompliantCandidateError("; ".join(reasons))

        test = TestCase(self.case_study, obstacles)

        print(f"\n[TG-MCTS-Elites] Simulation {index}/{budget}")
        print(f"Action: {node.action}")
        print(f"Scenario with {len(obstacles)} obstacle(s)")

        for k, obs in enumerate(obstacles):
            print(
                f"  obstacle {k + 1}: "
                f"x={float(obs.position.x):.2f}, y={float(obs.position.y):.2f}, "
                f"l={float(obs.size.l):.2f}, w={float(obs.size.w):.2f}, "
                f"h={float(obs.size.h):.2f}, r={float(obs.position.r):.2f}"
            )

        start = time.time()
        test.execute()
        elapsed_minutes = max((time.time() - start) / 60.0, 1e-6)

        distances = test.get_distances()

        if len(distances) == 0:
            raise RuntimeError("Simulation completed but returned no obstacle distances.")

        min_distance = min(distances)

        print(f"minimum_distance:{min_distance:.4f}")

        point = self._official_point(min_distance)
        mission_status = self._mission_completion_status(test)

        if min_distance >= self.HARD_FAIL_THRESHOLD and mission_status == "not_completed":
            raise NonCompliantCandidateError(
                "mission did not complete for a non-hard-fail candidate"
            )

        reward = self._reward(
            min_distance=min_distance,
            n_obstacles=len(obstacles),
            elapsed_minutes=elapsed_minutes,
            mission_status=mission_status,
        )

        cell = self._elite_cell(obstacles)

        scenario_plot = self._save_scenario_plot(
            test=test,
            obstacles=obstacles,
            index=index,
            min_distance=min_distance,
            point=point,
            node_id=node.node_id,
            mission_status=mission_status,
        )

        test.minimum_distance = min_distance
        test.official_point = point
        test.reward = reward
        test.elapsed_minutes = elapsed_minutes
        test.elite_cell = cell
        test.problem_type = self._problem_label(min_distance)
        test.mission_status = mission_status
        test.compliance_status = "compliant"

        return EvalResult(
            obstacles=obstacles,
            test=test,
            min_distance=min_distance,
            elapsed_minutes=elapsed_minutes,
            point=point,
            reward=reward,
            cell=cell,
            signature=self._scenario_signature(obstacles),
            scenario_plot=scenario_plot,
            mission_status=mission_status,
            compliance_status="compliant",
        )

    def _evaluate_with_retries(self, node: MCTSNode, index: int, budget: int) -> Optional[EvalResult]:
        signature = self._scenario_signature(node.obstacles)

        if signature in self.seen_signatures:
            return None

        for attempt in range(1, self.MAX_SYSTEM_RETRIES + 2):
            self._write_pending_candidate(
                node=node,
                simulation_index=index,
                budget=budget,
                attempt=attempt,
            )

            try:
                result = self._run_simulation_once(node=node, index=index, budget=budget)

                result = self._save_result_checkpoint(
                    result=result,
                    simulation_index=index,
                    node=node,
                )

                self.results.append(result)
                self.seen_signatures.add(signature)
                self._update_elites(result)
                self._clear_pending_candidate()

                return result

            except NonCompliantCandidateError as e:
                print("[invalid-candidate] Candidate violates rules or execution constraints.")
                print(e)

                self._log_invalid_candidate(
                    node=node,
                    simulation_index=index,
                    reason=str(e),
                )

                self.seen_signatures.add(signature)
                self._clear_pending_candidate()
                return None

            except Exception as e:
                self._log_system_error(
                    node=node,
                    simulation_index=index,
                    attempt=attempt,
                    error=e,
                )

                print(f"[system-error] Attempt {attempt}/{self.MAX_SYSTEM_RETRIES + 1} failed.")
                print(e)

                if attempt <= self.MAX_SYSTEM_RETRIES:
                    print("[system-error] Recomputing the same candidate.")
                    time.sleep(2.0)
                else:
                    print("[system-error] Candidate failed after all retries. It is not counted as a UAV failure.")
                    self._clear_pending_candidate()
                    return None

        return None

    # ==============================================================
    # History and output plots
    # ==============================================================

    def _record_history(self, simulation_index: int, node: MCTSNode, result: EvalResult) -> None:
        parent_id = node.parent.node_id if node.parent is not None else None

        obstacle_text = []

        for obs in result.obstacles:
            obstacle_text.append(
                f"x={float(obs.position.x):.3f},y={float(obs.position.y):.3f},"
                f"l={float(obs.size.l):.3f},w={float(obs.size.w):.3f},"
                f"h={float(obs.size.h):.3f},r={float(obs.position.r):.3f}"
            )

        row = {
            "simulation": simulation_index,
            "node_id": node.node_id,
            "parent_id": parent_id,
            "action": node.action,
            "n_obstacles": len(result.obstacles),
            "min_distance": result.min_distance,
            "problem_type": self._problem_label(result.min_distance),
            "mission_status": result.mission_status,
            "compliance_status": result.compliance_status,
            "point": result.point,
            "reward": result.reward,
            "cell": str(result.cell),
            "scenario_plot": result.scenario_plot,
            "yaml_file": result.yaml_file,
            "log_file": result.log_file,
            "obstacles": " | ".join(obstacle_text),
        }

        self.history.append(row)
        self._append_jsonl(self.history_jsonl_path, row)

    def _save_history_csv(self) -> None:
        path = os.path.join(self.output_dir, "history.csv")

        if len(self.history) == 0:
            return

        fieldnames = list(self.history[0].keys())

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.history)

        print(f"History saved to: {path}")

    def _collect_nodes(self, root: MCTSNode) -> List[MCTSNode]:
        nodes = []

        def dfs(node: MCTSNode):
            nodes.append(node)
            for child in node.children:
                dfs(child)

        dfs(root)
        return nodes

    def _node_depth(self, node: MCTSNode) -> int:
        depth = 0

        while node.parent is not None:
            depth += 1
            node = node.parent

        return depth

    def _save_tree_plot(self, root: MCTSNode) -> None:
        nodes = self._collect_nodes(root)

        if len(nodes) == 0:
            return

        levels = {}

        for node in nodes:
            depth = self._node_depth(node)
            levels.setdefault(depth, []).append(node)

        for depth in levels:
            levels[depth].sort(key=lambda n: n.node_id)

        max_width = max(len(level_nodes) for level_nodes in levels.values())
        max_depth = max(levels.keys())

        positions = {}

        for depth, level_nodes in levels.items():
            n_level = len(level_nodes)

            for i, node in enumerate(level_nodes):
                x = i - (n_level - 1) / 2.0
                y = -depth
                positions[node.node_id] = (x, y)

        fig_width = max(14, max_width * 0.8)
        fig_height = max(9, (max_depth + 1) * 1.3)

        plt.figure(figsize=(fig_width, fig_height))

        for node in nodes:
            if node.parent is not None:
                x1, y1 = positions[node.parent.node_id]
                x2, y2 = positions[node.node_id]
                plt.plot([x1, x2], [y1, y2], color="lightgray", linewidth=0.8, zorder=1)

        for node in nodes:
            x, y = positions[node.node_id]

            if node.eval_result is None:
                plt.scatter(x, y, s=45, marker="o", color="lightgray", zorder=3)
                label = f"{node.node_id}"
            else:
                d = node.eval_result.min_distance

                if d < self.HARD_FAIL_THRESHOLD:
                    plt.scatter(x, y, s=150, marker="X", color="red", linewidths=2.8, zorder=4)
                elif d < self.FAILURE_THRESHOLD:
                    plt.scatter(x, y, s=130, marker="x", color="red", linewidths=2.8, zorder=4)
                elif d < self.NEAR_MISS_THRESHOLD:
                    plt.scatter(x, y, s=100, marker="^", color="orange", zorder=4)
                else:
                    plt.scatter(x, y, s=65, marker="o", color="green", zorder=4)

                label = f"{node.node_id}\n{d:.1f}m"

            plt.text(x, y + 0.12, label, fontsize=6, ha="center", va="bottom")

        plt.scatter([], [], marker="X", color="red", s=150, label="Hard fail: d < 0.25 m")
        plt.scatter([], [], marker="x", color="red", s=130, label="Soft fail: d < 1.5 m")
        plt.scatter([], [], marker="^", color="orange", s=100, label="Near miss: 1.5 m <= d < 3.0 m")
        plt.scatter([], [], marker="o", color="green", s=65, label="Safe: d >= 3.0 m")
        plt.scatter([], [], marker="o", color="lightgray", s=45, label="Unevaluated/internal")

        plt.title("TG-MCTS-Elites generated search tree")
        plt.xlabel("Tree branching")
        plt.ylabel("Tree depth")
        plt.legend(loc="best")
        plt.grid(True, alpha=0.2)
        plt.tight_layout()

        path = os.path.join(self.output_dir, "tree_final.png")
        plt.savefig(path, dpi=220)
        plt.close()

        print(f"Tree plot saved to: {path}")

    def _save_progress_plot(self) -> None:
        if len(self.results) == 0:
            return

        distances = [result.min_distance for result in self.results]
        x_values = list(range(1, len(distances) + 1))

        best_so_far = []
        current_best = float("inf")

        for d in distances:
            current_best = min(current_best, d)
            best_so_far.append(current_best)

        plt.figure(figsize=(12, 6))

        plt.plot(
            x_values,
            distances,
            marker="o",
            linewidth=1.0,
            markersize=3,
            label="Simulation min distance",
        )

        plt.plot(
            x_values,
            best_so_far,
            linewidth=2.0,
            label="Best distance so far",
        )

        plt.axhline(
            self.HARD_FAIL_THRESHOLD,
            color="red",
            linestyle=":",
            linewidth=1.5,
            label="Hard-fail threshold: 0.25 m",
        )

        plt.axhline(
            self.FAILURE_THRESHOLD,
            color="red",
            linestyle="--",
            linewidth=1.5,
            label="Soft-fail threshold: 1.5 m",
        )

        plt.axhline(
            self.NEAR_MISS_THRESHOLD,
            color="orange",
            linestyle="--",
            linewidth=1.5,
            label="Near-miss threshold: 3.0 m",
        )

        plt.title("TG-MCTS-Elites progress over simulations")
        plt.xlabel("Simulation number")
        plt.ylabel("Minimum UAV-obstacle distance [m]")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        path = os.path.join(self.output_dir, "progress_final.png")
        plt.savefig(path, dpi=220)
        plt.close()

        print(f"Progress plot saved to: {path}")

    def _save_all_outputs(self, root: MCTSNode) -> None:
        self._ensure_output_dirs()
        self._save_history_csv()
        self._save_progress_plot()
        self._save_tree_plot(root)

    # ==============================================================
    # Final selection
    # ==============================================================

    def _final_suite(self) -> List[Any]:
        candidates = []

        candidates.extend(self.elites.values())

        global_best = sorted(self.results, key=self._sort_key, reverse=True)
        candidates.extend(global_best)

        selected: List[EvalResult] = []
        selected_signatures = set()

        for result in sorted(candidates, key=self._sort_key, reverse=True):
            if len(selected) >= self.RETURN_LIMIT:
                break

            if result.signature in selected_signatures:
                continue

            selected.append(result)
            selected_signatures.add(result.signature)

        print("\n===== TG-MCTS-Elites Summary =====")
        print(f"Total successful simulations: {len(self.results)}")
        print(f"Elite cells filled: {len(self.elites)}")
        print(f"Returned tests: {len(selected)}")

        if len(selected) > 0:
            best = selected[0]
            print(
                f"Best test: min_distance={best.min_distance:.4f}, "
                f"point={best.point}, reward={best.reward:.4f}, "
                f"cell={best.cell}, obstacles={len(best.obstacles)}, "
                f"mission_status={best.mission_status}"
            )

        print("\nReturned ranking:")

        for i, result in enumerate(selected):
            print(
                f"  rank {i + 1}: "
                f"min_distance={result.min_distance:.4f}, "
                f"problem_type={self._problem_label(result.min_distance)}, "
                f"mission_status={result.mission_status}, "
                f"point={result.point}, reward={result.reward:.4f}, "
                f"cell={result.cell}, obstacles={len(result.obstacles)}, "
                f"plot={result.scenario_plot}"
            )

        return [result.test for result in selected]

    # ==============================================================
    # Main entry point called by cli.py
    # ==============================================================

    def generate(self, budget: int) -> List[Any]:
        self.results = []
        self.elites = {}
        self.seen_signatures = set()
        self.tree_signatures = set()
        self.history = []

        self._setup_run_directory(budget=budget)
        self._load_previous_results()
        self._load_previous_history()

        self._node_counter = max(self._node_counter, len(self.history) + 1)
        root = MCTSNode(obstacles=[], node_id=self._next_node_id())

        print("\n======================================================")
        print("Rule-compliant Robust TG-MCTS-Elites UAV Test Generator")
        print(f"Case study: {self.case_study_file}")
        print(f"Budget target: {budget} successful simulations")
        print(f"Already completed from checkpoint: {len(self.results)}")
        print(f"Seed: {self.seed}")
        print(f"Output directory: {self.output_dir}")
        print("Rules: x/y/l/w/h/r bounds, <=3 obstacles, z=0, no overlap, feasible corridor")
        print("Crash handling: pending candidate is recomputed after restart")
        print("Mission completion: checked when trajectory can be extracted")
        print("UML: global documentation only, not saved per mission run")
        print("======================================================")

        simulations_done = len(self.results)
        failed_expansions = 0
        max_failed_expansions = max(50, budget * 15)

        pending_node = self._load_pending_candidate_as_node(root)

        if pending_node is not None and simulations_done < budget:
            result = self._evaluate_with_retries(
                node=pending_node,
                index=simulations_done + 1,
                budget=budget,
            )

            if result is not None:
                pending_node.eval_result = result
                self._record_history(simulations_done + 1, pending_node, result)
                simulations_done += 1
                self._backup(pending_node, result.reward)
                self._write_run_state(status="running", budget=budget)

        while simulations_done < budget and failed_expansions < max_failed_expansions:
            node = self._tree_policy(root)

            if node is None:
                failed_expansions += 1
                continue

            valid, reasons = self._validate_test_case_rules(node.obstacles)

            if not valid:
                self._log_invalid_candidate(
                    node=node,
                    simulation_index=simulations_done + 1,
                    reason="; ".join(reasons),
                )
                failed_expansions += 1
                continue

            result = self._evaluate_with_retries(
                node=node,
                index=simulations_done + 1,
                budget=budget,
            )

            if result is None:
                failed_expansions += 1
                continue

            node.eval_result = result
            self._record_history(simulations_done + 1, node, result)

            simulations_done += 1
            self._backup(node, result.reward)
            self._write_run_state(status="running", budget=budget)

        if len(self.results) == 0:
            print("No successful simulations. Returning empty suite.")
            self._save_all_outputs(root)
            self._write_run_state(status="failed_no_successful_simulations", budget=budget)
            return []

        final_tests = self._final_suite()
        self._save_all_outputs(root)

        if simulations_done >= budget:
            self._write_run_state(status="completed", budget=budget)
        else:
            self._write_run_state(status="stopped_before_budget", budget=budget)

        return final_tests


if __name__ == "__main__":
    generator = RandomGenerator("case_studies/mission1.yaml")
    generator.generate(10)
