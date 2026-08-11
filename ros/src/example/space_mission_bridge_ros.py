#!/usr/bin/env python3
"""ROS wrapper for the LAESim space-mission bridge."""

import argparse
import json
import math
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass

import rospy
from geometry_msgs.msg import Pose, Quaternion, Vector3
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import NavSatFix, NavSatStatus

from airsim_ros_pkgs.msg import SpaceAccessState, SpaceSatelliteState


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MULTI_USE = os.path.join(ROOT, "Multi_use")
PYCLIENT = os.path.join(ROOT, "PythonClient")
for path in (MULTI_USE, PYCLIENT):
    if path not in sys.path:
        sys.path.insert(0, path)

import space_mission_bridge as bridge


@dataclass(frozen=True)
class DynamicTargetSpec:
    vehicle_name: str
    kind: str
    topic: str

    @property
    def name(self):
        return self.vehicle_name


class RuntimeMissionRecorder:
    def __init__(self, jsonl_path, summary_path, metadata):
        self.jsonl_path = os.path.abspath(jsonl_path) if jsonl_path else ""
        self.summary_path = os.path.abspath(summary_path) if summary_path else ""
        self.metadata = metadata
        self.sample_count = 0
        self.first_time = None
        self.last_time = None
        self.satellite_name = ""
        self.source = ""
        self.targets = {}
        self.closed = False
        for path in (self.jsonl_path, self.summary_path):
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.jsonl_path:
            open(self.jsonl_path, "w", encoding="utf-8").close()
        if self.summary_path and os.path.exists(self.summary_path):
            os.unlink(self.summary_path)

    @staticmethod
    def _sample_time(sample):
        try:
            return bridge.parse_time(sample.timestamp)
        except (TypeError, ValueError):
            return bridge._dt.datetime.now(bridge._dt.timezone.utc)

    @staticmethod
    def _close_window(stats, stop_time):
        active = stats.pop("_active", None)
        if active is None:
            return
        duration_s = max(0.0, (stop_time - active["start_dt"]).total_seconds())
        stats["windows"].append({
            "start": bridge.format_time(active["start_dt"]),
            "stop": bridge.format_time(stop_time),
            "duration_s": duration_s,
            "max_elevation_deg": active["max_elevation_deg"],
            "min_range_m": active["min_range_m"],
        })

    def record(self, sample, display, access_states):
        timestamp = self._sample_time(sample)
        self.first_time = self.first_time or timestamp
        self.last_time = timestamp
        self.sample_count += 1
        self.satellite_name = sample.satellite_name
        self.source = sample.source

        bridge.write_jsonl(self.jsonl_path, {
            "timestamp": sample.timestamp,
            "sample": asdict(sample),
            "display": asdict(display),
            "access": [asdict(state) for state in access_states],
        })

        for state in access_states:
            stats = self.targets.setdefault(state.target_name, {
                "kind": state.target_kind,
                "samples": 0,
                "valid_samples": 0,
                "access_samples": 0,
                "windows": [],
            })
            stats["samples"] += 1
            if state.valid:
                stats["valid_samples"] += 1
            active = stats.get("_active")
            if state.valid and state.access:
                stats["access_samples"] += 1
                if active is None:
                    active = {
                        "start_dt": timestamp,
                        "max_elevation_deg": state.elevation_deg,
                        "min_range_m": state.range_m,
                    }
                    stats["_active"] = active
                else:
                    if math.isfinite(state.elevation_deg):
                        active["max_elevation_deg"] = max(
                            active["max_elevation_deg"], state.elevation_deg
                        )
                    if math.isfinite(state.range_m):
                        active["min_range_m"] = min(active["min_range_m"], state.range_m)
            elif active is not None:
                self._close_window(stats, timestamp)

    def close(self):
        if self.closed:
            return
        self.closed = True
        stop_time = self.last_time or bridge._dt.datetime.now(bridge._dt.timezone.utc)
        for stats in self.targets.values():
            self._close_window(stats, stop_time)
        if not self.summary_path:
            return

        targets = {}
        for name, stats in self.targets.items():
            windows = stats["windows"]
            targets[name] = {
                "kind": stats["kind"],
                "samples": stats["samples"],
                "valid_samples": stats["valid_samples"],
                "access_samples": stats["access_samples"],
                "access_sample_fraction": (
                    stats["access_samples"] / stats["valid_samples"]
                    if stats["valid_samples"] else 0.0
                ),
                "window_count": len(windows),
                "total_access_s": sum(window["duration_s"] for window in windows),
                "windows": windows,
            }
        summary = {
            "metadata": self.metadata,
            "satellite_name": self.satellite_name,
            "source": self.source,
            "scenario_start": bridge.format_time(self.first_time) if self.first_time else "",
            "scenario_stop": bridge.format_time(self.last_time) if self.last_time else "",
            "sample_count": self.sample_count,
            "targets": targets,
        }
        with open(self.summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False, allow_nan=True)


def parse_dynamic_target(value):
    parts = value.split(":", 1)
    vehicle_name = parts[0].strip()
    if not vehicle_name:
        raise argparse.ArgumentTypeError("Dynamic target must specify a vehicle name")
    kind = parts[1].strip() if len(parts) == 2 and parts[1].strip() else "vehicle"
    return DynamicTargetSpec(
        vehicle_name=vehicle_name,
        kind=kind,
        topic=f"/airsim_node/{vehicle_name}/global_gps",
    )


def ros_quaternion_from_yaw(yaw_rad):
    x, y, z, w = bridge.yaw_to_quaternion_values(yaw_rad)
    return Quaternion(x=x, y=y, z=z, w=w)


def parse_args():
    parser = argparse.ArgumentParser(description="Publish satellite mission truth and optionally drive a LAESim satellite pose.")
    parser.add_argument("--provider", choices=("tle", "orekit-tle", "csv", "mock"), default="csv")
    parser.add_argument("--tle", default=os.path.join(ROOT, "Multi_use", "space_mission_sample.tle"))
    parser.add_argument("--orekit-data", default="")
    parser.add_argument("--csv", default="")
    parser.add_argument("--satellite-name", default="")
    parser.add_argument("--satellite-index", type=int, default=0)
    parser.add_argument("--vehicle", default="Satellite")
    parser.add_argument("--namespace", default="/space")
    parser.add_argument("--rate", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=0.0, help="Stop after this many wall-clock seconds; 0 runs forever.")
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=bridge.RPCLIB_PORT_SATELLITE)
    parser.add_argument("--drive-laesim", action="store_true")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--clock-speed", type=float, default=1.0)
    parser.add_argument("--clock-source", choices=("wall", "ros"), default="wall")
    parser.add_argument("--clock-topic", default="/clock")
    parser.add_argument("--auto-next-access", action="store_true", help="Start shortly before the next access over the reference point.")
    parser.add_argument("--access-search-hours", type=float, default=48.0)
    parser.add_argument("--access-search-step-s", type=float, default=30.0)
    parser.add_argument("--access-lead-s", type=float, default=300.0)
    parser.add_argument("--target", action="append", default=[], help="Mission target as NAME:LAT:LON[:ALT[:KIND]]. Can be repeated.")
    parser.add_argument(
        "--target-vehicle",
        action="append",
        default=[],
        type=parse_dynamic_target,
        metavar="VEHICLE[:KIND]",
        help="Use /airsim_node/<vehicle>/global_gps as a live mission target. Can be repeated.",
    )
    parser.add_argument(
        "--dynamic-target-max-age",
        type=float,
        default=2.0,
        help="Reject dynamic GPS states older than this many wall-clock seconds.",
    )
    parser.add_argument("--min-elevation-deg", type=float, default=5.0)
    parser.add_argument("--max-range-m", type=float, default=0.0)
    parser.add_argument("--max-off-nadir-deg", type=float, default=180.0)
    parser.add_argument(
        "--sensor-pointing-mode",
        choices=("none", "nadir", "side-look", "target-track"),
        default="none",
    )
    parser.add_argument("--sensor-half-angle-deg", type=float, default=180.0)
    parser.add_argument("--side-look-angle-deg", type=float, default=0.0)
    parser.add_argument("--max-tle-age-days", type=float, default=14.0)
    parser.add_argument("--require-fresh-tle", action="store_true")
    parser.add_argument("--mission-report-jsonl", default="")
    parser.add_argument("--runtime-summary-json", default="")

    parser.add_argument("--reference-lat", type=float, default=22.591164)
    parser.add_argument("--reference-lon", type=float, default=113.975317)
    parser.add_argument("--reference-alt", type=float, default=0.0)
    parser.add_argument(
        "--display-mode",
        choices=("scaled-ned", "fixed-overhead", "subpoint-only", "global-track"),
        default="scaled-ned",
    )
    parser.add_argument("--horizontal-scale", type=float, default=0.001)
    parser.add_argument("--vertical-scale", type=float, default=0.001)
    parser.add_argument("--min-display-altitude", type=float, default=80.0)
    parser.add_argument("--fixed-display-altitude", type=float, default=300.0)
    parser.add_argument("--fixed-x", type=float, default=0.0)
    parser.add_argument("--fixed-y", type=float, default=0.0)
    parser.add_argument("--global-track-radius", type=float, default=80.0)
    parser.add_argument("--yaw-mode", choices=("course", "fixed"), default="course")
    parser.add_argument("--fixed-yaw-deg", type=float, default=0.0)

    parser.add_argument("--no-csv-loop", action="store_true")
    parser.add_argument("--mock-altitude-m", type=float, default=500000.0)
    parser.add_argument("--mock-radius-m", type=float, default=10000.0)
    parser.add_argument("--mock-period-s", type=float, default=120.0)
    return parser.parse_args(rospy.myargv()[1:])


def make_topic(namespace, vehicle):
    namespace = namespace.strip("/")
    return f"/{namespace}/{vehicle}/space_satellite_state"


def make_access_topic(namespace, vehicle, target):
    namespace = namespace.strip("/")
    return f"/{namespace}/{vehicle}/access/{target}"


def main():
    args = parse_args()
    rospy.init_node("space_mission_bridge", anonymous=True)

    if args.provider == "csv" and not args.csv:
        raise SystemExit("--provider csv requires --csv path")
    if args.dynamic_target_max_age <= 0.0:
        raise SystemExit("--dynamic-target-max-age must be positive")
    if args.auto_next_access and args.start_time:
        raise SystemExit("--auto-next-access and --start-time cannot be used together")
    if args.auto_next_access and args.provider not in ("tle", "orekit-tle"):
        raise SystemExit("--auto-next-access requires --provider tle or orekit-tle")
    if args.clock_source == "ros" and (args.auto_next_access or args.start_time):
        raise SystemExit("--clock-source ros gets scenario time from /clock; do not use --auto-next-access or --start-time")

    provider = bridge.create_provider(args)
    targets = [bridge.parse_target(value) for value in args.target]
    dynamic_targets = args.target_vehicle
    target_names = [target.name for target in targets] + [target.name for target in dynamic_targets]
    if len(target_names) != len(set(target_names)):
        raise SystemExit("Fixed and dynamic target names must be unique")
    scenario_start = bridge.parse_time(args.start_time) if args.start_time else None
    if args.auto_next_access:
        search_start = bridge._dt.datetime.now(bridge._dt.timezone.utc)
        reference_target = bridge.TargetSpec(
            name="ReferencePoint",
            latitude_deg=args.reference_lat,
            longitude_deg=args.reference_lon,
            altitude_m=args.reference_alt,
            kind="reference",
        )
        access_window = bridge.find_next_access_window(
            provider,
            reference_target,
            args,
            search_start,
            search_hours=args.access_search_hours,
            step_s=args.access_search_step_s,
        )
        if access_window is None:
            raise SystemExit(
                f"No access window found in the next {args.access_search_hours:.1f} hours"
            )
        rise_time, set_time = access_window
        scenario_start = rise_time - bridge._dt.timedelta(seconds=max(0.0, args.access_lead_s))
        rospy.loginfo(
            "Auto-selected access window: rise=%s set=%s scenario_start=%s clock_speed=%.1f",
            bridge.format_time(rise_time),
            bridge.format_time(set_time),
            bridge.format_time(scenario_start),
            args.clock_speed,
        )

    age_days = bridge.tle_age_days(provider, scenario_start)
    if age_days is not None:
        message = (
            f"TLE epoch={bridge.format_time(provider.epoch_utc)} "
            f"scenario_offset_days={age_days:.2f} limit_days={args.max_tle_age_days:.2f}"
        )
        if age_days > args.max_tle_age_days:
            if args.require_fresh_tle:
                raise SystemExit(message)
            rospy.logwarn(message)
        else:
            rospy.loginfo(message)

    recorder = RuntimeMissionRecorder(
        args.mission_report_jsonl,
        args.runtime_summary_json,
        {
            "provider": args.provider,
            "vehicle": args.vehicle,
            "tle": os.path.abspath(args.tle) if args.provider in ("tle", "orekit-tle") else "",
            "clock_speed": args.clock_speed,
            "clock_source": args.clock_source,
            "clock_topic": args.clock_topic,
            "rate_hz": args.rate,
            "min_elevation_deg": args.min_elevation_deg,
            "reference": {
                "latitude_deg": args.reference_lat,
                "longitude_deg": args.reference_lon,
                "altitude_m": args.reference_alt,
            },
        },
    )
    rospy.on_shutdown(recorder.close)
    wall_start = time.monotonic()
    publisher = rospy.Publisher(make_topic(args.namespace, args.vehicle), SpaceSatelliteState, queue_size=10)
    state_alias_publisher = rospy.Publisher(f"/{args.namespace.strip('/')}/{args.vehicle}/state", SpaceSatelliteState, queue_size=10)
    access_publishers = {
        target.name: rospy.Publisher(make_access_topic(args.namespace, args.vehicle, target.name), SpaceAccessState, queue_size=10)
        for target in targets + dynamic_targets
    }
    dynamic_lock = threading.RLock()
    dynamic_states = {}
    clock_lock = threading.RLock()
    clock_state = {"time_s": None}

    def dynamic_target_callback(message, target_spec):
        with dynamic_lock:
            first_state = target_spec.name not in dynamic_states
            dynamic_states[target_spec.name] = (message, time.monotonic())
        if first_state:
            rospy.loginfo(
                "Received first dynamic target GPS: target=%s topic=%s",
                target_spec.name,
                target_spec.topic,
            )

    dynamic_subscribers = [
        rospy.Subscriber(
            target.topic,
            NavSatFix,
            dynamic_target_callback,
            callback_args=target,
            queue_size=1,
        )
        for target in dynamic_targets
    ]

    def clock_callback(message):
        with clock_lock:
            first_state = clock_state["time_s"] is None
            clock_state["time_s"] = message.clock.to_sec()
        if first_state:
            rospy.loginfo("Received first unified scenario clock: %.9f", clock_state["time_s"])

    clock_subscriber = (
        rospy.Subscriber(args.clock_topic, Clock, clock_callback, queue_size=10)
        if args.clock_source == "ros" else None
    )

    client = None
    airsim_module = None
    if args.drive_laesim:
        airsim_module = bridge.import_airsim()
        client = airsim_module.SatelliteClient(ip=args.host, port=args.port)
        client.confirmConnection()
        client.enableApiControl(True, args.vehicle)
        client.armDisarm(True, args.vehicle)
        client.setSatelliteControls(airsim_module.SatelliteControls(), vehicle_name=args.vehicle)

    previous_real = None
    rate = rospy.Rate(max(0.001, args.rate))
    tick = 0
    try:
        while not rospy.is_shutdown():
            elapsed = time.monotonic() - wall_start
            if args.duration > 0.0 and elapsed >= args.duration:
                break
            if args.clock_source == "ros":
                with clock_lock:
                    clock_time_s = clock_state["time_s"]
                if clock_time_s is None:
                    time.sleep(0.05)
                    continue
                scenario_time = bridge._dt.datetime.fromtimestamp(
                    clock_time_s, tz=bridge._dt.timezone.utc
                )
            else:
                scenario_time = scenario_start + bridge._dt.timedelta(seconds=elapsed * args.clock_speed) if scenario_start else None
            sample = provider.sample(scenario_time)
            display = bridge.build_display_state(sample, args, previous_real)
            previous_real = bridge.DisplayState(0.0, 0.0, 0.0, display.yaw_rad, display.north_m, display.east_m, display.down_m)
            access_states = [bridge.compute_access(sample, target, args) for target in targets]
            now = time.monotonic()
            for target in dynamic_targets:
                with dynamic_lock:
                    dynamic_state = dynamic_states.get(target.name)
                if dynamic_state is None:
                    access_states.append(bridge.AccessState(
                        target_name=target.name,
                        target_kind=target.kind,
                        source="ros-global-gps",
                        valid=False,
                        access=False,
                        message=f"waiting for {target.topic}"))
                    continue

                gps, received_at = dynamic_state
                age_s = now - received_at
                values = (gps.latitude, gps.longitude, gps.altitude)
                if age_s > args.dynamic_target_max_age:
                    access_states.append(bridge.AccessState(
                        target_name=target.name,
                        target_kind=target.kind,
                        source="ros-global-gps",
                        valid=False,
                        access=False,
                        message=f"dynamic target GPS is stale ({age_s:.2f}s)"))
                    continue
                if gps.status.status == NavSatStatus.STATUS_NO_FIX or not all(math.isfinite(value) for value in values):
                    access_states.append(bridge.AccessState(
                        target_name=target.name,
                        target_kind=target.kind,
                        source="ros-global-gps",
                        valid=False,
                        access=False,
                        message="dynamic target GPS is invalid"))
                    continue

                live_target = bridge.TargetSpec(
                    name=target.name,
                    latitude_deg=gps.latitude,
                    longitude_deg=gps.longitude,
                    altitude_m=gps.altitude,
                    kind=target.kind,
                )
                access = bridge.compute_access(sample, live_target, args)
                access.source = "ros-global-gps"
                access_states.append(access)

            if client is not None:
                bridge.set_laesim_pose(client, args.vehicle, display, airsim_module)

            msg = SpaceSatelliteState()
            msg.header.stamp = rospy.Time.now()
            msg.header.frame_id = "laesim_ned"
            msg.vehicle_name = args.vehicle
            msg.satellite_name = sample.satellite_name
            msg.source = sample.source
            msg.scenario_time = sample.timestamp
            msg.latitude = sample.latitude_deg
            msg.longitude = sample.longitude_deg
            msg.altitude = sample.altitude_m
            msg.real_ned = Vector3(x=display.north_m, y=display.east_m, z=display.down_m)
            msg.display_pose = Pose()
            msg.display_pose.position.x = display.x
            msg.display_pose.position.y = display.y
            msg.display_pose.position.z = display.z
            msg.display_pose.orientation = ros_quaternion_from_yaw(display.yaw_rad)
            msg.horizontal_scale = args.horizontal_scale
            msg.vertical_scale = args.vertical_scale
            msg.valid = all(math.isfinite(v) for v in (
                msg.latitude, msg.longitude, msg.altitude,
                msg.real_ned.x, msg.real_ned.y, msg.real_ned.z,
                msg.display_pose.position.x, msg.display_pose.position.y, msg.display_pose.position.z))
            publisher.publish(msg)
            state_alias_publisher.publish(msg)

            for state in access_states:
                access_msg = SpaceAccessState()
                access_msg.header.stamp = msg.header.stamp
                access_msg.header.frame_id = "laesim_ned"
                access_msg.vehicle_name = args.vehicle
                access_msg.target_name = state.target_name
                access_msg.target_kind = state.target_kind
                access_msg.source = state.source
                access_msg.valid = state.valid
                access_msg.access = state.access
                access_msg.azimuth_deg = state.azimuth_deg
                access_msg.elevation_deg = state.elevation_deg
                access_msg.range_m = state.range_m
                access_msg.message = state.message
                access_publishers[state.target_name].publish(access_msg)

            recorder.record(sample, display, access_states)
            if tick % max(1, args.print_every) == 0:
                access_text = ", ".join(
                    f"{state.target_name}={'UP' if state.access and state.valid else 'DOWN'}"
                    for state in access_states
                ) or "no targets"
                rospy.loginfo(
                    "TLE state time=%s lat=%.4f lon=%.4f alt_km=%.1f display=(%.1f,%.1f,%.1f) %s",
                    sample.timestamp,
                    sample.latitude_deg,
                    sample.longitude_deg,
                    sample.altitude_m / 1000.0,
                    display.x,
                    display.y,
                    display.z,
                    access_text,
                )
            tick += 1
            if args.clock_source == "ros":
                time.sleep(1.0 / args.rate)
            else:
                rate.sleep()
    except rospy.ROSInterruptException:
        pass
    finally:
        recorder.close()
        if args.runtime_summary_json:
            rospy.loginfo("Wrote runtime summary: %s", os.path.abspath(args.runtime_summary_json))


if __name__ == "__main__":
    main()
