#!/usr/bin/env python3
"""Publish and visualize a real-time TLE constellation in LAESim."""

from __future__ import annotations

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
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceAccessState, SpaceSatelliteState


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MULTI_USE = os.path.join(ROOT, "Multi_use")
PYCLIENT = os.path.join(ROOT, "PythonClient")
NETWORK_PYTHON = os.path.join(ROOT, "NetworkSim", "python")
for path in (MULTI_USE, PYCLIENT, NETWORK_PYTHON):
    if path not in sys.path:
        sys.path.insert(0, path)

import space_mission_bridge as bridge
from satellite_selector import BestSatelliteSelector, SatelliteCandidate


@dataclass(frozen=True)
class SatelliteSpec:
    vehicle_name: str
    tle_path: str


@dataclass(frozen=True)
class DynamicTargetSpec:
    vehicle_name: str
    kind: str
    topic: str

    @property
    def name(self):
        return self.vehicle_name


def parse_satellite(value):
    parts = value.split("=", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise argparse.ArgumentTypeError("Satellite must use VEHICLE=TLE_PATH")
    return SatelliteSpec(parts[0].strip(), os.path.abspath(os.path.expanduser(parts[1].strip())))


def parse_assignment(value):
    parts = value.split("=", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise argparse.ArgumentTypeError("Value must use VEHICLE=VALUE")
    return parts[0].strip(), parts[1].strip()


def parse_dynamic_target(value):
    parts = value.split(":", 1)
    vehicle_name = parts[0].strip()
    if not vehicle_name:
        raise argparse.ArgumentTypeError("Dynamic target must specify a vehicle name")
    kind = parts[1].strip() if len(parts) == 2 and parts[1].strip() else "vehicle"
    return DynamicTargetSpec(vehicle_name, kind, f"/airsim_node/{vehicle_name}/global_gps")


def make_topic(namespace, vehicle, suffix):
    return f"/{namespace.strip('/')}/{vehicle}/{suffix}"


def make_selection_topic(namespace, target):
    return f"/{namespace.strip('/')}/selection/{target}"


def ros_quaternion_from_yaw(yaw_rad):
    x, y, z, w = bridge.yaw_to_quaternion_values(yaw_rad)
    return Quaternion(x=x, y=y, z=z, w=w)


class ConstellationRecorder:
    def __init__(self, jsonl_path, summary_path, metadata, selector):
        self.jsonl_path = os.path.abspath(jsonl_path) if jsonl_path else ""
        self.summary_path = os.path.abspath(summary_path) if summary_path else ""
        self.metadata = metadata
        self.selector = selector
        self.sample_count = 0
        self.first_time = ""
        self.last_time = ""
        self.last_elapsed_s = 0.0
        self.events = []
        self.closed = False
        for path in (self.jsonl_path, self.summary_path):
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.jsonl_path:
            open(self.jsonl_path, "w", encoding="utf-8").close()
        if self.summary_path and os.path.isfile(self.summary_path):
            os.remove(self.summary_path)

    def record(self, scenario_time, elapsed_s, satellites, selections, isl_links):
        if self.closed:
            return
        self.sample_count += 1
        self.first_time = self.first_time or scenario_time
        self.last_time = scenario_time
        self.last_elapsed_s = elapsed_s
        for selection in selections:
            if selection["changed"]:
                self.events.append({
                    "scenario_time": scenario_time,
                    "target": selection["target"],
                    "previous_satellite": selection["previous_satellite"],
                    "selected_satellite": selection["selected_satellite"],
                    "outage": selection["outage"],
                    "interruption_s": selection["interruption_s"],
                })
        bridge.write_jsonl(self.jsonl_path, {
            "scenario_time": scenario_time,
            "elapsed_s": elapsed_s,
            "satellites": satellites,
            "selections": selections,
            "isl_links": isl_links,
        })

    def close(self):
        if self.closed:
            return
        self.closed = True
        if not self.summary_path:
            return
        summary = {
            "metadata": self.metadata,
            "scenario_start": self.first_time,
            "scenario_stop": self.last_time,
            "sample_count": self.sample_count,
            "selection_statistics": self.selector.summary(self.last_elapsed_s),
            "selection_events": self.events,
        }
        with open(self.summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False, allow_nan=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Publish multiple TLE satellites, select the best visible satellite, and optionally drive LAESim."
    )
    parser.add_argument(
        "--satellite", action="append", required=True, type=parse_satellite,
        metavar="VEHICLE=TLE_PATH", help="Map one LAESim vehicle to one TLE file. Repeat for each satellite."
    )
    parser.add_argument(
        "--satellite-name", action="append", default=[], type=parse_assignment,
        metavar="VEHICLE=TLE_NAME", help="Select a named entry when a TLE file contains multiple satellites."
    )
    parser.add_argument("--provider", choices=("tle", "orekit-tle"), default="tle")
    parser.add_argument("--orekit-data", default="")
    parser.add_argument("--namespace", default="/space")
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--start-time", default="")
    parser.add_argument("--clock-speed", type=float, default=1.0)
    parser.add_argument("--clock-source", choices=("wall", "ros"), default="wall")
    parser.add_argument("--clock-topic", default="/clock")
    parser.add_argument("--auto-next-access", action="store_true")
    parser.add_argument("--access-search-hours", type=float, default=48.0)
    parser.add_argument("--access-search-step-s", type=float, default=30.0)
    parser.add_argument("--access-lead-s", type=float, default=300.0)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--target-vehicle", action="append", default=[], type=parse_dynamic_target)
    parser.add_argument("--dynamic-target-max-age", type=float, default=2.0)
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
    parser.add_argument("--selection-hysteresis-deg", type=float, default=2.0)
    parser.add_argument("--selection-min-hold-s", type=float, default=10.0)
    parser.add_argument("--publish-isl", action="store_true")
    parser.add_argument("--max-isl-range-m", type=float, default=5000000.0)
    parser.add_argument("--max-tle-age-days", type=float, default=14.0)
    parser.add_argument("--require-fresh-tle", action="store_true")
    parser.add_argument("--mission-report-jsonl", default="")
    parser.add_argument("--runtime-summary-json", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=bridge.RPCLIB_PORT_SATELLITE)
    parser.add_argument("--rpc-timeout", type=float, default=5.0)
    parser.add_argument("--drive-laesim", action="store_true")
    parser.add_argument(
        "--laesim-pose-rate",
        type=float,
        default=0.0,
        help="Maximum UE pose updates per second; 0 updates every mission frame.",
    )

    parser.add_argument("--reference-lat", type=float, default=22.591164)
    parser.add_argument("--reference-lon", type=float, default=113.975317)
    parser.add_argument("--reference-alt", type=float, default=0.0)
    parser.add_argument(
        "--display-mode", choices=("scaled-ned", "fixed-overhead", "subpoint-only", "global-track"),
        default="global-track"
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
    return parser.parse_args(rospy.myargv()[1:])


def create_provider(args, spec, satellite_names):
    if not os.path.isfile(spec.tle_path):
        raise SystemExit(f"TLE file not found for {spec.vehicle_name}: {spec.tle_path}")
    satellite_name = satellite_names.get(spec.vehicle_name, "")
    if args.provider == "orekit-tle":
        return bridge.OrekitTleProvider(spec.tle_path, satellite_name, 0, args.orekit_data)
    return bridge.TleProvider(spec.tle_path, satellite_name, 0)


def invalid_access(target, source, message):
    return bridge.AccessState(
        target_name=target.name,
        target_kind=target.kind,
        source=source,
        valid=False,
        access=False,
        message=message,
    )


def main():
    args = parse_args()
    rospy.init_node("space_constellation_bridge", anonymous=True)
    if args.rate <= 0.0 or args.clock_speed <= 0.0:
        raise SystemExit("--rate and --clock-speed must be positive")
    if args.rpc_timeout <= 0.0:
        raise SystemExit("--rpc-timeout must be positive")
    if args.laesim_pose_rate < 0.0:
        raise SystemExit("--laesim-pose-rate must be non-negative")
    if args.dynamic_target_max_age <= 0.0:
        raise SystemExit("--dynamic-target-max-age must be positive")
    if args.max_isl_range_m <= 0.0:
        raise SystemExit("--max-isl-range-m must be positive")
    if args.auto_next_access and args.start_time:
        raise SystemExit("--auto-next-access and --start-time cannot be used together")
    if args.clock_source == "ros" and (args.auto_next_access or args.start_time):
        raise SystemExit("--clock-source ros gets scenario time from /clock; do not use --auto-next-access or --start-time")

    vehicle_names = [spec.vehicle_name for spec in args.satellite]
    if len(vehicle_names) != len(set(vehicle_names)):
        raise SystemExit("Each --satellite vehicle name must be unique")
    satellite_names = dict(args.satellite_name)
    unknown_names = sorted(set(satellite_names) - set(vehicle_names))
    if unknown_names:
        raise SystemExit("--satellite-name references unknown vehicles: " + ", ".join(unknown_names))
    providers = {
        spec.vehicle_name: create_provider(args, spec, satellite_names)
        for spec in args.satellite
    }

    fixed_targets = [bridge.parse_target(value) for value in args.target]
    dynamic_targets = args.target_vehicle
    target_names = [target.name for target in fixed_targets] + [target.name for target in dynamic_targets]
    if not target_names:
        raise SystemExit("At least one --target or --target-vehicle is required")
    if len(target_names) != len(set(target_names)):
        raise SystemExit("Fixed and dynamic target names must be unique")

    scenario_start = bridge.parse_time(args.start_time) if args.start_time else None
    if args.auto_next_access:
        search_start = bridge._dt.datetime.now(bridge._dt.timezone.utc)
        reference_target = bridge.TargetSpec(
            "ReferencePoint", args.reference_lat, args.reference_lon, args.reference_alt, "reference"
        )
        windows = []
        for vehicle_name, provider in providers.items():
            window = bridge.find_next_access_window(
                provider, reference_target, args, search_start,
                search_hours=args.access_search_hours, step_s=args.access_search_step_s,
            )
            if window is not None:
                windows.append((window[0], window[1], vehicle_name))
        if not windows:
            raise SystemExit(f"No constellation access in the next {args.access_search_hours:.1f} hours")
        rise_time, set_time, first_vehicle = min(windows, key=lambda item: item[0])
        scenario_start = rise_time - bridge._dt.timedelta(seconds=max(0.0, args.access_lead_s))
        rospy.loginfo(
            "Auto-selected first access: vehicle=%s rise=%s set=%s scenario_start=%s",
            first_vehicle, bridge.format_time(rise_time), bridge.format_time(set_time),
            bridge.format_time(scenario_start),
        )

    for vehicle_name, provider in providers.items():
        age_days = bridge.tle_age_days(provider, scenario_start)
        if age_days is None:
            continue
        message = (
            f"{vehicle_name}: TLE epoch={bridge.format_time(provider.epoch_utc)} "
            f"scenario_offset_days={age_days:.2f} limit_days={args.max_tle_age_days:.2f}"
        )
        if age_days > args.max_tle_age_days:
            if args.require_fresh_tle:
                raise SystemExit(message)
            rospy.logwarn(message)
        else:
            rospy.loginfo(message)

    state_publishers = {
        vehicle: (
            rospy.Publisher(make_topic(args.namespace, vehicle, "space_satellite_state"), SpaceSatelliteState, queue_size=10),
            rospy.Publisher(make_topic(args.namespace, vehicle, "state"), SpaceSatelliteState, queue_size=10),
        )
        for vehicle in vehicle_names
    }
    access_publishers = {
        (vehicle, target): rospy.Publisher(
            make_topic(args.namespace, vehicle, f"access/{target}"), SpaceAccessState, queue_size=10
        )
        for vehicle in vehicle_names for target in target_names
    }
    isl_pairs = [
        (vehicle_names[left], vehicle_names[right])
        for left in range(len(vehicle_names))
        for right in range(left + 1, len(vehicle_names))
    ] if args.publish_isl else []
    isl_publishers = {
        pair: rospy.Publisher(
            make_topic(args.namespace, pair[0], f"access/{pair[1]}"),
            SpaceAccessState,
            queue_size=10,
        )
        for pair in isl_pairs
    }
    selection_publishers = {
        target: rospy.Publisher(make_selection_topic(args.namespace, target), String, queue_size=10, latch=True)
        for target in target_names
    }
    constellation_publisher = rospy.Publisher(
        f"/{args.namespace.strip('/')}/constellation/state", String, queue_size=10, latch=True
    )

    dynamic_lock = threading.RLock()
    dynamic_states = {}
    clock_lock = threading.RLock()
    clock_state = {"time_s": None, "initial_time_s": None}

    def dynamic_target_callback(message, target_spec):
        with dynamic_lock:
            first_state = target_spec.name not in dynamic_states
            dynamic_states[target_spec.name] = (message, time.monotonic())
        if first_state:
            rospy.loginfo("Received first target GPS: target=%s topic=%s", target_spec.name, target_spec.topic)

    dynamic_subscribers = [
        rospy.Subscriber(target.topic, NavSatFix, dynamic_target_callback, callback_args=target, queue_size=1)
        for target in dynamic_targets
    ]

    def clock_callback(message):
        value = message.clock.to_sec()
        with clock_lock:
            if clock_state["initial_time_s"] is None:
                clock_state["initial_time_s"] = value
                rospy.loginfo("Received first unified scenario clock: %.9f", value)
            clock_state["time_s"] = value

    clock_subscriber = (
        rospy.Subscriber(args.clock_topic, Clock, clock_callback, queue_size=10)
        if args.clock_source == "ros" else None
    )

    client = None
    airsim_module = None
    if args.drive_laesim:
        airsim_module = bridge.import_airsim()
        client = airsim_module.SatelliteClient(
            ip=args.host, port=args.port, timeout_value=args.rpc_timeout
        )
        client.confirmConnection()
        for vehicle in vehicle_names:
            client.enableApiControl(True, vehicle)
            client.armDisarm(True, vehicle)
            client.setSatelliteControls(airsim_module.SatelliteControls(), vehicle_name=vehicle)

    selector = BestSatelliteSelector(args.selection_hysteresis_deg, args.selection_min_hold_s)
    recorder = ConstellationRecorder(
        args.mission_report_jsonl,
        args.runtime_summary_json,
        {
            "provider": args.provider,
            "vehicles": vehicle_names,
            "tle_files": {spec.vehicle_name: spec.tle_path for spec in args.satellite},
            "targets": target_names,
            "clock_speed": args.clock_speed,
            "clock_source": args.clock_source,
            "clock_topic": args.clock_topic,
            "rate_hz": args.rate,
            "laesim_pose_rate_hz": args.laesim_pose_rate,
            "min_elevation_deg": args.min_elevation_deg,
            "selection_hysteresis_deg": args.selection_hysteresis_deg,
            "selection_min_hold_s": args.selection_min_hold_s,
            "publish_isl": args.publish_isl,
            "max_isl_range_m": args.max_isl_range_m,
        },
        selector,
    )
    previous_display = {vehicle: None for vehicle in vehicle_names}
    wall_start = time.monotonic()
    last_pose_update_wall = float("-inf")
    rate = rospy.Rate(args.rate)
    tick = 0
    try:
        while not rospy.is_shutdown():
            wall_elapsed_s = time.monotonic() - wall_start
            if args.duration > 0.0 and wall_elapsed_s >= args.duration:
                break
            if args.clock_source == "ros":
                with clock_lock:
                    clock_time_s = clock_state["time_s"]
                    initial_clock_s = clock_state["initial_time_s"]
                if clock_time_s is None:
                    time.sleep(0.05)
                    continue
                scenario_elapsed_s = max(0.0, clock_time_s - initial_clock_s)
                scenario_time = bridge._dt.datetime.fromtimestamp(
                    clock_time_s, tz=bridge._dt.timezone.utc
                )
            else:
                scenario_elapsed_s = wall_elapsed_s * args.clock_speed
                scenario_time = (
                    scenario_start + bridge._dt.timedelta(seconds=scenario_elapsed_s)
                    if scenario_start else bridge._dt.datetime.now(bridge._dt.timezone.utc)
                )
            now = time.monotonic()
            drive_pose_this_tick = client is not None and (
                args.laesim_pose_rate == 0.0
                or now - last_pose_update_wall >= 1.0 / args.laesim_pose_rate
            )
            live_targets = {target.name: target for target in fixed_targets}
            invalid_targets = {}
            for target in dynamic_targets:
                with dynamic_lock:
                    dynamic_state = dynamic_states.get(target.name)
                if dynamic_state is None:
                    invalid_targets[target.name] = invalid_access(target, "ros-global-gps", f"waiting for {target.topic}")
                    continue
                gps, received_at = dynamic_state
                age_s = now - received_at
                values = (gps.latitude, gps.longitude, gps.altitude)
                if age_s > args.dynamic_target_max_age:
                    invalid_targets[target.name] = invalid_access(
                        target, "ros-global-gps", f"dynamic target GPS is stale ({age_s:.2f}s)"
                    )
                elif gps.status.status == NavSatStatus.STATUS_NO_FIX or not all(math.isfinite(v) for v in values):
                    invalid_targets[target.name] = invalid_access(target, "ros-global-gps", "dynamic target GPS is invalid")
                else:
                    live_targets[target.name] = bridge.TargetSpec(
                        target.name, gps.latitude, gps.longitude, gps.altitude, target.kind
                    )

            satellite_records = []
            samples_by_vehicle = {}
            access_by_target = {target: [] for target in target_names}
            for vehicle, provider in providers.items():
                sample = provider.sample(scenario_time)
                samples_by_vehicle[vehicle] = sample
                display = bridge.build_display_state(sample, args, previous_display[vehicle])
                previous_display[vehicle] = bridge.DisplayState(
                    0.0, 0.0, 0.0, display.yaw_rad, display.north_m, display.east_m, display.down_m
                )
                if drive_pose_this_tick:
                    bridge.set_laesim_pose(client, vehicle, display, airsim_module)

                stamp = rospy.Time.now()
                state_msg = SpaceSatelliteState()
                state_msg.header.stamp = stamp
                state_msg.header.frame_id = "laesim_ned"
                state_msg.vehicle_name = vehicle
                state_msg.satellite_name = sample.satellite_name
                state_msg.source = sample.source
                state_msg.scenario_time = sample.timestamp
                state_msg.latitude = sample.latitude_deg
                state_msg.longitude = sample.longitude_deg
                state_msg.altitude = sample.altitude_m
                state_msg.real_ned = Vector3(x=display.north_m, y=display.east_m, z=display.down_m)
                state_msg.display_pose = Pose()
                state_msg.display_pose.position.x = display.x
                state_msg.display_pose.position.y = display.y
                state_msg.display_pose.position.z = display.z
                state_msg.display_pose.orientation = ros_quaternion_from_yaw(display.yaw_rad)
                state_msg.horizontal_scale = args.horizontal_scale
                state_msg.vertical_scale = args.vertical_scale
                state_msg.valid = all(math.isfinite(value) for value in (
                    sample.latitude_deg, sample.longitude_deg, sample.altitude_m,
                    display.north_m, display.east_m, display.down_m, display.x, display.y, display.z,
                ))
                state_publishers[vehicle][0].publish(state_msg)
                state_publishers[vehicle][1].publish(state_msg)

                access_records = []
                for target_name in target_names:
                    if target_name in invalid_targets:
                        access_state = invalid_targets[target_name]
                    else:
                        access_state = bridge.compute_access(sample, live_targets[target_name], args)
                        if target_name not in {target.name for target in fixed_targets}:
                            access_state.source = "ros-global-gps"
                    access_msg = SpaceAccessState()
                    access_msg.header.stamp = stamp
                    access_msg.header.frame_id = "laesim_ned"
                    access_msg.vehicle_name = vehicle
                    access_msg.target_name = access_state.target_name
                    access_msg.target_kind = access_state.target_kind
                    access_msg.source = access_state.source
                    access_msg.valid = access_state.valid
                    access_msg.access = access_state.access
                    access_msg.azimuth_deg = access_state.azimuth_deg
                    access_msg.elevation_deg = access_state.elevation_deg
                    access_msg.range_m = access_state.range_m
                    access_msg.message = access_state.message
                    access_publishers[(vehicle, target_name)].publish(access_msg)
                    access_by_target[target_name].append((vehicle, access_state))
                    access_records.append(asdict(access_state))

                satellite_records.append({
                    "vehicle_name": vehicle,
                    "sample": asdict(sample),
                    "display": asdict(display),
                    "access": access_records,
                })

            if drive_pose_this_tick:
                last_pose_update_wall = now

            isl_records = []
            for source, destination in isl_pairs:
                source_sample = samples_by_vehicle[source]
                destination_sample = samples_by_vehicle[destination]
                source_ecef = bridge.geodetic_to_ecef(
                    source_sample.latitude_deg,
                    source_sample.longitude_deg,
                    source_sample.altitude_m,
                )
                destination_ecef = bridge.geodetic_to_ecef(
                    destination_sample.latitude_deg,
                    destination_sample.longitude_deg,
                    destination_sample.altitude_m,
                )
                delta = [right - left for left, right in zip(source_ecef, destination_ecef)]
                range_m = math.sqrt(sum(value * value for value in delta))
                valid = math.isfinite(range_m) and range_m > 0.0
                access = valid and range_m <= args.max_isl_range_m
                isl_msg = SpaceAccessState()
                isl_msg.header.stamp = rospy.Time.now()
                isl_msg.header.frame_id = "earth_ecef"
                isl_msg.vehicle_name = source
                isl_msg.target_name = destination
                isl_msg.target_kind = "satellite"
                isl_msg.source = "constellation-isl"
                isl_msg.valid = valid
                isl_msg.access = access
                isl_msg.azimuth_deg = float("nan")
                isl_msg.elevation_deg = float("nan")
                isl_msg.range_m = range_m
                isl_msg.message = "" if access else (
                    "isl_range_exceeded" if valid else "invalid_isl_geometry"
                )
                isl_publishers[(source, destination)].publish(isl_msg)
                isl_records.append({
                    "source": source,
                    "destination": destination,
                    "valid": valid,
                    "access": access,
                    "range_m": range_m,
                    "max_range_m": args.max_isl_range_m,
                })

            selection_records = []
            for target_name, states in access_by_target.items():
                candidates = [
                    SatelliteCandidate(vehicle, state.elevation_deg, state.range_m)
                    for vehicle, state in states if state.valid and state.access
                ]
                result = selector.update(target_name, candidates, scenario_elapsed_s)
                selection_record = {
                    "scenario_time": bridge.format_time(scenario_time),
                    "target": target_name,
                    "selected_satellite": result.selected_satellite,
                    "previous_satellite": result.previous_satellite,
                    "changed": result.changed,
                    "outage": result.outage,
                    "handover_count": result.handover_count,
                    "acquisition_count": result.acquisition_count,
                    "interruption_s": result.interruption_s,
                    "candidates": [asdict(candidate) for candidate in result.candidates],
                }
                selection_publishers[target_name].publish(String(
                    data=json.dumps(selection_record, separators=(",", ":"), allow_nan=True)
                ))
                selection_records.append(selection_record)
                if result.changed:
                    rospy.loginfo(
                        "Selection changed: target=%s previous=%s selected=%s interruption_s=%.3f handovers=%d",
                        target_name, result.previous_satellite or "NONE",
                        result.selected_satellite or "NONE", result.interruption_s, result.handover_count,
                    )

            constellation_state = {
                "scenario_time": bridge.format_time(scenario_time),
                "satellite_count": len(vehicle_names),
                "target_count": len(target_names),
                "isl_link_count": len(isl_records),
                "isl_up_count": sum(1 for item in isl_records if item["access"]),
                "selections": {
                    item["target"]: item["selected_satellite"] for item in selection_records
                },
            }
            constellation_publisher.publish(String(
                data=json.dumps(constellation_state, separators=(",", ":"))
            ))
            recorder.record(
                constellation_state["scenario_time"], scenario_elapsed_s,
                satellite_records, selection_records, isl_records,
            )

            if tick % max(1, args.print_every) == 0:
                selection_text = ", ".join(
                    f"{item['target']}={item['selected_satellite'] or 'OUTAGE'}"
                    for item in selection_records
                )
                rospy.loginfo(
                    "Constellation time=%s satellites=%d %s",
                    constellation_state["scenario_time"], len(vehicle_names), selection_text,
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
            rospy.loginfo("Wrote constellation summary: %s", os.path.abspath(args.runtime_summary_json))


if __name__ == "__main__":
    main()
