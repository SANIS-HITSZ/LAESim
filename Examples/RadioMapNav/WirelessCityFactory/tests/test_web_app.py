import json
import os
import socket
from pathlib import Path
from subprocess import CompletedProcess

import numpy as np
import pytest

from wireless_city_factory import web_app
from wireless_city_factory.runtime import RadioObservation
from wireless_city_factory.web_app import (
    LAESimMissionManager,
    _radio_layer,
    _server,
    _suggest_connected_task,
    config_from_visualizer_payload,
    default_visualizer_output_root,
    generate_visualizer_run,
    import_laesim_run,
    laesim_run_status,
    load_laesim_context,
    open_laesim_run,
    preset_catalog,
    query_visualizer_radio,
    read_laesim_state,
)


def _payload() -> dict:
    return {
        "name": "visualizer_test",
        "seed": 17,
        "antenna_model": "sector3-tr38901-8x8-dualpol",
        "city": {
            "size_m": [160, 160],
            "morphology": "manhattan",
            "building": {
                "profile": "test",
                "coverage_ratio": 0.08,
                "density_per_km2": 30,
                "height_distribution": "normal",
                "height_min_m": 8,
                "height_max_m": 30,
                "height_mean_m": 16,
                "height_std_m": 4,
                "footprint_min_m": [8, 8],
                "footprint_max_m": [18, 18],
                "separation_m": 4,
            },
            "roads": {
                "grid_spacing_m": 60,
                "width_m": 10,
                "radial_count": 6,
                "ring_count": 1,
            },
            "base_stations": {
                "deployment_profile": "visualizer_test",
                "placement_family": "street_grid",
                "density_per_km2": 5,
                "height_m": 25,
                "height_reference": "absolute_agl",
                "power_dbm": 49,
                "carrier_frequency_hz": 3700000000,
                "bandwidth_hz": 40000000,
                "reference_inter_site_distance_m": 500,
                "reference_source": "test",
                "min_separation_m": 40,
                "sectors": 3,
                "sector_azimuths_deg": [0, 120, 240],
                "downtilt_deg": 12,
                "random_offset_m": 0,
            },
            "task": {"altitude_m": 50, "altitude_range_m": [35, 115], "count": 1},
            "validation": {"grid_resolution_m": 5, "minimum_largest_component_fraction": 0.8},
        },
    }


def test_visualizer_catalog_exposes_reference_presets() -> None:
    catalog = preset_catalog()
    assert {"dense_highrise_grid", "irregular_midrise", "sparse_suburban"} <= set(catalog["city"])
    assert {
        "low_band_wide_area",
        "sub6_low_altitude_macro",
        "isac_49_experimental",
        "mmwave_isac_experimental",
        "uma_reference",
        "umi_reference",
    } <= set(catalog["base_station"])
    assert catalog["base_station"]["low_band_wide_area"]["values"]["carrier_frequency_hz"] == 700e6
    assert catalog["base_station"]["sub6_low_altitude_macro"]["values"]["carrier_frequency_hz"] == 3.5e9
    assert catalog["base_station"]["isac_49_experimental"]["values"]["sensing_enabled"] is True
    assert catalog["base_station"]["mmwave_isac_experimental"]["values"]["parameter_status"] == "simulation_proxy"
    assert catalog["base_station"]["uma_reference"]["values"]["height_m"] == 25.0
    assert catalog["base_station"]["umi_reference"]["values"]["density_per_km2"] == 30.0


def test_visualizer_payload_preserves_custom_radio_parameters() -> None:
    config = config_from_visualizer_payload(_payload())
    assert config.radio.enabled is False
    assert config.ue.enabled is True
    assert config.ue.import_asset_name == "InteractiveCity"
    assert config.radio.antenna_model == "sector3-tr38901-8x8-dualpol"
    assert config.radio.tx_power_dbm == 49.0
    assert config.city.base_stations.deployment_profile == "visualizer_test"
    assert config.radio.frequency_hz == config.city.base_stations.carrier_frequency_hz == 3.7e9
    assert config.radio.bandwidth_hz == config.city.base_stations.bandwidth_hz == 40e6


def test_visualizer_payload_can_enable_quick_sionna_radio() -> None:
    payload = _payload()
    payload["radio"] = {
        "enabled": True,
        "quality": "quick",
        "height_m": 65,
        "frequency_hz": 4.9e9,
        "bandwidth_hz": 100e6,
    }
    config = config_from_visualizer_payload(payload)
    assert config.radio.enabled is True
    assert config.radio.backend == "sionna_rt"
    assert config.radio.cell_size_m == 40.0
    assert config.radio.heights_m == (65.0,)
    assert config.radio.samples_per_logical_sector == 4096
    assert config.radio.tx_power_dbm == 49.0


def test_visualizer_payload_preserves_manual_task_and_constraints() -> None:
    payload = _payload()
    payload["city"]["task"] = {
        "altitude_m": 65,
        "altitude_range_m": [35, 115],
        "count": 1,
        "selection_mode": "manual",
        "start_xy_m": [20.5, 40.5],
        "goal_xy_m": [120.5, 100.5],
        "constraint_preset": "custom",
        "minimum_sinr_db": 3.0,
        "minimum_rss_dbm": -98.0,
        "maximum_outage_fraction": 0.0,
    }
    config = config_from_visualizer_payload(payload)
    assert config.city.task.selection_mode == "manual"
    assert config.city.task.start_xy_m == (20.5, 40.5)
    assert config.city.task.goal_xy_m == (120.5, 100.5)
    assert config.city.task.minimum_sinr_db == 3.0
    assert config.city.task.minimum_rss_dbm == -98.0


def test_visualizer_generates_downloadable_city_bundle(tmp_path: Path) -> None:
    result = generate_visualizer_run(_payload(), project_root=tmp_path)
    assert result["status"] == "complete"
    assert result["scene"]["seed"] == 17
    assert result["base_station_manifest"]["status"] == "complete"
    assert {"scene.json", "scene.obj", "config.json"} <= set(result["downloads"])
    assert result["radio"] is None
    assert result["laesim"]["bundle_ready"] is True
    assert result["laesim"]["imported"] is False
    run_dir = Path(result["laesim"]["run_dir"])
    assert (run_dir / "ue_bundle" / "settings.json").is_file()


def test_visualizer_can_generate_in_explicit_user_output_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "user-data" / "outputs"
    result = generate_visualizer_run(_payload(), project_root=tmp_path, output_root=output_root)
    assert Path(result["downloads"]["scene.json"]).name == "scene.json"
    assert (output_root / result["run_id"] / "scene.json").is_file()


def test_default_visualizer_output_root_uses_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("WCF_VISUALIZER_OUTPUT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_visualizer_output_root() == tmp_path / "WirelessCityFactory" / "outputs"


def test_visualizer_output_root_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    override = tmp_path / "custom-output"
    monkeypatch.setenv("WCF_VISUALIZER_OUTPUT", str(override))
    assert default_visualizer_output_root() == override


def test_visualizer_radio_query_uses_current_task_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    class FakeLookup:
        scene = type(
            "Scene",
            (),
            {"tasks": [{"minimum_sinr_db": -4.0, "minimum_rss_dbm": -100.0}]},
        )()
        outage_threshold_db = None

        def query(self, position, *, outage_threshold_db=-6.0):
            self.outage_threshold_db = outage_threshold_db
            return RadioObservation(
                position_m=tuple(position),
                interpolation="test",
                detected_cells=[],
                rss_dbm={"cell-a": -101.0},
                serving_cell="cell-a",
                sinr_db=1.0,
                outage=False,
                detection_threshold_dbm=-125.0,
                outage_threshold_db=outage_threshold_db,
            )

    lookup = FakeLookup()
    monkeypatch.setattr(web_app, "_load_radio_lookup", lambda _path: lookup)

    observation = query_visualizer_radio(
        tmp_path,
        {"run_id": "run-1", "position_m": [1.0, 2.0, 65.0]},
    )

    assert lookup.outage_threshold_db == -4.0
    assert observation["outage_threshold_db"] == -4.0
    assert observation["outage"] is True


def test_visualizer_server_does_not_share_an_occupied_port(tmp_path: Path) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        occupied_port = reservation.getsockname()[1]
        reservation.listen(1)
        server, selected_port = _server(
            "127.0.0.1",
            occupied_port,
            tmp_path,
            tmp_path / "outputs",
        )
        try:
            assert selected_port != occupied_port
        finally:
            server.server_close()


def test_visualizer_rejects_unbounded_city_size() -> None:
    payload = _payload()
    payload["city"]["size_m"] = [3000, 1000]
    with pytest.raises(ValueError, match="2,000 m"):
        config_from_visualizer_payload(payload)


def test_visualizer_rejects_unknown_radio_quality() -> None:
    payload = _payload()
    payload["radio"] = {"enabled": True, "quality": "instant-magic"}
    with pytest.raises(ValueError, match="Unknown radio quality"):
        config_from_visualizer_payload(payload)


def test_visualizer_page_exposes_optional_radio_and_uav_controls() -> None:
    page = (
        Path(__file__).parents[1]
        / "src"
        / "wireless_city_factory"
        / "web"
        / "index.html"
    ).read_text(encoding="utf-8")
    assert 'id="radio-enabled"' in page
    assert 'id="uav-enabled"' in page
    assert 'id="laesim-tab"' in page
    assert 'id="laesim-panel"' in page
    assert 'id="laesim-sync"' in page
    assert 'id="route-progress"' in page
    assert 'id="rf-panel"' in page
    assert 'id="station-frequency"' in page
    assert 'id="station-bandwidth"' in page
    assert 'id="station-preset-metadata"' in page
    assert 'id="station-parameter-status"' in page
    assert 'id="station-modified-fields"' in page
    assert 'id="radio-map-summary"' in page
    assert 'id="radio-scale-mode"' in page
    assert 'id="laesim-radio-visible"' in page
    assert 'id="route-comparison-panel"' in page
    assert 'id="route-gain-summary"' in page
    assert 'id="route-base-min-sinr"' in page
    assert 'id="route-rf-min-sinr"' in page
    assert 'id="import-laesim"' in page
    assert 'id="open-laesim"' in page
    assert 'id="laesim-match-status"' in page
    assert 'id="start-laesim-mission"' in page
    assert 'id="stop-laesim-mission"' in page
    assert 'id="laesim-process-status"' in page
    assert 'id="task-tab"' in page
    assert 'id="task-point-mode"' in page
    assert 'id="mission-preset"' in page
    assert 'id="run-preflight"' in page
    radio_panel = page[page.index('id="radio-panel"'):page.index('id="laesim-panel"')]
    laesim_panel = page[page.index('id="laesim-panel"'):page.index('class="form-footer"')]
    assert 'id="laesim-sync"' not in radio_panel
    assert 'id="laesim-sync"' in laesim_panel
    assert 'id="laesim-guidance"' in laesim_panel
    assert 'id="radio-display-mode"' not in page


def test_laesim_live_state_and_context_load_the_same_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "run-1"
    run_dir.mkdir(parents=True)
    scene = {"scene_id": "live-scene", "metadata": {"scene_fingerprint": "scene-a"}}
    stations = {"site_count": 1, "sites": [], "base_station_fingerprint": "stations-a"}
    (run_dir / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    (run_dir / "base_station_manifest.json").write_text(json.dumps(stations), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({"config_fingerprint": "config-a"}), encoding="utf-8")
    (run_dir / "radio_manifest.json").write_text(json.dumps({"radio_fingerprint": "radio-a"}), encoding="utf-8")
    (run_dir / "ue_manifest.json").write_text(json.dumps({"source_scene_fingerprint": "scene-a"}), encoding="utf-8")
    state_path = tmp_path / "runtime" / "laesim_live_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "contract": "wireless-city-laesim-live-v1",
                "session_id": "session-1",
                "status": "flying",
                "run_dir": str(run_dir),
                "fingerprints": {
                    "run_id": "run-1",
                    "config_fingerprint": "config-a",
                    "scene_fingerprint": "scene-a",
                    "base_station_fingerprint": "stations-a",
                    "radio_fingerprint": "radio-a",
                    "ue_scene_fingerprint": "scene-a",
                },
                "latest": {"position_scene_m": [1, 2, 3]},
            }
        ),
        encoding="utf-8",
    )
    assert read_laesim_state(state_path)["latest"]["position_scene_m"] == [1, 2, 3]
    context = load_laesim_context(state_path, tmp_path)
    assert context["session_id"] == "session-1"
    assert context["scene"] == scene
    assert context["base_station_manifest"] == stations
    assert context["radio"] is None


def test_laesim_completed_result_remains_available(tmp_path: Path) -> None:
    state_path = tmp_path / "laesim_live_state.json"
    payload = {
        "contract": "wireless-city-laesim-live-v1",
        "session_id": "completed-session",
        "status": "complete",
        "final_error_m": 0.44,
    }
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(state_path, (1, 1))
    assert read_laesim_state(state_path) == payload


def test_laesim_live_state_ignores_stale_task_file(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "laesim_live_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "contract": "wireless-city-laesim-live-v1",
                "session_id": "old-session",
                "status": "error",
                "run_dir": str(tmp_path / "outputs" / "old-run"),
            }
        ),
        encoding="utf-8",
    )
    os.utime(state_path, (1, 1))

    state = read_laesim_state(state_path)

    assert state == {
        "status": "idle",
        "stale": True,
        "last_status": "error",
        "last_run_dir": str(tmp_path / "outputs" / "old-run"),
    }


def test_laesim_context_accepts_visualizer_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "user-data" / "outputs"
    run_dir = output_root / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "scene.json").write_text(json.dumps({"scene_id": "browser-scene", "metadata": {"scene_fingerprint": "scene-a"}}), encoding="utf-8")
    (run_dir / "base_station_manifest.json").write_text(
        json.dumps({"site_count": 0, "sites": [], "base_station_fingerprint": "stations-a"}), encoding="utf-8"
    )
    (run_dir / "manifest.json").write_text(json.dumps({"config_fingerprint": "config-a"}), encoding="utf-8")
    (run_dir / "radio_manifest.json").write_text(json.dumps({"radio_fingerprint": "radio-a"}), encoding="utf-8")
    (run_dir / "ue_manifest.json").write_text(json.dumps({"source_scene_fingerprint": "scene-a"}), encoding="utf-8")
    state_path = tmp_path / "runtime" / "laesim_live_state.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "contract": "wireless-city-laesim-live-v1",
                "session_id": "session-browser",
                "status": "planning",
                "run_dir": str(run_dir),
                "fingerprints": {
                    "run_id": "run-1",
                    "config_fingerprint": "config-a",
                    "scene_fingerprint": "scene-a",
                    "base_station_fingerprint": "stations-a",
                    "radio_fingerprint": "radio-a",
                    "ue_scene_fingerprint": "scene-a",
                },
            }
        ),
        encoding="utf-8",
    )
    context = load_laesim_context(state_path, tmp_path / "project", output_root)
    assert context["run_id"] == "run-1"
    assert context["scene"]["scene_id"] == "browser-scene"


def test_laesim_status_requires_matching_import_fingerprint(tmp_path: Path) -> None:
    bundle = tmp_path / "ue_bundle"
    bundle.mkdir()
    for name in ("scene.obj", "import_wireless_city.py", "settings.json"):
        (bundle / name).write_text("{}", encoding="utf-8")
    (tmp_path / "ue_manifest.json").write_text(
        json.dumps({"source_scene_fingerprint": "scene-a", "asset_name": "InteractiveCity"}),
        encoding="utf-8",
    )
    (tmp_path / "ue_import_result.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_scene_fingerprint": "scene-b",
                "map_path": "/Game/WirelessCity/Maps/InteractiveCity",
            }
        ),
        encoding="utf-8",
    )
    status = laesim_run_status(tmp_path)
    assert status["bundle_ready"] is True
    assert status["imported"] is True
    assert status["import_matches"] is False


def _write_laesim_bundle(run_dir: Path, fingerprint: str = "scene-a") -> None:
    bundle = run_dir / "ue_bundle"
    bundle.mkdir(parents=True)
    (bundle / "scene.obj").write_text("o scene\n", encoding="utf-8")
    (bundle / "import_wireless_city.py").write_text("# importer\n", encoding="utf-8")
    (bundle / "settings.json").write_text('{"SettingsVersion": 1.2}', encoding="utf-8")
    (run_dir / "ue_manifest.json").write_text(
        json.dumps(
            {
                "source_scene_fingerprint": fingerprint,
                "base_station_fingerprint": "stations-a",
                "asset_name": "InteractiveCity",
            }
        ),
        encoding="utf-8",
    )


def test_import_laesim_run_uses_bypass_and_backs_up_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "outputs" / "run-a"
    _write_laesim_bundle(run_dir)
    project_root = tmp_path / "project"
    registry = project_root / "runtime" / "active_ue_import.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "run_id": "run-a",
                "scene_fingerprint": "scene-a",
                "base_station_fingerprint": "stations-a",
            }
        ),
        encoding="utf-8",
    )
    importer = project_root / "unreal" / "WirelessCityFactory" / "Scripts" / "ImportExampleCity.ps1"
    importer.parent.mkdir(parents=True)
    importer.write_text("# test importer\n", encoding="utf-8")
    engine_root = tmp_path / "UE_4.27"
    home = tmp_path / "home"
    settings_dir = home / "Documents" / "AirSim"
    settings_dir.mkdir(parents=True)
    old_settings = b'{"SettingsVersion": 1.1}'
    (settings_dir / "settings.json").write_bytes(old_settings)
    recorded: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        (run_dir / "ue_import_result.json").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "source_scene_fingerprint": "scene-a",
                    "map_path": "/Game/WirelessCity/Maps/InteractiveCity",
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, stdout="complete", stderr="")

    monkeypatch.setattr(web_app, "_find_ue4_root", lambda: engine_root)
    monkeypatch.setattr(web_app.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(web_app.subprocess, "run", fake_run)
    monkeypatch.setattr(web_app.Path, "home", lambda: home)

    result = import_laesim_run(run_dir, project_root)

    command = recorded["command"]
    assert isinstance(command, list)
    assert command[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert command[command.index("-BundleRoot") + 1] == str(run_dir)
    assert command[command.index("-EngineRoot") + 1] == str(engine_root)
    assert recorded["kwargs"] == {
        "capture_output": True,
        "text": True,
        "errors": "replace",
        "timeout": 900,
        "check": False,
    }
    assert result["import_matches"] is True
    assert (settings_dir / "settings.json").read_bytes() == (run_dir / "ue_bundle" / "settings.json").read_bytes()
    backups = list(settings_dir.glob("settings.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_settings


def test_open_laesim_run_starts_matching_map_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "outputs" / "run-a"
    _write_laesim_bundle(run_dir)
    (run_dir / "ue_import_result.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_scene_fingerprint": "scene-a",
                "map_path": "/Game/WirelessCity/Maps/InteractiveCity",
            }
        ),
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    registry = project_root / "runtime" / "active_ue_import.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "run_id": "run-a",
                "scene_fingerprint": "scene-a",
                "base_station_fingerprint": "stations-a",
            }
        ),
        encoding="utf-8",
    )
    engine_root = tmp_path / "UE_4.27"
    calls: list[tuple[list[str], bool]] = []

    monkeypatch.setattr(web_app, "_find_ue4_root", lambda: engine_root)
    monkeypatch.setattr(
        web_app.subprocess,
        "Popen",
        lambda command, close_fds: calls.append((command, close_fds)),
    )

    result = open_laesim_run(run_dir, project_root)

    expected_editor = engine_root / "Engine" / "Binaries" / "Win64" / "UE4Editor.exe"
    expected_project = project_root / "unreal" / "WirelessCityFactory" / "WirelessCityFactory.uproject"
    assert calls == [
        (
            [
                str(expected_editor),
                str(expected_project),
                "/Game/WirelessCity/Maps/InteractiveCity",
            ],
            True,
        )
    ]
    assert result["status"] == "opening"


def test_open_laesim_run_rejects_stale_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "outputs" / "run-a"
    _write_laesim_bundle(run_dir)
    (run_dir / "ue_import_result.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_scene_fingerprint": "another-scene",
                "map_path": "/Game/WirelessCity/Maps/InteractiveCity",
            }
        ),
        encoding="utf-8",
    )
    called = False

    def fake_popen(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(web_app.subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="先把当前城市导入"):
        open_laesim_run(run_dir, tmp_path / "project")
    assert called is False


def test_open_laesim_run_rejects_non_active_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "outputs" / "run-a"
    _write_laesim_bundle(run_dir)
    (run_dir / "ue_import_result.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_scene_fingerprint": "scene-a",
                "map_path": "/Game/WirelessCity/Maps/InteractiveCity",
            }
        ),
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    registry = project_root / "runtime" / "active_ue_import.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "run_id": "run-b",
                "scene_fingerprint": "scene-b",
                "base_station_fingerprint": "stations-b",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_app.subprocess, "Popen", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="先把当前城市导入"):
        open_laesim_run(run_dir, project_root)


def test_mission_manager_starts_once_and_requests_safe_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    run_dir = tmp_path / "outputs" / "run-a"
    run_dir.mkdir(parents=True)
    python_executable = project_root / ".venv-airsim310" / "Scripts" / "python.exe"
    python_executable.parent.mkdir(parents=True)
    python_executable.write_bytes(b"")
    mission_script = project_root / "scripts" / "run_laesim_connectivity_mission.py"
    mission_script.parent.mkdir(parents=True)
    mission_script.write_text("# mission\n", encoding="utf-8")
    live_state = project_root / "runtime" / "laesim_live_state.json"
    live_state.parent.mkdir(parents=True)
    live_state.write_text("{}", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeProcess:
        pid = 4321
        return_code = None

        def poll(self):
            return self.return_code

        def terminate(self):
            self.return_code = -15

        def wait(self, timeout=None):
            if self.return_code is None:
                raise web_app.subprocess.TimeoutExpired("mission", timeout)
            return self.return_code

    process = FakeProcess()

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(
        web_app,
        "laesim_run_status",
        lambda *_args, **_kwargs: {"import_matches": True},
    )
    monkeypatch.setattr(
        web_app,
        "preflight_visualizer_run",
        lambda *_args, **_kwargs: {"status": "ready"},
    )
    monkeypatch.setattr(web_app.subprocess, "Popen", fake_popen)
    manager = LAESimMissionManager(project_root, live_state)

    started = manager.start(run_dir)

    assert started["status"] == "running"
    assert started["run_id"] == "run-a"
    assert started["pid"] == 4321
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:2] == [str(python_executable), str(mission_script)]
    assert command[command.index("--run-dir") + 1] == str(run_dir)
    stop_file = Path(command[command.index("--stop-file") + 1])
    assert kwargs["cwd"] == str(project_root)
    assert kwargs["close_fds"] is True
    assert live_state.exists() is False
    with pytest.raises(RuntimeError, match="已有 LAESim 任务"):
        manager.start(run_dir)

    stopping = manager.stop()

    assert stopping["status"] == "stopping"
    assert stop_file.read_text(encoding="ascii") == "stop\n"
    process.return_code = 0
    stopped = manager.status()
    assert stopped["status"] == "stopped"
    assert stopped["return_code"] == 0
    assert stop_file.exists() is False


def test_radio_heatmap_can_be_hidden_without_hiding_live_observations() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "wireless_city_factory"
        / "web"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert 'byId("radio-display-mode").value' not in script
    assert "depthTest: false" in script
    assert "Number(radio.height_m) + 0.5" in script
    assert "createRadioTexture(values, radio.finite_mask || radio.valid_mask, radioScale(metric), nx, ny)" in script
    assert 'context.fillStyle = "#7b8387"' in script
    assert "new THREE.CanvasTexture(image)" in script
    assert "buildingMesh.material.opacity = radioPrimaryView ? 0.28 : 1" in script
    assert "const visible = Boolean(available && state.radioLayerVisible);" in script
    assert 'toggle.checked = visible;\n  laesimToggle.disabled = !available;' in script
    assert 'if (!available) byId("rf-panel").hidden = true;\n  applyLayerVisibility();' in script
    assert "const radioPrimaryView = Boolean(state.layers.radio?.visible);" in script
    assert "function setRadioLayerPreference(visible)" in script
    assert 'byId("laesim-radio-visible").addEventListener("change"' in script
    assert 'laesimToggle.checked = state.radioLayerVisible && !laesimToggle.disabled;' in script
    assert 'if (!visible) byId("rf-panel").hidden = true;' not in script


def test_city_preset_refreshes_preview_without_running_radio() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "wireless_city_factory"
        / "web"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert "function collectPayload({ includeRadio = false } = {})" in script
    assert "enabled: includeRadio" in script
    assert 'await generateCity({ includeRadio: false });' in script
    assert 'requestId !== state.generationRequestId' in script
    assert 'const includeRadio = byId("radio-enabled").checked;' in script
    assert "state.stationPresetOrigin" in script
    assert "modifiedStationFields" in script
    assert "source_preset_id" in script
    assert "modified_fields" in script


def test_radio_generation_and_laesim_sync_do_not_depend_on_active_tab() -> None:
    root = Path(__file__).parents[1] / "src" / "wireless_city_factory" / "web"
    script = (root / "app.js").read_text(encoding="utf-8")
    styles = (root / "styles.css").read_text(encoding="utf-8")
    assert 'const includeRadio = byId("radio-enabled").checked;' in script
    assert 'const liveSync = byId("laesim-sync").checked;' in script
    assert "任务场景与当前网页不一致" in script
    assert "repeat(5, minmax(0, 1fr))" in styles


def test_radio_layer_exposes_numeric_summary_and_carrier(tmp_path: Path) -> None:
    rss = np.array(
        [
            [[[1.0, 4.0], [2.0, 3.0]]],
            [[[5.0, 0.0], [6.0, 1.0]]],
        ]
    )
    sinr = rss + 10.0
    np.savez_compressed(
        tmp_path / "radio_volume.npz",
        x_m=np.array([10.0, 20.0]),
        y_m=np.array([10.0, 20.0]),
        z_m=np.array([65.0]),
        rss_dbm=rss,
        sinr_db=sinr,
        base_station_ids=np.array(["cell-a", "cell-b"]),
    )
    (tmp_path / "radio_manifest.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "config": {"frequency_hz": 3.7e9, "bandwidth_hz": 40e6}
                }
            }
        ),
        encoding="utf-8",
    )
    layer = _radio_layer(tmp_path)
    assert layer["frequency_hz"] == 3.7e9
    assert layer["bandwidth_hz"] == 40e6
    assert layer["height_m"] == 65.0
    assert layer["summary"]["rss"]["minimum"] == 3.0
    assert layer["summary"]["rss"]["maximum"] == 6.0
    assert layer["power_metric"] == "wideband_rss_dbm"
    assert layer["sinr_model"] == "full-buffer-reuse-1-all-sectors"
    assert layer["valid_mask"] == [True, True, True, True]
    assert layer["serving_cell"] == ["cell-b", "cell-a", "cell-b", "cell-a"]


def test_radio_layer_masks_cells_below_detection_threshold(tmp_path: Path) -> None:
    rss = np.array([[[[-130.0, -100.0]]]])
    np.savez_compressed(
        tmp_path / "radio_volume.npz",
        x_m=np.array([10.0, 20.0]),
        y_m=np.array([10.0]),
        z_m=np.array([65.0]),
        rss_dbm=rss,
        sinr_db=np.array([[[[0.0, 10.0]]]]),
        base_station_ids=np.array(["cell-a"]),
    )
    (tmp_path / "radio_manifest.json").write_text(
        json.dumps({"metadata": {"config": {"frequency_hz": 3.7e9, "bandwidth_hz": 40e6}}}),
        encoding="utf-8",
    )
    layer = _radio_layer(tmp_path)
    assert layer["valid_mask"] == [True, True]
    assert layer["finite_mask"] == [True, True]
    assert layer["detectable_mask"] == [False, True]
    assert layer["serving_cell"] == [None, "cell-a"]
    assert layer["coverage"] == {"valid_cells": 1, "total_cells": 2, "fraction": 0.5}
    assert layer["grid_integrity"] == {
        "finite_cells": 2,
        "total_cells": 2,
        "fraction": 1.0,
        "complete": True,
    }
    assert layer["summary"]["rss"]["minimum"] == -100.0


def test_radio_layer_rejects_grid_shape_mismatch(tmp_path: Path) -> None:
    np.savez_compressed(
        tmp_path / "radio_volume.npz",
        x_m=np.array([10.0, 20.0]),
        y_m=np.array([10.0, 20.0]),
        z_m=np.array([65.0]),
        rss_dbm=np.zeros((1, 1, 1, 2)),
        sinr_db=np.zeros((1, 1, 1, 2)),
        base_station_ids=np.array(["cell-a"]),
    )
    (tmp_path / "radio_manifest.json").write_text(
        json.dumps({"metadata": {"config": {"frequency_hz": 3.7e9, "bandwidth_hz": 40e6}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dimensions do not match"):
        _radio_layer(tmp_path)


def test_auto_task_suggestion_uses_one_connected_component() -> None:
    lookup = type(
        "Lookup",
        (),
        {
            "x_m": np.array([0.0, 10.0, 20.0, 30.0]),
            "y_m": np.array([0.0, 10.0, 20.0, 30.0]),
            "query": lambda *_args, **_kwargs: object(),
        },
    )()
    planner = type(
        "Planner",
        (),
        {
            "config": type(
                "Config", (), {"detection_threshold_dbm": -125.0, "minimum_sinr_db": 0.0}
            )(),
            "_collision_free": lambda *_args: True,
            "_observation_feasible": lambda *_args: True,
            "_segment_feasible": lambda *_args: True,
        },
    )()
    suggestion = _suggest_connected_task(lookup, planner, 65.0)
    assert suggestion is not None
    assert suggestion["start_xy_m"][0] != suggestion["goal_xy_m"][0]
    assert suggestion["start_xy_m"][1] != suggestion["goal_xy_m"][1]


def test_auto_task_suggestion_keeps_endpoints_inside_city_boundary() -> None:
    axis = np.arange(5.0, 1000.0, 10.0)
    lookup = type(
        "Lookup",
        (),
        {
            "x_m": axis,
            "y_m": axis,
            "query": lambda *_args, **_kwargs: object(),
        },
    )()
    planner = type(
        "Planner",
        (),
        {
            "config": type(
                "Config", (), {"detection_threshold_dbm": -125.0, "minimum_sinr_db": 0.0}
            )(),
            "_collision_free": lambda _self, points: bool(
                abs(float(points[0, 0]) - float(points[0, 1])) < 1e-9
            ),
            "_observation_feasible": lambda *_args: True,
            "_segment_feasible": lambda *_args: True,
        },
    )()

    suggestion = _suggest_connected_task(lookup, planner, 65.0)

    assert suggestion is not None
    for endpoint in (suggestion["start_xy_m"], suggestion["goal_xy_m"]):
        assert 80.0 <= endpoint[0] <= 920.0
        assert 80.0 <= endpoint[1] <= 920.0
    assert suggestion["start_xy_m"][0] != suggestion["goal_xy_m"][0]
    assert suggestion["start_xy_m"][1] != suggestion["goal_xy_m"][1]


def test_auto_task_suggestion_rejects_radio_point_in_blocked_validation_cell() -> None:
    scene = type(
        "Scene",
        (),
        {
            "size_m": (30.0, 30.0, 100.0),
            "buildings": [
                {
                    "building_id": "edge-building",
                    "center_m": [22.5, 22.5, 50.0],
                    "size_m": [4.0, 4.0, 100.0],
                }
            ],
            "metadata": {"city_config": {"validation": {"grid_resolution_m": 5.0}}},
        },
    )()
    lookup = type(
        "Lookup",
        (),
        {
            "scene": scene,
            "x_m": np.array([0.0, 10.0, 20.0]),
            "y_m": np.array([0.0, 10.0, 20.0]),
            "query": lambda *_args, **_kwargs: object(),
        },
    )()
    planner = type(
        "Planner",
        (),
        {
            "config": type(
                "Config", (), {"detection_threshold_dbm": -125.0, "minimum_sinr_db": 0.0}
            )(),
            "_collision_free": lambda *_args: True,
            "_observation_feasible": lambda *_args: True,
            "_segment_feasible": lambda *_args: True,
        },
    )()

    suggestion = _suggest_connected_task(lookup, planner, 65.0)

    assert suggestion is not None
    assert [20.0, 20.0] not in (suggestion["start_xy_m"], suggestion["goal_xy_m"])
