#!/usr/bin/env python3
"""Draw satellite subpoints, coverage footprints, and selected links in UE."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

import rospy
from nav_msgs.msg import Odometry
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceSatelliteState


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PYCLIENT = os.path.join(ROOT, "PythonClient")
NETWORK_PYTHON = os.path.join(ROOT, "NetworkSim", "python")
for path in (PYCLIENT, NETWORK_PYTHON):
    if path not in sys.path:
        sys.path.insert(0, path)

import airsim
from space_visualization import (
    VehicleOrigin,
    circle_points,
    load_vehicle_origins,
    projected_coverage_radius,
    to_global_ned,
)


SATELLITE_COLORS = (
    [0.15, 0.75, 1.0, 1.0],
    [1.0, 0.78, 0.12, 1.0],
    [0.75, 0.35, 1.0, 1.0],
    [0.25, 1.0, 0.55, 1.0],
)
UP_COLOR = [0.1, 1.0, 0.25, 1.0]
DOWN_COLOR = [1.0, 0.15, 0.1, 1.0]
LABEL_COLOR = [1.0, 1.0, 1.0, 1.0]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Visualize LAESim satellite subpoints, footprints, and selected links in UE."
    )
    parser.add_argument("--satellite", action="append", default=[])
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--namespace", default="/space")
    parser.add_argument("--settings", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=41451)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--surface-z", type=float, default=0.0)
    parser.add_argument("--global-track-radius", type=float, default=80.0)
    parser.add_argument("--min-elevation-deg", type=float, default=5.0)
    parser.add_argument("--coverage-segments", type=int, default=32)
    parser.add_argument("--line-thickness", type=float, default=4.0)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--constellation-timeout", type=float, default=10.0)
    return parser.parse_args(rospy.myargv()[1:])


def vector(xyz):
    return airsim.Vector3r(*xyz)


def midpoint(left, right):
    return tuple((a + b) * 0.5 for a, b in zip(left, right))


def main():
    args = parse_args()
    if args.rate <= 0.0 or args.timeout <= 0.0 or args.constellation_timeout <= 0.0:
        raise SystemExit("--rate, --timeout, and --constellation-timeout must be positive")
    if args.max_consecutive_errors <= 0:
        raise SystemExit("--max-consecutive-errors must be positive")
    if args.coverage_segments < 8:
        raise SystemExit("--coverage-segments must be at least 8")
    satellites = args.satellite or ["Satellite"]
    targets = args.target or ["Car"]
    origins = load_vehicle_origins(os.path.abspath(os.path.expanduser(args.settings)))

    rospy.init_node("laesim_space_mission_visualizer", anonymous=True)
    lock = threading.RLock()
    states = {}
    selections = {}
    target_poses = {}
    constellation_last_received = {"wall_time": None}

    def state_callback(message, vehicle):
        with lock:
            states[vehicle] = message

    def selection_callback(message, target):
        try:
            value = json.loads(message.data)
        except json.JSONDecodeError as error:
            rospy.logwarn_throttle(5.0, "Invalid selection JSON for %s: %s", target, error)
            return
        with lock:
            selections[target] = value

    def target_pose_callback(message, target):
        position = message.pose.pose.position
        with lock:
            target_poses[target] = (position.x, position.y, position.z)

    def constellation_callback(_message):
        with lock:
            constellation_last_received["wall_time"] = time.monotonic()

    subscribers = []
    namespace = args.namespace.strip("/")
    subscribers.append(rospy.Subscriber(
        f"/{namespace}/constellation/state",
        String,
        constellation_callback,
        queue_size=1,
    ))
    for satellite in satellites:
        subscribers.append(rospy.Subscriber(
            f"/{namespace}/{satellite}/state",
            SpaceSatelliteState,
            state_callback,
            callback_args=satellite,
            queue_size=1,
        ))
    for target in targets:
        subscribers.append(rospy.Subscriber(
            f"/{namespace}/selection/{target}",
            String,
            selection_callback,
            callback_args=target,
            queue_size=1,
        ))
        subscribers.append(rospy.Subscriber(
            f"/airsim_node/{target}/odom_local_ned",
            Odometry,
            target_pose_callback,
            callback_args=target,
            queue_size=1,
        ))
    status_publisher = rospy.Publisher(
        f"/{namespace}/visualization/status", String, queue_size=1, latch=True
    )

    client = airsim.VehicleClient(ip=args.host, port=args.port, timeout_value=args.timeout)
    client.confirmConnection()
    marker_duration = max(0.75, 2.5 / args.rate)
    rate = rospy.Rate(args.rate)
    rospy.loginfo(
        "Space visualizer ready: satellites=%s targets=%s settings=%s",
        ",".join(satellites), ",".join(targets), args.settings,
    )
    frame_count = 0
    consecutive_errors = 0
    started_at = time.monotonic()

    while not rospy.is_shutdown():
        with lock:
            current_states = dict(states)
            current_selections = dict(selections)
            current_target_poses = dict(target_poses)
            last_constellation_at = constellation_last_received["wall_time"]
        reference_time = last_constellation_at if last_constellation_at is not None else started_at
        if time.monotonic() - reference_time > args.constellation_timeout:
            message = (
                "constellation state stopped; exiting UE visualizer to avoid stale RPC traffic"
            )
            status_publisher.publish(String(data=json.dumps({
                "frame_count": frame_count,
                "satellite_count": len(current_states),
                "target_count": len(current_selections),
                "target_pose_count": len(current_target_poses),
                "up_link_count": 0,
                "down_target_count": 0,
                "consecutive_error_count": consecutive_errors,
                "last_error": message,
            }, separators=(",", ":"))))
            rospy.logerr(message)
            return
        try:
            satellite_positions = {}
            satellite_points = []
            subpoint_points = []
            vertical_lines = []
            satellite_labels = []
            satellite_label_positions = []
            footprints = []
            for index, satellite in enumerate(satellites):
                state = current_states.get(satellite)
                if state is None or not state.valid:
                    continue
                origin = origins.get(satellite, VehicleOrigin())
                local = state.display_pose.position
                position = to_global_ned((local.x, local.y, local.z), origin)
                subpoint = (position[0], position[1], args.surface_z)
                satellite_positions[satellite] = position
                color = SATELLITE_COLORS[index % len(SATELLITE_COLORS)]
                satellite_points.append(vector(position))
                subpoint_points.append(vector(subpoint))
                vertical_lines.extend((vector(position), vector(subpoint)))
                satellite_labels.append(satellite)
                satellite_label_positions.append(vector(position))
                footprint_radius = projected_coverage_radius(
                    args.global_track_radius, state.altitude, args.min_elevation_deg
                )
                footprints.append((color, [vector(point) for point in circle_points(
                    subpoint[0], subpoint[1], subpoint[2], footprint_radius,
                    args.coverage_segments,
                )]))

            if satellite_points:
                client.simPlotPoints(
                    satellite_points, SATELLITE_COLORS[0], 16.0, marker_duration, False
                )
                client.simPlotPoints(
                    subpoint_points, SATELLITE_COLORS[0], 12.0, marker_duration, False
                )
                client.simPlotLineList(
                    vertical_lines, SATELLITE_COLORS[0],
                    args.line_thickness, marker_duration, False,
                )
                client.simPlotStrings(
                    satellite_labels, satellite_label_positions,
                    1.5, LABEL_COLOR, marker_duration,
                )
            for color, footprint in footprints:
                client.simPlotLineStrip(
                    footprint, color, max(1.0, args.line_thickness * 0.5), marker_duration, False
                )

            up_link_count = 0
            down_target_count = 0
            up_lines = []
            up_labels = []
            up_label_positions = []
            down_positions = []
            down_labels = []
            for target in targets:
                selection = current_selections.get(target)
                local_pose = current_target_poses.get(target)
                if selection is None or local_pose is None:
                    continue
                target_position = to_global_ned(
                    local_pose,
                    origins.get(target, VehicleOrigin()),
                )
                selected = selection.get("selected_satellite") or ""
                if selected and selected in satellite_positions and not selection.get("outage", False):
                    up_link_count += 1
                    satellite_position = satellite_positions[selected]
                    up_lines.extend((vector(satellite_position), vector(target_position)))
                    up_labels.append(f"{selected} -> {target} UP")
                    up_label_positions.append(vector(midpoint(satellite_position, target_position)))
                else:
                    down_target_count += 1
                    down_positions.append(vector(target_position))
                    down_labels.append(f"{target} DOWN")

            if up_lines:
                client.simPlotLineList(
                    up_lines, UP_COLOR, args.line_thickness + 1.0, marker_duration, False
                )
                client.simPlotStrings(
                    up_labels, up_label_positions, 1.5, UP_COLOR, marker_duration
                )
            if down_positions:
                client.simPlotPoints(
                    down_positions, DOWN_COLOR, 14.0, marker_duration, False
                )
                client.simPlotStrings(
                    down_labels, down_positions, 1.5, DOWN_COLOR, marker_duration
                )
            frame_count += 1
            consecutive_errors = 0
            status_publisher.publish(String(data=json.dumps({
                "frame_count": frame_count,
                "satellite_count": len(satellite_positions),
                "target_count": len(current_selections),
                "target_pose_count": len(current_target_poses),
                "up_link_count": up_link_count,
                "down_target_count": down_target_count,
                "consecutive_error_count": consecutive_errors,
                "last_error": "",
            }, separators=(",", ":"))))
        except Exception as error:
            consecutive_errors += 1
            status_publisher.publish(String(data=json.dumps({
                "frame_count": frame_count,
                "satellite_count": len(current_states),
                "target_count": len(current_selections),
                "target_pose_count": len(current_target_poses),
                "up_link_count": 0,
                "down_target_count": 0,
                "consecutive_error_count": consecutive_errors,
                "last_error": str(error),
            }, separators=(",", ":"))))
            rospy.logerr_throttle(
                5.0,
                "UE visualization RPC failed; confirm UE is in Play and not paused: %s",
                error,
            )
            if consecutive_errors >= args.max_consecutive_errors:
                rospy.logerr(
                    "UE visualizer reached %d consecutive RPC failures; exiting",
                    consecutive_errors,
                )
                return
        rate.sleep()


if __name__ == "__main__":
    main()
