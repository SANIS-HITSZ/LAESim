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


def _report_markdown(summary: dict[str, Any]) -> str:
    baseline = summary["routes"]["baseline"]
    connectivity = summary["routes"]["connectivity"]
    delta = summary["comparison"]
    execution = summary["execution"]
    setup = summary["setup"]
    return f"""# LAESim 通信连接约束轨迹规划 use case

## 证据级别

这是一次已完成的单场景闭环演示。几何基线航迹与通信约束航迹在同一城市、起终点、飞行高度、基站清单和 Sionna RT 离线信道地图上规划；仅通信约束航迹在 LAESim/UE 中实际执行。该结果可作为论文 use case 和系统能力证据，不能代替多场景、多随机种子的统计实验。

## 实验设置

| 项目 | 值 |
| --- | --- |
| 运行编号 | `{summary['run_id']}` |
| 场景 | `{summary['scene_id']}` |
| 任务 | `{summary['task_id']}` |
| 起点 | `{setup['start_m']}` m |
| 终点 | `{setup['goal_m']}` m |
| 飞行高度 | {setup['flight_altitude_m']:.1f} m |
| SINR 门限 | {setup['minimum_sinr_db']:.1f} dB |
| 最大允许中断比例 | {setup['maximum_outage_fraction'] * 100:.2f}% |
| Sionna RT 网格 | {setup['radio_grid']} |
| 载波频率 | {setup['frequency_hz'] / 1e9:.3g} GHz |
| 信道带宽 | {setup['bandwidth_hz'] / 1e6:.0f} MHz |

## 路线对比

| 指标 | 几何基线 | 通信约束 |
| --- | ---: | ---: |
| 路径长度 | {baseline['length_m']:.2f} m | {connectivity['length_m']:.2f} m |
| 最低 SINR | {baseline['minimum_sinr_db']:.2f} dB | {connectivity['minimum_sinr_db']:.2f} dB |
| 平均 SINR | {baseline['mean_sinr_db']:.2f} dB | {connectivity['mean_sinr_db']:.2f} dB |
| 中断比例 | {baseline['outage_fraction'] * 100:.2f}% | {connectivity['outage_fraction'] * 100:.2f}% |
| 小区切换 | {baseline['handover_count']} | {connectivity['handover_count']} |

通信约束航迹相对几何基线的距离变化为 {delta['distance_change_percent']:+.2f}%，最低 SINR 提升 {delta['minimum_sinr_gain_db']:+.2f} dB，中断比例下降 {delta['outage_reduction_percentage_points']:.2f} 个百分点，平均 SINR 变化 {delta['mean_sinr_change_db']:+.2f} dB。这个结果说明该方法优化的是弱覆盖尾部可靠性，而不是保证所有平均指标同时提高。

## LAESim 执行验证

| 项目 | 结果 |
| --- | ---: |
| 实际采样点数 | {execution['sample_count']} |
| 实际飞行轨迹长度 | {execution['actual_path_length_m']:.2f} m |
| 任务持续时间 | {execution['duration_s']:.2f} s |
| 碰撞采样数 | {execution['collision_sample_count']} |
| 最终位置误差 | {execution['final_error_m']:.3f} m |
| 完成状态 | `{execution['terminal_type']}` |

## 可复现性

`summary.json` 保存完整指纹、实验设置、比较结果和执行验证；`route_metrics.csv` 可直接用于论文表格；`trajectory_points.csv` 可绘制两条规划航迹；`flight_samples.csv` 保存 LAESim 实际位置及逐点无线观测。所有输入通过场景、基站、无线地图和 UE 导入指纹一致性检查。

## 论文表述边界

- 可以表述为“Neural-Primitive-inspired 通信感知专家规划 use case”。
- 不应表述为已经复现论文的神经网络、模仿学习或训练权重。
- 当前无线地图为离线静态 Sionna RT 结果；在线阶段执行查表与插值，不是逐飞行步实时射线追踪。
- 当前结果是单次演示。用于正式数值结论前，应使用冻结的生产网格，在三个城市类型、多随机种子和多任务点上重复实验并报告均值、标准差和失败率。
"""


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
    (output_dir / "README.md").write_text(_report_markdown(summary), encoding="utf-8")
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
