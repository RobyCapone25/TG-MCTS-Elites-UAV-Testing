import copy
import logging
from typing import List
from decouple import config
from aerialist.px4.aerialist_test import AerialistTest, AgentConfig
from aerialist.px4.obstacle import Obstacle
from aerialist.px4.trajectory import Trajectory

AGENT = config("AGENT", default=AgentConfig.DOCKER)

if AGENT == AgentConfig.LOCAL:
    from aerialist.px4.local_agent import LocalAgent
if AGENT == AgentConfig.DOCKER:
    from aerialist.px4.docker_agent import DockerAgent
if AGENT == AgentConfig.K8S:
    from aerialist.px4.k8s_agent import K8sAgent

logger = logging.getLogger(__name__)


class TestCase(object):
    def __init__(self, casestudy: AerialistTest, obstacles: List[Obstacle]):
        self.test = copy.deepcopy(casestudy)

        # Add the generated obstacles to the copied case study
        self.test.simulation.obstacles = obstacles

        # Important fix:
        # The provided case_studies YAML files do not contain an "agent" section.
        # DockerAgent expects self.test.agent to exist, otherwise it crashes with:
        # 'NoneType' object has no attribute 'id'
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

        if len(self.test_results) == 0:
            raise RuntimeError("Aerialist finished but returned no test results/log file.")

        self.trajectory = self.test_results[0].record
        self.log_file = self.test_results[0].log_file
        return self.trajectory

    def get_distances(self) -> List[float]:
        return [
            self.trajectory.min_distance_to_obstacles([obst])
            for obst in self.test.simulation.obstacles
        ]

    def plot(self):
        self.plot_file = AerialistTest.plot(self.test, self.test_results)

    def save_yaml(self, path):
        self.test.to_yaml(path)

# --- Compatibility patch for Aerialist versions without AerialistTest.plot ---
if not hasattr(AerialistTest, "plot"):
    def _aerialist_dummy_plot(test, test_results):
        import os
        import base64
        from datetime import datetime

        os.makedirs("results/plots", exist_ok=True)

        filename = datetime.now().strftime("plot_%d-%m-%H-%M-%S-%f.png")
        path = os.path.join("results", "plots", filename)

        # 1x1 transparent PNG
        png_base64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )

        with open(path, "wb") as f:
            f.write(base64.b64decode(png_base64))

        return path

    AerialistTest.plot = staticmethod(_aerialist_dummy_plot)
# --- End compatibility patch ---
