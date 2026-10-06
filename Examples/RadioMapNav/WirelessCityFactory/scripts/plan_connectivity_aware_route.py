"""Compare geometry-only and communication-aware motion-primitive routes offline."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from wireless_city_factory.planning import ConnectivityAwarePrimitivePlanner, PlannerConfig
from wireless_city_factory.runtime import RadioMapLookup


def _task(lookup: RadioMapLookup, task_id: str | None):
    if task_id is None:
        return lookup.scene.tasks[0]
    task = next((item for item in lookup.scene.tasks if str(item["task_id"]) == task_id), None)
    if task is None:
        raise ValueError(f"Unknown task-id: {task_id}")
    return task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task-id")
    parser.add_argument("--flight-altitude-m", type=float)
    parser.add_argument("--mode", choices=("baseline", "connectivity", "both"), default="both")
    parser.add_argument("--cruise-speed-mps", type=float, default=8.0)
    parser.add_argument("--maximum-speed-mps", type=float, default=15.0)
    parser.add_argument("--maximum-acceleration-mps2", type=float, default=20.0)
    parser.add_argument("--minimum-sinr-db", type=float, default=0.0)
    parser.add_argument("--minimum-rss-dbm", type=float)
    parser.add_argument("--maximum-outage-fraction", type=float, default=0.0)
    parser.add_argument("--radio-weight", type=float, default=6.0)
    parser.add_argument("--handover-weight", type=float, default=0.5)
    parser.add_argument("--maximum-replans", type=int, default=300)
    args = parser.parse_args()

    lookup = RadioMapLookup.load(args.run_dir)
    task = _task(lookup, args.task_id)
    start = [float(value) for value in task["start_m"]]
    goal = [float(value) for value in task["goal_m"]]
    if args.flight_altitude_m is not None:
        start[2] = goal[2] = float(args.flight_altitude_m)
    base = PlannerConfig(
        cruise_speed_mps=args.cruise_speed_mps,
        maximum_speed_mps=args.maximum_speed_mps,
        maximum_acceleration_mps2=args.maximum_acceleration_mps2,
        minimum_sinr_db=args.minimum_sinr_db,
        minimum_serving_rss_dbm=args.minimum_rss_dbm,
        maximum_outage_fraction=args.maximum_outage_fraction,
        radio_weight=args.radio_weight,
        handover_weight=args.handover_weight,
        maximum_replans=args.maximum_replans,
    )
    configurations = {
        "baseline": replace(base, enforce_connectivity=False, radio_weight=0.0, handover_weight=0.0),
        "connectivity": replace(base, enforce_connectivity=True, global_guidance_enabled=True),
    }
    selected_modes = ("baseline", "connectivity") if args.mode == "both" else (args.mode,)
    routes = {
        mode: ConnectivityAwarePrimitivePlanner(lookup, configurations[mode]).plan(tuple(start), tuple(goal)).to_dict()
        for mode in selected_modes
    }
    payload = {
        "contract": "wireless-city-route-comparison-v1",
        "run_dir": str(args.run_dir.resolve()),
        "scene_id": lookup.scene.scene_id,
        "scene_fingerprint": lookup.scene.fingerprint(),
        "task_id": str(task["task_id"]),
        "routes": routes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({mode: route["metrics"] for mode, route in routes.items()}, indent=2, ensure_ascii=False))
    print(f"Saved: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
