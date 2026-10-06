"""Local browser application for interactive city and base-station generation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from collections import deque
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import lru_cache, partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .city import _free_space_slice, _point_cell
from .config import BaseStationConfig, config_from_mapping, load_config
from .pipeline import generate
from .planning import ConnectivityAwarePrimitivePlanner, PlannerConfig, PlanningError
from .profiles import CITY_PROFILES
from .runtime import RadioMapLookup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_REQUEST_BYTES = 1_000_000
LAESIM_LIVE_STATE_TIMEOUT_S = 30.0
MISSION_STOP_GRACE_S = 5.0
DOWNLOAD_FILES = {
    "scene.json",
    "base_station_manifest.json",
    "scene.obj",
    "preview.svg",
    "config.json",
    "manifest.json",
    "radio_manifest.json",
    "radio_volume.npz",
}

RADIO_QUALITY_PRESETS = {
    "quick": {"cell_size_m": 40.0, "samples_per_logical_sector": 4096, "max_depth": 4},
    "balanced": {"cell_size_m": 20.0, "samples_per_logical_sector": 65536, "max_depth": 8},
    "detailed": {"cell_size_m": 10.0, "samples_per_logical_sector": 1048576, "max_depth": 12},
}

# These are transparent experiment presets, not claimed 3GPP service thresholds.
MISSION_PRESETS = {
    "reliable_control": {
        "label": "可靠控制链路（实验）",
        "description": "较严格的连续连接演示；数值是项目实验门限，不是设备标准。",
        "minimum_sinr_db": 5.0,
        "minimum_rss_dbm": -95.0,
        "maximum_outage_fraction": 0.0,
    },
    "telemetry": {
        "label": "普通遥测（实验）",
        "description": "首版默认任务；要求全程满足 0 dB SINR。",
        "minimum_sinr_db": 0.0,
        "minimum_rss_dbm": -105.0,
        "maximum_outage_fraction": 0.0,
    },
    "video": {
        "label": "视频回传（实验）",
        "description": "高质量链路对照；是否可行取决于当前城市和基站部署。",
        "minimum_sinr_db": 10.0,
        "minimum_rss_dbm": -90.0,
        "maximum_outage_fraction": 0.0,
    },
    "best_effort": {
        "label": "尽力而为（研究对照）",
        "description": "用于宽松对照，不代表可靠控制链路。",
        "minimum_sinr_db": -6.0,
        "minimum_rss_dbm": -115.0,
        "maximum_outage_fraction": 0.0,
    },
}


def default_visualizer_output_root() -> Path:
    """Return a user-writable output directory for the local application."""
    override = os.environ.get("WCF_VISUALIZER_OUTPUT")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "WirelessCityFactory" / "outputs"
    return Path.home() / ".wireless_city_factory" / "outputs"


def default_laesim_state_path(project_root: Path = PROJECT_ROOT) -> Path:
    override = os.environ.get("WCF_LAESIM_STATE")
    if override:
        return Path(override).expanduser()
    return project_root / "runtime" / "laesim_live_state.json"


def active_ue_import_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / "runtime" / "active_ue_import.json"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def preset_catalog(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    city_presets = {
        name: {
            "label": {
                "dense_highrise_grid": "密集高层网格",
                "irregular_midrise": "不规则中层城区",
                "compact_radial_lowrise": "紧凑放射低层",
                "sparse_suburban": "稀疏低层郊区",
            }[name],
            **_jsonable(profile),
        }
        for name, profile in CITY_PROFILES.items()
    }
    base_station_presets: dict[str, Any] = {}
    for key, label, filename, description in (
        (
            "low_band_wide_area",
            "低频广域通信站",
            "low_band_wide_area_1km.yaml",
            "700 MHz 广域通信工程参考；频段类别有政策与产业依据，具体射频和部署数值是仿真代理。",
        ),
        (
            "sub6_low_altitude_macro",
            "Sub-6 GHz 低空宏站",
            "sub6_low_altitude_macro_1km.yaml",
            "3.5 GHz 公网低空增强参考；采用 3GPP 宏站几何，功率、站高和密度是可配置仿真代理。",
        ),
        (
            "isac_49_experimental",
            "4.9 GHz 通感一体实验站",
            "isac_49_experimental_1km.yaml",
            "国内公开试点支持的实验类型；4.9 GHz 有案例依据，功率、阵列、站高和密度仍需标定。",
        ),
        (
            "mmwave_isac_experimental",
            "毫米波通感实验站",
            "mmwave_isac_experimental_1km.yaml",
            "面向重点区域的探索性通感预设；遮挡敏感，所有数值均按仿真代理处理。",
        ),
        (
            "uma_reference",
            "3GPP UMa 校准参考",
            "uma_reference_1km.yaml",
            "用于传播模型校准的 UMa 几何参考，不是国内低空基站产品标准。",
        ),
        (
            "umi_reference",
            "3GPP UMi 街谷校准参考",
            "umi_reference_1km.yaml",
            "用于传播模型校准的 UMi 街谷几何参考，不是国内低空基站产品标准。",
        ),
        (
            "project_intermediate",
            "项目中间档（兼容）",
            "project_intermediate_1km.yaml",
            "保留旧实验兼容性的敏感性配置，不属于标准或公开试点参数。",
        ),
    ):
        config = load_config(project_root / "configs" / "base_station_profiles" / filename)
        base_station_presets[key] = {
            "label": label,
            "description": description,
            "values": _jsonable(asdict(config.city.base_stations)),
        }
    return {
        "city": city_presets,
        "base_station": base_station_presets,
        "custom_base_station_defaults": _jsonable(asdict(BaseStationConfig())),
        "mission": MISSION_PRESETS,
        "capabilities": {
            "sionna_rt_installed": importlib.util.find_spec("sionna") is not None
            and importlib.util.find_spec("mitsuba") is not None,
            "radio_quality": RADIO_QUALITY_PRESETS,
        },
    }


def config_from_visualizer_payload(
    payload: dict[str, Any],
    *,
    output: Path | str = "examples/outputs/visualizer",
):
    if not isinstance(payload, dict) or not isinstance(payload.get("city"), dict):
        raise TypeError("Request must contain a city object.")
    seed = payload.get("seed", 20260821)
    city = payload["city"]
    size = city.get("size_m", [])
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError("city.size_m must contain X and Y dimensions.")
    if any(float(value) > 2_000.0 for value in size):
        raise ValueError("The visualizer limits each city dimension to 2,000 m.")
    building = city.get("building", {})
    stations = city.get("base_stations", {})
    if float(building.get("density_per_km2", 0.0)) > 1_000.0:
        raise ValueError("Building density exceeds the visualizer limit of 1,000/km².")
    if float(stations.get("density_per_km2", 0.0)) > 100.0:
        raise ValueError("Base-station density exceeds the visualizer limit of 100/km².")
    radio = payload.get("radio", {})
    if not isinstance(radio, dict):
        raise TypeError("radio must be an object.")
    radio_enabled = bool(radio.get("enabled", False))
    quality = str(radio.get("quality", "quick"))
    if quality not in RADIO_QUALITY_PRESETS:
        raise ValueError(f"Unknown radio quality preset: {quality}")
    quality_values = RADIO_QUALITY_PRESETS[quality]
    carrier_frequency_hz = float(stations.get("carrier_frequency_hz", 4.9e9))
    bandwidth_hz = float(stations.get("bandwidth_hz", 100e6))
    measurement_height_m = float(radio.get("height_m", city.get("task", {}).get("altitude_m", 65.0)))
    if not 35.0 <= measurement_height_m <= 115.0:
        raise ValueError("Radio measurement height must be between 35 and 115 m.")
    raw = {
        "global": {
            "seed": seed,
            "name": str(payload.get("name", "interactive_city")),
            "output": str(output),
        },
        "city": city,
        "radio": {
            "enabled": radio_enabled,
            "preset": "smoke",
            "frequency_hz": carrier_frequency_hz,
            "bandwidth_hz": bandwidth_hz,
            "cell_size_m": quality_values["cell_size_m"],
            "heights_m": [measurement_height_m],
            "samples_per_logical_sector": quality_values["samples_per_logical_sector"],
            "max_depth": quality_values["max_depth"],
            "antenna_model": str(payload.get("antenna_model", "sector3-tr38901-8x8-dualpol")),
            "tx_power_dbm": stations.get("power_dbm", 44.0),
            "downtilt_deg": stations.get("downtilt_deg", 0.0),
            "sector_azimuths_deg": stations.get("sector_azimuths_deg", [0.0, 120.0, 240.0]),
        },
        "ue": {
            "enabled": True,
            "editor_project": "unreal/WirelessCityFactory/WirelessCityFactory.uproject",
            "generate_airsim_settings": True,
            "import_asset_name": "InteractiveCity",
        },
    }
    return config_from_mapping(raw)


def generate_visualizer_run(
    payload: dict[str, Any],
    project_root: Path = PROJECT_ROOT,
    *,
    output_root: Path | None = None,
    resolve_auto_task: bool = True,
) -> dict[str, Any]:
    config = config_from_visualizer_payload(
        payload,
        output=output_root if output_root is not None else "examples/outputs/visualizer",
    )
    result = generate(config, project_root=project_root)
    run_dir = Path(result["output_dir"])
    scene = json.loads((run_dir / "scene.json").read_text(encoding="utf-8"))
    stations = json.loads((run_dir / "base_station_manifest.json").read_text(encoding="utf-8"))
    downloads = {
        name: f"/api/runs/{result['run_id']}/{name}"
        for name in sorted(DOWNLOAD_FILES)
        if (run_dir / name).is_file()
    }
    response = {
        "status": "complete",
        "run_id": result["run_id"],
        "reused": bool(result.get("reused", False)),
        "scene": scene,
        "base_station_manifest": stations,
        "downloads": downloads,
        "laesim": laesim_run_status(run_dir, project_root),
    }
    if (run_dir / "radio_volume.npz").is_file():
        response["radio"] = _radio_layer(run_dir)
    else:
        response["radio"] = None
    if (
        resolve_auto_task
        and response["radio"] is not None
        and config.city.task.selection_mode == "auto"
    ):
        preflight = preflight_visualizer_run(run_dir.parent, {"run_id": result["run_id"]})
        suggestion = preflight.get("suggested_task")
        if suggestion:
            resolved = deepcopy(payload)
            task = resolved["city"].setdefault("task", {})
            task["start_xy_m"] = suggestion["start_xy_m"]
            task["goal_xy_m"] = suggestion["goal_xy_m"]
            task["selection_mode"] = "auto_resolved"
            return generate_visualizer_run(
                resolved,
                project_root,
                output_root=output_root,
                resolve_auto_task=False,
            )
    return response


def _radio_layer(run_dir: Path) -> dict[str, Any]:
    """Return one compact, browser-ready horizontal slice from a radio volume."""
    import numpy as np

    with np.load(run_dir / "radio_volume.npz", allow_pickle=False) as volume:
        x_m = np.asarray(volume["x_m"], dtype=float)
        y_m = np.asarray(volume["y_m"], dtype=float)
        z_m = np.asarray(volume["z_m"], dtype=float)
        power_key = "rss_dbm" if "rss_dbm" in volume.files else "rsrp_dbm"
        rss = np.asarray(volume[power_key], dtype=float)
        sinr = np.asarray(volume["sinr_db"], dtype=float)
        transmitter_ids = [str(value) for value in volume["base_station_ids"].tolist()]
    z_index = 0
    rss_slice = rss[:, z_index, :, :]
    expected_slice_shape = (len(transmitter_ids), len(y_m), len(x_m))
    if rss_slice.shape != expected_slice_shape or sinr[:, z_index, :, :].shape != expected_slice_shape:
        raise ValueError(
            "Radio-map array dimensions do not match the published x/y grid: "
            f"expected {expected_slice_shape}, got RSS {rss_slice.shape} and "
            f"SINR {sinr[:, z_index, :, :].shape}."
        )
    serving_indices = np.argmax(np.nan_to_num(rss_slice, nan=-np.inf), axis=0)
    best_rss = np.take_along_axis(rss_slice, serving_indices[None, :, :], axis=0)[0]
    serving_sinr = np.take_along_axis(
        sinr[:, z_index, :, :], serving_indices[None, :, :], axis=0
    )[0]
    serving_ids = np.asarray(transmitter_ids, dtype=object)[serving_indices]

    detection_threshold_dbm = -125.0
    finite_mask = np.isfinite(best_rss) & np.isfinite(serving_sinr)
    detectable_mask = finite_mask & (best_rss >= detection_threshold_dbm)
    display_rss = np.where(finite_mask, best_rss, detection_threshold_dbm - 20.0)
    display_sinr = np.where(finite_mask, serving_sinr, -30.0)

    def summary(values: Any) -> dict[str, float | None]:
        finite = np.asarray(values, dtype=float)[detectable_mask]
        finite = finite[np.isfinite(finite)]
        if not finite.size:
            return {key: None for key in ("minimum", "p05", "median", "p95", "maximum")}
        return {
            "minimum": float(np.min(finite)),
            "p05": float(np.percentile(finite, 5)),
            "median": float(np.median(finite)),
            "p95": float(np.percentile(finite, 95)),
            "maximum": float(np.max(finite)),
        }

    radio_manifest = json.loads((run_dir / "radio_manifest.json").read_text(encoding="utf-8"))
    radio_config = radio_manifest["metadata"]["config"]
    quality = next(
        (
            name
            for name, values in RADIO_QUALITY_PRESETS.items()
            if float(radio_config.get("cell_size_m", -1.0)) == values["cell_size_m"]
            and int(radio_config.get("samples_per_logical_sector", -1))
            == values["samples_per_logical_sector"]
            and int(radio_config.get("max_depth", -1)) == values["max_depth"]
        ),
        "custom",
    )
    return {
        "status": "complete",
        "backend": "sionna-rt-2.x",
        "height_m": float(z_m[z_index]),
        "frequency_hz": float(radio_config["frequency_hz"]),
        "bandwidth_hz": float(radio_config["bandwidth_hz"]),
        "cell_size_m": float(radio_config.get("cell_size_m", 0.0)),
        "quality": quality,
        "material_frequency_contract": radio_manifest["metadata"].get(
            "material_frequency_contract"
        ),
        "power_metric": "wideband_rss_dbm",
        "sinr_model": "full-buffer-reuse-1-all-sectors",
        "detection_threshold_dbm": detection_threshold_dbm,
        "x_m": x_m.tolist(),
        "y_m": y_m.tolist(),
        "best_rss_dbm": display_rss.ravel().tolist(),
        "best_rsrp_dbm": display_rss.ravel().tolist(),
        "serving_sinr_db": display_sinr.ravel().tolist(),
        "serving_cell": np.where(detectable_mask, serving_ids, None).ravel().tolist(),
        # valid_mask is retained for older browser bundles and now means a real
        # numeric sample. Coverage below reports the receiver detection rule.
        "valid_mask": finite_mask.ravel().tolist(),
        "finite_mask": finite_mask.ravel().tolist(),
        "detectable_mask": detectable_mask.ravel().tolist(),
        "grid_integrity": {
            "finite_cells": int(np.count_nonzero(finite_mask)),
            "total_cells": int(finite_mask.size),
            "fraction": float(np.mean(finite_mask)),
            "complete": bool(np.all(finite_mask)),
        },
        "coverage": {
            "valid_cells": int(np.count_nonzero(detectable_mask)),
            "total_cells": int(detectable_mask.size),
            "fraction": float(np.mean(detectable_mask)),
        },
        "summary": {
            "rss": summary(best_rss),
            "rsrp": summary(best_rss),
            "sinr": summary(serving_sinr),
        },
    }


def _run_dir(output_root: Path, run_id: str) -> Path:
    if Path(run_id).name != run_id:
        raise ValueError("Invalid run ID.")
    run_dir = output_root / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Unknown run: {run_id}")
    return run_dir


@lru_cache(maxsize=2)
def _load_radio_lookup(run_dir: str) -> RadioMapLookup:
    return RadioMapLookup.load(run_dir)


def query_visualizer_radio(output_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("Request must be a JSON object.")
    run_dir = _run_dir(output_root, str(payload.get("run_id", "")))
    position = payload.get("position_m")
    if not isinstance(position, list) or len(position) != 3:
        raise ValueError("position_m must contain x, y and z.")
    lookup = _load_radio_lookup(str(run_dir))
    task = lookup.scene.tasks[0] if lookup.scene.tasks else {}
    minimum_sinr_db = float(task.get("minimum_sinr_db", -6.0))
    minimum_rss_dbm = task.get("minimum_rss_dbm")
    observation = lookup.query(position, outage_threshold_db=minimum_sinr_db)
    if minimum_rss_dbm is not None and not observation.outage:
        serving_rss = (
            None
            if observation.serving_cell is None
            else observation.rss_dbm.get(observation.serving_cell)
        )
        if serving_rss is None or serving_rss < float(minimum_rss_dbm):
            observation = replace(observation, outage=True)
    return observation.to_dict()


def _suggest_connected_task(
    lookup: RadioMapLookup,
    planner: ConnectivityAwarePrimitivePlanner,
    altitude_m: float,
) -> dict[str, list[float]] | None:
    """Find distant endpoints in one geometry-and-radio-feasible grid component."""
    import numpy as np

    x_axis = np.asarray(lookup.x_m, dtype=float)
    y_axis = np.asarray(lookup.y_m, dtype=float)

    geometry_components: tuple[list[bool], list[int], int, int, float] | None = None
    scene = getattr(lookup, "scene", None)
    if scene is not None:
        city_config = scene.metadata.get("city_config", {})
        validation = city_config.get("validation", {})
        resolution = float(validation.get("grid_resolution_m", 5.0))
        _, blocked, labels, nx, ny = _free_space_slice(scene, altitude_m, resolution)
        geometry_components = blocked, labels, nx, ny, resolution

    def point(node: tuple[int, int]) -> np.ndarray:
        yi, xi = node
        return np.array([x_axis[xi], y_axis[yi], altitude_m], dtype=float)

    def geometry_component(candidate: np.ndarray) -> int | None:
        if geometry_components is None:
            return 0
        blocked, labels, nx, ny, resolution = geometry_components
        cell = _point_cell(candidate, resolution, nx, ny)
        index = cell[1] * nx + cell[0]
        return None if blocked[index] else labels[index]

    feasible: set[tuple[int, int]] = set()
    geometry_label: dict[tuple[int, int], int] = {}
    for yi in range(len(y_axis)):
        for xi in range(len(x_axis)):
            node = (yi, xi)
            candidate = point(node)
            if not planner._collision_free(np.asarray([candidate])):
                continue
            component = geometry_component(candidate)
            if component is None:
                continue
            observation = lookup.query(
                tuple(float(value) for value in candidate),
                detection_threshold_dbm=planner.config.detection_threshold_dbm,
                outage_threshold_db=planner.config.minimum_sinr_db,
            )
            if planner._observation_feasible(observation):
                feasible.add(node)
                geometry_label[node] = component
    if len(feasible) < 2:
        return None

    offsets = (
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    )
    components: list[list[tuple[int, int]]] = []
    remaining = set(feasible)
    while remaining:
        start = remaining.pop()
        component = [start]
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for dy, dx in offsets:
                neighbour = (current[0] + dy, current[1] + dx)
                if neighbour not in remaining:
                    continue
                if geometry_label[neighbour] != geometry_label[current]:
                    continue
                if not planner._segment_feasible(point(current), point(neighbour)):
                    continue
                remaining.remove(neighbour)
                component.append(neighbour)
                queue.append(neighbour)
        components.append(component)
    component = max(components, key=len)
    if len(component) < 2:
        return None

    spacing_x = float(np.min(np.diff(x_axis))) if len(x_axis) > 1 else 0.0
    spacing_y = float(np.min(np.diff(y_axis))) if len(y_axis) > 1 else 0.0
    candidates = [point(node) for node in component]

    # Keep automatically selected mission endpoints visibly inside the city. Radio-map
    # samples are cell centres, so choosing the farthest pair without an inset tends to
    # place both endpoints in the outermost cells (for example, 5 m and 995 m).
    if scene is not None and hasattr(scene, "bounds_min_m") and hasattr(scene, "bounds_max_m"):
        lower_xy = np.asarray(scene.bounds_min_m[:2], dtype=float)
        upper_xy = np.asarray(scene.bounds_max_m[:2], dtype=float)
    elif scene is not None and hasattr(scene, "size_m"):
        lower_xy = np.zeros(2, dtype=float)
        upper_xy = np.asarray(scene.size_m[:2], dtype=float)
    else:
        lower_xy = np.array([float(x_axis[0]), float(y_axis[0])], dtype=float)
        upper_xy = np.array([float(x_axis[-1]), float(y_axis[-1])], dtype=float)

    city_span = upper_xy - lower_xy
    boundary_margin = max(
        2.0 * max(spacing_x, spacing_y),
        0.08 * float(np.min(city_span)),
    )
    interior_candidates = [
        candidate
        for candidate in candidates
        if np.all(candidate[:2] >= lower_xy + boundary_margin)
        and np.all(candidate[:2] <= upper_xy - boundary_margin)
    ]
    if len(interior_candidates) >= 2:
        candidates = interior_candidates

    pairs = [
        (first, second)
        for index, first in enumerate(candidates)
        for second in candidates[index + 1 :]
        if abs(first[0] - second[0]) > spacing_x
        and abs(first[1] - second[1]) > spacing_y
    ]
    if not pairs:
        pairs = [
            (first, second)
            for index, first in enumerate(candidates)
            for second in candidates[index + 1 :]
        ]
    start, goal = max(pairs, key=lambda pair: float(np.linalg.norm(pair[1] - pair[0])))
    return {
        "start_xy_m": [float(start[0]), float(start[1])],
        "goal_xy_m": [float(goal[0]), float(goal[1])],
    }


def preflight_visualizer_run(output_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed before a live mission and return actionable diagnostics."""
    run_dir = _run_dir(output_root, str(payload.get("run_id", "")))
    required = (
        "manifest.json",
        "scene.json",
        "base_station_manifest.json",
        "radio_manifest.json",
        "radio_volume.npz",
        "ue_manifest.json",
    )
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        return {
            "status": "blocked",
            "run_id": run_dir.name,
            "checks": [
                {
                    "id": "bundle",
                    "label": "运行数据完整",
                    "status": "error",
                    "detail": f"缺少文件：{', '.join(missing)}",
                }
            ],
            "route": None,
        }

    lookup = RadioMapLookup.load(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    station_manifest = json.loads(
        (run_dir / "base_station_manifest.json").read_text(encoding="utf-8")
    )
    radio_manifest = json.loads((run_dir / "radio_manifest.json").read_text(encoding="utf-8"))
    ue_manifest = json.loads((run_dir / "ue_manifest.json").read_text(encoding="utf-8"))
    radio_layer = _radio_layer(run_dir)
    ue_matches = (
        ue_manifest.get("source_scene_fingerprint") == lookup.scene.fingerprint()
        and ue_manifest.get("base_station_fingerprint")
        == station_manifest.get("base_station_fingerprint")
    )
    checks = [
        {
            "id": "bundle",
            "label": "运行数据完整",
            "status": "pass",
            "detail": f"运行编号 {run_dir.name}",
        },
        {
            "id": "fingerprints",
            "label": "城市、基站、无线与 UE 来源一致",
            "status": "pass" if ue_matches else "error",
            "detail": "所有静态指纹已通过加载校验" if ue_matches else "UE 导入包指纹与城市或基站不一致",
        },
        {
            "id": "radio_grid",
            "label": "信道网格完整",
            "status": "pass" if radio_layer["grid_integrity"]["complete"] else "error",
            "detail": (
                f"{radio_layer['grid_integrity']['finite_cells']} / "
                f"{radio_layer['grid_integrity']['total_cells']} 个网格具有有限数值"
            ),
        },
    ]
    task = lookup.scene.tasks[0]
    altitude = float(task["start_m"][2])
    checks.append(
        {
            "id": "altitude",
            "label": "任务高度可查询",
            "status": "pass" if float(lookup.z_m[0]) <= altitude <= float(lookup.z_m[-1]) else "error",
            "detail": f"任务 {altitude:g} m；无线地图 {float(lookup.z_m[0]):g}–{float(lookup.z_m[-1]):g} m",
        }
    )
    fingerprints = {
        "run_id": run_dir.name,
        "config_fingerprint": manifest.get("config_fingerprint"),
        "scene_fingerprint": lookup.scene.fingerprint(),
        "base_station_fingerprint": station_manifest.get("base_station_fingerprint"),
        "radio_fingerprint": radio_manifest.get("radio_fingerprint"),
        "ue_scene_fingerprint": ue_manifest.get("source_scene_fingerprint"),
    }
    if any(item["status"] == "error" for item in checks):
        return {
            "status": "blocked",
            "run_id": run_dir.name,
            "checks": checks,
            "fingerprints": fingerprints,
            "route": None,
        }

    config = PlannerConfig(
        cruise_speed_mps=5.0,
        minimum_sinr_db=float(task.get("minimum_sinr_db", 0.0)),
        minimum_serving_rss_dbm=(
            None if task.get("minimum_rss_dbm") is None else float(task["minimum_rss_dbm"])
        ),
        maximum_outage_fraction=float(task.get("maximum_outage_fraction", 0.0)),
        enforce_connectivity=True,
        global_guidance_enabled=True,
    )
    try:
        route = ConnectivityAwarePrimitivePlanner(lookup, config).plan(
            tuple(float(value) for value in task["start_m"]),
            tuple(float(value) for value in task["goal_m"]),
        )
    except (PlanningError, ValueError) as exc:
        checks.append(
            {
                "id": "route",
                "label": "存在满足硬约束的连续航迹",
                "status": "error",
                "detail": str(exc),
            }
        )
        suggestion = None
        if task.get("selection_mode") == "auto":
            suggestion = _suggest_connected_task(lookup, ConnectivityAwarePrimitivePlanner(lookup, config), altitude)
        return {
            "status": "blocked",
            "run_id": run_dir.name,
            "checks": checks,
            "fingerprints": fingerprints,
            "route": None,
            "guidance": "请调整任务点、高度、基站部署或任务预设后重新生成；程序不会自动降低门限。",
            "suggested_task": suggestion,
        }

    checks.append(
        {
            "id": "route",
            "label": "存在满足硬约束的连续航迹",
            "status": "pass",
            "detail": (
                f"航迹 {route.metrics.length_m:.1f} m；最低 SINR "
                f"{route.metrics.minimum_sinr_db:.1f} dB"
            ),
        }
    )
    return {
        "status": "ready",
        "run_id": run_dir.name,
        "checks": checks,
        "fingerprints": fingerprints,
        "task": task,
        "route": route.to_dict(),
    }


def laesim_run_status(run_dir: Path, project_root: Path | None = None) -> dict[str, Any]:
    """Describe whether one generated run is ready and imported into UE."""
    manifest_path = run_dir / "ue_manifest.json"
    required = (
        run_dir / "ue_bundle" / "scene.obj",
        run_dir / "ue_bundle" / "import_wireless_city.py",
        run_dir / "ue_bundle" / "settings.json",
    )
    bundle_ready = manifest_path.is_file() and all(path.is_file() for path in required)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if bundle_ready else {}
    fingerprint = str(manifest.get("source_scene_fingerprint", ""))
    result_path = run_dir / "ue_import_result.json"
    import_result = (
        json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    )
    imported = import_result.get("status") == "complete"
    file_import_matches = bool(
        imported
        and fingerprint
        and import_result.get("source_scene_fingerprint") == fingerprint
    )
    active_import: dict[str, Any] = {}
    if project_root is not None and active_ue_import_path(project_root).is_file():
        active_import = json.loads(
            active_ue_import_path(project_root).read_text(encoding="utf-8")
        )
    active_import_matches = bool(
        active_import
        and active_import.get("run_id") == run_dir.name
        and active_import.get("scene_fingerprint") == fingerprint
        and active_import.get("base_station_fingerprint")
        == manifest.get("base_station_fingerprint")
    )
    import_matches = file_import_matches and (
        active_import_matches if project_root is not None else True
    )
    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir.resolve()),
        "bundle_ready": bundle_ready,
        "imported": imported,
        "import_matches": import_matches,
        "active_import_matches": active_import_matches if project_root is not None else None,
        "scene_fingerprint": fingerprint or None,
        "map_path": import_result.get("map_path")
        or (f"/Game/WirelessCity/Maps/{manifest.get('asset_name')}" if bundle_ready else None),
    }


def _find_ue4_root() -> Path:
    candidates = [
        os.environ.get("WCF_UE4_ROOT"),
        os.environ.get("UNREAL_ENGINE_ROOT"),
        r"D:\Program Files\Epic Games\UE_4.27",
        r"C:\Program Files\Epic Games\UE_4.27",
    ]
    launcher_manifest = Path(r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat")
    if launcher_manifest.is_file():
        launcher = json.loads(launcher_manifest.read_text(encoding="utf-8-sig"))
        candidates.extend(
            item.get("InstallLocation")
            for item in launcher.get("InstallationList", [])
            if item.get("AppName") == "UE_4.27"
        )
    for candidate in candidates:
        if not candidate:
            continue
        root = Path(candidate).expanduser()
        if (root / "Engine" / "Binaries" / "Win64" / "UE4Editor-Cmd.exe").is_file():
            return root.resolve()
    raise FileNotFoundError("未找到 UE 4.27，请设置 WCF_UE4_ROOT 后重新启动可视化程序。")


def import_laesim_run(run_dir: Path, project_root: Path) -> dict[str, Any]:
    """Import a validated browser run with the repository's existing UE script."""
    status = laesim_run_status(run_dir)
    if not status["bundle_ready"]:
        raise FileNotFoundError("当前结果没有 LAESim 导入包，请重新生成城市。")
    engine_root = _find_ue4_root()
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise FileNotFoundError("未找到 Windows PowerShell。")
    importer = project_root / "unreal" / "WirelessCityFactory" / "Scripts" / "ImportExampleCity.ps1"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(importer),
        "-BundleRoot",
        str(run_dir),
        "-EngineRoot",
        str(engine_root),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        output = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(f"LAESim 导入失败（退出码 {completed.returncode}）：{output[-4000:]}")
    status = laesim_run_status(run_dir)
    if not status["import_matches"]:
        raise RuntimeError("UE 导入结果与当前城市指纹不一致。")

    registry = {
        "contract": "wireless-city-active-ue-import-v1",
        "run_id": run_dir.name,
        "scene_fingerprint": status["scene_fingerprint"],
        "base_station_fingerprint": json.loads(
            (run_dir / "ue_manifest.json").read_text(encoding="utf-8")
        ).get("base_station_fingerprint"),
        "map_path": status["map_path"],
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    registry_path = active_ue_import_path(project_root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_registry = registry_path.with_name(f".{registry_path.name}.{os.getpid()}.tmp")
    temporary_registry.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary_registry.replace(registry_path)

    settings_source = run_dir / "ue_bundle" / "settings.json"
    settings_dir = Path.home() / "Documents" / "AirSim"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_target = settings_dir / "settings.json"
    if settings_target.is_file() and settings_target.read_bytes() != settings_source.read_bytes():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        shutil.copy2(settings_target, settings_dir / f"settings.json.bak-{stamp}")
    shutil.copy2(settings_source, settings_target)
    return {
        **laesim_run_status(run_dir, project_root),
        "status": "complete",
        "settings_path": str(settings_target),
        "engine_root": str(engine_root),
    }


def open_laesim_run(run_dir: Path, project_root: Path) -> dict[str, Any]:
    status = laesim_run_status(run_dir, project_root)
    if not status["import_matches"]:
        raise RuntimeError("请先把当前城市导入 LAESim。")
    engine_root = _find_ue4_root()
    editor = engine_root / "Engine" / "Binaries" / "Win64" / "UE4Editor.exe"
    project = project_root / "unreal" / "WirelessCityFactory" / "WirelessCityFactory.uproject"
    subprocess.Popen([str(editor), str(project), str(status["map_path"])], close_fds=True)
    return {**status, "status": "opening"}


def read_laesim_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "idle"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != "wireless-city-laesim-live-v1":
        raise ValueError("LAESim live-state contract is not supported.")
    age_s = max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
    if age_s > LAESIM_LIVE_STATE_TIMEOUT_S and payload.get("status") != "complete":
        return {
            "status": "idle",
            "stale": True,
            "last_status": payload.get("status"),
            "last_run_dir": payload.get("run_dir"),
        }
    return payload


def load_laesim_context(
    path: Path,
    project_root: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    state = read_laesim_state(path)
    if state.get("status") == "idle":
        return state
    run_dir = Path(str(state.get("run_dir", ""))).resolve()
    allowed_roots = [project_root.resolve()]
    if output_root is not None:
        allowed_roots.append(output_root.resolve())
    if not any(run_dir == root or root in run_dir.parents for root in allowed_roots):
        raise ValueError("LAESim run directory is outside the allowed output roots.")
    scene_path = run_dir / "scene.json"
    station_path = run_dir / "base_station_manifest.json"
    if not scene_path.is_file() or not station_path.is_file():
        raise FileNotFoundError("LAESim run is missing scene or base-station data.")
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    stations = json.loads(station_path.read_text(encoding="utf-8"))
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    radio_manifest = json.loads((run_dir / "radio_manifest.json").read_text(encoding="utf-8"))
    ue_manifest = json.loads((run_dir / "ue_manifest.json").read_text(encoding="utf-8"))
    expected = {
        "run_id": run_dir.name,
        "config_fingerprint": run_manifest.get("config_fingerprint"),
        "scene_fingerprint": scene.get("metadata", {}).get("scene_fingerprint"),
        "base_station_fingerprint": stations.get("base_station_fingerprint"),
        "radio_fingerprint": radio_manifest.get("radio_fingerprint"),
        "ue_scene_fingerprint": ue_manifest.get("source_scene_fingerprint"),
    }
    if state.get("fingerprints") != expected:
        raise ValueError(
            "LAESim live-state fingerprints do not match the selected run; restart the mission."
        )
    return {
        "status": state["status"],
        "session_id": state["session_id"],
        "run_id": run_dir.name,
        "scene": scene,
        "base_station_manifest": stations,
        "radio": _radio_layer(run_dir) if (run_dir / "radio_volume.npz").is_file() else None,
        "laesim": {**laesim_run_status(run_dir, project_root), "actions_available": False},
    }


class LAESimMissionManager:
    """Own at most one live LAESim mission launched by the local web app."""

    def __init__(self, project_root: Path, live_state_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.live_state_path = live_state_path.resolve()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._console_stream: Any | None = None
        self._stop_file: Path | None = None
        self._stop_requested_at: float | None = None
        self._state: dict[str, Any] = {"status": "idle", "running": False}

    def _refresh_locked(self) -> None:
        if self._process is None:
            return
        return_code = self._process.poll()
        if (
            return_code is None
            and self._stop_requested_at is not None
            and time.monotonic() - self._stop_requested_at > MISSION_STOP_GRACE_S
        ):
            self._process.terminate()
            self._state.update(
                {
                    "status": "stopping",
                    "message": "任务未在安全停止期限内退出，正在终止任务进程。",
                }
            )
            return
        if return_code is None:
            return
        stopped = self._stop_requested_at is not None
        self._state.update(
            {
                "status": "stopped" if stopped else ("complete" if return_code == 0 else "error"),
                "running": False,
                "return_code": int(return_code),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if self._console_stream is not None:
            self._console_stream.close()
            self._console_stream = None
        if self._stop_file is not None:
            self._stop_file.unlink(missing_ok=True)
        self._process = None
        self._stop_requested_at = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            return dict(self._state)

    def start(self, run_dir: Path) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is not None:
                raise RuntimeError("已有 LAESim 任务正在运行，请先停止或等待任务完成。")
            import_status = laesim_run_status(run_dir, self.project_root)
            if not import_status["import_matches"]:
                raise RuntimeError("当前运行尚未正确导入 LAESim，请先导入并打开对应场景。")
            preflight = preflight_visualizer_run(run_dir.parent, {"run_id": run_dir.name})
            if preflight.get("status") != "ready":
                raise RuntimeError("当前任务未通过运行前检查，请先在任务页处理诊断项。")
            python_executable = self.project_root / ".venv-airsim310" / "Scripts" / "python.exe"
            mission_script = self.project_root / "scripts" / "run_laesim_connectivity_mission.py"
            if not python_executable.is_file():
                raise FileNotFoundError(f"AirSim Python 环境不存在：{python_executable}")
            if not mission_script.is_file():
                raise FileNotFoundError(f"任务脚本不存在：{mission_script}")

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            mission_dir = self.project_root / "runtime" / "missions"
            mission_dir.mkdir(parents=True, exist_ok=True)
            output_path = mission_dir / f"{run_dir.name}-{stamp}.jsonl"
            console_path = mission_dir / f"{run_dir.name}-{stamp}.log"
            stop_file = mission_dir / f"{run_dir.name}-{stamp}.stop"
            stop_file.unlink(missing_ok=True)
            self.live_state_path.unlink(missing_ok=True)
            command = [
                str(python_executable),
                str(mission_script),
                "--run-dir",
                str(run_dir),
                "--output",
                str(output_path),
                "--visualizer-state",
                str(self.live_state_path),
                "--stop-file",
                str(stop_file),
            ]
            environment = os.environ.copy()
            source_root = str(self.project_root / "src")
            environment["PYTHONPATH"] = os.pathsep.join(
                item for item in (source_root, environment.get("PYTHONPATH", "")) if item
            )
            console_stream = console_path.open("wb")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.project_root),
                    env=environment,
                    stdout=console_stream,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                console_stream.close()
                raise
            self._process = process
            self._console_stream = console_stream
            self._stop_file = stop_file
            self._stop_requested_at = None
            self._state = {
                "status": "running",
                "running": True,
                "run_id": run_dir.name,
                "pid": process.pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "output_path": str(output_path),
                "console_path": str(console_path),
            }
            return dict(self._state)

    def stop(self, expected_run_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is None:
                raise RuntimeError("当前没有正在运行的 LAESim 任务。")
            if expected_run_id and self._state.get("run_id") != expected_run_id:
                raise RuntimeError("正在运行的任务不属于当前网页场景，未执行停止操作。")
            assert self._stop_file is not None
            self._stop_file.write_text("stop\n", encoding="ascii")
            self._stop_requested_at = time.monotonic()
            self._state.update(
                {
                    "status": "stopping",
                    "running": True,
                    "message": "正在请求无人机悬停并释放控制权…",
                }
            )
            return dict(self._state)

    def shutdown(self) -> None:
        with self._lock:
            self._refresh_locked()
            if self._process is None:
                return
            assert self._stop_file is not None
            self._stop_file.write_text("stop\n", encoding="ascii")
            self._stop_requested_at = time.monotonic()
            process = self._process
        try:
            process.wait(timeout=MISSION_STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        with self._lock:
            self._refresh_locked()


class VisualizerHandler(SimpleHTTPRequestHandler):
    server_version = "WirelessCityVisualizer/1.0"

    def __init__(
        self,
        *args: Any,
        project_root: Path,
        output_root: Path,
        live_state_path: Path,
        mission_manager: LAESimMissionManager,
        **kwargs: Any,
    ) -> None:
        self.project_root = project_root
        self.output_root = output_root
        self.live_state_path = live_state_path
        self.mission_manager = mission_manager
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        # This is a local, stateful application. Stale HTML can otherwise keep
        # loading an older JavaScript bundle after an update.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/presets":
            self._send_json(preset_catalog(self.project_root))
            return
        if path == "/api/laesim/state":
            try:
                self._send_json(read_laesim_state(self.live_state_path))
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                self._send_json(
                    {"error": str(exc), "error_type": type(exc).__name__},
                    HTTPStatus.BAD_REQUEST,
                )
            return
        if path == "/api/laesim/mission-status":
            self._send_json(self.mission_manager.status())
            return
        if path == "/api/laesim/context":
            try:
                self._send_json(
                    load_laesim_context(
                        self.live_state_path,
                        self.project_root,
                        self.output_root,
                    )
                )
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                self._send_json(
                    {"error": str(exc), "error_type": type(exc).__name__},
                    HTTPStatus.BAD_REQUEST,
                )
            return
        if path == "/api/laesim/run-status":
            try:
                run_id = parse_qs(parsed.query).get("run_id", [""])[0]
                self._send_json(
                    laesim_run_status(_run_dir(self.output_root, run_id), self.project_root)
                )
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                self._send_json(
                    {"error": str(exc), "error_type": type(exc).__name__},
                    HTTPStatus.BAD_REQUEST,
                )
            return
        if path.startswith("/api/runs/"):
            self._serve_run_file(path)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {
            "/api/generate",
            "/api/preflight",
            "/api/radio/query",
            "/api/laesim/import",
            "/api/laesim/open",
            "/api/laesim/start",
            "/api/laesim/stop",
        }:
            self._send_json({"error": "Unknown API endpoint."}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body is empty or too large.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/generate":
                result = generate_visualizer_run(
                    payload,
                    self.project_root,
                    output_root=self.output_root,
                )
            elif path == "/api/preflight":
                result = preflight_visualizer_run(self.output_root, payload)
            elif path == "/api/radio/query":
                result = query_visualizer_radio(self.output_root, payload)
            elif path == "/api/laesim/stop":
                result = self.mission_manager.stop(str(payload.get("run_id", "")) or None)
            else:
                run_dir = _run_dir(self.output_root, str(payload.get("run_id", "")))
                if path == "/api/laesim/import":
                    result = import_laesim_run(run_dir, self.project_root)
                elif path == "/api/laesim/start":
                    result = self.mission_manager.start(run_dir)
                else:
                    result = open_laesim_run(run_dir, self.project_root)
            self._send_json(result)
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
            RuntimeError,
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            self._send_json(
                {"error": str(exc), "error_type": type(exc).__name__},
                HTTPStatus.BAD_REQUEST,
            )

    def _serve_run_file(self, path: str) -> None:
        parts = [unquote(item) for item in path.split("/") if item]
        if len(parts) != 4 or parts[:2] != ["api", "runs"]:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        run_id, filename = parts[2], parts[3]
        if Path(run_id).name != run_id or filename not in DOWNLOAD_FILES:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        target = self.output_root / run_id / filename
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        content_type = {
            ".json": "application/json; charset=utf-8",
            ".obj": "text/plain; charset=ascii",
            ".svg": "image/svg+xml",
        }.get(target.suffix.lower(), "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        if urlparse(self.path).path == "/api/laesim/mission-status":
            return
        print(f"[visualizer] {self.address_string()} {format % args}")


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Prevent multiple Windows processes from sharing the same listening port."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def _server(
    host: str,
    port: int,
    project_root: Path,
    output_root: Path,
    live_state_path: Path | None = None,
) -> tuple[ThreadingHTTPServer, int]:
    resolved_live_state_path = live_state_path or default_laesim_state_path(project_root)
    mission_manager = LAESimMissionManager(project_root, resolved_live_state_path)
    handler = partial(
        VisualizerHandler,
        project_root=project_root,
        output_root=output_root,
        live_state_path=resolved_live_state_path,
        mission_manager=mission_manager,
    )
    for candidate in range(port, port + 20):
        try:
            server = ExclusiveThreadingHTTPServer((host, candidate), handler)
            server.mission_manager = mission_manager  # type: ignore[attr-defined]
            return server, candidate
        except OSError as exc:
            if exc.errno not in {13, 48, 98, 10013, 10048} and getattr(
                exc, "winerror", None
            ) not in {10013, 10048}:
                raise
    raise OSError(f"No available port between {port} and {port + 19}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Wireless City Factory local 3D visualizer.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not WEB_ROOT.is_dir():
        raise FileNotFoundError(f"Visualizer assets are missing: {WEB_ROOT}")
    output_root = default_visualizer_output_root()
    server, port = _server(args.host, args.port, PROJECT_ROOT, output_root)
    url = f"http://{args.host}:{port}/"
    print(f"Wireless City Factory visualizer: {url}")
    print(f"Generated files: {output_root}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.mission_manager.shutdown()  # type: ignore[attr-defined]
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
