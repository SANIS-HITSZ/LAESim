"""Read-only validation of the saved Wireless City map inside UE 4.27 Python."""
from __future__ import print_function

import json
import os
import sys
import traceback
from pathlib import Path

COORDINATE_CONTRACT = "wireless-city-scene-to-ue-cm-yflip"
COORDINATE_TRANSFORM = "scene_m_to_ue_cm=(x,-y,z)*100"
SCALE_M_TO_CM = 100.0


def write_result(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")


def actor_label(actor):
    try:
        return str(actor.get_actor_label())
    except Exception:
        return ""


def class_name(actor):
    try:
        return str(actor.get_class().get_name())
    except Exception:
        return ""


def object_path(value):
    if value is None:
        return ""
    try:
        return str(value.get_path_name())
    except Exception:
        return str(value)


def component_property(component, name, aliases=()):
    for candidate in (name,) + tuple(aliases):
        try:
            value = component.get_editor_property(candidate)
            if value is not None:
                return value
        except Exception:
            pass
    return None


def component_material_path(component):
    try:
        return object_path(component.get_material(0))
    except Exception:
        materials = component_property(component, "override_materials") or []
        return object_path(materials[0]) if materials else ""


def scene_m_to_ue_cm(point):
    return [SCALE_M_TO_CM * float(point[0]), -SCALE_M_TO_CM * float(point[1]), SCALE_M_TO_CM * float(point[2])]


def vector_list(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def actor_bounds(actor):
    try:
        origin, extent = actor.get_actor_bounds(False, False)
        center = vector_list(origin)
        half_extent = vector_list(extent)
        return {
            "minimum": [center[i] - half_extent[i] for i in range(3)],
            "maximum": [center[i] + half_extent[i] for i in range(3)],
        }
    except Exception:
        try:
            box = actor.get_components_bounding_box()
            minimum = vector_list(box.min)
            maximum = vector_list(box.max)
            return {"minimum": minimum, "maximum": maximum}
        except Exception:
            return None


def transformed_scene_bounds(scene):
    bounds = scene["bounds_m"]
    minimum = bounds["minimum"]
    maximum = bounds["maximum"]
    return {
        "minimum": scene_m_to_ue_cm((minimum[0], maximum[1], minimum[2])),
        "maximum": scene_m_to_ue_cm((maximum[0], minimum[1], maximum[2])),
    }


def expected_geometry_bounds(scene):
    bounds = scene["bounds_m"]
    maximum_building_z = max(
        (float(item["center_m"][2]) + float(item["size_m"][2]) / 2.0 for item in scene.get("buildings", [])),
        default=0.0,
    )
    return {
        "minimum": scene_m_to_ue_cm((bounds["minimum"][0], bounds["maximum"][1], -0.2)),
        "maximum": scene_m_to_ue_cm((bounds["maximum"][0], bounds["minimum"][1], maximum_building_z)),
    }


def expected_marker_locations(scene, asset_name):
    expected = {}
    for station in scene.get("base_stations", []):
        expected[asset_name + "_BS_" + str(station["base_station_id"])] = scene_m_to_ue_cm(station["position_m"])
    for task in scene.get("tasks", []):
        task_id = str(task["task_id"])
        expected[asset_name + "_Task_" + task_id + "_start"] = scene_m_to_ue_cm(task["start_m"])
        expected[asset_name + "_Task_" + task_id + "_goal"] = scene_m_to_ue_cm(task["goal_m"])
        expected[asset_name + "_PlayerStart_" + task_id] = scene_m_to_ue_cm(task["start_m"])
    return expected


def locations_match_expected(observed, expected, tolerance_cm=0.1):
    return set(observed) == set(expected) and all(
        all(abs(float(actual[i]) - float(expected[label][i])) <= tolerance_cm for i in range(3))
        for label, actual in observed.items()
    )


def locations_inside_bounds(locations, bounds, tolerance_cm=1.0):
    return all(
        all(bounds["minimum"][i] - tolerance_cm <= point[i] <= bounds["maximum"][i] + tolerance_cm for i in range(3))
        for point in locations.values()
    )


def run_validation(unreal, bundle):
    manifest = json.loads((bundle / "ue_manifest.json").read_text(encoding="utf-8"))
    scene = json.loads((bundle / "scene.json").read_text(encoding="utf-8"))
    marker_path = bundle / "ue_import_result.json"
    if not marker_path.exists():
        raise RuntimeError("ue_import_result.json is missing")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("status") != "complete":
        raise RuntimeError("ue_import_result.json is not complete")
    expected_contract = "wireless-city-ue-import-visual"
    if marker.get("import_contract") != expected_contract:
        raise RuntimeError("ue_import_result.json does not match the current import contract")
    expected_geometry_contract = "wireless-city-obj-watertight"
    if manifest.get("geometry_contract") != expected_geometry_contract or marker.get("geometry_contract") != expected_geometry_contract:
        raise RuntimeError("geometry contract is missing or does not match the current contract")
    if (
        manifest.get("coordinate_contract") != COORDINATE_CONTRACT
        or manifest.get("coordinate_transform") != COORDINATE_TRANSFORM
        or marker.get("coordinate_contract") != COORDINATE_CONTRACT
        or marker.get("coordinate_transform") != COORDINATE_TRANSFORM
    ):
        raise RuntimeError("coordinate contract is missing or does not match the current contract")
    fingerprint = manifest.get("source_scene_fingerprint")
    if marker.get("source_scene_fingerprint") != fingerprint:
        raise RuntimeError("import marker and UE manifest have different scene fingerprints")

    map_path = marker.get("map_path")
    if not map_path:
        raise RuntimeError("import marker does not contain map_path")
    if not unreal.EditorLevelLibrary.load_level(map_path):
        raise RuntimeError("UE could not load saved map: " + map_path)
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world is None:
        raise RuntimeError("UE has no editor world after loading the saved map")

    world_settings = world.get_world_settings()
    default_mode = world_settings.get_editor_property("default_game_mode")
    game_mode_path = object_path(default_mode)
    expected_game_mode = "/Script/AirSim.AirSimGameMode"

    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    asset_name = str(manifest.get("asset_name", "WirelessCity"))
    bs_ids = set(str(item["base_station_id"]) for item in scene.get("base_stations", []))
    expected_mesh = str(marker.get("mesh_asset", ""))

    geometry = []
    base_stations = []
    target_points = []
    player_starts = []
    directional_lights = []
    sky_lights = []
    sky_atmospheres = []
    sky_spheres = []
    geometry_material_paths = []
    directional_intensities = []
    directional_z = []
    directional_sun_flags = []
    directional_sun_indices = []
    directional_colors = []
    directional_use_temperature = []
    directional_rotations = []
    sky_intensities = []
    sky_sphere_heights = []
    sky_sphere_brightness = []
    observed_marker_locations = {}
    for actor in actors:
        label = actor_label(actor)
        kind = class_name(actor)
        if kind == "StaticMeshActor":
            mesh = actor.get_component_by_class(unreal.StaticMeshComponent)
            mesh_path = object_path(mesh.get_editor_property("static_mesh")) if mesh else ""
            if label == asset_name + "_Geometry" or mesh_path == expected_mesh:
                geometry.append(actor)
                if mesh is not None:
                    geometry_material_paths.append(component_material_path(mesh))
            if label in bs_ids or label.startswith(asset_name + "_BS_"):
                base_stations.append(actor)
                observed_marker_locations[label] = vector_list(actor.get_actor_location())
        if kind == "TargetPoint" and label.startswith(asset_name + "_Task_"):
            target_points.append(actor)
            observed_marker_locations[label] = vector_list(actor.get_actor_location())
        if kind == "PlayerStart":
            player_starts.append(actor)
            if label.startswith(asset_name + "_PlayerStart_"):
                observed_marker_locations[label] = vector_list(actor.get_actor_location())
        if kind == "DirectionalLight" and label == asset_name + "_DirectionalLight":
            directional_lights.append(actor)
            component = actor.get_component_by_class(unreal.DirectionalLightComponent)
            if component is not None:
                directional_intensities.append(float(component_property(component, "intensity") or 0.0))
                color = component_property(component, "light_color")
                if color is None:
                    directional_colors.append(None)
                else:
                    directional_colors.append([float(color.r), float(color.g), float(color.b), float(color.a)])
                directional_use_temperature.append(component_property(component, "use_temperature"))
                location = actor.get_actor_location()
                directional_z.append(float(location.z))
                rotation = actor.get_actor_rotation()
                directional_rotations.append([float(rotation.pitch), float(rotation.yaw), float(rotation.roll)])
                sun_flag = component_property(component, "atmosphere_sun_light")
                directional_sun_flags.append(None if sun_flag is None else bool(sun_flag))
                index = component_property(component, "atmosphere_sun_light_index")
                directional_sun_indices.append(None if index is None else int(index))
        if kind == "SkyLight" and label == asset_name + "_SkyLight":
            sky_lights.append(actor)
            component = actor.get_component_by_class(unreal.SkyLightComponent)
            if component is not None:
                sky_intensities.append(float(component_property(component, "intensity") or 0.0))
        if kind == "SkyAtmosphere" and label == asset_name + "_SkyAtmosphere":
            sky_atmospheres.append(actor)
        if label == asset_name + "_SkySphere":
            sky_spheres.append(actor)
            sky_sphere_heights.append(component_property(actor, "sun_height", ("Sun height",)))
            sky_sphere_brightness.append(component_property(actor, "sun_brightness", ("Sun brightness",)))

    expected_counts = {
        "geometry": 1,
        "base_stations": len(scene.get("base_stations", [])),
        "target_points": 2 * len(scene.get("tasks", [])),
        "player_starts": 1 if scene.get("tasks") else 0,
    }
    observed_counts = {
        "geometry": len(geometry),
        "base_stations": len(base_stations),
        "target_points": len(target_points),
        "player_starts": len(player_starts),
    }
    expected_visual_counts = {"directional_lights": 1, "sky_lights": 1, "sky_atmospheres": 1, "sky_spheres": 0}
    observed_visual_counts = {
        "directional_lights": len(directional_lights),
        "sky_lights": len(sky_lights),
        "sky_atmospheres": len(sky_atmospheres),
        "sky_spheres": len(sky_spheres),
    }
    expected_material = str(marker.get("geometry_material", "/Engine/EngineMaterials/DefaultMaterial"))
    geometry_material_ok = (
        len(geometry_material_paths) == 1
        and (
            geometry_material_paths[0] == expected_material
            or geometry_material_paths[0].startswith(expected_material + ".")
        )
    )
    geometry_collision_ok = False
    if len(geometry) == 1:
        geometry_mesh = geometry[0].get_component_by_class(unreal.StaticMeshComponent)
        geometry_asset = component_property(geometry_mesh, "static_mesh") if geometry_mesh is not None else None
        geometry_collision_ok = geometry_asset is not None and component_property(geometry_asset, "body_setup") is not None
    geometry_bounds = actor_bounds(geometry[0]) if len(geometry) == 1 else None
    expected_geometry = expected_geometry_bounds(scene)
    geometry_bounds_ok = (
        geometry_bounds is not None
        and all(geometry_bounds["minimum"][i] <= expected_geometry["minimum"][i] + 1.0 for i in range(3))
        and all(geometry_bounds["maximum"][i] >= expected_geometry["maximum"][i] - 1.0 for i in range(3))
    )
    expected_markers = expected_marker_locations(scene, asset_name)
    transformed_bounds = transformed_scene_bounds(scene)
    marker_locations_ok = locations_match_expected(observed_marker_locations, expected_markers)
    marker_bounds_ok = locations_inside_bounds(observed_marker_locations, transformed_bounds)
    directional_ok = (
        len(directional_intensities) == 1
        and directional_intensities[0] >= 10.0
        and all(index == 0 for index in directional_sun_indices)
    )
    directional_height_ok = len(directional_z) == 1 and directional_z[0] >= 100000.0
    directional_color_ok = False
    if len(directional_colors) == 1 and directional_colors[0] is not None:
        # UE4.27 exposes the stored FColor bytes through Python as 0..255,
        # while newer builds expose normalized LinearColor values.
        normalized_color = [value / 255.0 if value > 1.01 else value for value in directional_colors[0]]
        directional_color_ok = all(abs(value - 1.0) <= 0.01 for value in normalized_color)
    directional_temperature_ok = len(directional_use_temperature) == 1 and directional_use_temperature[0] is False
    directional_rotation_ok = (
        len(directional_rotations) == 1
        and all(abs(value - expected) <= 0.01 for value, expected in zip(directional_rotations[0], [-65.0, -30.0, 0.0]))
    )
    sky_ok = len(sky_intensities) == 1 and sky_intensities[0] > 0.0
    sky_sphere_ok = len(sky_spheres) == 0
    expected_visual_settings = {
        "directional_light_z_cm": 100000.0,
        "directional_intensity": 10.0,
        "atmosphere_sun_light_index": 0,
        "light_color": [1.0, 1.0, 1.0, 1.0],
        "use_temperature": False,
        "directional_light_rotation": [-65.0, -30.0, 0.0],
        "background_actor": "SkyAtmosphere",
    }
    satellite_asset_paths = {
        "/Game/AirSim/Models/Satellite/10477_Satellite_v1": False,
        "/Game/AirSim/Models/Satellite/10477_Satellite_v1_L3": False,
        "/Game/AirSim/Models/Satellite/10477_Satellite_v1_Diffuse": False,
    }
    for asset_path in list(satellite_asset_paths):
        try:
            satellite_asset_paths[asset_path] = bool(unreal.EditorAssetLibrary.does_asset_exist(asset_path))
        except Exception:
            satellite_asset_paths[asset_path] = False
    satellite_compatibility_ok = all(satellite_asset_paths.values())
    checks = {
        "map_loaded": True,
        "game_mode": game_mode_path == expected_game_mode,
        "actor_counts": observed_counts == expected_counts,
        "marker_actor_counts": marker.get("actor_counts") == expected_counts,
        "visual_actor_counts": observed_visual_counts == expected_visual_counts,
        "marker_visual_actor_counts": marker.get("visual_actor_counts") == expected_visual_counts,
        "geometry_material": geometry_material_ok,
        "geometry_collision": geometry_collision_ok,
        "geometry_bounds": geometry_bounds_ok,
        "marker_locations": marker_locations_ok,
        "marker_bounds": marker_bounds_ok,
        "directional_light": directional_ok,
        "directional_light_height": directional_height_ok,
        "directional_light_color": directional_color_ok,
        "directional_light_temperature": directional_temperature_ok,
        "directional_light_rotation": directional_rotation_ok,
        "sky_light": sky_ok,
        "sky_atmosphere": len(sky_atmospheres) == 1,
        "sky_sphere": sky_sphere_ok,
        "visual_settings": marker.get("visual_settings") == expected_visual_settings,
        "satellite_compatibility_assets": satellite_compatibility_ok,
    }
    status = "complete" if all(checks.values()) else "failed"
    return {
        "status": status,
        "map_path": map_path,
        "source_scene_fingerprint": fingerprint,
        "game_mode": game_mode_path,
        "expected_game_mode": expected_game_mode,
        "expected_actor_counts": expected_counts,
        "observed_actor_counts": observed_counts,
        "expected_visual_actor_counts": expected_visual_counts,
        "observed_visual_actor_counts": observed_visual_counts,
        "geometry_material": geometry_material_paths[0] if geometry_material_paths else "",
        "geometry_collision": geometry_collision_ok,
        "geometry_bounds": geometry_bounds,
        "expected_geometry_bounds": expected_geometry,
        "transformed_scene_bounds": transformed_bounds,
        "expected_marker_locations": expected_markers,
        "observed_marker_locations": observed_marker_locations,
        "coordinate_contract": COORDINATE_CONTRACT,
        "coordinate_transform": COORDINATE_TRANSFORM,
        "directional_intensities": directional_intensities,
        "directional_colors": directional_colors,
        "directional_use_temperature": directional_use_temperature,
        "directional_z": directional_z,
        "directional_rotations": directional_rotations,
        "directional_atmosphere_sun_flags": directional_sun_flags,
        "directional_atmosphere_sun_indices": directional_sun_indices,
        "sky_intensities": sky_intensities,
        "sky_sphere_sun_heights": sky_sphere_heights,
        "sky_sphere_sun_brightness": sky_sphere_brightness,
        "satellite_compatibility_assets": satellite_asset_paths,
        "level_actor_count": len(actors),
        "checks": checks,
    }


def main():
    output = Path(os.environ.get("WCF_VALIDATION_OUTPUT", "ue_validation_result.json"))
    bundle = Path(os.environ.get("WCF_BUNDLE_ROOT", ""))
    try:
        if not bundle.is_dir():
            raise RuntimeError("WCF_BUNDLE_ROOT is missing or is not a directory")
        import unreal

        payload = run_validation(unreal, bundle)
    except Exception as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    write_result(output, payload)
    print("UE_VALIDATION_RESULT=" + json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
