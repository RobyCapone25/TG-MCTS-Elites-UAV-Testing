from __future__ import annotations

import math
import random
from collections import deque
from typing import Dict, List, Optional, Tuple

from aerialist.px4.obstacle import Obstacle


class ValidationMixin:
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
