#!/usr/bin/env python3
"""Verify LAESim odometry-driven ns-3 message delivery from ROS."""

from __future__ import annotations

import argparse
import json
import math
import threading
import time

import rospy
from nav_msgs.msg import Odometry
from std_msgs.msg import String


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send repeatable UAV-to-Car messages through LAESim ns-3."
    )
    parser.add_argument("--source", default="UAV")
    parser.add_argument("--destination", default="Car")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--size-bytes", type=int, default=1024)
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--expect", choices=("delivered", "dropped"), default="delivered")
    args = parser.parse_args(rospy.myargv()[1:])
    if args.count <= 0 or not 1 <= args.size_bytes <= 60000 or args.timeout <= 0.0:
        parser.error("count, size-bytes, and timeout must be in valid ranges")

    rospy.init_node("laesim_ns3_quickstart", anonymous=True)
    lock = threading.RLock()
    positions = {}
    received = {}
    prefix = f"quickstart-{int(time.time())}"

    def odom_callback(message: Odometry, vehicle_name: str) -> None:
        point = message.pose.pose.position
        with lock:
            positions[vehicle_name] = (point.x, point.y, point.z)

    def receive_callback(message: String) -> None:
        try:
            data = json.loads(message.data)
        except json.JSONDecodeError:
            return
        packet_id = str(data.get("packet_id", ""))
        if packet_id.startswith(prefix):
            with lock:
                received[packet_id] = data

    for vehicle_name in (args.source, args.destination):
        rospy.Subscriber(
            f"/airsim_node/{vehicle_name}/odom_local_ned",
            Odometry,
            odom_callback,
            callback_args=vehicle_name,
            queue_size=1,
        )
    rospy.Subscriber(
        f"/network_sim/rx/{args.destination}",
        String,
        receive_callback,
        queue_size=100,
    )
    publisher = rospy.Publisher("/network_sim/tx", String, queue_size=100)

    ready_deadline = time.monotonic() + args.timeout
    while time.monotonic() < ready_deadline and not rospy.is_shutdown():
        with lock:
            odometry_ready = all(
                name in positions for name in (args.source, args.destination)
            )
        if odometry_ready and publisher.get_num_connections() > 0:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError(
            "odometry or /network_sim/tx bridge connection did not become ready"
        )

    with lock:
        source_position = positions[args.source]
        destination_position = positions[args.destination]
    local_odom_distance = math.dist(source_position, destination_position)
    print(
        "ROS local-odometry distance: "
        f"{local_odom_distance:.2f} m; ns-3 also applies configured X/Y/Z origins"
    )

    packet_ids = []
    for index in range(args.count):
        packet_id = f"{prefix}-{index:03d}"
        packet_ids.append(packet_id)
        publisher.publish(
            String(
                data=json.dumps(
                    {
                        "packet_id": packet_id,
                        "src": args.source,
                        "dst": args.destination,
                        "size_bytes": args.size_bytes,
                        "payload": f"LAESim ns-3 quickstart packet {index}",
                    },
                    separators=(",", ":"),
                )
            )
        )
        time.sleep(0.1)

    receive_deadline = time.monotonic() + args.timeout
    while time.monotonic() < receive_deadline and not rospy.is_shutdown():
        with lock:
            if len(received) == len(packet_ids):
                break
        time.sleep(0.05)

    delivered = [packet_id for packet_id in packet_ids if packet_id in received]
    dropped = [packet_id for packet_id in packet_ids if packet_id not in received]
    simulation_times = [
        int(received[packet_id].get("simulation_time_ns", 0))
        for packet_id in delivered
    ]
    summary = {
        "source": args.source,
        "destination": args.destination,
        "sent": len(packet_ids),
        "delivered": len(delivered),
        "dropped": len(dropped),
        "delivery_ratio": len(delivered) / len(packet_ids),
        "simulation_time_ns": simulation_times,
    }
    print(json.dumps(summary, indent=2))

    if args.expect == "delivered":
        if len(delivered) != len(packet_ids):
            raise RuntimeError("expected every packet to be delivered")
        if any(value <= 0 for value in simulation_times):
            raise RuntimeError("packets were delivered without the ns-3 backend")
    elif delivered:
        raise RuntimeError("expected every packet to be dropped")
    print(f"expectation '{args.expect}' passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
