from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import List

from decouple import config
from aerialist.px4.aerialist_test import AerialistTest, AgentConfig
from aerialist.px4.obstacle import Obstacle
from aerialist.px4.trajectory import Trajectory

AGENT = config("AGENT", default=AgentConfig.DOCKER)

if AGENT == AgentConfig.LOCAL:
    from aerialist.px4.local_agent import LocalAgent
elif AGENT == AgentConfig.DOCKER:
    from aerialist.px4.docker_agent import DockerAgent
elif AGENT == AgentConfig.K8S:
    from aerialist.px4.k8s_agent import K8sAgent

logger = logging.getLogger(__name__)


class TestCase:
    """Executable Aerialist test obtained by adding generated obstacles."""

    def __init__(self, casestudy: AerialistTest, obstacles: List[Obstacle]) -> None:
        self.test = copy.deepcopy(casestudy)
        self.test.simulation.obstacles = obstacles
        self.plot_file = ""
        self.xy_time_plot_file = ""
        self.log_file = ""

        if self.test.agent is None:
            self.test.agent = AgentConfig(engine=AGENT)

    def execute(self) -> Trajectory:
        if AGENT == AgentConfig.LOCAL:
            agent = LocalAgent(self.test)
        elif AGENT == AgentConfig.DOCKER:
            agent = DockerAgent(self.test)
        elif AGENT == AgentConfig.K8S:
            agent = K8sAgent(self.test)
        else:
            raise ValueError(f"Unknown AGENT value: {AGENT}")

        logger.info("running the test...")
        self.test_results = agent.run()
        logger.info("test finished...")

        if not self.test_results:
            raise RuntimeError("Aerialist finished but returned no test results/log file.")

        first_result = self.test_results[0]
        self.trajectory = first_result.record
        self.log_file = first_result.log_file
        return self.trajectory

    def get_distances(self) -> List[float]:
        if not hasattr(self, "trajectory"):
            raise RuntimeError("The test must be executed before distances are requested.")
        return [
            self.trajectory.min_distance_to_obstacles([obstacle])
            for obstacle in self.test.simulation.obstacles
        ]

    def save_yaml(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.test.to_yaml(str(destination))
