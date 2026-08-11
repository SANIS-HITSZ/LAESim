#!/usr/bin/env python3
"""Controllable /clock publisher for deterministic LAESim mission runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import rospy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
NETWORK_PYTHON = os.path.join(ROOT, "NetworkSim", "python")
MULTI_USE = os.path.join(ROOT, "Multi_use")
for path in (NETWORK_PYTHON, MULTI_USE):
    if path not in sys.path:
        sys.path.insert(0, path)

from unified_clock import DeterministicClock
import space_mission_bridge as bridge


def parse_args():
    parser = argparse.ArgumentParser(description="Publish a controllable LAESim scenario /clock.")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--publish-rate", type=float, default=20.0)
    parser.add_argument("--paused", action="store_true")
    parser.add_argument("--clock-topic", default="/clock")
    parser.add_argument("--control-topic", default="/space_clock/control")
    parser.add_argument("--status-topic", default="/space_clock/status")
    return parser.parse_args(rospy.myargv()[1:])


def main():
    args = parse_args()
    if args.rate <= 0.0 or args.publish_rate <= 0.0:
        raise SystemExit("--rate and --publish-rate must be positive")
    start = bridge.parse_time(args.start_time) if args.start_time else dt.datetime.now(dt.timezone.utc)
    start_s = start.timestamp()
    rospy.init_node("laesim_space_sim_clock", anonymous=False)
    clock = DeterministicClock(start_s, args.rate, args.paused, time.monotonic())
    clock_publisher = rospy.Publisher(args.clock_topic, Clock, queue_size=10, latch=True)
    status_publisher = rospy.Publisher(args.status_topic, String, queue_size=10, latch=True)

    def publish_status():
        status_publisher.publish(String(
            data=json.dumps(clock.status_dict(), separators=(",", ":"))
        ))

    def control_callback(message):
        try:
            data = json.loads(message.data)
            command = str(data["command"])
            values = dict(data)
            values.pop("command", None)
            if command == "set_time":
                scenario_time = bridge.parse_time(str(values.pop("scenario_time")))
                values["scenario_time_s"] = scenario_time.timestamp()
            clock.command(command, time.monotonic(), **values)
            publish_status()
            rospy.loginfo("Clock command applied: %s", clock.status_dict())
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            rospy.logerr("Rejected clock command: %s", error)

    rospy.Subscriber(args.control_topic, String, control_callback, queue_size=10)
    publish_status()
    period_s = 1.0 / args.publish_rate
    while not rospy.is_shutdown():
        scenario_time_s = clock.advance(time.monotonic())
        message = Clock()
        message.clock = rospy.Time.from_sec(scenario_time_s)
        clock_publisher.publish(message)
        publish_status()
        time.sleep(period_s)


if __name__ == "__main__":
    main()
