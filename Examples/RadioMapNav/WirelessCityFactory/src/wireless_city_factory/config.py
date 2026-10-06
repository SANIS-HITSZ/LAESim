"""Configuration loading and validation for the wireless city factory."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

MORPHOLOGIES = ("manhattan", "bsp_tjunction", "voronoi", "radial_organic")
GENERATOR_CONTRACT = "wireless-city-generator-v9"
RADIO_CONTRACT = "wireless-city-radio-v4"
ANTENNA_MODELS = (
    "isotropic",
    "sector3-tr38901",
    "sector3-tr38901-ula8",
    "sector3-tr38901-8x4-dualpol",
    "sector3-tr38901-8x8-dualpol",
)
PARAMETER_STATUSES = ("public_verified", "trial_specific", "simulation_proxy", "unknown")

_RADIO_PRESETS: dict[str, dict[str, Any]] = {
    "production_v1": {
        "frequency_hz": 4.9e9,
        "bandwidth_hz": 100e6,
        "noise_figure_db": 9.0,
        "cell_size_m": 2.0,
        "heights_m": [35.0, 65.0, 95.0, 115.0],
        "samples_per_logical_sector": 16_777_216,
        "max_depth": 20,
        "antenna_model": "sector3-tr38901-8x8-dualpol",
        "sector_azimuths_deg": [0.0, 120.0, 240.0],
        "downtilt_deg": 12.0,
        "tx_power_dbm": 44.0,
        "diffraction": False,
        "diffuse_reflection": False,
        "mitsuba_variant": "cuda_ad_mono_polarized",
    },
    "formal": {
        "frequency_hz": 4.9e9,
        "bandwidth_hz": 100e6,
        "noise_figure_db": 9.0,
        "cell_size_m": 2.0,
        "heights_m": [35.0, 65.0, 95.0, 115.0],
        "samples_per_logical_sector": 45_000_000,
        "max_depth": 20,
        "antenna_model": "sector3-tr38901-8x4-dualpol",
        "sector_azimuths_deg": [0.0, 120.0, 240.0],
        "downtilt_deg": 10.0,
        "tx_power_dbm": 53.0,
        "diffraction": False,
        "diffuse_reflection": False,
        "mitsuba_variant": "cuda_ad_mono_polarized",
    },
    "smoke": {
        "frequency_hz": 4.9e9,
        "bandwidth_hz": 100e6,
        "noise_figure_db": 9.0,
        "cell_size_m": 40.0,
        "heights_m": [35.0, 65.0],
        "samples_per_logical_sector": 256,
        "max_depth": 4,
        "antenna_model": "isotropic",
        "sector_azimuths_deg": [0.0, 120.0, 240.0],
        "downtilt_deg": 0.0,
        "tx_power_dbm": 44.0,
        "diffraction": False,
        "diffuse_reflection": False,
        "mitsuba_variant": "cuda_ad_mono_polarized",
    },
}


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number.")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return result


def _integer(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return int(value)


def _vec2(value: Any, name: str, *, positive: bool = False) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain exactly two numbers.")
    result = (_number(value[0], f"{name}[0]"), _number(value[1], f"{name}[1]"))
    if positive and (result[0] <= 0.0 or result[1] <= 0.0):
        raise ValueError(f"{name} values must be positive.")
    return result


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a sequence of strings.")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError(f"{name} must not contain empty values.")
    return result


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass(frozen=True)
class BuildingConfig:
    profile: str = "urban"
    coverage_ratio: float = 0.28
    density_per_km2: float = 180.0
    height_distribution: str = "lognormal"
    height_min_m: float = 8.0
    height_max_m: float = 90.0
    height_mean_m: float = 28.0
    height_std_m: float = 14.0
    footprint_min_m: tuple[float, float] = (8.0, 8.0)
    footprint_max_m: tuple[float, float] = (28.0, 28.0)
    separation_m: float = 5.0


@dataclass(frozen=True)
class RoadConfig:
    grid_spacing_m: float = 80.0
    width_m: float = 12.0
    radial_count: int = 8
    ring_count: int = 2


@dataclass(frozen=True)
class BaseStationConfig:
    preset_id: str = "custom"
    preset_version: str = "1.0.0"
    source_preset_id: str | None = None
    modified_fields: tuple[str, ...] = ()
    deployment_profile: str = "custom"
    function_type: str = "communication"
    source_evidence_level: str = "D"
    parameter_status: str = "simulation_proxy"
    applicable_scenarios: tuple[str, ...] = ()
    placement_family: str = "rooftop_grid"
    density_per_km2: float = 8.0
    height_m: float = 35.0
    height_reference: str = "mast_above_rooftop"
    power_dbm: float = 44.0
    carrier_frequency_hz: float = 4.9e9
    bandwidth_hz: float = 100e6
    antenna_model: str = "sector3-tr38901-8x8-dualpol"
    polarization: str = "cross_dual_slant"
    duplex_mode: str = "unspecified"
    sensing_enabled: bool = False
    sensing_waveform_class: str | None = None
    reference_inter_site_distance_m: float | None = None
    reference_source: str | None = None
    min_separation_m: float = 80.0
    sectors: int = 3
    sector_azimuths_deg: tuple[float, ...] = (0.0, 120.0, 240.0)
    downtilt_deg: float = 0.0
    random_offset_m: float = 0.0


@dataclass(frozen=True)
class TaskConfig:
    altitude_m: float = 50.0
    altitude_range_m: tuple[float, float] = (35.0, 115.0)
    count: int = 1
    start_xy_m: tuple[float, float] | None = None
    goal_xy_m: tuple[float, float] | None = None
    selection_mode: str = "auto"
    constraint_preset: str = "telemetry"
    minimum_sinr_db: float = 0.0
    minimum_rss_dbm: float | None = None
    maximum_outage_fraction: float = 0.0


@dataclass(frozen=True)
class ValidationConfig:
    grid_resolution_m: float = 5.0
    minimum_largest_component_fraction: float = 0.95


@dataclass(frozen=True)
class CityConfig:
    size_m: tuple[float, float] = (400.0, 400.0)
    morphology: str = "manhattan"
    building: BuildingConfig = field(default_factory=BuildingConfig)
    roads: RoadConfig = field(default_factory=RoadConfig)
    base_stations: BaseStationConfig = field(default_factory=BaseStationConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)


@dataclass(frozen=True)
class RadioConfig:
    enabled: bool = False
    preset: str = "smoke"
    backend: str = "sionna_rt"
    frequency_hz: float = 4.9e9
    bandwidth_hz: float = 100e6
    temperature_k: float = 293.0
    noise_figure_db: float = 9.0
    cell_size_m: float = 2.0
    heights_m: tuple[float, ...] = (35.0, 65.0, 95.0, 115.0)
    samples_per_logical_sector: int = 45_000_000
    max_depth: int = 20
    antenna_model: str = "sector3-tr38901-8x4-dualpol"
    sector_azimuths_deg: tuple[float, ...] = (0.0, 120.0, 240.0)
    downtilt_deg: float = 10.0
    tx_power_dbm: float = 53.0
    diffraction: bool = False
    diffuse_reflection: bool = False
    mitsuba_variant: str = "cuda_ad_mono_polarized"
    seed: int | None = None


@dataclass(frozen=True)
class UEConfig:
    enabled: bool = False
    output_format: str = "ue-ready-bundle"
    editor_project: str | None = None
    generate_airsim_settings: bool = True
    import_asset_name: str = "WirelessCity"
    marker_scale_m: float = 2.0


@dataclass(frozen=True)
class FactoryConfig:
    seed: int = 20260821
    output: str = "outputs"
    name: str = "city"
    city: CityConfig = field(default_factory=CityConfig)
    radio: RadioConfig = field(default_factory=RadioConfig)
    ue: UEConfig = field(default_factory=UEConfig)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = self.as_dict()
        payload.pop("output", None)
        payload["generator_contract"] = GENERATOR_CONTRACT
        if self.radio.enabled:
            payload["radio_contract"] = RADIO_CONTRACT
        return payload

    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.fingerprint_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _parse_building(raw: Mapping[str, Any]) -> BuildingConfig:
    value = BuildingConfig(
        profile=str(raw.get("profile", "urban")),
        coverage_ratio=_number(raw.get("coverage_ratio", 0.28), "building.coverage_ratio"),
        density_per_km2=_number(raw.get("density_per_km2", 180.0), "building.density_per_km2", minimum=0.0),
        height_distribution=str(raw.get("height_distribution", raw.get("height_distribution_type", "lognormal"))),
        height_min_m=_number(raw.get("height_min_m", 8.0), "building.height_min_m", minimum=0.1),
        height_max_m=_number(raw.get("height_max_m", 90.0), "building.height_max_m", minimum=0.1),
        height_mean_m=_number(raw.get("height_mean_m", 28.0), "building.height_mean_m", minimum=0.1),
        height_std_m=_number(raw.get("height_std_m", 14.0), "building.height_std_m", minimum=0.0),
        footprint_min_m=_vec2(raw.get("footprint_min_m", [8.0, 8.0]), "building.footprint_min_m", positive=True),
        footprint_max_m=_vec2(raw.get("footprint_max_m", [28.0, 28.0]), "building.footprint_max_m", positive=True),
        separation_m=_number(raw.get("separation_m", 5.0), "building.separation_m", minimum=0.0),
    )
    if not 0.0 <= value.coverage_ratio < 1.0:
        raise ValueError("building.coverage_ratio must be in [0, 1).")
    if value.height_max_m < value.height_min_m:
        raise ValueError("building.height_max_m must be >= height_min_m.")
    if any(a > b for a, b in zip(value.footprint_min_m, value.footprint_max_m)):
        raise ValueError("building footprint minimum must not exceed maximum.")
    if value.height_distribution not in {"uniform", "normal", "lognormal"}:
        raise ValueError("building.height_distribution must be uniform, normal, or lognormal.")
    return value


def _parse_city(raw: Mapping[str, Any]) -> CityConfig:
    size = _vec2(raw.get("size_m", [400.0, 400.0]), "city.size_m", positive=True)
    morphology = str(raw.get("morphology", "manhattan"))
    if morphology not in MORPHOLOGIES:
        raise ValueError(f"city.morphology must be one of: {', '.join(MORPHOLOGIES)}")
    roads_raw = raw.get("roads", {})
    bs_raw = raw.get("base_stations", raw.get("bs", {}))
    task_raw = raw.get("task", {})
    roads = RoadConfig(
        grid_spacing_m=_number(roads_raw.get("grid_spacing_m", 80.0), "roads.grid_spacing_m", minimum=5.0),
        width_m=_number(roads_raw.get("width_m", 12.0), "roads.width_m", minimum=1.0),
        radial_count=_integer(roads_raw.get("radial_count", 8), "roads.radial_count", minimum=2),
        ring_count=_integer(roads_raw.get("ring_count", 2), "roads.ring_count", minimum=0),
    )
    if roads.width_m >= roads.grid_spacing_m:
        raise ValueError("roads.width_m must be smaller than roads.grid_spacing_m.")
    base_stations = BaseStationConfig(
        preset_id=str(bs_raw.get("preset_id", "custom")),
        preset_version=str(bs_raw.get("preset_version", "1.0.0")),
        source_preset_id=(
            None if bs_raw.get("source_preset_id") is None else str(bs_raw["source_preset_id"])
        ),
        modified_fields=_strings(bs_raw.get("modified_fields", []), "base_stations.modified_fields"),
        deployment_profile=str(bs_raw.get("deployment_profile", "custom")),
        function_type=str(bs_raw.get("function_type", "communication")),
        source_evidence_level=str(bs_raw.get("source_evidence_level", "D")),
        parameter_status=str(bs_raw.get("parameter_status", "simulation_proxy")),
        applicable_scenarios=_strings(
            bs_raw.get("applicable_scenarios", []), "base_stations.applicable_scenarios"
        ),
        placement_family=str(bs_raw.get("placement_family", "rooftop_grid")),
        density_per_km2=_number(bs_raw.get("density_per_km2", 8.0), "base_stations.density_per_km2", minimum=0.0),
        height_m=_number(bs_raw.get("height_m", 35.0), "base_stations.height_m", minimum=1.0),
        height_reference=str(bs_raw.get("height_reference", "mast_above_rooftop")),
        power_dbm=_number(bs_raw.get("power_dbm", 44.0), "base_stations.power_dbm"),
        carrier_frequency_hz=_number(
            bs_raw.get("carrier_frequency_hz", 4.9e9),
            "base_stations.carrier_frequency_hz",
            minimum=1.0,
        ),
        bandwidth_hz=_number(
            bs_raw.get("bandwidth_hz", 100e6),
            "base_stations.bandwidth_hz",
            minimum=1.0,
        ),
        antenna_model=str(
            bs_raw.get("antenna_model", "sector3-tr38901-8x8-dualpol")
        ),
        polarization=str(bs_raw.get("polarization", "cross_dual_slant")),
        duplex_mode=str(bs_raw.get("duplex_mode", "unspecified")),
        sensing_enabled=bool(bs_raw.get("sensing_enabled", False)),
        sensing_waveform_class=(
            None
            if bs_raw.get("sensing_waveform_class") is None
            else str(bs_raw["sensing_waveform_class"])
        ),
        reference_inter_site_distance_m=(
            None
            if bs_raw.get("reference_inter_site_distance_m") is None
            else _number(
                bs_raw["reference_inter_site_distance_m"],
                "base_stations.reference_inter_site_distance_m",
                minimum=1.0,
            )
        ),
        reference_source=(
            None if bs_raw.get("reference_source") is None else str(bs_raw["reference_source"])
        ),
        min_separation_m=_number(bs_raw.get("min_separation_m", 80.0), "base_stations.min_separation_m", minimum=0.0),
        sectors=_integer(bs_raw.get("sectors", 3), "base_stations.sectors", minimum=1),
        sector_azimuths_deg=tuple(
            _number(item, "base_stations.sector_azimuths_deg item")
            for item in bs_raw.get("sector_azimuths_deg", [0.0, 120.0, 240.0])
        ),
        downtilt_deg=_number(bs_raw.get("downtilt_deg", 0.0), "base_stations.downtilt_deg"),
        random_offset_m=_number(
            bs_raw.get("random_offset_m", 0.0),
            "base_stations.random_offset_m",
            minimum=0.0,
        ),
    )
    if base_stations.placement_family not in {"rooftop_grid", "street_grid", "random_rooftop"}:
        raise ValueError("base_stations.placement_family is not supported.")
    if base_stations.height_reference not in {"absolute_agl", "mast_above_rooftop"}:
        raise ValueError(
            "base_stations.height_reference must be absolute_agl or mast_above_rooftop."
        )
    if (
        base_stations.placement_family == "street_grid"
        and base_stations.height_reference != "absolute_agl"
    ):
        raise ValueError("street_grid base stations require height_reference=absolute_agl.")
    if len(base_stations.sector_azimuths_deg) != base_stations.sectors:
        raise ValueError("base_stations.sector_azimuths_deg count must match sectors.")
    if len({value % 360.0 for value in base_stations.sector_azimuths_deg}) != base_stations.sectors:
        raise ValueError("base_stations.sector_azimuths_deg values must be unique modulo 360 degrees.")
    if not -90.0 <= base_stations.downtilt_deg <= 90.0:
        raise ValueError("base_stations.downtilt_deg must be in [-90, 90].")
    if base_stations.antenna_model not in ANTENNA_MODELS:
        raise ValueError("base_stations.antenna_model is not supported.")
    if base_stations.parameter_status not in PARAMETER_STATUSES:
        raise ValueError(
            "base_stations.parameter_status must be public_verified, trial_specific, "
            "simulation_proxy, or unknown."
        )
    altitude_range = _vec2(task_raw.get("altitude_range_m", [35.0, 115.0]), "task.altitude_range_m", positive=True)
    if altitude_range[1] <= altitude_range[0]:
        raise ValueError("task.altitude_range_m must be strictly increasing.")
    start_xy = task_raw.get("start_xy_m")
    goal_xy = task_raw.get("goal_xy_m")
    if (start_xy is None) != (goal_xy is None):
        raise ValueError("task.start_xy_m and task.goal_xy_m must be provided together.")
    explicit_start = None if start_xy is None else _vec2(start_xy, "task.start_xy_m")
    explicit_goal = None if goal_xy is None else _vec2(goal_xy, "task.goal_xy_m")
    task = TaskConfig(
        altitude_m=_number(task_raw.get("altitude_m", 50.0), "task.altitude_m", minimum=0.1),
        altitude_range_m=altitude_range,
        count=_integer(task_raw.get("count", 1), "task.count", minimum=1),
        start_xy_m=explicit_start,
        goal_xy_m=explicit_goal,
        selection_mode=str(task_raw.get("selection_mode", "manual" if explicit_start else "auto")),
        constraint_preset=str(task_raw.get("constraint_preset", "telemetry")),
        minimum_sinr_db=_number(
            task_raw.get("minimum_sinr_db", 0.0), "task.minimum_sinr_db"
        ),
        minimum_rss_dbm=(
            None
            if task_raw.get("minimum_rss_dbm") is None
            else _number(task_raw["minimum_rss_dbm"], "task.minimum_rss_dbm")
        ),
        maximum_outage_fraction=_number(
            task_raw.get("maximum_outage_fraction", 0.0),
            "task.maximum_outage_fraction",
        ),
    )
    if not altitude_range[0] <= task.altitude_m <= altitude_range[1]:
        raise ValueError("task.altitude_m must lie within task.altitude_range_m.")
    if not 0.0 <= task.maximum_outage_fraction <= 1.0:
        raise ValueError("task.maximum_outage_fraction must lie within [0, 1].")
    if task.selection_mode not in {"auto", "auto_resolved", "manual"}:
        raise ValueError("task.selection_mode must be auto, auto_resolved, or manual.")
    if task.start_xy_m is not None:
        if task.count != 1:
            raise ValueError("Explicit task coordinates currently require task.count=1.")
        for name, point in (("start_xy_m", task.start_xy_m), ("goal_xy_m", task.goal_xy_m)):
            if not 0.0 <= point[0] <= size[0] or not 0.0 <= point[1] <= size[1]:
                raise ValueError(f"task.{name} lies outside city.size_m.")
    validation_raw = raw.get("validation", {})
    validation = ValidationConfig(
        grid_resolution_m=_number(
            validation_raw.get("grid_resolution_m", 5.0),
            "validation.grid_resolution_m",
            minimum=0.1,
        ),
        minimum_largest_component_fraction=_number(
            validation_raw.get("minimum_largest_component_fraction", 0.95),
            "validation.minimum_largest_component_fraction",
        ),
    )
    if not 0.0 <= validation.minimum_largest_component_fraction <= 1.0:
        raise ValueError("validation.minimum_largest_component_fraction must be in [0, 1].")
    return CityConfig(
        size_m=size,
        morphology=morphology,
        building=_parse_building(raw.get("building", {})),
        roads=roads,
        base_stations=base_stations,
        task=task,
        validation=validation,
    )


def _parse_radio(raw: Mapping[str, Any]) -> RadioConfig:
    preset = str(raw.get("preset", "smoke"))
    if preset not in _RADIO_PRESETS:
        raise ValueError(f"radio.preset must be one of: {', '.join(_RADIO_PRESETS)}")
    merged = _merge(_RADIO_PRESETS[preset], raw)
    heights_raw = merged.get("heights_m", [35.0, 65.0, 95.0, 115.0])
    if not isinstance(heights_raw, (list, tuple)) or not heights_raw:
        raise ValueError("radio.heights_m must be a non-empty sequence.")
    heights = tuple(_number(item, "radio.heights_m item", minimum=0.0) for item in heights_raw)
    if any(b <= a for a, b in pairwise(heights)):
        raise ValueError("radio.heights_m must be strictly increasing.")
    azimuths_raw = merged.get("sector_azimuths_deg", [0.0, 120.0, 240.0])
    azimuths = tuple(_number(item, "radio.sector_azimuths_deg item") for item in azimuths_raw)
    samples = _integer(merged.get("samples_per_logical_sector", 45_000_000), "radio.samples_per_logical_sector", minimum=1)
    cfg = RadioConfig(
        enabled=bool(raw.get("enabled", False)),
        preset=preset,
        backend=str(raw.get("backend", "sionna_rt")),
        frequency_hz=_number(merged.get("frequency_hz", 3.5e9), "radio.frequency_hz", minimum=1.0),
        bandwidth_hz=_number(merged.get("bandwidth_hz", 20e6), "radio.bandwidth_hz", minimum=1.0),
        temperature_k=_number(merged.get("temperature_k", 293.0), "radio.temperature_k", minimum=0.0),
        noise_figure_db=_number(merged.get("noise_figure_db", 9.0), "radio.noise_figure_db"),
        cell_size_m=_number(merged.get("cell_size_m", 10.0), "radio.cell_size_m", minimum=0.001),
        heights_m=heights,
        samples_per_logical_sector=samples,
        max_depth=_integer(merged.get("max_depth", 20), "radio.max_depth", minimum=0),
        antenna_model=str(merged.get("antenna_model", "sector3-tr38901-ula8")),
        sector_azimuths_deg=azimuths,
        downtilt_deg=_number(merged.get("downtilt_deg", 10.0), "radio.downtilt_deg"),
        tx_power_dbm=_number(merged.get("tx_power_dbm", 44.0), "radio.tx_power_dbm"),
        diffraction=bool(merged.get("diffraction", False)),
        diffuse_reflection=bool(merged.get("diffuse_reflection", False)),
        mitsuba_variant=str(merged.get("mitsuba_variant", "cuda_ad_mono_polarized")),
        seed=(None if raw.get("seed") is None else _integer(raw["seed"], "radio.seed")),
    )
    if cfg.backend not in {"sionna_rt"}:
        raise ValueError("radio.backend must be sionna_rt; geometry-only checks are separate tests.")
    if cfg.antenna_model not in ANTENNA_MODELS:
        raise ValueError("radio.antenna_model is not supported.")
    if not cfg.sector_azimuths_deg:
        raise ValueError("radio.sector_azimuths_deg must not be empty.")
    return cfg


def _parse_ue(raw: Mapping[str, Any]) -> UEConfig:
    marker = _number(raw.get("marker_scale_m", 2.0), "ue.marker_scale_m", minimum=0.01)
    editor_project = raw.get("editor_project")
    if editor_project is not None:
        editor_project = str(editor_project)
    return UEConfig(
        enabled=bool(raw.get("enabled", False)),
        output_format=str(raw.get("output_format", "ue-ready-bundle")),
        editor_project=editor_project,
        generate_airsim_settings=bool(raw.get("generate_airsim_settings", True)),
        import_asset_name=str(raw.get("import_asset_name", "WirelessCity")),
        marker_scale_m=marker,
    )


def config_from_mapping(raw: Mapping[str, Any]) -> FactoryConfig:
    if not isinstance(raw, Mapping):
        raise TypeError("Configuration root must be a mapping.")
    global_raw = raw.get("global", raw)
    if not isinstance(global_raw, Mapping):
        raise TypeError("global must be a mapping.")
    return FactoryConfig(
        seed=_integer(global_raw.get("seed", 20260821), "global.seed"),
        output=str(global_raw.get("output", "outputs")),
        name=str(global_raw.get("name", "city")),
        city=_parse_city(raw.get("city", raw)),
        radio=_parse_radio(raw.get("radio", {})),
        ue=_parse_ue(raw.get("ue", {})),
    )


def load_config(path: Path | str) -> FactoryConfig:
    target = Path(path)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load YAML configuration files.") from exc
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    return config_from_mapping(raw)
