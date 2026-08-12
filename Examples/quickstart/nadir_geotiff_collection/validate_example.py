#!/usr/bin/env python3
"""Dependency-free structural validation for the nadir collection quickstart."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    required = (
        "coverage_mission.py",
        "collect_geotiff_dataset.py",
        "collect_airsim_nadir.py",
        "prepare_scenemap.py",
        "settings.example.json",
        "requirements.txt",
        "README.md",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"missing quickstart files: {', '.join(missing)}")

    settings = json.loads((root / "settings.example.json").read_text(encoding="utf-8"))
    scene_map = settings["SceneMap"]
    camera = settings["Vehicles"]["UAV"]["Cameras"]["nadir"]
    gimbal = camera["Gimbal"]
    if scene_map["PixelCoordinateFrame"] != "NorthUp":
        raise RuntimeError("SceneMap must use the NorthUp frame")
    if camera["Pitch"] != -90.0 or gimbal != {
        "Stabilization": 1.0,
        "Pitch": -90.0,
        "Roll": 0.0,
        "Yaw": 0.0,
    }:
        raise RuntimeError("the nadir camera must use full world-frame stabilization")
    print("nadir GeoTIFF collection quickstart: configuration check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
