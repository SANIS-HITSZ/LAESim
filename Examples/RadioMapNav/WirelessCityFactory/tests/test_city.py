import math
from collections import Counter
from dataclasses import replace

import pytest

from wireless_city_factory.city import generate_city, validate_free_space
from wireless_city_factory.config import config_from_mapping
from wireless_city_factory.exporters import _FACES, GEOMETRY_CONTRACT, export_obj
from wireless_city_factory.geometry import road_intersects_xy_box
from wireless_city_factory.schema import load_scene


def _config(morphology: str):
    return config_from_mapping({"global": {"seed": 17}, "city": {"size_m": [240, 240], "morphology": morphology, "building": {"coverage_ratio": 0.12, "density_per_km2": 40}, "roads": {"grid_spacing_m": 60, "width_m": 10}, "task": {"altitude_m": 50, "altitude_range_m": [35, 115]}}, "radio": {"enabled": False}, "ue": {"enabled": False}})


def test_all_morphologies_validate_and_are_reproducible() -> None:
    for morphology in ("manhattan", "bsp_tjunction", "voronoi", "radial_organic"):
        config = _config(morphology)
        first = generate_city(config.city, seed=config.seed)
        second = generate_city(config.city, seed=config.seed)
        first.validate()
        assert first.fingerprint() == second.fingerprint()
        assert first.buildings
        statistics = first.metadata["statistics"]
        assert statistics == second.metadata["statistics"]
        assert statistics["building_count"] == len(first.buildings)
        assert 0.0 < statistics["footprint_coverage_ratio"] < 1.0
        assert statistics["free_space_fraction"] > 0.0
        assert statistics["connected_component_count"] >= 1
        assert statistics["task_paths"][0]["reachable"] is True
        assert statistics["task_paths"][0]["shortest_path_m"] > 0.0


def test_all_morphologies_keep_buildings_clear_of_every_road() -> None:
    fingerprints = set()
    for morphology in ("manhattan", "bsp_tjunction", "voronoi", "radial_organic"):
        scene = generate_city(_config(morphology).city, seed=17)
        fingerprints.add(scene.fingerprint())
        for building in scene.buildings:
            minimum = [
                float(building["center_m"][axis]) - float(building["size_m"][axis]) / 2.0
                for axis in (0, 1)
            ]
            maximum = [
                float(building["center_m"][axis]) + float(building["size_m"][axis]) / 2.0
                for axis in (0, 1)
            ]
            assert not any(
                road_intersects_xy_box(road, minimum, maximum) for road in scene.roads
            )
    assert len(fingerprints) == 4


def test_manhattan_default_task_uses_different_cross_streets() -> None:
    scene = generate_city(_config("manhattan").city, seed=17)
    task = scene.tasks[0]
    assert task["start_m"][0] != task["goal_m"][0]
    assert task["start_m"][1] != task["goal_m"][1]
    assert 0.0 < task["start_m"][1] < 240.0
    assert 0.0 < task["goal_m"][1] < 240.0


def test_irregular_morphology_is_a_connected_varied_street_network() -> None:
    scene = generate_city(_config("voronoi").city, seed=17)
    local_roads = [road for road in scene.roads if road["axis"] == "irregular"]
    assert len(local_roads) >= 4

    endpoint_counts = Counter(
        tuple(round(float(value), 6) for value in point[:2])
        for road in local_roads
        for point in (road["start_m"], road["end_m"])
    )
    assert max(endpoint_counts.values()) >= 3

    headings = {
        round(
            math.degrees(
                math.atan2(
                    float(road["end_m"][1]) - float(road["start_m"][1]),
                    float(road["end_m"][0]) - float(road["start_m"][0]),
                )
            ),
        )
        for road in local_roads
    }
    assert len(headings) >= 4


def test_configured_building_separation_is_applied() -> None:
    factory = _config("bsp_tjunction")
    city_config = replace(
        factory.city,
        building=replace(factory.city.building, separation_m=6.0),
    )
    scene = generate_city(city_config, seed=17)
    for index, first in enumerate(scene.buildings):
        for second in scene.buildings[index + 1 :]:
            if first["block_id"] != second["block_id"]:
                continue
            first_min = [
                first["center_m"][axis] - first["size_m"][axis] / 2.0 for axis in (0, 1)
            ]
            first_max = [
                first["center_m"][axis] + first["size_m"][axis] / 2.0 for axis in (0, 1)
            ]
            second_min = [
                second["center_m"][axis] - second["size_m"][axis] / 2.0 for axis in (0, 1)
            ]
            second_max = [
                second["center_m"][axis] + second["size_m"][axis] / 2.0 for axis in (0, 1)
            ]
            dx = max(0.0, first_min[0] - second_max[0], second_min[0] - first_max[0])
            dy = max(0.0, first_min[1] - second_max[1], second_min[1] - first_max[1])
            assert math.hypot(dx, dy) >= 6.0 - 1e-7


def test_scene_round_trip(tmp_path) -> None:
    scene = generate_city(_config("manhattan").city, seed=17)
    path = tmp_path / "scene.json"
    second_path = tmp_path / "scene-copy.json"
    scene.save_json(path)
    generate_city(_config("manhattan").city, seed=17).save_json(second_path)
    loaded = load_scene(path)
    assert loaded.fingerprint() == scene.fingerprint()
    assert path.read_bytes() == second_path.read_bytes()


def test_building_footprint_axes_use_their_own_configured_ranges() -> None:
    config = config_from_mapping(
        {
            "global": {"seed": 23},
            "city": {
                "size_m": [240, 240],
                "building": {
                    "coverage_ratio": 0.2,
                    "density_per_km2": 100,
                    "footprint_min_m": [5, 7],
                    "footprint_max_m": [15, 21],
                },
                "roads": {"grid_spacing_m": 60, "width_m": 10},
            },
        }
    )
    scene = generate_city(config.city, seed=config.seed)
    assert all(5.0 <= item["size_m"][0] <= 15.0 for item in scene.buildings)
    assert all(7.0 <= item["size_m"][1] <= 21.0 for item in scene.buildings)


def test_obj_boxes_are_closed_and_outward(tmp_path) -> None:
    vertices = (
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    )
    edges = Counter(tuple(sorted((a, b))) for a, b, c in _FACES for a, b in ((a, b), (b, c), (c, a)))
    assert GEOMETRY_CONTRACT == "wireless-city-obj-watertight"
    assert len(_FACES) == 12
    assert set(edges.values()) == {2}
    for a, b, c in _FACES:
        p0, p1, p2 = vertices[a], vertices[b], vertices[c]
        u = tuple(p1[i] - p0[i] for i in range(3))
        v = tuple(p2[i] - p0[i] for i in range(3))
        normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        face_center = tuple((p0[i] + p1[i] + p2[i]) / 3.0 for i in range(3))
        assert sum(normal[i] * face_center[i] for i in range(3)) > 0.0

    scene = generate_city(_config("manhattan").city, seed=17)
    obj_path = tmp_path / "scene.obj"
    export_obj(scene, obj_path)
    text = obj_path.read_text(encoding="ascii")
    assert "# geometry contract: wireless-city-obj-watertight" in text
    assert sum(line.startswith("f ") for line in text.splitlines()) == 12 * (1 + len(scene.buildings))


def test_free_space_validation_rejects_unreachable_task() -> None:
    scene = generate_city(_config("manhattan").city, seed=17)
    wall = {
        "building_id": "blocking-wall",
        "block_id": scene.blocks[0]["block_id"],
        "center_m": [120.0, 120.0, 50.0],
        "size_m": [10.0, 240.0, 100.0],
        "material": "concrete",
    }
    blocked_scene = replace(scene, buildings=[wall])
    with pytest.raises(ValueError, match="unreachable"):
        validate_free_space(
            blocked_scene,
            grid_resolution_m=5.0,
            minimum_largest_component_fraction=0.0,
        )
