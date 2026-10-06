"""Deterministic online observations backed by an offline Sionna radio map."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from laesim_scene.schema import Scene, load_scene

from .base_stations import load_base_station_manifest


class RadioMapError(RuntimeError):
    """The offline radio map cannot serve a valid observation."""


class PositionOutOfBoundsError(RadioMapError):
    """The requested canonical position lies outside the scene or height range."""


@dataclass(frozen=True)
class RadioObservation:
    position_m: tuple[float, float, float]
    interpolation: str
    detected_cells: list[dict[str, Any]]
    rss_dbm: dict[str, float]
    serving_cell: str | None
    sinr_db: float | None
    outage: bool
    detection_threshold_dbm: float
    outage_threshold_db: float

    @property
    def rsrp_dbm(self) -> dict[str, float]:
        """Compatibility alias; v3 called the wideband RSS value RSRP."""
        return self.rss_dbm

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_m": list(self.position_m),
            "interpolation": self.interpolation,
            "detected_cells": self.detected_cells,
            "rss_dbm": self.rss_dbm,
            # Compatibility alias for clients written against the v3 response.
            "rsrp_dbm": self.rss_dbm,
            "serving_cell": self.serving_cell,
            "sinr_db": self.sinr_db,
            "outage": self.outage,
            "detection_threshold_dbm": self.detection_threshold_dbm,
            "outage_threshold_db": self.outage_threshold_db,
        }


class RadioMapLookup:
    """Validate and query one generated radio run using trilinear interpolation."""

    def __init__(
        self,
        scene: Scene,
        transmitter_ids: tuple[str, ...],
        x_m: np.ndarray,
        y_m: np.ndarray,
        z_m: np.ndarray,
        path_gain_linear: np.ndarray,
        metadata: dict[str, Any],
    ) -> None:
        self.scene = scene
        self.transmitter_ids = transmitter_ids
        self.x_m = _axis(x_m, "x_m")
        self.y_m = _axis(y_m, "y_m")
        self.z_m = _axis(z_m, "z_m")
        self.path_gain_linear = np.asarray(path_gain_linear, dtype=float)
        self.metadata = metadata
        expected_shape = (len(transmitter_ids), len(self.z_m), len(self.y_m), len(self.x_m))
        if self.path_gain_linear.shape != expected_shape:
            raise RadioMapError(f"path_gain_linear shape must be {expected_shape}.")
        if not np.all(np.isfinite(self.path_gain_linear)) or np.any(self.path_gain_linear < 0.0):
            raise RadioMapError("path_gain_linear must contain finite non-negative values.")
        config = metadata.get("config", {})
        powers = metadata.get("transmitter_power_dbm")
        if powers is None:
            powers = [float(config["tx_power_dbm"])] * len(transmitter_ids)
        self.tx_power_dbm = np.asarray(powers, dtype=float)
        if self.tx_power_dbm.shape != (len(transmitter_ids),) or not np.all(np.isfinite(self.tx_power_dbm)):
            raise RadioMapError("Transmitter powers do not match transmitter IDs.")
        self.bandwidth_hz = float(config["bandwidth_hz"])
        self.temperature_k = float(config["temperature_k"])
        self.noise_figure_db = float(config["noise_figure_db"])
        self.sector_azimuths_deg = tuple(float(value) for value in config.get("sector_azimuths_deg", []))
        self.downtilt_deg = float(config.get("downtilt_deg", 0.0))
        self.antenna_model = str(metadata.get("antenna_model", config.get("antenna_model", "unknown")))
        if self.bandwidth_hz <= 0.0 or self.temperature_k <= 0.0:
            raise RadioMapError("Radio bandwidth and temperature must be positive.")
        self._stations = {str(item["base_station_id"]): item for item in scene.base_stations}
        self._transmitter_metadata = {
            tx_id: self._metadata_for_transmitter(tx_id) for tx_id in self.transmitter_ids
        }

    @classmethod
    def load(cls, run_dir: Path | str) -> RadioMapLookup:
        root = Path(run_dir)
        scene = load_scene(root / "scene.json")
        station_manifest = load_base_station_manifest(root / "base_station_manifest.json", scene)
        manifest = json.loads((root / "radio_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "complete":
            raise RadioMapError("radio_manifest.json is not complete.")
        if manifest.get("scene_fingerprint") != scene.fingerprint():
            raise RadioMapError("Radio map and scene fingerprints do not match.")
        if manifest.get("metadata", {}).get("base_station_fingerprint") != station_manifest.get(
            "base_station_fingerprint"
        ):
            raise RadioMapError("Radio map and base-station manifest fingerprints do not match.")
        volume_path = root / str(manifest["radio_volume"])
        expected_hash = str(manifest.get("radio_volume_sha256", ""))
        if not expected_hash or _sha256(volume_path) != expected_hash:
            raise RadioMapError("Radio volume SHA-256 does not match its manifest.")
        with np.load(volume_path, allow_pickle=False) as volume:
            metadata = json.loads(str(volume["metadata_json"].item()))
            transmitter_ids = tuple(str(value) for value in volume["base_station_ids"].tolist())
            if tuple(metadata.get("transmitter_ids", [])) != transmitter_ids:
                raise RadioMapError("Radio transmitter IDs do not match the stored metadata.")
            return cls(
                scene,
                transmitter_ids,
                volume["x_m"],
                volume["y_m"],
                volume["z_m"],
                volume["path_gain_linear"],
                metadata,
            )

    def query(
        self,
        position_m: tuple[float, float, float] | list[float],
        *,
        detection_threshold_dbm: float = -125.0,
        outage_threshold_db: float = -6.0,
    ) -> RadioObservation:
        position = tuple(float(value) for value in position_m)
        if len(position) != 3 or not all(math.isfinite(value) for value in position):
            raise ValueError("position_m must contain three finite values.")
        gains = self._interpolate(position)
        rss = self.tx_power_dbm + 10.0 * np.log10(np.maximum(gains, np.finfo(float).tiny))
        detected_indices = [index for index, value in enumerate(rss) if value >= detection_threshold_dbm]
        detected_cells = [self._transmitter_metadata[self.transmitter_ids[index]] for index in detected_indices]
        rss_by_cell = {self.transmitter_ids[index]: float(rss[index]) for index in detected_indices}
        if not detected_indices:
            return RadioObservation(
                position, "trilinear-linear-path-gain", [], {}, None, None, True,
                detection_threshold_dbm, outage_threshold_db,
            )
        serving_index = int(np.argmax(rss))
        serving_cell = self.transmitter_ids[serving_index]
        received_w = gains * 10.0 ** ((self.tx_power_dbm - 30.0) / 10.0)
        noise_w = 1.380649e-23 * self.temperature_k * self.bandwidth_hz * 10.0 ** (self.noise_figure_db / 10.0)
        interference_w = float(np.sum(received_w) - received_w[serving_index])
        sinr_linear = float(received_w[serving_index]) / max(noise_w + interference_w, np.finfo(float).tiny)
        sinr_db = 10.0 * math.log10(max(sinr_linear, np.finfo(float).tiny))
        return RadioObservation(
            position,
            "trilinear-linear-path-gain",
            detected_cells,
            rss_by_cell,
            serving_cell,
            sinr_db,
            sinr_db < outage_threshold_db,
            detection_threshold_dbm,
            outage_threshold_db,
        )

    def canonical_from_airsim_ned(
        self,
        ned_position_m: tuple[float, float, float] | list[float],
        *,
        task_id: str | None = None,
    ) -> tuple[float, float, float]:
        tasks = self.scene.tasks
        if not tasks:
            raise RadioMapError("Scene has no task start to define the AirSim NED origin.")
        if task_id is None:
            task = tasks[0]
        else:
            task = next((item for item in tasks if str(item["task_id"]) == task_id), None)
            if task is None:
                raise RadioMapError(f"Unknown task_id: {task_id}")
        north, east, down = (float(value) for value in ned_position_m)
        start_x, start_y, start_z = (float(value) for value in task["start_m"])
        return (start_x + north, start_y - east, start_z - down)

    def airsim_ned_from_canonical(
        self,
        scene_position_m: tuple[float, float, float] | list[float],
        *,
        task_id: str | None = None,
    ) -> tuple[float, float, float]:
        tasks = self.scene.tasks
        if not tasks:
            raise RadioMapError("Scene has no task start to define the AirSim NED origin.")
        if task_id is None:
            task = tasks[0]
        else:
            task = next((item for item in tasks if str(item["task_id"]) == task_id), None)
            if task is None:
                raise RadioMapError(f"Unknown task_id: {task_id}")
        x, y, z = (float(value) for value in scene_position_m)
        start_x, start_y, start_z = (float(value) for value in task["start_m"])
        return (x - start_x, start_y - y, start_z - z)

    def _interpolate(self, position: tuple[float, float, float]) -> np.ndarray:
        x, y, z = position
        bounds_min, bounds_max = self.scene.bounds_min_m, self.scene.bounds_max_m
        ix = _weights(self.x_m, x, bounds_min[0], bounds_max[0], "x")
        iy = _weights(self.y_m, y, bounds_min[1], bounds_max[1], "y")
        iz = _weights(self.z_m, z, float(self.z_m[0]), float(self.z_m[-1]), "z")
        result = np.zeros(len(self.transmitter_ids), dtype=float)
        for zi, zw in iz:
            for yi, yw in iy:
                for xi, xw in ix:
                    result += self.path_gain_linear[:, zi, yi, xi] * zw * yw * xw
        return result

    def _metadata_for_transmitter(self, transmitter_id: str) -> dict[str, Any]:
        station_id = next(
            (candidate for candidate in self._stations if transmitter_id == candidate or transmitter_id.startswith(candidate + "-sector-")),
            None,
        )
        if station_id is None:
            raise RadioMapError(f"Transmitter {transmitter_id} has no matching base station.")
        station = self._stations[station_id]
        sector_index = None
        sector_azimuth_deg = None
        sector_downtilt_deg = None
        if transmitter_id != station_id:
            try:
                sector_index = int(transmitter_id.rsplit("-sector-", 1)[1])
                sector = station["sectors"][sector_index]
                if str(sector["sector_id"]) != transmitter_id:
                    raise ValueError("sector ID mismatch")
                sector_azimuth_deg = float(sector["azimuth_deg"])
                sector_downtilt_deg = float(sector["downtilt_deg"])
            except (ValueError, IndexError) as exc:
                raise RadioMapError(f"Transmitter {transmitter_id} has invalid sector metadata.") from exc
        transmitter_index = self.transmitter_ids.index(transmitter_id)
        return {
            "cell_id": transmitter_id,
            "site_id": station_id,
            "position_m": [float(value) for value in station["position_m"]],
            "nominal_tx_power_dbm": float(self.tx_power_dbm[transmitter_index]),
            "carrier_frequency_hz": float(self.metadata["config"]["frequency_hz"]),
            "bandwidth_hz": float(self.metadata["config"]["bandwidth_hz"]),
            "sector_index": sector_index,
            "sector_azimuth_deg": sector_azimuth_deg,
            "downtilt_deg": sector_downtilt_deg,
            "antenna_model": self.antenna_model,
        }


def _axis(values: np.ndarray, name: str) -> np.ndarray:
    axis = np.asarray(values, dtype=float)
    if axis.ndim != 1 or len(axis) == 0 or not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0.0):
        raise RadioMapError(f"{name} must be finite and strictly increasing.")
    return axis


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _weights(axis: np.ndarray, value: float, lower: float, upper: float, name: str) -> list[tuple[int, float]]:
    # AirSim/UE centimetre-to-metre conversion can drift by sub-millimetres at a boundary.
    tolerance = 1e-4
    if value < lower - tolerance or value > upper + tolerance:
        raise PositionOutOfBoundsError(f"{name}={value} lies outside [{lower}, {upper}].")
    if value <= axis[0]:
        return [(0, 1.0)]
    if value >= axis[-1]:
        return [(len(axis) - 1, 1.0)]
    high = int(np.searchsorted(axis, value, side="right"))
    low = high - 1
    fraction = (value - float(axis[low])) / (float(axis[high]) - float(axis[low]))
    return [(low, 1.0 - fraction), (high, fraction)]
