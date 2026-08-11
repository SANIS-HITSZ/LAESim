#!/usr/bin/env python3
"""Send one command to the LAESim controllable scenario clock."""

from __future__ import annotations

import argparse
import json
import time

import rospy
from std_msgs.msg import String


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("pause", "resume", "step", "set_rate", "set_time", "reset"))
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--scenario-time", default="")
    parser.add_argument("--topic", default="/space_clock/control")
    return parser.parse_args(rospy.myargv()[1:])


def main():
    args = parse_args()
    rospy.init_node("laesim_space_clock_control", anonymous=True)
    publisher = rospy.Publisher(args.topic, String, queue_size=1)
    deadline = time.monotonic() + 5.0
    while publisher.get_num_connections() == 0 and time.monotonic() < deadline:
        rospy.sleep(0.05)
    if publisher.get_num_connections() == 0:
        raise RuntimeError(f"no scenario-clock subscriber on {args.topic}")
    message = {"command": args.command}
    if args.command == "step":
        message["seconds"] = args.seconds
    elif args.command == "set_rate":
        message["rate"] = args.rate
    elif args.command == "set_time":
        if not args.scenario_time:
            raise SystemExit("set_time requires --scenario-time")
        message["scenario_time"] = args.scenario_time
    publisher.publish(String(data=json.dumps(message, separators=(",", ":"))))
    rospy.sleep(0.2)
    print(json.dumps(message, indent=2))


if __name__ == "__main__":
    main()
