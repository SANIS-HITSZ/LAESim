"""Canonical, dependency-light scene schema used by every output stage."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .geometry import road_intersects_xy_box

Vec3 = tuple[float, float, float]


def _vec3(value: Iterable[Any], name: str) -> Vec3:
    values = tuple(float(item) for item in value)
    if len(values) != 3:
        raise ValueError(f"{name} must contain three values.")
    return values  # type: ignore[return-value]


@dataclass(frozen=True)
class Scene:
    schema_version: str
    scene_id: str
    seed: int
    units: str
    frame: str
    bounds_min_m: Vec3
    bounds_max_m: Vec3
    roads: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    buildings: list[dict[str, Any]]
    base_stations: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def size_m(self) -> Vec3:
        return tuple(b - a for a, b in zip(self.bounds_min_m, self.bounds_max_m))  # type: ignore[return-value]

    @property
    def center_m(self) -> Vec3:
        return tuple((a + b) / 2.0 for a, b in zip(self.bounds_min_m, self.bounds_max_m))  # type: ignore[return-value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scene_id": self.scene_id,
            "seed": self.seed,
            "units": self.units,
            "frame": self.frame,
            "bounds_m": {"minimum": list(self.bounds_min_m), "maximum": list(self.bounds_max_m)},
            "roads": self.roads,
            "blocks": self.blocks,
            "buildings": self.buildings,
            "base_stations": self.base_stations,
            "tasks": self.tasks,
            "metadata": self.metadata,
        }

    def canonical_dict(self) -> dict[str, Any]:
        value = self.to_dict()
        metadata = dict(value.get("metadata", {}))
        metadata.pop("scene_fingerprint", None)
        value["metadata"] = metadata
        return value

    def fingerprint(self) -> str:
        encoded = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def with_fingerprint(self) -> Scene:
        metadata = dict(self.metadata)
        metadata["scene_fingerprint"] = self.fingerprint()
        return Scene(
            schema_version=self.schema_version,
            scene_id=self.scene_id,
            seed=self.seed,
            units=self.units,
            frame=self.frame,
            bounds_min_m=self.bounds_min_m,
            bounds_max_m=self.bounds_max_m,
            roads=self.roads,
            blocks=self.blocks,
            buildings=self.buildings,
            base_stations=self.base_stations,
            tasks=self.tasks,
            metadata=metadata,
        )

    def validate(self) -> None:
        if self.units != "m" or self.frame != "right-handed,+z-up":
            raise ValueError("Canonical scene must use metres and a right-handed +z-up frame.")
        if self.schema_version != "wireless-city-scene":
            raise ValueError("Scene schema does not match the current contract.")
        if any(a >= b for a, b in zip(self.bounds_min_m, self.bounds_max_m)):
            raise ValueError("Scene bounds must be strictly increasing.")
        self._unique(self.roads, "road_id")
        self._unique(self.blocks, "block_id")
        self._unique(self.buildings, "building_id")
        self._unique(self.base_stations, "base_station_id")
        self._unique(self.tasks, "task_id")
        for road in self.roads:
            start = _vec3(road["start_m"], "road.start_m")
            end = _vec3(road["end_m"], "road.end_m")
            width = float(road["width_m"])
            if width <= 0.0:
                raise ValueError(f"Road {road['road_id']} has non-positive width.")
            self._inside(start, start, self.bounds_min_m, self.bounds_max_m, str(road["road_id"]))
            self._inside(end, end, self.bounds_min_m, self.bounds_max_m, str(road["road_id"]))
        blocks = {str(item["block_id"]): item for item in self.blocks}
        for building in self.buildings:
            center = _vec3(building["center_m"], "building.center_m")
            size = _vec3(building["size_m"], "building.size_m")
            if any(value <= 0.0 for value in size):
                raise ValueError(f"Building {building['building_id']} has non-positive size.")
            minimum, maximum = _box(center, size)
            self._inside(minimum, maximum, self.bounds_min_m, self.bounds_max_m, str(building["building_id"]))
            block = blocks.get(str(building["block_id"]))
            if block is None:
                raise ValueError(f"Building {building['building_id']} references missing block.")
            block_min = tuple(float(value) for value in block["minimum_xy_m"])
            block_max = tuple(float(value) for value in block["maximum_xy_m"])
            if not (block_min[0] <= minimum[0] <= maximum[0] <= block_max[0] and block_min[1] <= minimum[1] <= maximum[1] <= block_max[1]):
                raise ValueError(f"Building {building['building_id']} leaves its block.")
        for index, first in enumerate(self.buildings):
            first_min, first_max = _box(_vec3(first["center_m"], "center"), _vec3(first["size_m"], "size"))
            for second in self.buildings[index + 1 :]:
                second_min, second_max = _box(_vec3(second["center_m"], "center"), _vec3(second["size_m"], "size"))
                if _strict_xy_overlap(first_min, first_max, second_min, second_max):
                    raise ValueError(f"Buildings {first['building_id']} and {second['building_id']} overlap.")
        for building in self.buildings:
            center = _vec3(building["center_m"], "center")
            size = _vec3(building["size_m"], "size")
            minimum, maximum = _box(center, size)
            if any(
                road_intersects_xy_box(road, minimum[:2], maximum[:2])
                for road in self.roads
            ):
                raise ValueError(f"Building {building['building_id']} intersects a road.")
        buildings_by_id = {str(item["building_id"]): item for item in self.buildings}
        building_ids = set(buildings_by_id)
        sector_ids: set[str] = set()
        for station in self.base_stations:
            point = _vec3(station["position_m"], "base station.position_m")
            self._inside(point, point, self.bounds_min_m, self.bounds_max_m, str(station["base_station_id"]))
            if float(station.get("antenna_height_m", point[2])) != point[2]:
                raise ValueError(f"Base station {station['base_station_id']} antenna height does not match position.")
            carrier_frequency_hz = float(station.get("carrier_frequency_hz", 0.0))
            bandwidth_hz = float(station.get("bandwidth_hz", 0.0))
            if not all(
                math.isfinite(value) and value > 0.0
                for value in (carrier_frequency_hz, bandwidth_hz)
            ):
                raise ValueError(f"Base station {station['base_station_id']} has invalid carrier settings.")
            host = station.get("host_building_id")
            if host is not None and str(host) not in building_ids:
                raise ValueError(f"Base station {station['base_station_id']} references missing host building.")
            if host is not None:
                host_building = buildings_by_id[str(host)]
                host_min, host_max = _box(
                    _vec3(host_building["center_m"], "center"),
                    _vec3(host_building["size_m"], "size"),
                )
                if not (
                    host_min[0] <= point[0] <= host_max[0]
                    and host_min[1] <= point[1] <= host_max[1]
                    and point[2] > host_max[2]
                ):
                    raise ValueError(f"Base station {station['base_station_id']} is not above its host rooftop.")
            if any(_strict_point_in_box(point, *_box(_vec3(item["center_m"], "center"), _vec3(item["size_m"], "size"))) for item in self.buildings):
                raise ValueError(f"Base station {station['base_station_id']} lies inside a building volume.")
            sectors = list(station.get("sectors", []))
            if int(station.get("sector_count", len(sectors))) != len(sectors) or not sectors:
                raise ValueError(f"Base station {station['base_station_id']} has an invalid sector count.")
            for index, sector in enumerate(sectors):
                sector_id = str(sector["sector_id"])
                if sector_id in sector_ids:
                    raise ValueError(f"Duplicate sector_id: {sector_id}")
                sector_ids.add(sector_id)
                if int(sector["sector_index"]) != index:
                    raise ValueError(f"Base station {station['base_station_id']} has non-canonical sector indices.")
                azimuth = float(sector["azimuth_deg"])
                downtilt = float(sector["downtilt_deg"])
                power = float(sector["nominal_tx_power_dbm"])
                sector_frequency_hz = float(sector.get("carrier_frequency_hz", 0.0))
                sector_bandwidth_hz = float(sector.get("bandwidth_hz", 0.0))
                if not all(
                    math.isfinite(value)
                    for value in (azimuth, downtilt, power, sector_frequency_hz, sector_bandwidth_hz)
                ):
                    raise ValueError(f"Sector {sector_id} contains non-finite radio metadata.")
                if not 0.0 <= azimuth < 360.0 or not -90.0 <= downtilt <= 90.0:
                    raise ValueError(f"Sector {sector_id} contains invalid orientation metadata.")
                if (
                    sector_frequency_hz != carrier_frequency_hz
                    or sector_bandwidth_hz != bandwidth_hz
                ):
                    raise ValueError(f"Sector {sector_id} carrier settings do not match its site.")
        for index, first in enumerate(self.base_stations):
            first_position = _vec3(first["position_m"], "base station.position_m")
            for second in self.base_stations[index + 1 :]:
                second_position = _vec3(second["position_m"], "base station.position_m")
                distance = math.hypot(first_position[0] - second_position[0], first_position[1] - second_position[1])
                required = max(
                    float(first.get("metadata", {}).get("minimum_separation_m", 0.0)),
                    float(second.get("metadata", {}).get("minimum_separation_m", 0.0)),
                )
                if distance < required - 1e-7:
                    raise ValueError(
                        f"Base stations {first['base_station_id']} and {second['base_station_id']} "
                        f"are closer than {required} m."
                    )
        for task in self.tasks:
            for key in ("start_m", "goal_m"):
                point = _vec3(task[key], f"task.{key}")
                self._inside(point, point, self.bounds_min_m, self.bounds_max_m, f"{task['task_id']}:{key}")
                if any(_strict_point_in_box(point, *_box(_vec3(item["center_m"], "center"), _vec3(item["size_m"], "size"))) for item in self.buildings):
                    raise ValueError(f"Task {task['task_id']} {key} lies inside a building volume.")

    @staticmethod
    def _unique(items: list[dict[str, Any]], key: str) -> None:
        values = [str(item[key]) for item in items]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {key} identifier.")

    @staticmethod
    def _inside(minimum: Vec3, maximum: Vec3, bounds_min: Vec3, bounds_max: Vec3, name: str) -> None:
        if any(a < lo - 1e-7 or b > hi + 1e-7 for a, b, lo, hi in zip(minimum, maximum, bounds_min, bounds_max)):
            raise ValueError(f"{name} lies outside scene bounds.")

    def save_json(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _box(center: Vec3, size: Vec3) -> tuple[Vec3, Vec3]:
    return (
        tuple(c - s / 2.0 for c, s in zip(center, size)),  # type: ignore[return-value]
        tuple(c + s / 2.0 for c, s in zip(center, size)),  # type: ignore[return-value]
    )


def _strict_xy_overlap(first_min: Vec3, first_max: Vec3, second_min: Vec3, second_max: Vec3) -> bool:
    return first_min[0] < second_max[0] - 1e-7 and second_min[0] < first_max[0] - 1e-7 and first_min[1] < second_max[1] - 1e-7 and second_min[1] < first_max[1] - 1e-7


def _strict_point_in_box(point: Vec3, minimum: Vec3, maximum: Vec3) -> bool:
    return all(lo + 1e-7 < value < hi - 1e-7 for value, lo, hi in zip(point, minimum, maximum))


def load_scene(path: Path | str) -> Scene:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    bounds = raw["bounds_m"]
    scene = Scene(
        schema_version=str(raw["schema_version"]),
        scene_id=str(raw["scene_id"]),
        seed=int(raw["seed"]),
        units=str(raw["units"]),
        frame=str(raw["frame"]),
        bounds_min_m=_vec3(bounds["minimum"], "bounds.minimum"),
        bounds_max_m=_vec3(bounds["maximum"], "bounds.maximum"),
        roads=list(raw.get("roads", [])),
        blocks=list(raw.get("blocks", [])),
        buildings=list(raw.get("buildings", [])),
        base_stations=list(raw.get("base_stations", [])),
        tasks=list(raw.get("tasks", [])),
        metadata=dict(raw.get("metadata", {})),
    )
    scene.validate()
    return scene
