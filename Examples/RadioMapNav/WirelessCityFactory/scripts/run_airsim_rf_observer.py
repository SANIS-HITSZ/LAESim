"""Drive a short AirSim action and log synchronized offline RF observations."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import airsim

from wireless_city_factory.runtime import RadioMapLookup


def _vector(value):
    return {"x": value.x_val, "y": value.y_val, "z": value.z_val}


def _record(client, lookup, output, action, vehicle_name, task_id):
    state = client.getMultirotorState(vehicle_name=vehicle_name)
    ned = state.kinematics_estimated.position
    ned_position = (ned.x_val, ned.y_val, ned.z_val)
    canonical = lookup.canonical_from_airsim_ned(ned_position, task_id=task_id)
    query_started = time.perf_counter()
    observation = lookup.query(canonical)
    query_latency_ms = (time.perf_counter() - query_started) * 1000.0
    collision = client.simGetCollisionInfo(vehicle_name=vehicle_name)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sim_timestamp_ns": int(state.timestamp),
        "pose_ned_m": list(ned_position),
        "pose_scene_m": list(canonical),
        "velocity_ned_mps": _vector(state.kinematics_estimated.linear_velocity),
        "action": action,
        "query_latency_ms": query_latency_ms,
        "valid_mask": True,
        "collision": {"has_collided": collision.has_collided, "object_name": collision.object_name},
        **observation.to_dict(),
    }
    output.write(json.dumps(row, separators=(",", ":")) + "\n")
    output.flush()
    print(json.dumps(row, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=41471)
    parser.add_argument("--vehicle-name", default="UAV")
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--sample-period", type=float, default=0.25)
    parser.add_argument("--vx", type=float, default=1.0)
    parser.add_argument("--vy", type=float, default=0.0)
    parser.add_argument("--vz", type=float, default=0.0)
    parser.add_argument("--flight-altitude-m", type=float, default=None)
    parser.add_argument("--vertical-speed", type=float, default=5.0)
    args = parser.parse_args()
    if args.duration <= 0.0 or args.sample_period <= 0.0 or args.vertical_speed <= 0.0:
        raise ValueError("duration, sample-period, and vertical-speed must be positive")
    lookup = RadioMapLookup.load(args.run_dir)
    task = lookup.scene.tasks[0]
    if args.task_id is not None:
        task = next(
            (item for item in lookup.scene.tasks if str(item["task_id"]) == args.task_id),
            None,
        )
        if task is None:
            raise ValueError(f"Unknown task-id: {args.task_id}")
    flight_altitude_m = (
        float(args.flight_altitude_m)
        if args.flight_altitude_m is not None
        else float(task["start_m"][2])
    )
    if not float(lookup.z_m[0]) <= flight_altitude_m <= float(lookup.z_m[-1]):
        raise ValueError(
            f"flight-altitude-m={flight_altitude_m} lies outside the radio-map altitude "
            f"range [{float(lookup.z_m[0])}, {float(lookup.z_m[-1])}]."
        )
    target_ned_z = lookup.airsim_ned_from_canonical(
        (float(task["start_m"][0]), float(task["start_m"][1]), flight_altitude_m),
        task_id=args.task_id,
    )[2]
    client = airsim.MultirotorClient(ip=args.host, port=args.port)
    client.confirmConnection()
    client.enableApiControl(True, vehicle_name=args.vehicle_name)
    client.armDisarm(True, vehicle_name=args.vehicle_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.takeoffAsync(vehicle_name=args.vehicle_name).join()
        client.moveToZAsync(
            target_ned_z,
            args.vertical_speed,
            vehicle_name=args.vehicle_name,
        ).join()
        client.hoverAsync(vehicle_name=args.vehicle_name).join()
        with args.output.open("w", encoding="utf-8") as output:
            _record(client, lookup, output, "hover", args.vehicle_name, args.task_id)
            future = client.moveByVelocityAsync(
                args.vx, args.vy, args.vz, args.duration, vehicle_name=args.vehicle_name
            )
            started = time.monotonic()
            while time.monotonic() - started < args.duration:
                _record(
                    client,
                    lookup,
                    output,
                    f"velocity=({args.vx},{args.vy},{args.vz})",
                    args.vehicle_name,
                    args.task_id,
                )
                time.sleep(args.sample_period)
            future.join()
            client.hoverAsync(vehicle_name=args.vehicle_name).join()
            _record(client, lookup, output, "hover", args.vehicle_name, args.task_id)
    finally:
        client.enableApiControl(False, vehicle_name=args.vehicle_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
