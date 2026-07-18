#!/usr/bin/env python3
"""Publish one LAESim network message and verify its ROS delivery."""

from __future__ import annotations

import argparse
import json
import threading

import rospy
from std_msgs.msg import String


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="UAV")
    parser.add_argument("--destination", default="Car")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(rospy.myargv()[1:])

    rospy.init_node("laesim_network_roundtrip_test", anonymous=True)
    received = []
    event = threading.Event()

    def callback(message: String) -> None:
        received.append(json.loads(message.data))
        event.set()

    rospy.Subscriber(f"/network_sim/rx/{args.destination}", String, callback, queue_size=1)
    publisher = rospy.Publisher("/network_sim/tx", String, queue_size=1)

    deadline = rospy.Time.now() + rospy.Duration(args.timeout)
    while publisher.get_num_connections() == 0 and rospy.Time.now() < deadline:
        rospy.sleep(0.05)
    if publisher.get_num_connections() == 0:
        raise RuntimeError("network bridge did not subscribe to /network_sim/tx")

    expected_payload = "laesim-network-roundtrip"
    publisher.publish(
        String(
            data=json.dumps(
                {
                    "packet_id": "ros-roundtrip",
                    "src": args.source,
                    "dst": args.destination,
                    "size_bytes": 1024,
                    "payload": expected_payload,
                }
            )
        )
    )

    if not event.wait(args.timeout):
        raise RuntimeError("network message was not delivered before timeout")
    if received[0]["payload"] != expected_payload:
        raise RuntimeError(f"unexpected payload: {received[0]}")

    print(json.dumps(received[0], indent=2))


if __name__ == "__main__":
    main()
