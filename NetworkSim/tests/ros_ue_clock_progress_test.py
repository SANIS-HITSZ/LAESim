#!/usr/bin/env python3
"""Fail when AirSim ROS messages repeat without advancing UE simulation time."""

from __future__ import annotations

import argparse
import json
import threading
import time

import rospy
from nav_msgs.msg import Odometry


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehicle", default="Satellite")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--topic", default="")
    return parser.parse_args(rospy.myargv()[1:])


def main():
    args = parse_args()
    if args.timeout <= 0.0:
        raise SystemExit("--timeout must be positive")
    topic = args.topic or f"/airsim_node/{args.vehicle}/odom_local_ned"
    rospy.init_node("laesim_ue_clock_progress_test", anonymous=True)
    lock = threading.Lock()
    first_stamp_ns = None
    latest_stamp_ns = None
    message_count = 0

    def callback(message):
        nonlocal first_stamp_ns, latest_stamp_ns, message_count
        stamp_ns = message.header.stamp.to_nsec()
        with lock:
            if first_stamp_ns is None:
                first_stamp_ns = stamp_ns
            latest_stamp_ns = stamp_ns
            message_count += 1

    subscriber = rospy.Subscriber(topic, Odometry, callback, queue_size=10)
    deadline = time.monotonic() + args.timeout
    while not rospy.is_shutdown() and time.monotonic() < deadline:
        with lock:
            progressed = (
                first_stamp_ns is not None
                and latest_stamp_ns is not None
                and latest_stamp_ns > first_stamp_ns
            )
        if progressed:
            break
        rospy.sleep(0.05)

    with lock:
        result = {
            "topic": topic,
            "message_count": message_count,
            "first_stamp_ns": first_stamp_ns,
            "latest_stamp_ns": latest_stamp_ns,
            "progressed": bool(
                first_stamp_ns is not None
                and latest_stamp_ns is not None
                and latest_stamp_ns > first_stamp_ns
            ),
        }
    subscriber.unregister()
    print(json.dumps(result, indent=2))
    if not result["progressed"]:
        print(
            "ERROR: UE simulation timestamp did not advance; click Play, ensure the game is not "
            "paused, and restart the AirSim ROS wrapper.",
            flush=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
