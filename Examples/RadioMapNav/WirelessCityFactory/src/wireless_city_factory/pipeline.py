"""Atomic city -> radio -> UE orchestration with stage completion gates."""

from __future__ import annotations

import json
import os
import shutil
import statistics
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .base_stations import build_base_station_manifest, save_base_station_manifest
from .city import generate_city
from .config import FactoryConfig
from .exporters import export_obj, export_preview_svg
from .profiles import CITY_PROFILES, apply_city_profile
from .radio import run_radio_stage
from .ue import generate_ue_bundle


class PipelineError(RuntimeError):
    """A requested optional stage failed and no success manifest was published."""


_GENERATE_LOCK = threading.Lock()


def generate(config: FactoryConfig, *, project_root: Path | str | None = None) -> dict[str, Any]:
    """Serialize publication so identical concurrent runs cannot corrupt one another."""
    with _GENERATE_LOCK:
        return _generate_unlocked(config, project_root=project_root)


def _generate_unlocked(config: FactoryConfig, *, project_root: Path | str | None = None) -> dict[str, Any]:
    base = Path(project_root) if project_root is not None else Path.cwd()
    output_root = Path(config.output).expanduser()
    if not output_root.is_absolute():
        output_root = base / output_root
    output_root.mkdir(parents=True, exist_ok=True)
    config_fingerprint = config.fingerprint()
    run_id = f"{_safe_id(config.name)}-{config_fingerprint[:12]}"
    final_dir = output_root / run_id
    existing_manifest = final_dir / "manifest.json"
    if existing_manifest.exists():
        existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if existing.get("config_fingerprint") == config_fingerprint and existing.get("status") == "complete":
            existing["reused"] = True
            existing["output_dir"] = str(final_dir)
            return existing
        raise PipelineError(f"Existing run {final_dir} has a different fingerprint; refusing stale cache reuse.")
    if final_dir.exists():
        raise PipelineError(f"Output directory {final_dir} already exists without a matching complete manifest.")
    temporary = output_root / f"{run_id}.staging-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    status: dict[str, Any] = {"status": "running", "config_fingerprint": config_fingerprint, "stages": {}}
    try:
        scene = generate_city(config.city, seed=config.seed, name=config.name)
        export_obj(scene, temporary / "scene.obj")
        export_preview_svg(scene, temporary / "preview.svg")
        scene.save_json(temporary / "scene.json")
        base_station_manifest = build_base_station_manifest(scene)
        save_base_station_manifest(base_station_manifest, temporary / "base_station_manifest.json")
        status["stages"]["city"] = {
            "status": "complete",
            "scene_fingerprint": scene.fingerprint(),
            "scene_file": "scene.json",
            "mesh_file": "scene.obj",
            "preview_file": "preview.svg",
            "base_station_manifest": "base_station_manifest.json",
            "base_station_fingerprint": base_station_manifest["base_station_fingerprint"],
        }
        _write_json(temporary / "city_manifest.json", status["stages"]["city"])
        _write_json(temporary / "config.json", config.as_dict())
        if config.radio.enabled:
            try:
                radio_manifest = run_radio_stage(scene, config.radio, temporary, base_station_manifest)
            except Exception as exc:  # noqa: BLE001 - optional stage is fail-closed and records the exact error.
                _fail(temporary, status, "radio", exc)
            status["stages"]["radio"] = {"status": "complete", "manifest": "radio_manifest.json", "radio_fingerprint": radio_manifest["radio_fingerprint"]}
        else:
            status["stages"]["radio"] = {"status": "disabled"}
        if config.ue.enabled:
            try:
                ue_manifest = generate_ue_bundle(scene, config.ue, temporary, base_station_manifest)
            except Exception as exc:  # noqa: BLE001 - optional stage is fail-closed and records the exact error.
                _fail(temporary, status, "ue", exc)
            status["stages"]["ue"] = {"status": "complete", "manifest": "ue_manifest.json", "backend": ue_manifest["backend"]}
        else:
            status["stages"]["ue"] = {"status": "disabled"}
        status.update({"status": "complete", "run_id": run_id, "config_fingerprint": config_fingerprint, "scene_fingerprint": scene.fingerprint(), "scene_file": "scene.json", "stage_status": status.pop("stages")})
        _write_json(temporary / "manifest.json", status)
        _publish_directory(temporary, final_dir)
        status["output_dir"] = str(final_dir)
        return status
    except Exception:
        if temporary.exists():
            failed = output_root / f"{run_id}.failed-{uuid.uuid4().hex[:8]}"
            try:
                _publish_directory(temporary, failed)
            except OSError:
                pass
        raise


def generate_candidates(
    config: FactoryConfig,
    *,
    morphologies: list[str] | None = None,
    city_profiles: list[str] | None = None,
    seeds: list[int],
    site_densities_per_km2: list[float] | None = None,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    """Generate a deterministic city-only morphology/seed matrix."""
    if config.radio.enabled or config.ue.enabled:
        raise ValueError("Candidate generation requires radio.enabled=false and ue.enabled=false.")
    if bool(morphologies) == bool(city_profiles):
        raise ValueError("Choose exactly one of morphologies or city_profiles.")
    if not seeds:
        raise ValueError("Candidate generation requires at least one seed.")
    densities = site_densities_per_km2 or [config.city.base_stations.density_per_km2]
    if any(value < 0.0 for value in densities):
        raise ValueError("Candidate site densities must be non-negative.")
    include_density_in_name = site_densities_per_km2 is not None
    candidates = []
    variants = (
        [(profile, apply_city_profile(config, profile)) for profile in city_profiles]
        if city_profiles
        else [(morphology, replace(config, city=replace(config.city, morphology=morphology))) for morphology in morphologies]
    )
    for variant_name, variant_config in variants:
        for seed in seeds:
            for density in densities:
                suffix = f"-sites-{density:g}" if include_density_in_name else ""
                candidate = replace(
                    variant_config,
                    seed=int(seed),
                    name=f"{config.name}-{variant_name}-seed-{seed}{suffix}",
                    city=replace(
                        variant_config.city,
                        base_stations=replace(
                            variant_config.city.base_stations,
                            density_per_km2=float(density),
                        ),
                    ),
                )
                result = generate(candidate, project_root=project_root)
                scene = json.loads(
                    (Path(result["output_dir"]) / "scene.json").read_text(encoding="utf-8")
                )
                candidates.append(
                    {
                        "city_profile": variant_name if city_profiles else None,
                        "morphology": candidate.city.morphology,
                        "seed": int(seed),
                        "site_density_per_km2": float(density),
                        "run_id": result["run_id"],
                        "config_fingerprint": result["config_fingerprint"],
                        "scene_fingerprint": result["scene_fingerprint"],
                        "statistics": scene["metadata"]["statistics"],
                    }
                )
    base = Path(project_root) if project_root is not None else Path.cwd()
    output_root = Path(config.output).expanduser()
    if not output_root.is_absolute():
        output_root = base / output_root
    manifest = {
        "schema_version": "wireless-city-candidate-set-v1",
        "status": "complete",
        "base_name": config.name,
        "candidate_count": len(candidates),
        "morphologies": sorted({item["morphology"] for item in candidates}),
        "city_profiles": list(city_profiles or []),
        "seeds": [int(seed) for seed in seeds],
        "site_densities_per_km2": [float(value) for value in densities],
        "profile_summary": _summarize_candidates(candidates),
        "candidates": candidates,
    }
    kind = "base-station-candidates" if include_density_in_name else "candidates"
    manifest_path = output_root / f"{_safe_id(config.name)}-{kind}.json"
    _write_json(manifest_path, manifest)
    return {**manifest, "manifest": str(manifest_path)}


def _summarize_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = str(candidate.get("city_profile") or candidate["morphology"])
        groups.setdefault(key, []).append(candidate)
    result: dict[str, Any] = {}
    for name, items in groups.items():
        metric_values = {
            "building_count": [float(item["statistics"]["building_count"]) for item in items],
            "footprint_coverage_ratio": [
                float(item["statistics"]["footprint_coverage_ratio"]) for item in items
            ],
            "mean_building_height_m": [
                float(item["statistics"]["building_height_m"]["mean"]) for item in items
            ],
            "free_space_fraction_at_task_altitude": [
                float(item["statistics"]["free_space_fraction"]) for item in items
            ],
        }
        result[name] = {
            "description": CITY_PROFILES.get(name, {}).get("description"),
            "sample_count": len(items),
            "metrics": {
                metric: {
                    "mean": statistics.fmean(values),
                    "minimum": min(values),
                    "maximum": max(values),
                }
                for metric, values in metric_values.items()
            },
        }
    return result


def _fail(temporary: Path, status: dict[str, Any], stage: str, exc: Exception) -> None:
    failure = {"status": "failed", "stage": stage, "error_type": type(exc).__name__, "error": str(exc), "success_manifest_published": False}
    status["stages"][stage] = failure
    _write_json(temporary / f"{stage}_failure.json", failure)
    raise PipelineError(f"{stage} stage failed: {exc}") from exc


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _publish_directory(source: Path, destination: Path) -> None:
    """Publish a completed run, avoiding Windows directory-rename access failures."""
    if os.name != "nt":
        source.replace(destination)
        return
    try:
        shutil.copytree(source, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    shutil.rmtree(source, ignore_errors=True)
