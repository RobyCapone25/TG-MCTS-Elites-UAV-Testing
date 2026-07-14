from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from aerialist.px4.obstacle import Obstacle


class NonCompliantCandidateError(Exception):
    """Candidate violates submission constraints or cannot be evaluated reliably."""


class SimulationBudgetExhausted(Exception):
    """No additional simulator execution is allowed by the declared budget."""


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
        trajectory_xy: Optional[List[Tuple[float, float]]] = None,
        xy_time_plot_file: str = "",
    ) -> None:
        self.yaml_file = yaml_file
        self.log_file = log_file
        self.plot_file = plot_file
        self.xy_time_plot_file = xy_time_plot_file
        self.minimum_distance = minimum_distance
        self.official_point = official_point
        self.reward = reward
        self.elapsed_minutes = elapsed_minutes
        self.elite_cell = elite_cell
        self.problem_type = problem_type
        self.mission_status = mission_status
        self.compliance_status = compliance_status
        self.trajectory_xy = list(trajectory_xy or [])

    def save_yaml(self, path: str) -> None:
        if not self.yaml_file:
            raise RuntimeError("This metadata-only evaluation has no persisted YAML artifact.")
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
    scenario_plot: str = ""
    xy_time_plot: str = ""
    yaml_file: str = ""
    log_file: str = ""
    mission_status: str = "unknown"
    compliance_status: str = "unknown"
    artifacts_saved: bool = False
    simulation_attempt: int = 0
    trajectory_xy: List[Tuple[float, float]] = field(default_factory=list)
    point_samples: List[int] = field(default_factory=list)
    distance_samples: List[float] = field(default_factory=list)
    elapsed_samples: List[float] = field(default_factory=list)
    confirmation_attempts: int = 0


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
