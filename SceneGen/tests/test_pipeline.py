import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import laesim_scene.pipeline as pipeline_module
import pytest
from laesim_scene.city import generate_city
from laesim_scene.config import config_from_mapping
from laesim_scene.exporters import GEOMETRY_CONTRACT
from laesim_scene.pipeline import PipelineError, generate, generate_candidates
from laesim_scene.profiles import CITY_PROFILE_NAMES, apply_city_profile
from laesim_scene.ue import (
    COORDINATE_CONTRACT,
    COORDINATE_TRANSFORM,
    IMPORT_CONTRACT,
    IMPORTER,
    _airsim_settings,
    scene_m_to_ue_cm,
)


def _importer_namespace() -> dict:
    namespace = {"__name__": "wireless_city_importer_test"}
    exec(IMPORTER, namespace)
    return namespace


def _config(output: str, *, ue: bool = False, radio: bool = False):
    return config_from_mapping({"global": {"seed": 4, "name": "test", "output": output}, "city": {"size_m": [120, 120], "building": {"coverage_ratio": 0.08, "density_per_km2": 20}, "roads": {"grid_spacing_m": 50, "width_m": 8}, "task": {"altitude_m": 50, "altitude_range_m": [35, 65]}}, "radio": {"enabled": radio}, "ue": {"enabled": ue}})


def test_city_only_and_ue_routing(tmp_path) -> None:
    city_result = generate(_config(str(tmp_path / "city")), project_root=tmp_path)
    assert city_result["status"] == "complete"
    assert (Path(city_result["output_dir"]) / "scene.json").exists()
    assert (Path(city_result["output_dir"]) / "base_station_manifest.json").exists()
    ue_result = generate(_config(str(tmp_path / "ue"), ue=True), project_root=tmp_path)
    ue_dir = Path(ue_result["output_dir"])
    assert (ue_dir / "ue_manifest.json").exists()
    completed = json.loads((ue_dir / "manifest.json").read_text())
    assert completed["stage_status"]["ue"]["status"] == "complete"
    importer = ue_dir / "ue_bundle" / "import_wireless_city.py"
    result = subprocess.run([sys.executable, str(importer), "--bundle", str(ue_dir), "--dry-run"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert '"status": "dry-run"' in result.stdout


def test_identical_concurrent_runs_publish_once_and_reuse(tmp_path) -> None:
    config = _config(str(tmp_path / "concurrent"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(config, project_root=tmp_path), range(2)))
    assert results[0]["output_dir"] == results[1]["output_dir"]
    assert sorted(result.get("reused", False) for result in results) == [False, True]
    manifest = json.loads((Path(results[0]["output_dir"]) / "manifest.json").read_text())
    assert manifest["status"] == "complete"


def test_radio_failure_does_not_publish_success_manifest(tmp_path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("Sionna missing")

    monkeypatch.setattr(pipeline_module, "run_radio_stage", fail)
    with pytest.raises(PipelineError):
        generate(_config(str(tmp_path / "radio"), radio=True), project_root=tmp_path)
    failed = list((tmp_path / "radio").glob("*.failed-*"))
    assert failed
    assert not (failed[0] / "manifest.json").exists()
    assert json.loads((failed[0] / "radio_failure.json").read_text())["success_manifest_published"] is False


def test_radio_and_ue_combination_routes_both_stages(tmp_path, monkeypatch) -> None:
    def fake_radio(scene, config, output_dir, base_station_manifest):
        payload = {"status": "complete", "radio_fingerprint": "smoke-test"}
        (Path(output_dir) / "radio_manifest.json").write_text(json.dumps(payload))
        return payload

    monkeypatch.setattr(pipeline_module, "run_radio_stage", fake_radio)
    result = generate(_config(str(tmp_path / "both"), ue=True, radio=True), project_root=tmp_path)
    assert result["stage_status"]["radio"]["status"] == "complete"
    assert result["stage_status"]["ue"]["status"] == "complete"


def test_candidate_generation_builds_morphology_seed_matrix(tmp_path) -> None:
    config = _config(str(tmp_path / "candidates"))
    result = generate_candidates(
        config,
        morphologies=["manhattan", "radial_organic"],
        seeds=[3, 5],
        project_root=tmp_path,
    )
    assert result["candidate_count"] == 4
    assert Path(result["manifest"]).exists()
    assert {(item["morphology"], item["seed"]) for item in result["candidates"]} == {
        ("manhattan", 3),
        ("manhattan", 5),
        ("radial_organic", 3),
        ("radial_organic", 5),
    }


def test_candidate_generation_supports_base_station_density_matrix(tmp_path) -> None:
    config = _config(str(tmp_path / "base-stations"))
    result = generate_candidates(
        config,
        morphologies=["manhattan"],
        seeds=[3],
        site_densities_per_km2=[5, 10, 30],
        project_root=tmp_path,
    )
    assert result["candidate_count"] == 3
    assert result["site_densities_per_km2"] == [5.0, 10.0, 30.0]
    assert str(result["manifest"]).endswith("base-station-candidates.json")


def test_city_profiles_have_deliberately_separated_characteristics() -> None:
    config = _config("unused")
    profiles = {name: apply_city_profile(config, name).city for name in CITY_PROFILE_NAMES}
    assert profiles["dense_highrise_grid"].building.height_mean_m == 55.0
    assert profiles["compact_radial_lowrise"].building.density_per_km2 == 360.0
    assert profiles["sparse_suburban"].building.coverage_ratio == 0.12
    assert len({profile.morphology for profile in profiles.values()}) == len(profiles)


def test_candidate_manifest_summarizes_profile_statistics(tmp_path) -> None:
    result = generate_candidates(
        _config(str(tmp_path / "profiles")),
        city_profiles=["dense_highrise_grid", "sparse_suburban"],
        seeds=[3],
        project_root=tmp_path,
    )
    assert set(result["profile_summary"]) == {"dense_highrise_grid", "sparse_suburban"}
    dense = result["profile_summary"]["dense_highrise_grid"]["metrics"]
    sparse = result["profile_summary"]["sparse_suburban"]["metrics"]
    assert dense["mean_building_height_m"]["mean"] > sparse["mean_building_height_m"]["mean"]


def test_ue_settings_follow_laesim_single_uav_template() -> None:
    scene = generate_city(_config("unused").city, seed=4)
    settings = _airsim_settings(scene)
    vehicle = settings["Vehicles"]["UAV"]
    assert settings["SimMode"] == "Multirotor"
    assert settings["ClockType"] == "ScalableClock"
    assert settings["ApiServerPortMultirotor"] == 41471
    assert settings["ViewMode"] == "FlyWithMe"
    assert vehicle["VehicleType"] == "SimpleFlight"
    assert (vehicle["X"], vehicle["Y"], vehicle["Z"]) == (0.0, 0.0, 0.0)
    assert settings["WirelessCity"]["player_start_source"].startswith("UE PlayerStart")
    assert IMPORT_CONTRACT == "wireless-city-ue-import-visual"
    assert GEOMETRY_CONTRACT == "wireless-city-obj-watertight"


def test_scene_to_ue_coordinate_contract_and_bounds() -> None:
    scene = generate_city(_config("unused").city, seed=4)
    assert COORDINATE_CONTRACT == "wireless-city-scene-to-ue-cm-yflip"
    assert COORDINATE_TRANSFORM == "scene_m_to_ue_cm=(x,-y,z)*100"
    assert scene_m_to_ue_cm((1.0, 2.0, 3.0)) == (100.0, -200.0, 300.0)
    minimum = (100.0 * scene.bounds_min_m[0], -100.0 * scene.bounds_max_m[1], 100.0 * scene.bounds_min_m[2])
    maximum = (100.0 * scene.bounds_max_m[0], -100.0 * scene.bounds_min_m[1], 100.0 * scene.bounds_max_m[2])
    points = [
        *(point for road in scene.roads for point in (road["start_m"], road["end_m"])),
        *(station["position_m"] for station in scene.base_stations),
        *(point for task in scene.tasks for point in (task["start_m"], task["goal_m"])),
    ]
    for point in points:
        mapped = scene_m_to_ue_cm(tuple(point))
        assert all(lo - 1e-7 <= value <= hi + 1e-7 for value, lo, hi in zip(mapped, minimum, maximum))


def test_ue_importer_clears_asset_named_and_tagged_stale_actors() -> None:
    namespace = _importer_namespace()

    class Actor:
        def __init__(self, label: str, tags=()) -> None:
            self.label = label
            self.tags = list(tags)

        def get_actor_label(self) -> str:
            return self.label

        def get_editor_property(self, name: str):
            assert name == "tags"
            return self.tags

    class EditorLevelLibrary:
        actors = [
            Actor("InteractiveCity_PlayerStart_task-old"),
            Actor("OtherLabel", ["WirelessCityGenerated"]),
            Actor("UnrelatedActor"),
        ]

        @classmethod
        def get_all_level_actors(cls):
            return list(cls.actors)

        @classmethod
        def destroy_actor(cls, actor) -> None:
            cls.actors.remove(actor)

    unreal = type("FakeUnreal", (), {"EditorLevelLibrary": EditorLevelLibrary})
    namespace["clear_partial_generated_actors"](unreal, "InteractiveCity", {})

    assert [actor.label for actor in EditorLevelLibrary.actors] == ["UnrelatedActor"]


def test_ue_importer_rejects_ambiguous_player_starts() -> None:
    namespace = _importer_namespace()

    class ActorClass:
        @staticmethod
        def get_name() -> str:
            return "PlayerStart"

    class Actor:
        def __init__(self, label: str) -> None:
            self.label = label

        def get_actor_label(self) -> str:
            return self.label

        def get_class(self):
            return ActorClass()

    class EditorLevelLibrary:
        @staticmethod
        def get_all_level_actors():
            return [Actor("InteractiveCity_PlayerStart_task-000"), Actor("Old_PlayerStart")]

    unreal = type("FakeUnreal", (), {"EditorLevelLibrary": EditorLevelLibrary})
    with pytest.raises(RuntimeError, match="exactly one current PlayerStart"):
        namespace["require_single_player_start"](
            unreal,
            "InteractiveCity_PlayerStart_task-000",
        )
