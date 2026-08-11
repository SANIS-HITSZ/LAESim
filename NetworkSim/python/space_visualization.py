#!/usr/bin/env python3
"""Pure geometry and settings helpers for LAESim space visualization."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


EARTH_RADIUS_M = 6378137.0


@dataclass(frozen=True)
class VehicleOrigin:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


def load_vehicle_origins(settings_path):
    with open(settings_path, "r", encoding="utf-8-sig") as handle:
        settings = json.load(handle)
    origins = {}
    for name, vehicle in settings.get("Vehicles", {}).items():
        origins[name] = VehicleOrigin(
            float(vehicle.get("X", 0.0)),
            float(vehicle.get("Y", 0.0)),
            float(vehicle.get("Z", 0.0)),
        )
    return origins


def to_global_ned(local_xyz, origin=VehicleOrigin()):
    return (
        float(local_xyz[0]) + origin.x,
        float(local_xyz[1]) + origin.y,
        float(local_xyz[2]) + origin.z,
    )


def coverage_central_angle_rad(altitude_m, min_elevation_deg, earth_radius_m=EARTH_RADIUS_M):
    altitude_m = max(0.0, float(altitude_m))
    elevation_rad = math.radians(max(0.0, min(90.0, float(min_elevation_deg))))
    satellite_radius_m = earth_radius_m + altitude_m
    ratio = max(-1.0, min(1.0, earth_radius_m / satellite_radius_m * math.cos(elevation_rad)))
    angle = math.pi * 0.5 - elevation_rad - math.asin(ratio)
    return max(0.0, angle)


def projected_coverage_radius(display_radius, altitude_m, min_elevation_deg):
    angle = coverage_central_angle_rad(altitude_m, min_elevation_deg)
    return abs(float(display_radius)) * math.sin(angle)


def circle_points(center_x, center_y, z, radius, segments=48):
    if segments < 8:
        raise ValueError("segments must be at least 8")
    radius = max(0.0, float(radius))
    return [
        (
            float(center_x) + radius * math.cos(2.0 * math.pi * index / segments),
            float(center_y) + radius * math.sin(2.0 * math.pi * index / segments),
            float(z),
        )
        for index in range(segments + 1)
    ]
