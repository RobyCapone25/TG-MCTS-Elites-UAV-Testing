from __future__ import annotations

import math
import random
from typing import List, Tuple

from aerialist.px4.obstacle import Obstacle

from .models import MCTSNode


class ScenarioMixin:
    def _canonical_box_orientation(
        self,
        length: float,
        width: float,
        angle_deg: float,
    ) -> Tuple[float, float, float]:
        """Represent an equivalent rectangle with rotation inside [0, 90]."""
        angle = angle_deg % 180.0
        if angle > 90.0:
            angle -= 90.0
            length, width = width, length
        return length, width, self._clamp(angle, self.MIN_R, self.MAX_R)

    def _path_frame(
        self,
        x: float,
        y: float,
        heading: float,
        along: float = 0.0,
        lateral: float = 0.0,
    ) -> Tuple[float, float]:
        tangent_x = math.cos(heading)
        tangent_y = math.sin(heading)
        normal_x = -tangent_y
        normal_y = tangent_x
        return (
            x + along * tangent_x + lateral * normal_x,
            y + along * tangent_y + lateral * normal_y,
        )

    def _single_blocker(self) -> List[Obstacle]:
        center_x, center_y, heading = self._sample_reference_pose()
        x, y = self._path_frame(
            center_x,
            center_y,
            heading,
            along=random.gauss(0.0, 2.0),
            lateral=random.gauss(0.0, 1.5),
        )

        length = random.uniform(6.0, 17.0)
        width = random.uniform(4.0, 12.0)
        height = random.uniform(self.MIN_H, self.MAX_H)
        normal_angle = math.degrees(heading) + 90.0 + random.gauss(0.0, 12.0)
        length, width, rotation = self._canonical_box_orientation(
            length,
            width,
            normal_angle,
        )
        return [self._make_obstacle(x, y, length, width, height, rotation)]

    def _gate_scenario(self) -> List[Obstacle]:
        center_x, center_y, heading = self._sample_reference_pose()
        gap = random.uniform(2.2, 5.0)

        l1 = random.uniform(4.0, 9.0)
        l2 = random.uniform(4.0, 9.0)
        normal_extent1 = l1 / 2.0
        normal_extent2 = l2 / 2.0
        w1 = random.uniform(8.0, 16.0)
        w2 = random.uniform(8.0, 16.0)
        h1 = random.uniform(self.MIN_H, self.MAX_H)
        h2 = random.uniform(self.MIN_H, self.MAX_H)

        normal_angle = math.degrees(heading) + 90.0
        l1, w1, r1 = self._canonical_box_orientation(
            l1,
            w1,
            normal_angle + random.gauss(0.0, 7.0),
        )
        l2, w2, r2 = self._canonical_box_orientation(
            l2,
            w2,
            normal_angle + random.gauss(0.0, 7.0),
        )

        left_x, left_y = self._path_frame(
            center_x,
            center_y,
            heading,
            along=random.gauss(0.0, 0.7),
            lateral=-(gap / 2.0 + normal_extent1),
        )
        right_x, right_y = self._path_frame(
            center_x,
            center_y,
            heading,
            along=random.gauss(0.0, 0.7),
            lateral=gap / 2.0 + normal_extent2,
        )

        left = self._make_obstacle(left_x, left_y, l1, w1, h1, r1)
        right = self._make_obstacle(right_x, right_y, l2, w2, h2, r2)
        obstacles = self._repair_scenario([left, right])
        return obstacles if self._is_valid_scenario(obstacles) else self._single_blocker()

    def _staggered_scenario(self) -> List[Obstacle]:
        center_x, center_y, heading = self._sample_reference_pose()
        count = random.choices([2, 3], weights=[0.80, 0.20], k=1)[0]
        spacing = random.uniform(6.0, 9.0)
        obstacles: List[Obstacle] = []

        for index in range(count):
            along = (index - (count - 1) / 2.0) * spacing
            lateral = ((-1.0) ** index) * random.uniform(1.5, 4.0)
            x, y = self._path_frame(
                center_x,
                center_y,
                heading,
                along=along,
                lateral=lateral,
            )
            length = random.uniform(4.0, 13.0)
            width = random.uniform(4.0, 13.0)
            height = random.uniform(self.MIN_H, self.MAX_H)
            base_angle = math.degrees(heading) + random.choice([0.0, 90.0])
            length, width, rotation = self._canonical_box_orientation(
                length,
                width,
                base_angle + random.gauss(0.0, 15.0),
            )
            obstacles.append(
                self._make_obstacle(x, y, length, width, height, rotation)
            )

        obstacles = self._repair_scenario(obstacles)
        return obstacles if self._is_valid_scenario(obstacles) else self._gate_scenario()

    def _random_tg_scenario(self) -> List[Obstacle]:
        draw = random.random()
        if draw < 0.35:
            return self._single_blocker()
        if draw < 0.75:
            return self._gate_scenario()
        return self._staggered_scenario()

    def _mutate_obstacle(self, obs: Obstacle, sigma: float) -> Obstacle:
        x = float(obs.position.x) + random.gauss(0.0, 2.2 * sigma)
        y = float(obs.position.y) + random.gauss(0.0, 2.8 * sigma)
        length = float(obs.size.l) + random.gauss(0.0, 1.5 * sigma)
        width = float(obs.size.w) + random.gauss(0.0, 1.5 * sigma)
        height = float(obs.size.h) + random.gauss(0.0, 1.0)
        rotation = float(obs.position.r) + random.gauss(0.0, 8.0 * sigma)
        return self._make_obstacle(x, y, length, width, height, rotation)

    def _tighten_gate(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        if len(obstacles) != 2:
            return obstacles

        first, second = self._clone_obstacles(obstacles)
        center_x = (float(first.position.x) + float(second.position.x)) / 2.0
        center_y = (float(first.position.y) + float(second.position.y)) / 2.0
        _, _, heading = self._nearest_reference_pose(center_x, center_y)
        normal_x = -math.sin(heading)
        normal_y = math.cos(heading)
        projection_first = (
            (float(first.position.x) - center_x) * normal_x
            + (float(first.position.y) - center_y) * normal_y
        )
        projection_second = (
            (float(second.position.x) - center_x) * normal_x
            + (float(second.position.y) - center_y) * normal_y
        )
        shift = random.uniform(0.20, 0.60)

        def shifted(obs: Obstacle, projection: float) -> Obstacle:
            sign = -1.0 if projection > 0.0 else 1.0
            return self._make_obstacle(
                x=float(obs.position.x) + sign * shift * normal_x,
                y=float(obs.position.y) + sign * shift * normal_y,
                l=float(obs.size.l) + random.gauss(0.0, 0.5),
                w=float(obs.size.w) + random.gauss(0.0, 0.7),
                h=float(obs.size.h),
                r=float(obs.position.r) + random.gauss(0.0, 4.0),
            )

        repaired = self._repair_scenario(
            [shifted(first, projection_first), shifted(second, projection_second)]
        )
        return repaired if self._is_valid_scenario(repaired) else obstacles

    def _slide_along_path(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        index = random.randrange(len(child))
        obstacle = child[index]
        _, _, heading = self._nearest_reference_pose(
            float(obstacle.position.x),
            float(obstacle.position.y),
        )
        x, y = self._path_frame(
            float(obstacle.position.x),
            float(obstacle.position.y),
            heading,
            along=random.gauss(0.0, 4.0),
            lateral=random.gauss(0.0, 1.0),
        )
        child[index] = self._make_obstacle(
            x=x,
            y=y,
            l=float(obstacle.size.l),
            w=float(obstacle.size.w),
            h=float(obstacle.size.h),
            r=float(obstacle.position.r),
        )
        child = self._repair_scenario(child)
        return child if self._is_valid_scenario(child) else obstacles

    def _resize_obstacle(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        index = random.randrange(len(child))
        obstacle = child[index]
        child[index] = self._make_obstacle(
            x=float(obstacle.position.x),
            y=float(obstacle.position.y),
            l=float(obstacle.size.l) + random.gauss(0.5, 1.2),
            w=float(obstacle.size.w) + random.gauss(0.5, 1.2),
            h=float(obstacle.size.h),
            r=float(obstacle.position.r),
        )
        child = self._repair_scenario(child)
        return child if self._is_valid_scenario(child) else obstacles

    def _rotate_obstacle(self, obstacles: List[Obstacle]) -> List[Obstacle]:
        child = self._clone_obstacles(obstacles)
        index = random.randrange(len(child))
        obstacle = child[index]
        child[index] = self._make_obstacle(
            x=float(obstacle.position.x),
            y=float(obstacle.position.y),
            l=float(obstacle.size.l),
            w=float(obstacle.size.w),
            h=float(obstacle.size.h),
            r=float(obstacle.position.r) + random.gauss(0.0, 15.0),
        )
        child = self._repair_scenario(child)
        return child if self._is_valid_scenario(child) else obstacles

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

        if action == "mutate_local" and child:
            index = random.randrange(len(child))
            child[index] = self._mutate_obstacle(child[index], sigma=1.0)
            child = self._repair_scenario(child)
            if self._is_valid_scenario(child):
                return child

        if action == "mutate_strong" and child:
            index = random.randrange(len(child))
            child[index] = self._mutate_obstacle(child[index], sigma=2.0)
            child = self._repair_scenario(child)
            if self._is_valid_scenario(child):
                return child

        if action == "tighten_gate":
            return self._tighten_gate(child)
        if action == "slide_y" and child:
            return self._slide_along_path(child)
        if action == "resize" and child:
            return self._resize_obstacle(child)
        if action == "rotate" and child:
            return self._rotate_obstacle(child)
        return self._random_tg_scenario()

    def _available_actions(self, node: MCTSNode) -> List[str]:
        if not node.obstacles:
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
