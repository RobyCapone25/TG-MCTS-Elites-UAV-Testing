from __future__ import annotations

import math
from typing import List, Tuple

from aerialist.px4.obstacle import Obstacle


class GeometryMixin:
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
