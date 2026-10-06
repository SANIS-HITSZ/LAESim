"""Unreal-ready bundle generation and fail-closed Editor Python importer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base_stations import build_base_station_manifest, validate_base_station_manifest
from .config import UEConfig
from .exporters import GEOMETRY_CONTRACT, export_obj
from .schema import Scene

IMPORT_CONTRACT = "wireless-city-ue-import-visual"
COORDINATE_CONTRACT = "wireless-city-scene-to-ue-cm-yflip"
COORDINATE_TRANSFORM = "scene_m_to_ue_cm=(x,-y,z)*100"
SCALE_M_TO_CM = 100.0


def scene_m_to_ue_cm(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """Map canonical right-handed +Z-up metres to UE OBJ world centimetres."""
    return (SCALE_M_TO_CM * float(point[0]), -SCALE_M_TO_CM * float(point[1]), SCALE_M_TO_CM * float(point[2]))

IMPORTER = r'''"""Run inside Unreal Editor Python, or use --dry-run in ordinary Python."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

SCALE_M_TO_CM = 100.0
GENERATED_LABEL_PREFIX = "WirelessCity_"
GENERATED_ACTOR_TAG = "WirelessCityGenerated"
IMPORT_CONTRACT = "wireless-city-ue-import-visual"
COORDINATE_CONTRACT = "wireless-city-scene-to-ue-cm-yflip"
COORDINATE_TRANSFORM = "scene_m_to_ue_cm=(x,-y,z)*100"
DEFAULT_MATERIAL_PATH = "/Engine/EngineMaterials/DefaultMaterial"
DIRECTIONAL_LIGHT_Z_CM = 100000.0
GEOMETRY_CONTRACT = "wireless-city-obj-watertight"
DAY_LIGHT_COLOR = [1.0, 1.0, 1.0, 1.0]
DAY_LIGHT_ROTATION = [-65.0, -30.0, 0.0]

def load_manifest(root: Path) -> dict:
    value = json.loads((root / "ue_manifest.json").read_text(encoding="utf-8"))
    if value.get("status") != "complete":
        raise RuntimeError("UE manifest is not complete")
    if value.get("source_units") != "m" or value.get("ue_units") != "cm":
        raise RuntimeError("Unexpected unit contract")
    if value.get("geometry_contract") != GEOMETRY_CONTRACT:
        raise RuntimeError("UE manifest geometry contract does not match the current contract: " + str(value.get("geometry_contract")))
    if value.get("import_contract") != IMPORT_CONTRACT:
        raise RuntimeError("UE manifest import contract does not match the current contract: " + str(value.get("import_contract")))
    if value.get("coordinate_contract") != COORDINATE_CONTRACT or value.get("coordinate_transform") != COORDINATE_TRANSFORM:
        raise RuntimeError("UE manifest coordinate contract does not match the current contract")
    return value

def load_scene_and_stations(root: Path, manifest: dict) -> dict:
    scene = json.loads((root / "scene.json").read_text(encoding="utf-8"))
    stations = json.loads((root / manifest["base_station_manifest"]).read_text(encoding="utf-8"))
    if stations.get("status") != "complete":
        raise RuntimeError("Base-station manifest is not complete")
    if stations.get("base_station_fingerprint") != manifest.get("base_station_fingerprint"):
        raise RuntimeError("UE and base-station manifest fingerprints do not match")
    if stations.get("scene_fingerprint") != manifest.get("source_scene_fingerprint"):
        raise RuntimeError("Base-station and scene fingerprints do not match")
    if stations.get("sites") != scene.get("base_stations"):
        raise RuntimeError("Base-station manifest sites do not match scene.json")
    scene["base_stations"] = stations["sites"]
    return scene

def scene_m_to_ue_cm(point):
    """Map canonical metres to UE centimetres, compensating for OBJ Y inversion."""
    return (SCALE_M_TO_CM * float(point[0]), -SCALE_M_TO_CM * float(point[1]), SCALE_M_TO_CM * float(point[2]))

def dry_run(root: Path) -> int:
    manifest = load_manifest(root)
    scene = load_scene_and_stations(root, manifest)
    required = ["buildings", "base_stations", "tasks", "roads"]
    missing = [key for key in required if key not in scene]
    if missing:
        raise RuntimeError("Canonical scene is missing: " + ", ".join(missing))
    print(json.dumps({"status": "dry-run", "would_import": manifest["mesh_file"], "building_count": len(scene["buildings"]), "base_station_count": len(scene["base_stations"]), "task_count": len(scene["tasks"]), "scale_m_to_cm": SCALE_M_TO_CM, "coordinate_contract": COORDINATE_CONTRACT, "coordinate_transform": COORDINATE_TRANSFORM}, indent=2, sort_keys=True))
    return 0

def require_unreal():
    try:
        import unreal
    except ImportError as exc:
        raise RuntimeError("This importer must run inside Unreal Editor Python; ordinary Python cannot create a .umap.") from exc
    required = ["AssetImportTask", "AssetToolsHelpers", "EditorAssetLibrary", "EditorLevelLibrary", "StaticMeshActor", "StaticMeshComponent", "TargetPoint", "Vector", "DirectionalLight", "DirectionalLightComponent", "SkyLight", "SkyLightComponent", "SkyAtmosphere", "SkyAtmosphereComponent"]
    missing = [name for name in required if not hasattr(unreal, name)]
    if not hasattr(unreal.EditorLevelLibrary, "destroy_actor"):
        missing.append("EditorLevelLibrary.destroy_actor")
    if missing:
        raise RuntimeError("Unreal Python API is missing: " + ", ".join(missing))
    return unreal

def safe_asset_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not name or name[0].isdigit():
        name = "City_" + name
    return name

def expected_counts(scene: dict) -> dict:
    return {
        "geometry": 1,
        "base_stations": len(scene["base_stations"]),
        "target_points": 2 * len(scene["tasks"]),
        "player_starts": 1 if scene["tasks"] else 0,
    }

def expected_visual_counts() -> dict:
    return {"directional_lights": 1, "sky_lights": 1, "sky_atmospheres": 1, "sky_spheres": 0}

def expected_visual_settings() -> dict:
    return {
        "directional_light_z_cm": DIRECTIONAL_LIGHT_Z_CM,
        "directional_intensity": 10.0,
        "atmosphere_sun_light_index": 0,
        "light_color": DAY_LIGHT_COLOR,
        "use_temperature": False,
        "directional_light_rotation": DAY_LIGHT_ROTATION,
        "background_actor": "SkyAtmosphere",
    }

def result_path(root: Path) -> Path:
    return root / "ue_import_result.json"

def _asset_exists(unreal, asset_path: str) -> bool:
    try:
        return unreal.EditorAssetLibrary.load_asset(asset_path) is not None
    except Exception:
        return False

def _map_exists(unreal, map_path: str) -> bool:
    try:
        return bool(unreal.EditorAssetLibrary.does_asset_exist(map_path))
    except Exception:
        return False

def reusable_result(unreal, root: Path, manifest: dict, scene: dict, map_path: str) -> bool:
    path = result_path(root)
    if not path.exists():
        return False
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("status") != "complete":
        return False
    if result.get("import_contract") != IMPORT_CONTRACT:
        return False
    if result.get("geometry_contract") != GEOMETRY_CONTRACT:
        return False
    if result.get("coordinate_contract") != COORDINATE_CONTRACT or result.get("coordinate_transform") != COORDINATE_TRANSFORM:
        return False
    if result.get("source_scene_fingerprint") != manifest.get("source_scene_fingerprint"):
        raise RuntimeError("A completed UE import exists with a different scene fingerprint; refusing to overwrite the map")
    if result.get("map_path") != map_path:
        raise RuntimeError("A completed UE import exists at an unexpected map path; refusing to overwrite it")
    expected = expected_counts(scene)
    if result.get("actor_counts") != expected:
        raise RuntimeError("The completed UE import marker has unexpected actor counts; refusing to overwrite the map")
    if result.get("visual_actor_counts") != expected_visual_counts():
        raise RuntimeError("The completed UE import marker has an incomplete visual environment; refusing to overwrite the map")
    if result.get("visual_settings") != expected_visual_settings():
        raise RuntimeError("The completed UE import marker has non-current visual settings; refusing to overwrite the map")
    if not _map_exists(unreal, map_path) or not _asset_exists(unreal, result.get("mesh_asset", "")):
        raise RuntimeError("The completed UE import marker exists but its map or mesh asset cannot be loaded")
    return True

def _label(actor) -> str:
    try:
        return str(actor.get_actor_label())
    except Exception:
        return ""

def _tags(actor) -> set[str]:
    try:
        return {str(tag) for tag in actor.get_editor_property("tags")}
    except Exception:
        return set()

def clear_partial_generated_actors(unreal, asset_name: str, scene: dict) -> None:
    asset_prefix = asset_name + "_"
    for actor in list(unreal.EditorLevelLibrary.get_all_level_actors()):
        label = _label(actor)
        if (
            GENERATED_ACTOR_TAG in _tags(actor)
            or label.startswith(asset_prefix)
            or label.startswith(GENERATED_LABEL_PREFIX)
        ):
            unreal.EditorLevelLibrary.destroy_actor(actor)
    remaining = [
        _label(actor)
        for actor in unreal.EditorLevelLibrary.get_all_level_actors()
        if GENERATED_ACTOR_TAG in _tags(actor) or _label(actor).startswith(asset_prefix)
    ]
    if remaining:
        raise RuntimeError("UE could not remove stale generated actors: " + ", ".join(sorted(remaining)))

def create_city_level(unreal, asset_name: str, root: Path, manifest: dict, scene: dict) -> tuple[str, bool]:
    map_path = "/Game/WirelessCity/Maps/" + safe_asset_name(asset_name)
    if unreal.EditorAssetLibrary.does_asset_exist(map_path):
        if not unreal.EditorLevelLibrary.load_level(map_path):
            raise RuntimeError("UE could not load the existing city level: " + map_path)
        clear_partial_generated_actors(unreal, asset_name, scene)
    elif not unreal.EditorLevelLibrary.new_level(map_path):
        raise RuntimeError("UE could not create the city level: " + map_path)
    return map_path, False

def configure_airsim_game_mode(unreal) -> None:
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world is None:
        raise RuntimeError("UE has no editor world after creating the city level")
    game_mode = unreal.load_class(None, "/Script/AirSim.AirSimGameMode")
    if game_mode is None:
        raise RuntimeError("AirSimGameMode is unavailable; verify that the AirSim plugin loaded")
    world.get_world_settings().set_editor_property("default_game_mode", game_mode)

def mark_generated(actor, label: str) -> None:
    actor.set_actor_label(label)
    try:
        actor.set_editor_property("tags", [GENERATED_ACTOR_TAG])
    except Exception:
        pass

def require_single_player_start(unreal, expected_label: str | None) -> None:
    player_starts = [
        actor
        for actor in unreal.EditorLevelLibrary.get_all_level_actors()
        if str(actor.get_class().get_name()) == "PlayerStart"
    ]
    if expected_label is None:
        if player_starts:
            raise RuntimeError("UE map contains a PlayerStart although the scene has no task")
        return
    if len(player_starts) != 1 or _label(player_starts[0]) != expected_label:
        observed = [_label(actor) for actor in player_starts]
        raise RuntimeError(
            "UE map must contain exactly one current PlayerStart; observed: "
            + json.dumps(observed, sort_keys=True)
        )

def set_default_material(unreal, component) -> str:
    material = unreal.EditorAssetLibrary.load_asset(DEFAULT_MATERIAL_PATH)
    if material is None:
        raise RuntimeError("UE default material is unavailable: " + DEFAULT_MATERIAL_PATH)
    component.set_material(0, material)
    return DEFAULT_MATERIAL_PATH

def set_required_property(obj, name: str, value, aliases=()) -> None:
    last_error = None
    for candidate in (name,) + tuple(aliases):
        try:
            obj.set_editor_property(candidate, value)
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError("UE could not set required property " + name) from last_error

def ensure_visual_environment(unreal, asset_name: str) -> dict:
    labels = {str(actor.get_actor_label()): actor for actor in unreal.EditorLevelLibrary.get_all_level_actors()}
    changed = False
    light = labels.get(asset_name + "_DirectionalLight")
    if light is None:
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0.0, 0.0, DIRECTIONAL_LIGHT_Z_CM))
        mark_generated(light, asset_name + "_DirectionalLight")
        changed = True
    # Directional-light position does not affect illumination; high Z keeps the
    # source easy to inspect in the editor without intersecting the city.
    light.set_actor_location(unreal.Vector(0.0, 0.0, DIRECTIONAL_LIGHT_Z_CM), False, False)
    # Unreal's positional Rotator constructor is (roll, pitch, yaw), while
    # the contract records the editor-facing (pitch, yaw, roll) order.
    light.set_actor_rotation(unreal.Rotator(DAY_LIGHT_ROTATION[2], DAY_LIGHT_ROTATION[0], DAY_LIGHT_ROTATION[1]), False)
    light_component = light.get_component_by_class(unreal.DirectionalLightComponent)
    if light_component is None:
        raise RuntimeError("DirectionalLight has no DirectionalLightComponent")
    set_required_property(light_component, "intensity", 10.0)
    # UE4.27 exposes LightColor as BlueprintReadOnly; use its setter instead
    # of set_editor_property, which fails even though the light is editable.
    try:
        light_component.set_light_color(unreal.LinearColor(*DAY_LIGHT_COLOR), True)
    except TypeError:
        light_component.set_light_color(unreal.LinearColor(*DAY_LIGHT_COLOR))
    except Exception as exc:
        raise RuntimeError("UE could not set required light_color") from exc
    try:
        light_component.set_use_temperature(False)
    except Exception as exc:
        raise RuntimeError("UE could not disable light temperature") from exc
    try:
        light_component.set_atmosphere_sun_light(True)
    except Exception as exc:
        raise RuntimeError("UE could not enable atmosphere sun light") from exc
    set_required_property(light_component, "atmosphere_sun_light_index", 0)

    sky = labels.get(asset_name + "_SkyLight")
    if sky is None:
        sky = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0.0, 0.0, 1000.0))
        mark_generated(sky, asset_name + "_SkyLight")
        changed = True
    sky_component = sky.get_component_by_class(unreal.SkyLightComponent)
    if sky_component is None:
        raise RuntimeError("SkyLight has no SkyLightComponent")
    sky_component.set_editor_property("intensity", 1.0)
    if hasattr(sky_component, "recapture_sky"):
        sky_component.recapture_sky()

    atmosphere = labels.get(asset_name + "_SkyAtmosphere")
    if atmosphere is None:
        atmosphere = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0.0, 0.0, 0.0))
        mark_generated(atmosphere, asset_name + "_SkyAtmosphere")
        changed = True
    atmosphere_component = atmosphere.get_component_by_class(unreal.SkyAtmosphereComponent)
    if atmosphere_component is None:
        raise RuntimeError("SkyAtmosphere has no SkyAtmosphereComponent")
    # BP_Sky_Sphere has a sunset-oriented material in UE4.27 and its
    # Blueprint variables are not reliably writable from Editor Python.  The
    # native SkyAtmosphere is the stable daytime background for this map.
    sky_sphere = labels.get(asset_name + "_SkySphere")
    if sky_sphere is not None:
        unreal.EditorLevelLibrary.destroy_actor(sky_sphere)
        changed = True
    changed = True
    return {**expected_visual_counts(), "changed": changed}

def import_bundle(root: Path) -> int:
    unreal = require_unreal()
    manifest = load_manifest(root)
    scene = load_scene_and_stations(root, manifest)
    asset_name = safe_asset_name(str(manifest["asset_name"]))
    map_path, reused = create_city_level(unreal, asset_name, root, manifest, scene)
    if reused:
        if not unreal.EditorLevelLibrary.load_level(map_path):
            raise RuntimeError("UE could not reload the completed city level: " + map_path)
        visual_counts = ensure_visual_environment(unreal, asset_name)
        if visual_counts["changed"] and not unreal.EditorLevelLibrary.save_current_level():
            raise RuntimeError("UE could not save the visual environment changes")
        result = json.loads(result_path(root).read_text(encoding="utf-8"))
        result["import_contract"] = IMPORT_CONTRACT
        result["coordinate_contract"] = COORDINATE_CONTRACT
        result["coordinate_transform"] = COORDINATE_TRANSFORM
        result["visual_actor_counts"] = expected_visual_counts()
        result["visual_settings"] = expected_visual_settings()
        result_path(root).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
        print("Reused completed Wireless City level: " + map_path)
        return 0
    configure_airsim_game_mode(unreal)
    import_task = unreal.AssetImportTask()
    import_task.filename = str((root / manifest["mesh_file"]).resolve())
    import_task.destination_path = "/Game/WirelessCity/Geometry/" + asset_name
    import_task.automated = True
    import_task.replace_existing = True
    import_task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([import_task])
    imported = list(import_task.imported_object_paths)
    if not imported:
        raise RuntimeError("UE did not report an imported static mesh")
    mesh_asset = unreal.EditorAssetLibrary.load_asset(imported[0])
    if mesh_asset is None:
        raise RuntimeError("UE could not load the imported static mesh")
    if hasattr(mesh_asset, "get_editor_property"):
        body_setup = mesh_asset.get_editor_property("body_setup")
        if body_setup is not None and hasattr(unreal, "CollisionTraceFlag"):
            body_setup.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            mesh_asset.modify()
            unreal.EditorAssetLibrary.save_loaded_asset(mesh_asset)
    mesh_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, 0.0))
    mesh_component = mesh_actor.get_component_by_class(unreal.StaticMeshComponent)
    mesh_component.set_static_mesh(mesh_asset)
    geometry_material = set_default_material(unreal, mesh_component)
    mesh_actor.set_actor_scale3d(unreal.Vector(SCALE_M_TO_CM, SCALE_M_TO_CM, SCALE_M_TO_CM))
    mark_generated(mesh_actor, asset_name + "_Geometry")
    # The imported mesh carries building collision; markers are spawned separately.
    cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    if cube is None:
        raise RuntimeError("UE basic cube asset is unavailable for markers")
    for station in scene["base_stations"]:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*scene_m_to_ue_cm(station["position_m"])))
        actor.static_mesh_component.set_static_mesh(cube)
        actor.set_actor_scale3d(unreal.Vector(0.5, 0.5, 3.0))
        mark_generated(actor, asset_name + "_BS_" + str(station["base_station_id"]))
    for task in scene["tasks"]:
        for key, label in (("start_m", "start"), ("goal_m", "goal")):
            point = task[key]
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(*scene_m_to_ue_cm(point)))
            mark_generated(actor, asset_name + "_Task_" + str(task["task_id"]) + "_" + label)
    if scene["tasks"] and hasattr(unreal, "PlayerStart"):
        first_task = scene["tasks"][0]
        point = first_task["start_m"]
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*scene_m_to_ue_cm(point)))
        mark_generated(actor, asset_name + "_PlayerStart_" + str(first_task["task_id"]))
    expected_player_start = (
        asset_name + "_PlayerStart_" + str(scene["tasks"][0]["task_id"])
        if scene["tasks"]
        else None
    )
    require_single_player_start(unreal, expected_player_start)
    visual_counts = ensure_visual_environment(unreal, asset_name)
    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("UE could not save the imported city level")
    result = {
        "status": "complete",
        "import_contract": IMPORT_CONTRACT,
        "geometry_contract": GEOMETRY_CONTRACT,
        "coordinate_contract": COORDINATE_CONTRACT,
        "coordinate_transform": COORDINATE_TRANSFORM,
        "map_path": map_path,
        "mesh_asset": str(imported[0]),
        "source_scene_fingerprint": manifest["source_scene_fingerprint"],
        "building_count": len(scene["buildings"]),
        "base_station_count": len(scene["base_stations"]),
        "task_count": len(scene["tasks"]),
        "actor_counts": expected_counts(scene),
        "visual_actor_counts": expected_visual_counts(),
        "visual_settings": expected_visual_settings(),
        "geometry_material": geometry_material,
        "airsim_game_mode": "/Script/AirSim.AirSimGameMode",
    }
    (root / "ue_import_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("Imported and saved Wireless City level: " + map_path)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return dry_run(args.bundle) if args.dry_run else import_bundle(args.bundle)
    except Exception as exc:
        print("UE IMPORT FAILED: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
'''


def generate_ue_bundle(
    scene: Scene,
    config: UEConfig,
    output_dir: Path | str,
    base_station_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    bundle = target / "ue_bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    station_manifest = base_station_manifest or build_base_station_manifest(scene)
    validate_base_station_manifest(station_manifest, scene)
    export_obj(scene, bundle / "scene.obj")
    (bundle / "scene.json").write_text(json.dumps(scene.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    (bundle / "base_station_manifest.json").write_text(
        json.dumps(station_manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (bundle / "import_wireless_city.py").write_text(IMPORTER, encoding="ascii")
    if config.generate_airsim_settings:
        settings = _airsim_settings(scene)
        (bundle / "settings.json").write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="ascii")
    project_exists = bool(config.editor_project and Path(config.editor_project).expanduser().is_file())
    manifest = {
        "schema_version": "wireless-city-ue",
        "status": "complete",
        "backend": "unreal-editor-python-bundle",
        "source_scene_id": scene.scene_id,
        "source_scene_fingerprint": scene.fingerprint(),
        "base_station_manifest": "ue_bundle/base_station_manifest.json",
        "base_station_fingerprint": station_manifest["base_station_fingerprint"],
        "source_units": "m",
        "source_frame": "right-handed,+z-up",
        "ue_units": "cm",
        "ue_frame": "right-handed,+z-up",
        "meters_to_centimeters": 100.0,
        "mesh_file": "ue_bundle/scene.obj",
        "importer_file": "ue_bundle/import_wireless_city.py",
        "asset_name": config.import_asset_name,
        "collision": "OBJ static mesh collision plus marker actors",
        "editor_project_configured": project_exists,
        "editor_project": config.editor_project,
        "airsim_settings": "ue_bundle/settings.json" if config.generate_airsim_settings else None,
        "source_of_truth": "scene.json; UE is not a channel truth source",
        "geometry_contract": GEOMETRY_CONTRACT,
        "import_contract": IMPORT_CONTRACT,
        "coordinate_contract": COORDINATE_CONTRACT,
        "coordinate_transform": COORDINATE_TRANSFORM,
    }
    (target / "ue_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _airsim_settings(scene: Scene) -> dict[str, Any]:
    return {
        "SettingsVersion": 1.2,
        "SimMode": "Multirotor",
        "ClockType": "ScalableClock",
        "ApiServerPortMultirotor": 41471,
        "ViewMode": "FlyWithMe",
        "CoordinateConvention": "UE editor uses centimetres and +Z-up; AirSim runtime pose is NED relative to PlayerStart",
        "Vehicles": {
            "UAV": {
                "VehicleType": "SimpleFlight",
                "AutoCreate": True,
                "X": 0.0,
                "Y": 0.0,
                "Z": 0.0,
            }
        },
        "WirelessCity": {"scene_id": scene.scene_id, "scene_fingerprint": scene.fingerprint(), "player_start_source": "UE PlayerStart actor; do not copy canonical +Z-up coordinates into NED X/Y/Z"},
    }


def validate_ue_bundle(bundle: Path | str) -> dict[str, Any]:
    root = Path(bundle)
    manifest = json.loads((root / "ue_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("UE bundle is not complete")
    if not (root / "scene.json").is_file():
        raise FileNotFoundError("scene.json")
    for relative in (
        manifest["mesh_file"],
        manifest["importer_file"],
        manifest["base_station_manifest"],
    ):
        if not (root.parent / relative).exists() and not (root / relative).exists():
            raise FileNotFoundError(relative)
    return manifest
