import json
from pathlib import Path

import pytest

from scripts.export_paper_usecase import export_use_case


def _route(length: float, minimum_sinr: float, outage: float) -> dict:
    return {
        "points_m": [[0.0, 0.0, 65.0], [length, 0.0, 65.0]],
        "metrics": {
            "length_m": length,
            "outage_fraction": outage,
            "minimum_sinr_db": minimum_sinr,
            "mean_sinr_db": 8.0,
            "minimum_serving_rss_dbm": -90.0,
            "mean_serving_rss_dbm": -70.0,
            "handover_count": 2,
            "replans": 1,
            "final_error_m": 0.0,
            "reached_goal": True,
        },
        "planner_config": {"minimum_sinr_db": -4.5, "maximum_outage_fraction": 0.0},
    }


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir()
    scene_fingerprint = "scene-a"
    station_fingerprint = "stations-a"
    files = {
        "manifest.json": {"config_fingerprint": "config-a", "scene_fingerprint": scene_fingerprint},
        "city_manifest.json": {
            "scene_fingerprint": scene_fingerprint,
            "base_station_fingerprint": station_fingerprint,
        },
        "base_station_manifest.json": {"base_station_fingerprint": station_fingerprint},
        "radio_manifest.json": {
            "scene_fingerprint": scene_fingerprint,
            "radio_fingerprint": "radio-a",
            "shape": [3, 1, 4, 4],
            "metadata": {
                "base_station_fingerprint": station_fingerprint,
                "config": {"frequency_hz": 4.9e9, "bandwidth_hz": 100e6},
            },
        },
        "ue_manifest.json": {"source_scene_fingerprint": scene_fingerprint},
        "ue_import_result.json": {"source_scene_fingerprint": scene_fingerprint},
        "scene.json": {
            "scene_id": "test-city",
            "tasks": [
                {"task_id": "task-000", "start_m": [0.0, 0.0, 65.0], "goal_m": [12.0, 0.0, 65.0]}
            ],
        },
    }
    for name, payload in files.items():
        (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_log(path: Path, *, terminal_type: str = "complete") -> None:
    rows = [
        {
            "type": "mission",
            "routes": {
                "baseline": _route(10.0, -12.0, 0.25),
                "connectivity": _route(12.0, -4.0, 0.0),
            },
        },
        {
            "type": "sample",
            "timestamp": "2026-10-03T00:00:00+00:00",
            "position_scene_m": [0.0, 0.0, 65.0],
            "has_collided": False,
            "radio": {"sinr_db": 2.0, "serving_cell": "cell-a", "rss_dbm": {"cell-a": -70.0}, "outage": False},
        },
        {
            "type": terminal_type,
            "timestamp": "2026-10-03T00:00:02+00:00",
            "position_scene_m": [12.0, 0.0, 65.0],
            "final_error_m": 0.2,
            "has_collided": False,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_export_completed_mission_as_paper_usecase(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    log = tmp_path / "mission.jsonl"
    output = tmp_path / "paper"
    _write_run(run_dir)
    _write_log(log)

    summary = export_use_case(run_dir, log, output)

    assert summary["contract"] == "wireless-city-paper-usecase-v1"
    assert summary["comparison"]["minimum_sinr_gain_db"] == 8.0
    assert summary["comparison"]["outage_reduction_percentage_points"] == 25.0
    assert summary["execution"]["terminal_type"] == "complete"
    assert (output / "summary.json").is_file()
    assert (output / "route_metrics.csv").is_file()
    assert (output / "trajectory_points.csv").is_file()
    assert (output / "flight_samples.csv").is_file()
    report = (output / "README.md").read_text(encoding="utf-8")
    assert "单场景闭环演示" in report
    assert "仅通信约束航迹在 LAESim/UE 中实际执行" in report


def test_export_rejects_incomplete_mission(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    log = tmp_path / "mission.jsonl"
    _write_run(run_dir)
    _write_log(log, terminal_type="stopped")

    with pytest.raises(ValueError, match="incomplete"):
        export_use_case(run_dir, log, tmp_path / "paper")
