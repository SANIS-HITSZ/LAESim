"""Plan and execute a communication-aware route in a running LAESim world."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from wireless_city_factory.laesim_bridge import LAESimBridge
from wireless_city_factory.planning import ConnectivityAwarePrimitivePlanner, PlannerConfig, PlanningError
from wireless_city_factory.runtime import RadioMapLookup

DEFAULT_VISUALIZER_STATE = Path(__file__).resolve().parents[1] / "runtime" / "laesim_live_state.json"


class MissionStopped(RuntimeError):
    """The operator requested a controlled mission stop."""


def _write_row(stream, row) -> None:
    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    stream.flush()


def _write_visualizer_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)


def _route_progress(points, position) -> float:
    route = np.asarray(points, dtype=float)
    distances = np.linalg.norm(route - np.asarray(position, dtype=float), axis=1)
    return float(np.argmin(distances) / max(1, len(route) - 1))


def _downsample(points, spacing_m: float = 1.0):
    selected = [points[0]]
    for point in points[1:-1]:
        if np.linalg.norm(np.asarray(point) - np.asarray(selected[-1])) >= spacing_m:
            selected.append(point)
    selected.append(points[-1])
    return selected


def _project_to_radio_altitude(position, altitude_m: float) -> tuple[float, float, float]:
    """Evaluate a fixed-altitude radio map without falsifying the LAESim pose."""
    return (float(position[0]), float(position[1]), float(altitude_m))


def _check_stop_requested(stop_file: Path | None) -> None:
    if stop_file is not None and stop_file.is_file():
        raise MissionStopped("Mission stop requested by the operator.")


def _query_task_observation(
    lookup: RadioMapLookup,
    position: tuple[float, float, float],
    *,
    minimum_sinr_db: float,
    minimum_rss_dbm: float | None,
):
    """Apply the same hard radio thresholds used by the task planner."""
    observation = lookup.query(position, outage_threshold_db=minimum_sinr_db)
    if minimum_rss_dbm is None or observation.outage:
        return observation
    serving_rss = (
        None
        if observation.serving_cell is None
        else observation.rss_dbm.get(observation.serving_cell)
    )
    if serving_rss is None or serving_rss < minimum_rss_dbm:
        return replace(observation, outage=True)
    return observation


def _planning_failure_details(error: PlanningError, *, altitude_m: float, minimum_sinr_db: float) -> dict:
    message = str(error)
    if "No globally connected route" in message:
        guidance = (
            "当前任务的起终点在此高度和门限下不属于同一连续可行区域。"
            "请增加基站密度、改用更细的无线网格、调整任务点或重新评估 SINR 门限；"
            "仅降低门限不一定能修复由遮挡或无覆盖网格造成的断裂。"
        )
        code = "no_globally_connected_route"
    elif "endpoint" in message.lower():
        guidance = "任务端点无法接入可行无线网格，请调整起终点、飞行高度或无线地图范围后重新生成。"
        code = "endpoint_not_connected"
    else:
        guidance = "规划约束无法同时满足，请检查建筑碰撞、无线覆盖、飞行高度和任务端点。"
        code = "planning_infeasible"
    return {
        "error_code": code,
        "error": message,
        "guidance": guidance,
        "planning": {
            "flight_altitude_m": float(altitude_m),
            "minimum_sinr_db": float(minimum_sinr_db),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task-id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=41471)
    parser.add_argument("--vehicle-name", default="UAV")
    parser.add_argument("--flight-altitude-m", type=float)
    parser.add_argument("--cruise-speed-mps", type=float, default=5.0)
    parser.add_argument("--maximum-speed-mps", type=float, default=15.0)
    parser.add_argument("--maximum-acceleration-mps2", type=float, default=20.0)
    parser.add_argument("--vertical-speed-mps", type=float, default=5.0)
    parser.add_argument("--sample-period-s", type=float, default=0.25)
    parser.add_argument("--minimum-sinr-db", type=float)
    parser.add_argument("--minimum-rss-dbm", type=float)
    parser.add_argument("--maximum-outage-fraction", type=float)
    parser.add_argument("--radio-weight", type=float, default=6.0)
    parser.add_argument("--handover-weight", type=float, default=0.5)
    parser.add_argument("--timeout-margin-s", type=float, default=20.0)
    parser.add_argument("--visualizer-state", type=Path, default=DEFAULT_VISUALIZER_STATE)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if min(args.cruise_speed_mps, args.vertical_speed_mps, args.sample_period_s) <= 0.0:
        raise ValueError("Speeds and sample-period-s must be positive.")

    lookup = RadioMapLookup.load(args.run_dir)
    task = lookup.scene.tasks[0] if args.task_id is None else next(
        (item for item in lookup.scene.tasks if str(item["task_id"]) == args.task_id),
        None,
    )
    if task is None:
        raise ValueError(f"Unknown task-id: {args.task_id}")
    altitude = float(args.flight_altitude_m if args.flight_altitude_m is not None else task["start_m"][2])
    minimum_sinr_db = float(
        args.minimum_sinr_db
        if args.minimum_sinr_db is not None
        else task.get("minimum_sinr_db", 0.0)
    )
    minimum_rss_dbm = (
        args.minimum_rss_dbm
        if args.minimum_rss_dbm is not None
        else task.get("minimum_rss_dbm")
    )
    maximum_outage_fraction = float(
        args.maximum_outage_fraction
        if args.maximum_outage_fraction is not None
        else task.get("maximum_outage_fraction", 0.0)
    )
    goal = (float(task["goal_m"][0]), float(task["goal_m"][1]), altitude)
    config = PlannerConfig(
        cruise_speed_mps=args.cruise_speed_mps,
        maximum_speed_mps=args.maximum_speed_mps,
        maximum_acceleration_mps2=args.maximum_acceleration_mps2,
        minimum_sinr_db=minimum_sinr_db,
        minimum_serving_rss_dbm=(None if minimum_rss_dbm is None else float(minimum_rss_dbm)),
        maximum_outage_fraction=maximum_outage_fraction,
        radio_weight=args.radio_weight,
        handover_weight=args.handover_weight,
        enforce_connectivity=True,
        global_guidance_enabled=True,
    )
    bridge = LAESimBridge(
        lookup,
        host=args.host,
        port=args.port,
        vehicle_name=args.vehicle_name,
        task_id=args.task_id,
    )
    run_dir = args.run_dir.resolve()
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    station_manifest = json.loads(
        (run_dir / "base_station_manifest.json").read_text(encoding="utf-8")
    )
    radio_manifest = json.loads((run_dir / "radio_manifest.json").read_text(encoding="utf-8"))
    ue_manifest = json.loads((run_dir / "ue_manifest.json").read_text(encoding="utf-8"))
    session = {
        "contract": "wireless-city-laesim-live-v1",
        "session_id": uuid.uuid4().hex,
        "status": "connecting",
        "run_dir": str(run_dir),
        "fingerprints": {
            "run_id": run_dir.name,
            "config_fingerprint": run_manifest.get("config_fingerprint"),
            "scene_fingerprint": lookup.scene.fingerprint(),
            "base_station_fingerprint": station_manifest.get("base_station_fingerprint"),
            "radio_fingerprint": radio_manifest.get("radio_fingerprint"),
            "ue_scene_fingerprint": ue_manifest.get("source_scene_fingerprint"),
        },
        "planning": {
            "flight_altitude_m": altitude,
            "minimum_sinr_db": minimum_sinr_db,
            "minimum_rss_dbm": minimum_rss_dbm,
            "maximum_outage_fraction": maximum_outage_fraction,
        },
        "route": None,
        "routes": None,
        "latest": None,
        "progress": 0.0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_visualizer_state(args.visualizer_state, session)
        bridge.connect()
        _check_stop_requested(args.stop_file)
        initial = bridge.read_state()
        planning_start = _project_to_radio_altitude(initial.position_scene_m, altitude)
        session.update({"status": "planning", "latest": initial.to_dict()})
        _write_visualizer_state(args.visualizer_state, session)
        baseline_config = replace(
            config,
            enforce_connectivity=False,
            global_guidance_enabled=False,
            radio_weight=0.0,
            handover_weight=0.0,
        )
        baseline = ConnectivityAwarePrimitivePlanner(lookup, baseline_config).plan(
            planning_start,
            goal,
        )
        route = ConnectivityAwarePrimitivePlanner(lookup, config).plan(planning_start, goal)
        _check_stop_requested(args.stop_file)
        routes = {"baseline": baseline.to_dict(), "connectivity": route.to_dict()}
        session.update({"status": "preview", "route": route.to_dict(), "routes": routes})
        _write_visualizer_state(args.visualizer_state, session)
        bridge.prepare_flight(altitude, vertical_speed_mps=args.vertical_speed_mps)
        _check_stop_requested(args.stop_file)
        session.update({"status": "flying"})
        _write_visualizer_state(args.visualizer_state, session)
        execution_points = _downsample(route.points_m)
        timeout_s = route.metrics.length_m / args.cruise_speed_mps + args.timeout_margin_s
        future = bridge.start_route(
            execution_points,
            velocity_mps=args.cruise_speed_mps,
            timeout_s=timeout_s,
        )
        with args.output.open("w", encoding="utf-8") as output:
            _write_row(output, {"type": "mission", "route": route.to_dict(), "routes": routes})
            started = time.monotonic()
            while time.monotonic() - started < timeout_s:
                _check_stop_requested(args.stop_file)
                state = bridge.read_state()
                radio_position = _project_to_radio_altitude(state.position_scene_m, altitude)
                observation = _query_task_observation(
                    lookup,
                    radio_position,
                    minimum_sinr_db=minimum_sinr_db,
                    minimum_rss_dbm=(
                        None if minimum_rss_dbm is None else float(minimum_rss_dbm)
                    ),
                )
                progress = _route_progress(route.points_m, state.position_scene_m)
                _write_row(
                    output,
                    {
                        "type": "sample",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": {
                            "type": "follow_connectivity_route",
                            "command": "moveOnPathAsync",
                            "cruise_speed_mps": args.cruise_speed_mps,
                        },
                        **state.to_dict(),
                        "radio": observation.to_dict(),
                    },
                )
                session.update(
                    {
                        "status": "flying",
                        "latest": state.to_dict(),
                        "radio": observation.to_dict(),
                        "progress": progress,
                    }
                )
                _write_visualizer_state(args.visualizer_state, session)
                if state.has_collided:
                    bridge.hover()
                    raise RuntimeError(f"LAESim collision with {state.collision_object!r}.")
                if np.linalg.norm(np.asarray(state.position_scene_m) - np.asarray(goal)) <= config.target_tolerance_m:
                    break
                time.sleep(args.sample_period_s)
            future.join()
            bridge.hover()
            final_state = bridge.read_state()
            final_error = float(np.linalg.norm(np.asarray(final_state.position_scene_m) - np.asarray(goal)))
            _write_row(output, {"type": "complete", "final_error_m": final_error, **final_state.to_dict()})
            session.update(
                {
                    "status": "complete",
                    "latest": final_state.to_dict(),
                    "progress": 1.0,
                    "final_error_m": final_error,
                }
            )
            _write_visualizer_state(args.visualizer_state, session)
            if final_error > config.target_tolerance_m:
                raise RuntimeError(f"LAESim stopped {final_error:.2f} m from the planned goal.")
    except MissionStopped:
        try:
            bridge.hover()
            final_state = bridge.read_state()
            stopped = {
                "type": "stopped",
                "reason": "operator_request",
                **final_state.to_dict(),
            }
            with args.output.open("a", encoding="utf-8") as output:
                _write_row(output, stopped)
            session.update(
                {
                    "status": "stopped",
                    "latest": final_state.to_dict(),
                    "stop_reason": "operator_request",
                }
            )
        except Exception:  # noqa: BLE001 - cleanup must survive third-party RPC failures
            session.update({"status": "stopped", "stop_reason": "operator_request"})
        try:
            _write_visualizer_state(args.visualizer_state, session)
        except OSError:
            pass
        print(f"Mission stopped: {args.output.resolve()}")
        return 0
    except PlanningError as exc:
        details = _planning_failure_details(
            exc,
            altitude_m=altitude,
            minimum_sinr_db=minimum_sinr_db,
        )
        session.update({"status": "error", **details})
        try:
            _write_visualizer_state(args.visualizer_state, session)
        except OSError:
            pass
        print(f"任务未执行：{details['error']}", file=sys.stderr)
        print(f"建议：{details['guidance']}", file=sys.stderr)
        return 2
    except Exception as exc:
        session.update({"status": "error", "error": str(exc)})
        try:
            _write_visualizer_state(args.visualizer_state, session)
        except OSError:
            pass
        raise
    finally:
        bridge.release()
        if args.stop_file is not None:
            args.stop_file.unlink(missing_ok=True)
    print(f"Mission log: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
