import json
import sys
from pathlib import Path

import pytest

import scripts.run_laesim_connectivity_mission as mission
from scripts.run_laesim_connectivity_mission import (
    MissionStopped,
    _check_stop_requested,
    _project_to_radio_altitude,
    _query_task_observation,
)
from wireless_city_factory.planning import PlanningError
from wireless_city_factory.runtime import RadioObservation


def test_live_pose_is_projected_to_fixed_radio_map_altitude() -> None:
    assert _project_to_radio_altitude((50.0, 50.0, 65.13576366), 65.0) == (
        50.0,
        50.0,
        65.0,
    )


def test_stop_file_requests_controlled_mission_stop(tmp_path: Path) -> None:
    stop_file = tmp_path / "mission.stop"
    _check_stop_requested(stop_file)
    stop_file.write_text("stop\n", encoding="ascii")
    with pytest.raises(MissionStopped, match="operator"):
        _check_stop_requested(stop_file)


def test_live_observation_uses_task_sinr_and_rss_thresholds() -> None:
    class FakeLookup:
        outage_threshold_db = None

        def query(self, position, *, outage_threshold_db=-6.0):
            self.outage_threshold_db = outage_threshold_db
            return RadioObservation(
                position_m=position,
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
    observation = _query_task_observation(
        lookup,
        (1.0, 2.0, 65.0),
        minimum_sinr_db=-4.0,
        minimum_rss_dbm=-100.0,
    )

    assert lookup.outage_threshold_db == -4.0
    assert observation.outage_threshold_db == -4.0
    assert observation.outage is True


def test_infeasible_route_is_reported_before_takeoff(
    monkeypatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class FakeState:
        position_scene_m = (150.0, 0.0, 0.0)

        @staticmethod
        def to_dict() -> dict:
            return {"position_scene_m": [150.0, 0.0, 0.0]}

    class FakeBridge:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def connect(self) -> None:
            events.append("connect")

        def read_state(self) -> FakeState:
            events.append("read_state")
            return FakeState()

        def prepare_flight(self, *_args, **_kwargs) -> None:
            events.append("prepare_flight")

        def release(self) -> None:
            events.append("release")

    class FakeRoute:
        @staticmethod
        def to_dict() -> dict:
            return {"points_m": [[150.0, 0.0, 65.0], [850.0, 0.0, 65.0]]}

    class FakePlanner:
        def __init__(self, _lookup, config) -> None:
            self.config = config

        def plan(self, _start, _goal) -> FakeRoute:
            if self.config.enforce_connectivity:
                raise PlanningError("No globally connected route exists at the configured thresholds.")
            return FakeRoute()

    lookup = type(
        "FakeLookup",
        (),
        {
            "scene": type(
                "FakeScene",
                (),
                {
                    "tasks": [
                        {
                            "task_id": "task-000",
                            "start_m": [150.0, 0.0, 65.0],
                            "goal_m": [850.0, 0.0, 65.0],
                        }
                    ],
                    "fingerprint": staticmethod(lambda: "scene-a"),
                },
            )()
        },
    )()
    state_path = tmp_path / "state.json"
    (tmp_path / "manifest.json").write_text(
        json.dumps({"config_fingerprint": "config-a"}), encoding="utf-8"
    )
    (tmp_path / "base_station_manifest.json").write_text(
        json.dumps({"base_station_fingerprint": "stations-a"}), encoding="utf-8"
    )
    (tmp_path / "radio_manifest.json").write_text(
        json.dumps({"radio_fingerprint": "radio-a"}), encoding="utf-8"
    )
    (tmp_path / "ue_manifest.json").write_text(
        json.dumps({"source_scene_fingerprint": "scene-a"}), encoding="utf-8"
    )
    monkeypatch.setattr(mission.RadioMapLookup, "load", lambda _path: lookup)
    monkeypatch.setattr(mission, "LAESimBridge", FakeBridge)
    monkeypatch.setattr(mission, "ConnectivityAwarePrimitivePlanner", FakePlanner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_laesim_connectivity_mission.py",
            "--run-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "mission.jsonl"),
            "--flight-altitude-m",
            "65",
            "--minimum-sinr-db",
            "0",
            "--visualizer-state",
            str(state_path),
        ],
    )

    assert mission.main() == 2
    assert "prepare_flight" not in events
    assert events[-1] == "release"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "error"
    assert state["error_code"] == "no_globally_connected_route"
    assert state["planning"] == {"flight_altitude_m": 65.0, "minimum_sinr_db": 0.0}
    assert "增加基站密度" in state["guidance"]
