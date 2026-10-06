"""Named city morphology profiles with deliberately separated statistics."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .config import FactoryConfig

CITY_PROFILES: dict[str, dict[str, Any]] = {
    "dense_highrise_grid": {
        "description": "Dense orthogonal high-rise core with wide arterial street canyons.",
        "morphology": "manhattan",
        "building": {
            "profile": "dense_highrise_grid",
            "coverage_ratio": 0.38,
            "density_per_km2": 220.0,
            "height_distribution": "lognormal",
            "height_min_m": 25.0,
            "height_max_m": 140.0,
            "height_mean_m": 55.0,
            "height_std_m": 25.0,
            "footprint_min_m": (12.0, 12.0),
            "footprint_max_m": (34.0, 34.0),
            "separation_m": 5.0,
        },
        "roads": {"grid_spacing_m": 90.0, "width_m": 18.0, "radial_count": 8, "ring_count": 2},
    },
    "irregular_midrise": {
        "description": "Organic mid-rise district with a connected network of offset junctions and varied street directions.",
        "morphology": "voronoi",
        "building": {
            "profile": "irregular_midrise",
            "coverage_ratio": 0.27,
            "density_per_km2": 180.0,
            "height_distribution": "normal",
            "height_min_m": 8.0,
            "height_max_m": 55.0,
            "height_mean_m": 24.0,
            "height_std_m": 9.0,
            "footprint_min_m": (8.0, 8.0),
            "footprint_max_m": (26.0, 26.0),
            "separation_m": 4.0,
        },
        "roads": {"grid_spacing_m": 75.0, "width_m": 11.0, "radial_count": 8, "ring_count": 2},
    },
    # 紧凑径向低层建筑
    "compact_radial_lowrise": {
        "description": "Compact low-rise district organized by radial and ring roads.",
        "morphology": "radial_organic",
        "building": {
            "profile": "compact_radial_lowrise",
            "coverage_ratio": 0.43,
            "density_per_km2": 360.0,
            "height_distribution": "uniform",
            "height_min_m": 5.0,
            "height_max_m": 28.0,
            "height_mean_m": 16.0,
            "height_std_m": 6.0,
            "footprint_min_m": (6.0, 6.0),
            "footprint_max_m": (18.0, 18.0),
            "separation_m": 2.0,
        },
        "roads": {"grid_spacing_m": 68.0, "width_m": 8.0, "radial_count": 12, "ring_count": 3},
    },
    "sparse_suburban": {
        "description": "Sparse low-rise suburb with large blocks and generous open space.",
        "morphology": "bsp_tjunction",
        "building": {
            "profile": "sparse_suburban",
            "coverage_ratio": 0.12,
            "density_per_km2": 70.0,
            "height_distribution": "normal",
            "height_min_m": 4.0,
            "height_max_m": 18.0,
            "height_mean_m": 9.0,
            "height_std_m": 3.0,
            "footprint_min_m": (10.0, 10.0),
            "footprint_max_m": (30.0, 30.0),
            "separation_m": 8.0,
        },
        "roads": {"grid_spacing_m": 130.0, "width_m": 12.0, "radial_count": 6, "ring_count": 1},
    },
}

CITY_PROFILE_NAMES = tuple(CITY_PROFILES)


def apply_city_profile(config: FactoryConfig, profile_name: str) -> FactoryConfig:
    """Apply one named morphology and its building/road parameters."""
    try:
        profile = CITY_PROFILES[profile_name]
    except KeyError as exc:
        raise ValueError(f"Unknown city profile: {profile_name}") from exc
    city = replace(
        config.city,
        morphology=str(profile["morphology"]),
        building=replace(config.city.building, **profile["building"]),
        roads=replace(config.city.roads, **profile["roads"]),
    )
    return replace(config, city=city)
