"""Versioned base-station manifest shared by radio, Unreal, and runtime stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import Scene

BASE_STATION_SCHEMA = "wireless-city-base-stations-v1"


def build_base_station_manifest(scene: Scene) -> dict[str, Any]:
    cells = []
    for site in scene.base_stations:
        for sector in site["sectors"]:
            cells.append(
                {
                    **sector,
                    "site_id": str(site["base_station_id"]),
                    "position_m": [float(value) for value in site["position_m"]],
                    "antenna_height_m": float(site["antenna_height_m"]),
                    "antenna_height_agl_m": float(site["antenna_height_agl_m"]),
                    "deployment_profile": str(site["deployment_profile"]),
                    "preset_id": str(site.get("preset_id", "custom")),
                    "preset_version": str(site.get("preset_version", "1.0.0")),
                    "antenna_model": str(site.get("antenna_model", "unknown")),
                    "function_type": site["metadata"].get("function_type"),
                    "source_evidence_level": site["metadata"].get("source_evidence_level"),
                    "parameter_status": site["metadata"].get("parameter_status"),
                    "sensing_enabled": bool(site["metadata"].get("sensing_enabled", False)),
                    "height_reference": str(site["metadata"]["height_reference"]),
                    "reference_inter_site_distance_m": site["metadata"].get(
                        "reference_inter_site_distance_m"
                    ),
                    "reference_source": site["metadata"].get("reference_source"),
                }
            )
    manifest = {
        "schema_version": BASE_STATION_SCHEMA,
        "status": "complete",
        "scene_id": scene.scene_id,
        "scene_fingerprint": scene.fingerprint(),
        "units": "m",
        "frame": scene.frame,
        "site_count": len(scene.base_stations),
        "sector_count": len(cells),
        "sites": scene.base_stations,
        "cells": cells,
        "source_of_truth": "sites and sectors in this manifest; copies must match scene.json",
    }
    manifest["base_station_fingerprint"] = _fingerprint(manifest)
    validate_base_station_manifest(manifest, scene)
    return manifest


def validate_base_station_manifest(manifest: dict[str, Any], scene: Scene) -> None:
    if manifest.get("schema_version") != BASE_STATION_SCHEMA or manifest.get("status") != "complete":
        raise ValueError("Base-station manifest contract is not complete.")
    if manifest.get("scene_fingerprint") != scene.fingerprint():
        raise ValueError("Base-station manifest scene fingerprint does not match scene.json.")
    if manifest.get("sites") != scene.base_stations:
        raise ValueError("Base-station manifest sites do not match scene.json.")
    sites = list(manifest.get("sites", []))
    cells = list(manifest.get("cells", []))
    expected_cells = [
        {
            **sector,
            "site_id": str(site["base_station_id"]),
            "position_m": [float(value) for value in site["position_m"]],
            "antenna_height_m": float(site["antenna_height_m"]),
            "antenna_height_agl_m": float(site["antenna_height_agl_m"]),
            "deployment_profile": str(site["deployment_profile"]),
            "preset_id": str(site.get("preset_id", "custom")),
            "preset_version": str(site.get("preset_version", "1.0.0")),
            "antenna_model": str(site.get("antenna_model", "unknown")),
            "function_type": site["metadata"].get("function_type"),
            "source_evidence_level": site["metadata"].get("source_evidence_level"),
            "parameter_status": site["metadata"].get("parameter_status"),
            "sensing_enabled": bool(site["metadata"].get("sensing_enabled", False)),
            "height_reference": str(site["metadata"]["height_reference"]),
            "reference_inter_site_distance_m": site["metadata"].get(
                "reference_inter_site_distance_m"
            ),
            "reference_source": site["metadata"].get("reference_source"),
        }
        for site in sites
        for sector in site["sectors"]
    ]
    if int(manifest.get("site_count", -1)) != len(sites):
        raise ValueError("Base-station manifest site count is inconsistent.")
    if int(manifest.get("sector_count", -1)) != len(cells) or cells != expected_cells:
        raise ValueError("Base-station manifest sector list is inconsistent.")
    expected_fingerprint = _fingerprint(manifest)
    if manifest.get("base_station_fingerprint") != expected_fingerprint:
        raise ValueError("Base-station manifest fingerprint is invalid.")


def save_base_station_manifest(manifest: dict[str, Any], path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_base_station_manifest(path: Path | str, scene: Scene) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_base_station_manifest(manifest, scene)
    return manifest


def _fingerprint(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("base_station_fingerprint", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
