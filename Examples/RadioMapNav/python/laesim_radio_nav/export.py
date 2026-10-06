"""Export a completed LAESim connectivity mission as a paper-use-case evidence package."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

ROUTE_FIELDS = (
    "length_m",
    "outage_fraction",
    "minimum_sinr_db",
    "mean_sinr_db",
    "minimum_serving_rss_dbm",
    "mean_serving_rss_dbm",
    "handover_count",
    "replans",
    "final_error_m",
    "reached_goal",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {path}") from exc
    return rows


def _fingerprint_contract(run_dir: Path) -> dict[str, str]:
    run = _load_json(run_dir / "manifest.json")
    city = _load_json(run_dir / "city_manifest.json")
    radio = _load_json(run_dir / "radio_manifest.json")
    stations = _load_json(run_dir / "base_station_manifest.json")
    ue = _load_json(run_dir / "ue_manifest.json")
    imported = _load_json(run_dir / "ue_import_result.json")
    scene_values = {
        str(run.get("scene_fingerprint")),
        str(city.get("scene_fingerprint")),
        str(radio.get("scene_fingerprint")),
        str(ue.get("source_scene_fingerprint")),
        str(imported.get("source_scene_fingerprint")),
    }
    if "None" in scene_values or len(scene_values) != 1:
        raise ValueError("Run, radio map, UE bundle, and imported UE scene fingerprints do not match.")
    station_values = {
        str(stations.get("base_station_fingerprint")),
        str(city.get("base_station_fingerprint")),
        str(radio.get("metadata", {}).get("base_station_fingerprint")),
    }
    if "None" in station_values or len(station_values) != 1:
        raise ValueError("City and radio-map base-station fingerprints do not match.")
    return {
        "config_fingerprint": str(run.get("config_fingerprint")),
        "scene_fingerprint": scene_values.pop(),
        "base_station_fingerprint": station_values.pop(),
        "radio_fingerprint": str(radio.get("radio_fingerprint")),
    }


def _route_metrics(mode: str, route: dict[str, Any]) -> dict[str, Any]:
    metrics = route.get("metrics", {})
    return {"mode": mode, **{field: metrics.get(field) for field in ROUTE_FIELDS}}


def _distance(points: list[list[float]]) -> float:
    return sum(
        math.dist([float(value) for value in first], [float(value) for value in second])
        for first, second in pairwise(points)
    )


def _delta_summary(baseline: dict[str, Any], connectivity: dict[str, Any]) -> dict[str, float]:
    base_length = float(baseline["length_m"])
    return {
        "distance_change_percent": (float(connectivity["length_m"]) / base_length - 1.0) * 100.0,
        "minimum_sinr_gain_db": float(connectivity["minimum_sinr_db"]) - float(baseline["minimum_sinr_db"]),
        "mean_sinr_change_db": float(connectivity["mean_sinr_db"]) - float(baseline["mean_sinr_db"]),
        "outage_reduction_percentage_points": (
            float(baseline["outage_fraction"]) - float(connectivity["outage_fraction"])
        ) * 100.0,
        "handover_change": float(connectivity["handover_count"]) - float(baseline["handover_count"]),
    }


def _write_route_metrics(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("mode", *ROUTE_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def _write_trajectory_points(path: Path, routes: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mode", "point_index", "x_m", "y_m", "z_m"))
        for mode in ("baseline", "connectivity"):
            for index, point in enumerate(routes[mode]["points_m"]):
                writer.writerow((mode, index, *point))


def _write_flight_samples(path: Path, samples: list[dict[str, Any]]) -> None:
    first_timestamp = datetime.fromisoformat(samples[0]["timestamp"])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "sample_index",
                "elapsed_s",
                "timestamp",
                "x_m",
                "y_m",
                "z_m",
                "sinr_db",
                "serving_rss_dbm",
                "serving_cell",
                "outage",
                "has_collided",
            )
        )
        for index, sample in enumerate(samples):
            timestamp = datetime.fromisoformat(sample["timestamp"])
            radio = sample.get("radio", {})
            serving_cell = radio.get("serving_cell")
            rss = radio.get("rss_dbm", {})
            writer.writerow(
                (
                    index,
                    (timestamp - first_timestamp).total_seconds(),
                    sample["timestamp"],
                    *sample["position_scene_m"],
                    radio.get("sinr_db"),
                    rss.get(serving_cell),
                    serving_cell,
                    radio.get("outage"),
                    sample.get("has_collided"),
                )
            )


def export_use_case(run_dir: Path, mission_log: Path, output_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    mission_log = mission_log.resolve()
    fingerprints = _fingerprint_contract(run_dir)
    rows = _load_jsonl(mission_log)
    missions = [row for row in rows if row.get("type") == "mission"]
    samples = [row for row in rows if row.get("type") == "sample"]
    if len(missions) != 1 or not samples:
        raise ValueError("Mission log must contain exactly one mission row and at least one sample row.")
    terminal = rows[-1]
    if terminal.get("type") != "complete":
        raise ValueError("Mission log is incomplete; the final row must have type=complete.")
    routes = missions[0].get("routes", {})
    if not all(mode in routes for mode in ("baseline", "connectivity")):
        raise ValueError("Mission log must contain baseline and connectivity routes.")

    scene = _load_json(run_dir / "scene.json")
    radio = _load_json(run_dir / "radio_manifest.json")
    radio_config = radio.get("metadata", {}).get("config", {})
    task = scene["tasks"][0]
    route_rows = [_route_metrics(mode, routes[mode]) for mode in ("baseline", "connectivity")]
    route_by_mode = {row["mode"]: row for row in route_rows}
    timestamps = [datetime.fromisoformat(sample["timestamp"]) for sample in samples]
    actual_points = [[float(value) for value in sample["position_scene_m"]] for sample in samples]
    summary = {
        "contract": "wireless-city-paper-usecase-v1",
        "evidence_level": "single-run-demonstrator",
        "run_id": run_dir.name,
        "scene_id": scene["scene_id"],
        "task_id": str(task["task_id"]),
        "fingerprints": fingerprints,
        "setup": {
            "start_m": task["start_m"],
            "goal_m": task["goal_m"],
            "flight_altitude_m": float(task["start_m"][2]),
            "minimum_sinr_db": float(routes["connectivity"]["planner_config"]["minimum_sinr_db"]),
            "maximum_outage_fraction": float(
                routes["connectivity"]["planner_config"]["maximum_outage_fraction"]
            ),
            "radio_grid": " x ".join(str(value) for value in radio["shape"]),
            "frequency_hz": float(radio_config["frequency_hz"]),
            "bandwidth_hz": float(radio_config["bandwidth_hz"]),
        },
        "routes": route_by_mode,
        "comparison": _delta_summary(route_by_mode["baseline"], route_by_mode["connectivity"]),
        "execution": {
            "executed_mode": "connectivity",
            "baseline_execution": "offline-planning-only",
            "sample_count": len(samples),
            "duration_s": (timestamps[-1] - timestamps[0]).total_seconds(),
            "actual_path_length_m": _distance(actual_points),
            "collision_sample_count": sum(bool(sample.get("has_collided")) for sample in samples),
            "terminal_type": terminal["type"],
            "final_error_m": float(terminal["final_error_m"]),
            "final_position_scene_m": terminal["position_scene_m"],
        },
        "sources": {"run_dir": str(run_dir), "mission_log": str(mission_log)},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_route_metrics(output_dir / "route_metrics.csv", route_rows)
    _write_trajectory_points(output_dir / "trajectory_points.csv", routes)
    _write_flight_samples(output_dir / "flight_samples.csv", samples)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--mission-log", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = export_use_case(args.run_dir, args.mission_log, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "comparison": summary["comparison"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
