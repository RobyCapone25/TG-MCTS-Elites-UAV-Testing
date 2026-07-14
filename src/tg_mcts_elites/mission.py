from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


class MissionPlanError(RuntimeError):
    """The case-study mission cannot be converted into a local reference path."""


class MissionPlanMixin:
    """Read the mission referenced by the case-study YAML.

    QGroundControl ``.plan`` files store waypoints as latitude/longitude pairs.
    They are converted to the local ENU convention used by the obstacle domain:
    ``x = east`` and ``y = north`` relative to the planned home position.
    """

    EARTH_RADIUS_M = 6_378_137.0
    REFERENCE_SAMPLE_STEP_M = 1.0

    def _load_case_study_mapping(self) -> Dict[str, Any]:
        path = Path(self.case_study_file).expanduser().resolve()
        try:
            with path.open("r", encoding="utf-8") as stream:
                data = yaml.safe_load(stream) or {}
        except (OSError, yaml.YAMLError) as error:
            raise MissionPlanError(
                f"Cannot read case-study YAML {path}: {error}"
            ) from error

        if not isinstance(data, dict):
            raise MissionPlanError(f"Case-study YAML must contain a mapping: {path}")
        return data

    def _find_mission_file_value(self, value: Any) -> Optional[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                normalised = str(key).lower().replace("-", "_")
                if normalised in {"mission_file", "missionfile"} and isinstance(child, str):
                    if child.strip():
                        return child.strip()
            for child in value.values():
                result = self._find_mission_file_value(child)
                if result:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = self._find_mission_file_value(child)
                if result:
                    return result
        return None

    def _resolve_mission_plan_path(self) -> Path:
        mapping = self._load_case_study_mapping()
        raw = self._find_mission_file_value(mapping)
        if not raw:
            raise MissionPlanError(
                f"No mission_file entry was found in {self.case_study_file}."
            )

        case_path = Path(self.case_study_file).expanduser().resolve()
        raw_path = Path(raw).expanduser()
        candidates: List[Path] = []

        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            # Aerialist examples commonly use a repository-root-relative path,
            # while external case studies may use a YAML-relative path.
            candidates.extend(
                [
                    Path.cwd() / raw_path,
                    case_path.parent / raw_path,
                    case_path.parent / raw_path.name,
                ]
            )

        seen = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file():
                return resolved

        rendered = ", ".join(str(path.resolve()) for path in candidates)
        raise MissionPlanError(
            f"Mission plan {raw!r} referenced by {case_path} was not found. "
            f"Checked: {rendered}"
        )

    def _valid_geographic_pair(self, latitude: Any, longitude: Any) -> bool:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            return False
        return (
            math.isfinite(lat)
            and math.isfinite(lon)
            and -90.0 <= lat <= 90.0
            and -180.0 <= lon <= 180.0
            and not (abs(lat) < 1e-12 and abs(lon) < 1e-12)
        )

    def _coordinate_from_item(self, item: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        coordinate = item.get("coordinate")
        if isinstance(coordinate, (list, tuple)) and len(coordinate) >= 2:
            if self._valid_geographic_pair(coordinate[0], coordinate[1]):
                return float(coordinate[0]), float(coordinate[1])

        params = item.get("params")
        if isinstance(params, (list, tuple)) and len(params) >= 6:
            if self._valid_geographic_pair(params[4], params[5]):
                return float(params[4]), float(params[5])

        return None

    def _walk_mission_items(self, value: Any) -> Iterable[Tuple[float, float]]:
        if isinstance(value, dict):
            coordinate = self._coordinate_from_item(value)
            if coordinate is not None:
                yield coordinate
            for key, child in value.items():
                if str(key) in {"plannedHomePosition", "homePosition"}:
                    continue
                yield from self._walk_mission_items(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_mission_items(child)

    def _planned_home(self, plan: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        candidates = [
            plan.get("plannedHomePosition"),
            (plan.get("mission") or {}).get("plannedHomePosition")
            if isinstance(plan.get("mission"), dict)
            else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
                if self._valid_geographic_pair(candidate[0], candidate[1]):
                    return float(candidate[0]), float(candidate[1])
        return None

    def _geographic_to_local(
        self,
        latitude: float,
        longitude: float,
        home_latitude: float,
        home_longitude: float,
    ) -> Tuple[float, float]:
        lat = math.radians(latitude)
        lon = math.radians(longitude)
        lat0 = math.radians(home_latitude)
        lon0 = math.radians(home_longitude)
        east = self.EARTH_RADIUS_M * math.cos((lat + lat0) / 2.0) * (lon - lon0)
        north = self.EARTH_RADIUS_M * (lat - lat0)
        return east, north

    def _deduplicate_reference_points(
        self,
        points: List[Tuple[float, float]],
        tolerance_m: float = 0.25,
    ) -> List[Tuple[float, float]]:
        output: List[Tuple[float, float]] = []
        for point in points:
            if not output:
                output.append(point)
                continue
            dx = point[0] - output[-1][0]
            dy = point[1] - output[-1][1]
            if math.hypot(dx, dy) > tolerance_m:
                output.append(point)
        return output

    def _load_reference_path_from_plan(self) -> List[Tuple[float, float]]:
        plan_path = self._resolve_mission_plan_path()
        try:
            with plan_path.open("r", encoding="utf-8") as stream:
                plan = json.load(stream)
        except (OSError, json.JSONDecodeError) as error:
            raise MissionPlanError(f"Cannot read mission plan {plan_path}: {error}") from error

        if not isinstance(plan, dict):
            raise MissionPlanError(f"Mission plan must contain a JSON object: {plan_path}")

        mission = plan.get("mission")
        search_root: Any = mission.get("items", []) if isinstance(mission, dict) else []
        coordinates = list(self._walk_mission_items(search_root))
        home = self._planned_home(plan)

        if home is None and coordinates:
            home = coordinates[0]
        if home is None:
            raise MissionPlanError(
                f"No planned home position or geographic mission waypoint was found in {plan_path}."
            )

        raw_local_points: List[Tuple[float, float]] = [(0.0, 0.0)]
        for latitude, longitude in coordinates:
            raw_local_points.append(
                self._geographic_to_local(latitude, longitude, home[0], home[1])
            )

        raw_local_points = self._deduplicate_reference_points(raw_local_points)
        if len(raw_local_points) < 2:
            raise MissionPlanError(
                f"Mission plan {plan_path} does not define a non-zero local flight path."
            )

        local_points, transform_name = self._select_simulator_frame(raw_local_points)
        self.mission_plan_path = str(plan_path)
        self.mission_path_source = "qgroundcontrol_plan"
        self.mission_frame_transform = transform_name
        return local_points

    def _frame_transformations(self) -> List[Tuple[str, Any]]:
        """Candidate mappings from geographic ENU to the simulator XY frame.

        QGroundControl stores geographic waypoints, while the competition's
        obstacle domain is expressed in the simulator frame. Depending on the
        mission exporter and world configuration, axes can be swapped and one
        or both signs can differ. We infer the mapping from the fixed legal
        obstacle area instead of relying on the mission filename.
        """
        return [
            ("east_north", lambda east, north: (east, north)),
            ("east_south", lambda east, north: (east, -north)),
            ("west_north", lambda east, north: (-east, north)),
            ("west_south", lambda east, north: (-east, -north)),
            ("north_east", lambda east, north: (north, east)),
            ("north_west", lambda east, north: (north, -east)),
            ("south_east", lambda east, north: (-north, east)),
            ("south_west", lambda east, north: (-north, -east)),
        ]

    def _legal_area_overlap_score(
        self,
        path: List[Tuple[float, float]],
    ) -> Tuple[int, float, float]:
        """Return a deterministic score for how much a path crosses the area.

        The first component counts one-metre samples inside the legal obstacle
        rectangle. The second estimates in-area path length. The third favours
        paths that remain near the legal rectangle when two transforms tie.
        """
        inside_count = 0
        inside_length = 0.0
        proximity_penalty = 0.0

        centre_x = 0.5 * (self.X_MIN + self.X_MAX)
        centre_y = 0.5 * (self.Y_MIN + self.Y_MAX)

        for start, end in zip(path, path[1:]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue

            count = max(2, int(math.ceil(length / self.REFERENCE_SAMPLE_STEP_M)))
            previous_inside = False
            step_length = length / count

            for index in range(count + 1):
                t = index / count
                x = start[0] + t * dx
                y = start[1] + t * dy
                inside = self.X_MIN <= x <= self.X_MAX and self.Y_MIN <= y <= self.Y_MAX
                if inside:
                    inside_count += 1
                    if previous_inside:
                        inside_length += step_length
                previous_inside = inside

                clipped_x = min(max(x, self.X_MIN), self.X_MAX)
                clipped_y = min(max(y, self.Y_MIN), self.Y_MAX)
                proximity_penalty += math.hypot(x - clipped_x, y - clipped_y)

        # Larger is better for every returned component.
        return inside_count, inside_length, -proximity_penalty

    def _select_simulator_frame(
        self,
        raw_enu_path: List[Tuple[float, float]],
    ) -> Tuple[List[Tuple[float, float]], str]:
        """Choose the axis/sign mapping that intersects the legal area most.

        This resolves the observed case where a valid mission was represented
        with the forward direction on a negative or swapped geographic axis.
        It remains filename-independent and works for unseen missions that use
        the same fixed competition obstacle domain.
        """
        candidates: List[Tuple[Tuple[int, float, float], int, str, List[Tuple[float, float]]]] = []

        for preference, (name, transform) in enumerate(self._frame_transformations()):
            transformed = [transform(east, north) for east, north in raw_enu_path]
            transformed = self._deduplicate_reference_points(transformed)
            score = self._legal_area_overlap_score(transformed)
            candidates.append((score, -preference, name, transformed))

        best_score, _, best_name, best_path = max(candidates, key=lambda item: (item[0], item[1]))
        if best_score[0] <= 0:
            details = ", ".join(
                f"{name}:inside={score[0]}"
                for score, _, name, _ in candidates
            )
            raise MissionPlanError(
                "The mission path does not intersect the legal obstacle-generation area "
                f"under any supported simulator-frame mapping ({details})."
            )

        return best_path, best_name

    def _mission_reference_path(self) -> List[Tuple[float, float]]:
        cached = getattr(self, "_mission_reference_cache", None)
        if cached is None:
            cached = self._load_reference_path_from_plan()
            self._mission_reference_cache = cached
        return list(cached)

    def _fallback_reference_path(self) -> List[Tuple[float, float]]:
        """Backward-compatible name now backed by the actual mission plan."""
        return self._mission_reference_path()

    def _reference_pose_samples(self) -> List[Tuple[float, float, float]]:
        cached = getattr(self, "_reference_pose_cache", None)
        if cached is not None:
            return list(cached)

        path = self._mission_reference_path()
        samples: List[Tuple[float, float, float]] = []
        for start, end in zip(path, path[1:]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            heading = math.atan2(dy, dx)
            count = max(2, int(math.ceil(length / self.REFERENCE_SAMPLE_STEP_M)))
            for index in range(count + 1):
                t = index / count
                x = start[0] + t * dx
                y = start[1] + t * dy
                if self.X_MIN <= x <= self.X_MAX and self.Y_MIN <= y <= self.Y_MAX:
                    samples.append((x, y, heading))

        if not samples:
            raise MissionPlanError(
                "The mission path does not intersect the legal obstacle-generation area."
            )

        self._reference_pose_cache = samples
        return list(samples)

    def _sample_reference_pose(self) -> Tuple[float, float, float]:
        return random.choice(self._reference_pose_samples())

    def _nearest_reference_pose(self, x: float, y: float) -> Tuple[float, float, float]:
        return min(
            self._reference_pose_samples(),
            key=lambda pose: (pose[0] - x) ** 2 + (pose[1] - y) ** 2,
        )

    def _mission_corridors(self) -> List[float]:
        """Compatibility helper returning path-derived x coordinates."""
        values = sorted({round(x, 1) for x, _, _ in self._reference_pose_samples()})
        return values or [0.0]
