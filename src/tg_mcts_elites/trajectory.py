from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple


class TrajectoryMixin:
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

    def _extract_numeric_sequence(self, obj: Any, names: List[str]) -> List[float]:
        if obj is None:
            return []

        lowered = [name.lower() for name in names]

        if hasattr(obj, "columns"):
            try:
                columns = list(obj.columns)
                lower_to_original = {str(c).lower(): c for c in columns}

                for name in lowered:
                    if name in lower_to_original:
                        values = []
                        for raw in list(obj[lower_to_original[name]]):
                            value = self._try_float(raw)
                            if value is not None:
                                values.append(value)
                        if len(values) >= 2:
                            return values
            except Exception:
                pass

        if isinstance(obj, dict):
            for name in names:
                if name in obj:
                    try:
                        values = []
                        for raw in list(obj[name]):
                            value = self._try_float(raw)
                            if value is not None:
                                values.append(value)
                        if len(values) >= 2:
                            return values
                    except Exception:
                        pass

            lower_to_original = {str(k).lower(): k for k in obj.keys()}
            for name in lowered:
                if name in lower_to_original:
                    try:
                        values = []
                        for raw in list(obj[lower_to_original[name]]):
                            value = self._try_float(raw)
                            if value is not None:
                                values.append(value)
                        if len(values) >= 2:
                            return values
                    except Exception:
                        pass

        attrs = dir(obj)
        lower_to_original = {str(attr).lower(): attr for attr in attrs}
        for name in lowered:
            if name in lower_to_original:
                attr = lower_to_original[name]
                try:
                    candidate = getattr(obj, attr)
                    values = []
                    for raw in list(candidate):
                        value = self._try_float(raw)
                        if value is not None:
                            values.append(value)
                    if len(values) >= 2:
                        return values
                except Exception:
                    pass

        return []

    def _normalise_time_sequence(self, times: List[float], n: int) -> List[float]:
        if n <= 0:
            return []
        if len(times) < n:
            return [float(i) for i in range(n)]

        trimmed = [float(value) for value in times[:n]]
        first = trimmed[0]
        trimmed = [value - first for value in trimmed]

        max_abs = max((abs(value) for value in trimmed), default=0.0)
        if max_abs > 1e6:
            trimmed = [value * 1e-6 for value in trimmed]
        elif max_abs > 1e3 and max_abs / max(n - 1, 1) > 10.0:
            trimmed = [value * 1e-3 for value in trimmed]

        if all(abs(trimmed[i] - i) < 1e-9 for i in range(min(len(trimmed), n))):
            return [float(i) for i in range(n)]

        return trimmed

    def _extract_trajectory_series(self, test: Any) -> Tuple[List[float], List[float], List[float], List[float], bool]:
        points, actual = self._extract_trajectory_xy(test)
        n = len(points)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        fallback_z = [0.0 for _ in range(n)]
        fallback_t = [float(i) for i in range(n)]

        trajectory = getattr(test, "trajectory", None)
        if trajectory is None:
            return fallback_t, xs, ys, fallback_z, actual

        candidate_attrs = [
            None,
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

        z_names = ["z", "local_z", "position_z", "alt", "altitude", "height"]
        t_names = [
            "t",
            "time",
            "time_s",
            "flight_time",
            "seconds",
            "timestamp",
            "timestamps",
            "time_boot_ms",
        ]

        for attr in candidate_attrs:
            candidate = trajectory if attr is None else getattr(trajectory, attr, None)
            if candidate is None:
                continue

            zs = self._extract_numeric_sequence(candidate, z_names)
            ts = self._extract_numeric_sequence(candidate, t_names)

            if len(zs) >= n:
                zs = zs[:n]
            else:
                zs = fallback_z

            if len(ts) >= n:
                ts = self._normalise_time_sequence(ts, n)
            else:
                ts = fallback_t

            if len(zs) == n and len(ts) == n:
                return ts, xs, ys, zs, actual

        return fallback_t, xs, ys, fallback_z, actual

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
