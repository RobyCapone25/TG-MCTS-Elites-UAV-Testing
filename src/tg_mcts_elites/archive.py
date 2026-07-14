from __future__ import annotations

import math
from typing import List, Tuple

from aerialist.px4.obstacle import Obstacle

from .models import EvalResult


class ArchiveMixin:
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
