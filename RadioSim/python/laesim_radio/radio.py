"""Optional Sionna RT 2.x backend and its dependency-free mesh reducer."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from laesim_scene.config import RADIO_CONTRACT, RadioConfig
from laesim_scene.schema import Scene

from .base_stations import build_base_station_manifest, validate_base_station_manifest

ITU_MATERIAL_FREQUENCY_RANGES_HZ = {
    "concrete": (1.0e9, 100.0e9),
    "very_dry_ground": (1.0e9, 10.0e9),
}


@dataclass(frozen=True)
class MultilayerMesh:
    x_m: np.ndarray
    y_m: np.ndarray
    z_m: np.ndarray
    vertices_m: np.ndarray
    faces: np.ndarray

    @property
    def cell_shape(self) -> tuple[int, int, int]:
        return (len(self.z_m), len(self.y_m), len(self.x_m))

    @property
    def face_count(self) -> int:
        return int(self.faces.shape[0])


@dataclass(frozen=True)
class RadioVolume:
    x_m: np.ndarray
    y_m: np.ndarray
    z_m: np.ndarray
    base_station_ids: tuple[str, ...]
    path_gain_linear: np.ndarray
    rss_dbm: np.ndarray
    sinr_linear: np.ndarray
    sinr_db: np.ndarray
    metadata: dict[str, Any]

    def save_npz(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = json.dumps(self.metadata, sort_keys=True, allow_nan=False)
        with target.open("wb") as stream:
            np.savez_compressed(
                stream,
                x_m=self.x_m,
                y_m=self.y_m,
                z_m=self.z_m,
                base_station_ids=np.asarray(self.base_station_ids),
                path_gain_linear=self.path_gain_linear,
                rss_dbm=self.rss_dbm,
                # Compatibility alias for v3 readers. This is wideband RSS, not 3GPP RSRP.
                rsrp_dbm=self.rss_dbm,
                sinr_linear=self.sinr_linear,
                sinr_db=self.sinr_db,
                metadata_json=np.asarray(metadata),
            )


def build_multilayer_mesh(scene: Scene, heights_m: tuple[float, ...] | list[float], cell_size_m: float) -> MultilayerMesh:
    """Build one disconnected horizontal mesh stack, two equal-area faces/cell."""
    heights = np.asarray(tuple(float(value) for value in heights_m), dtype=float)
    if heights.ndim != 1 or len(heights) == 0 or not np.all(np.isfinite(heights)) or np.any(np.diff(heights) <= 0.0):
        raise ValueError("heights_m must be finite and strictly increasing.")
    if cell_size_m <= 0.0 or not math.isfinite(cell_size_m):
        raise ValueError("cell_size_m must be finite and positive.")
    if np.any(heights < scene.bounds_min_m[2]) or np.any(heights > scene.bounds_max_m[2]):
        raise ValueError("Measurement heights must lie within scene bounds.")
    nx = max(1, math.ceil(scene.size_m[0] / cell_size_m))
    ny = max(1, math.ceil(scene.size_m[1] / cell_size_m))
    x_edges = np.linspace(scene.bounds_min_m[0], scene.bounds_max_m[0], nx + 1, dtype=float)
    y_edges = np.linspace(scene.bounds_min_m[1], scene.bounds_max_m[1], ny + 1, dtype=float)
    x_m = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_m = 0.5 * (y_edges[:-1] + y_edges[1:])
    vertices = np.empty((len(heights) * (ny + 1) * (nx + 1), 3), dtype=np.float32)
    faces = np.empty((len(heights) * ny * nx * 2, 3), dtype=np.uint32)
    vertex_cursor = face_cursor = 0
    for height in heights:
        layer_base = vertex_cursor
        for y in y_edges:
            vertices[vertex_cursor : vertex_cursor + nx + 1, 0] = x_edges
            vertices[vertex_cursor : vertex_cursor + nx + 1, 1] = float(y)
            vertices[vertex_cursor : vertex_cursor + nx + 1, 2] = float(height)
            vertex_cursor += nx + 1
        for yi in range(ny):
            for xi in range(nx):
                v00 = layer_base + yi * (nx + 1) + xi
                v10, v01, v11 = v00 + 1, v00 + nx + 1, v00 + nx + 2
                faces[face_cursor] = (v00, v10, v11)
                faces[face_cursor + 1] = (v00, v11, v01)
                face_cursor += 2
    return MultilayerMesh(x_m=x_m, y_m=y_m, z_m=heights, vertices_m=vertices, faces=faces)


def reduce_triangle_values(raw_values: np.ndarray, mesh: MultilayerMesh) -> np.ndarray:
    """Reduce [Tx, face] values to [Tx, Z, Y, X] using equal-area means."""
    raw = np.asarray(raw_values, dtype=float)
    if raw.ndim != 2 or raw.shape[1] != mesh.face_count:
        raise ValueError(f"Expected [transmitter, {mesh.face_count}] triangle values.")
    return raw.reshape((raw.shape[0], *mesh.cell_shape, 2)).mean(axis=-1)


def _noise_power_w(config: RadioConfig) -> float:
    return 1.380649e-23 * config.temperature_k * config.bandwidth_hz * 10.0 ** (config.noise_figure_db / 10.0)


def _radio_metrics(
    path_gain: np.ndarray,
    powers_w: np.ndarray,
    noise_w: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return per-transmitter wideband RSS and full-reuse SINR on the radio grid."""
    received = path_gain * powers_w.reshape((-1, 1, 1, 1))
    interference = np.sum(received, axis=0, keepdims=True) - received
    floor = np.finfo(float).tiny
    rss_dbm = 10.0 * np.log10(np.maximum(received, floor)) + 30.0
    sinr_linear = received / np.maximum(noise_w + interference, floor)
    sinr_db = 10.0 * np.log10(np.maximum(sinr_linear, floor))
    return rss_dbm, sinr_linear, sinr_db


def sionna_orientation_rad(azimuth_deg: float, downtilt_deg: float) -> list[float]:
    """Convert cellular azimuth/downtilt to Sionna's (z, y, x) Euler angles."""
    return [math.radians(float(azimuth_deg)), math.radians(float(downtilt_deg)), 0.0]


def material_frequency_contract(frequency_hz: float) -> dict[str, Any]:
    """Describe transparent boundary clamping for ITU material properties."""
    requested = float(frequency_hz)
    if not math.isfinite(requested) or requested <= 0.0:
        raise ValueError("Material frequency must be finite and positive.")
    materials = {}
    for material, (lower, upper) in ITU_MATERIAL_FREQUENCY_RANGES_HZ.items():
        evaluation = min(upper, max(lower, requested))
        materials[material] = {
            "valid_range_hz": [lower, upper],
            "evaluation_frequency_hz": evaluation,
            "clamped": evaluation != requested,
        }
    return {
        "policy": "itu-p2040-nearest-valid-boundary",
        "requested_frequency_hz": requested,
        "note": (
            "Ray tracing uses the requested carrier frequency. Only material permittivity and "
            "conductivity are evaluated at the nearest frequency covered by Sionna's ITU-R "
            "P.2040 table when the carrier lies outside that material's valid range."
        ),
        "materials": materials,
    }


def run_radio_stage(
    scene: Scene,
    config: RadioConfig,
    output_dir: Path | str,
    base_station_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run native Windows Sionna RT and persist a complete radio stage."""
    if not config.enabled:
        raise ValueError("Radio stage requested with radio.enabled=false.")
    station_manifest = base_station_manifest or build_base_station_manifest(scene)
    validate_base_station_manifest(station_manifest, scene)
    _validate_radio_station_contract(config, station_manifest)
    mesh = build_multilayer_mesh(scene, config.heights_m, config.cell_size_m)
    mi, rt = _load_sionna_runtime(config)
    solve_started = time.perf_counter()
    path_gain, transmitter_ids, runtime_metadata = _solve_mesh_radio_map(
        scene,
        config,
        mesh,
        mi,
        rt,
        station_manifest,
    )
    solver_elapsed_s = time.perf_counter() - solve_started
    powers_w = np.asarray(
        [10.0 ** ((value - 30.0) / 10.0) for value in runtime_metadata["transmitter_power_dbm"]],
        dtype=float,
    )
    rss_dbm, sinr_linear, sinr_db = _radio_metrics(
        path_gain,
        powers_w,
        _noise_power_w(config),
    )
    volume = RadioVolume(
        mesh.x_m,
        mesh.y_m,
        mesh.z_m,
        tuple(transmitter_ids),
        path_gain,
        rss_dbm,
        sinr_linear,
        sinr_db,
        {
            "backend": "sionna-rt-2.x",
            "radio_contract": RADIO_CONTRACT,
            "scene_id": scene.scene_id,
            "scene_fingerprint": scene.fingerprint(),
            "base_station_fingerprint": station_manifest["base_station_fingerprint"],
            "config": _json_safe(config.__dict__),
            "execution_platform": "native-windows",
            "mitsuba_variant": str(mi.variant()),
            "sionna_rt_version": importlib.metadata.version("sionna-rt"),
            "radio_map_estimator": "mesh-stack",
            "power_metric": "wideband_rss_dbm",
            "power_metric_note": "Total received power over the configured bandwidth; not 3GPP RSRP.",
            "sinr_model": "full-buffer-reuse-1-all-sectors",
            "measurement_surface": "transparent-disconnected-multilayer-mesh",
            "measurement_surface_interaction": "transparent-capture",
            "solver_call_count": 1,
            "mesh_vertex_count": len(mesh.vertices_m),
            "mesh_triangle_count": int(mesh.face_count),
            "triangles_per_xy_cell": 2,
            "triangle_reduction": "equal-area-mean",
            "mesh_face_order": ["z", "y", "x", "triangle"],
            "output_axis_order": ["transmitter", "z", "y", "x"],
            "samples_semantics": "samples per logical sector per one multilayer call",
            "transmitter_ids": list(transmitter_ids),
            **runtime_metadata,
        },
    )
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    volume_path = target / "radio_volume.npz"
    temporary = target / ".radio_volume.tmp.npz"
    volume.save_npz(temporary)
    temporary.replace(volume_path)
    digest = _sha256(volume_path)
    manifest = {
        "schema_version": "wireless-city-radio",
        "radio_contract": RADIO_CONTRACT,
        "status": "complete",
        "scene_fingerprint": scene.fingerprint(),
        "radio_fingerprint": _hash_json(volume.metadata),
        "radio_volume": volume_path.name,
        "radio_volume_sha256": digest,
        "shape": list(path_gain.shape),
        "transmitter_ids": list(transmitter_ids),
        "array_shapes": {
            "path_gain_linear": list(path_gain.shape),
            "rss_dbm": list(rss_dbm.shape),
            "rsrp_dbm": list(rss_dbm.shape),
            "sinr_linear": list(sinr_linear.shape),
            "sinr_db": list(sinr_db.shape),
        },
        "summary": {
            "min_path_gain_linear": float(np.min(path_gain)),
            "max_path_gain_linear": float(np.max(path_gain)),
            "min_rss_dbm": float(np.min(rss_dbm)),
            "max_rss_dbm": float(np.max(rss_dbm)),
            "min_sinr_db": float(np.min(sinr_db)),
            "max_sinr_db": float(np.max(sinr_db)),
        },
        "runtime": {"solver_elapsed_s": round(solver_elapsed_s, 6)},
        "metadata": volume.metadata,
    }
    _atomic_json(target / "radio_manifest.json", manifest)
    return manifest


def _load_sionna_runtime(config: RadioConfig) -> tuple[Any, Any]:
    if os.name != "nt":
        raise RuntimeError("Sionna RT stage is fail-closed to native Windows CUDA/OptiX execution.")
    try:
        import mitsuba as mi
    except ImportError as exc:
        raise RuntimeError("Sionna RT extra is missing: install wireless-city-factory[rt].") from exc
    if config.mitsuba_variant != "cuda_ad_mono_polarized":
        raise RuntimeError("Only cuda_ad_mono_polarized is supported by the active MeshRadioMap contract.")
    try:
        mi.set_variant(config.mitsuba_variant)
        from sionna import rt
    except Exception as exc:
        raise RuntimeError("Sionna RT could not initialize the CUDA/OptiX polarized variant.") from exc
    return mi, rt


def _solve_mesh_radio_map(
    scene: Scene,
    config: RadioConfig,
    mesh: MultilayerMesh,
    mi: Any,
    rt: Any,
    station_manifest: dict[str, Any],
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    rt_scene = rt.load_scene()
    rt_scene.frequency = config.frequency_hz
    rt_scene.bandwidth = config.bandwidth_hz
    rt_scene.temperature = config.temperature_k
    material_contract = material_frequency_contract(config.frequency_hz)
    concrete = _sionna_material(rt, "city-concrete", "concrete", material_contract)
    ground_material = _sionna_material(
        rt,
        "city-ground",
        "very_dry_ground",
        material_contract,
    )
    objects = [_cuboid(mi, rt, "ground", scene.center_m[0], scene.center_m[1], -0.1, scene.size_m[0], scene.size_m[1], 0.2, ground_material)]
    for building in scene.buildings:
        center, size = building["center_m"], building["size_m"]
        objects.append(_cuboid(mi, rt, str(building["building_id"]), float(center[0]), float(center[1]), float(center[2]), float(size[0]), float(size[1]), float(size[2]), concrete))
    rt_scene.edit(add=objects)
    array_contract = antenna_array_contract(config.antenna_model)
    array = rt.PlanarArray(**array_contract["sionna_parameters"])
    rt_scene.tx_array = array
    transmitter_ids: list[str] = []
    transmitter_power_dbm: list[float] = []
    for station in station_manifest["sites"]:
        sectors = station["sectors"] if config.antenna_model != "isotropic" else [station["sectors"][0]]
        for sector in sectors:
            tx_id = str(sector["sector_id"]) if config.antenna_model != "isotropic" else str(station["base_station_id"])
            power_dbm = float(sector["nominal_tx_power_dbm"])
            parameters: dict[str, Any] = {
                "name": tx_id,
                "position": [float(value) for value in station["position_m"]],
                "power_dbm": power_dbm,
            }
            if config.antenna_model != "isotropic":
                parameters["orientation"] = sionna_orientation_rad(
                    float(sector["azimuth_deg"]),
                    float(sector["downtilt_deg"]),
                )
            rt_scene.add(rt.Transmitter(**parameters))
            transmitter_ids.append(tx_id)
            transmitter_power_dbm.append(power_dbm)
    surface = mi.Mesh("wireless-city-measurement-surface", vertex_count=len(mesh.vertices_m), face_count=mesh.face_count, has_vertex_normals=False, has_vertex_texcoords=False)
    parameters = mi.traverse(surface)
    parameters["vertex_positions"] = mesh.vertices_m.ravel()
    parameters["faces"] = mesh.faces.ravel()
    parameters.update()
    radio_map = rt.RadioMapSolver()(rt_scene, measurement_surface=surface, samples_per_tx=config.samples_per_logical_sector, max_depth=config.max_depth, los=True, specular_reflection=True, diffuse_reflection=config.diffuse_reflection, refraction=False, diffraction=config.diffraction, seed=config.seed or scene.seed)
    raw = np.asarray(radio_map.path_gain.numpy(), dtype=float)
    reduced = reduce_triangle_values(raw, mesh)
    if reduced.shape[0] != len(transmitter_ids):
        raise RuntimeError("Sionna returned a transmitter count inconsistent with the scene contract.")
    if not np.all(np.isfinite(reduced)) or np.any(reduced < 0.0):
        raise RuntimeError("Sionna returned invalid path-gain values.")
    return reduced, transmitter_ids, {
        "physical_site_ids": [str(item["base_station_id"]) for item in station_manifest["sites"]],
        "antenna_model": config.antenna_model,
        "antenna_array": array_contract,
        "material_frequency_contract": material_contract,
        "sector_count_per_site": 1 if config.antenna_model == "isotropic" else len(config.sector_azimuths_deg),
        "transmitter_power_dbm": transmitter_power_dbm,
    }


def _sionna_material(
    rt: Any,
    name: str,
    itu_type: str,
    contract: dict[str, Any],
) -> Any:
    material = contract["materials"][itu_type]
    if not material["clamped"]:
        return rt.ITURadioMaterial(name=name, itu_type=itu_type, thickness=0.30)
    evaluation_frequency = float(material["evaluation_frequency_hz"])
    relative_permittivity, conductivity = rt.itu_material.itu_material(
        itu_type,
        evaluation_frequency,
    )
    return rt.RadioMaterial(
        name=name,
        thickness=0.30,
        relative_permittivity=relative_permittivity,
        conductivity=conductivity,
    )


def antenna_array_contract(antenna_model: str) -> dict[str, Any]:
    if antenna_model in {
        "sector3-tr38901-8x4-dualpol",
        "sector3-tr38901-8x8-dualpol",
    }:
        columns = 8 if antenna_model.endswith("8x8-dualpol") else 4
        parameters = {
            "num_rows": 8,
            "num_cols": columns,
            "vertical_spacing": 0.5,
            "horizontal_spacing": 0.5,
            "pattern": "tr38901",
            "polarization": "cross",
        }
        return {
            "spatial_positions": 8 * columns,
            "polarizations_per_position": 2,
            "linear_port_count": 16 * columns,
            "polarization_basis": "Sionna cross pair with -45/+45 degree slant angles",
            "sionna_parameters": parameters,
        }
    if antenna_model == "sector3-tr38901-ula8":
        parameters = {
            "num_rows": 8,
            "num_cols": 1,
            "vertical_spacing": 0.5,
            "horizontal_spacing": 0.5,
            "pattern": "tr38901",
            "polarization": "V",
        }
        return {
            "spatial_positions": 8,
            "polarizations_per_position": 1,
            "linear_port_count": 8,
            "polarization_basis": "vertical",
            "sionna_parameters": parameters,
        }
    parameters = {
        "num_rows": 1,
        "num_cols": 1,
        "vertical_spacing": 0.5,
        "horizontal_spacing": 0.5,
        "pattern": "tr38901" if "tr38901" in antenna_model else "iso",
        "polarization": "V",
    }
    return {
        "spatial_positions": 1,
        "polarizations_per_position": 1,
        "linear_port_count": 1,
        "polarization_basis": "vertical",
        "sionna_parameters": parameters,
    }


def _validate_radio_station_contract(config: RadioConfig, manifest: dict[str, Any]) -> None:
    if any(
        float(site["carrier_frequency_hz"]) != float(config.frequency_hz)
        or float(site["bandwidth_hz"]) != float(config.bandwidth_hz)
        for site in manifest["sites"]
    ):
        raise ValueError("Radio frequency or bandwidth does not match the base-station manifest.")
    if config.antenna_model == "isotropic":
        powers = {float(site["sectors"][0]["nominal_tx_power_dbm"]) for site in manifest["sites"]}
        if powers != {float(config.tx_power_dbm)}:
            raise ValueError("Radio Tx power does not match the base-station manifest.")
        return
    expected_azimuths = [float(value) % 360.0 for value in config.sector_azimuths_deg]
    for site in manifest["sites"]:
        sectors = site["sectors"]
        if [float(item["azimuth_deg"]) for item in sectors] != expected_azimuths:
            raise ValueError("Radio sector azimuths do not match the base-station manifest.")
        if any(float(item["downtilt_deg"]) != float(config.downtilt_deg) for item in sectors):
            raise ValueError("Radio downtilt does not match the base-station manifest.")
        if any(float(item["nominal_tx_power_dbm"]) != float(config.tx_power_dbm) for item in sectors):
            raise ValueError("Radio Tx power does not match the base-station manifest.")


def _cuboid(mi: Any, rt: Any, name: str, x: float, y: float, z: float, sx: float, sy: float, sz: float, material: Any) -> Any:
    transform = mi.ScalarAffineTransform4f().translate([x, y, z]) @ mi.ScalarAffineTransform4f().scale([sx / 2.0, sy / 2.0, sz / 2.0])
    mesh = mi.load_dict({"type": "cube", "to_world": transform})
    return rt.SceneObject(mi_mesh=mesh, name=name, radio_material=material)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _hash_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
