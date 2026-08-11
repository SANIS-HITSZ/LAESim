#!/usr/bin/env python3
"""Publish one LAESim network message and verify its ROS delivery."""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from typing import List

import rospy
from std_msgs.msg import String


def discover_network_vehicles(timeout: float) -> List[str]:
    deadline = rospy.Time.now() + rospy.Duration(timeout)
    while rospy.Time.now() < deadline and not rospy.is_shutdown():
        vehicles = sorted(
            topic.rsplit("/", 1)[-1]
            for topic, message_type in rospy.get_published_topics()
            if message_type == "std_msgs/String" and topic.startswith("/network_sim/rx/")
        )
        if vehicles:
            return vehicles
        rospy.sleep(0.1)
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="")
    parser.add_argument("--destination", default="")
    parser.add_argument("--packet-id", default="")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--expect-drop",
        action="store_true",
        help="Pass only when the packet is reported on /network_sim/drop.",
    )
    parser.add_argument(
        "--expect-drop-stage",
        choices=("space_access_policy", "ns3"),
        default="",
        help="Additionally require this drop_stage value.",
    )
    parser.add_argument(
        "--expect-drop-reason",
        choices=("range", "routing", "timeout", "socket", "link_budget", "link_error"),
        default="",
        help="Additionally require this ns-3 drop_reason value.",
    )
    parser.add_argument(
        "--expect-link-type",
        choices=("wifi", "satellite", "satellite_route"),
        default="",
        help="Require the delivered packet to use this network link type.",
    )
    args = parser.parse_args(rospy.myargv()[1:])

    rospy.init_node("laesim_network_roundtrip_test", anonymous=True)
    vehicles = discover_network_vehicles(args.timeout)
    if not vehicles:
        raise RuntimeError("no /network_sim/rx/<vehicle> topics were found")

    source = args.source
    destination = args.destination
    if not source and not destination:
        if len(vehicles) < 2:
            raise RuntimeError("at least two /network_sim/rx/<vehicle> topics are required")
        source, destination = vehicles[0], vehicles[1]
    elif not source:
        source = next((vehicle for vehicle in vehicles if vehicle != destination), "")
    elif not destination:
        destination = next((vehicle for vehicle in vehicles if vehicle != source), "")

    if source not in vehicles:
        raise RuntimeError(f"source vehicle is not configured in NetworkSim: {source}")
    if destination not in vehicles:
        raise RuntimeError(f"destination vehicle is not configured in NetworkSim: {destination}")
    if source == destination:
        raise RuntimeError("source and destination must be different vehicles")

    packet_id = args.packet_id or f"ros-roundtrip-{uuid.uuid4().hex[:12]}"
    received = []
    dropped = []
    event = threading.Event()

    def callback(message: String) -> None:
        data = json.loads(message.data)
        if data.get("packet_id") == packet_id:
            received.append(data)
            event.set()

    def drop_callback(message: String) -> None:
        data = json.loads(message.data)
        if data.get("packet_id") == packet_id:
            dropped.append(data)
            event.set()

    receive_subscriber = rospy.Subscriber(
        f"/network_sim/rx/{destination}", String, callback, queue_size=1
    )
    drop_subscriber = rospy.Subscriber(
        "/network_sim/drop", String, drop_callback, queue_size=1
    )
    publisher = rospy.Publisher("/network_sim/tx", String, queue_size=1)

    deadline = rospy.Time.now() + rospy.Duration(args.timeout)
    while rospy.Time.now() < deadline:
        tx_ready = publisher.get_num_connections() > 0
        result_ready = (
            drop_subscriber.get_num_connections() > 0
            if args.expect_drop
            else receive_subscriber.get_num_connections() > 0
        )
        if tx_ready and result_ready:
            break
        rospy.sleep(0.05)
    if publisher.get_num_connections() == 0:
        raise RuntimeError("network bridge did not subscribe to /network_sim/tx")
    if args.expect_drop and drop_subscriber.get_num_connections() == 0:
        raise RuntimeError("network bridge did not advertise /network_sim/drop")

    expected_payload = "laesim-network-roundtrip"
    publisher.publish(
        String(
            data=json.dumps(
                {
                    "packet_id": packet_id,
                    "src": source,
                    "dst": destination,
                    "size_bytes": 1024,
                    "payload": expected_payload,
                }
            )
        )
    )

    if not event.wait(args.timeout):
        expectation = "dropped" if args.expect_drop else "delivered"
        raise RuntimeError(f"network message was not {expectation} before timeout")
    if args.expect_drop:
        if not dropped:
            raise RuntimeError(f"expected a drop but packet was delivered: {received[0]}")
        if args.expect_drop_stage and dropped[0].get("drop_stage") != args.expect_drop_stage:
            raise RuntimeError(
                f"expected drop_stage={args.expect_drop_stage}, got: {dropped[0]}"
            )
        if args.expect_drop_reason and dropped[0].get("drop_reason") != args.expect_drop_reason:
            raise RuntimeError(
                f"expected drop_reason={args.expect_drop_reason}, got: {dropped[0]}"
            )
        print(json.dumps(dropped[0], indent=2))
        return
    if dropped:
        raise RuntimeError(f"network message was rejected: {dropped[0]}")
    if received[0]["payload"] != expected_payload:
        raise RuntimeError(f"unexpected payload: {received[0]}")
    actual_link_type = received[0].get("link_type", "wifi")
    if args.expect_link_type and actual_link_type != args.expect_link_type:
        raise RuntimeError(
            f"expected link_type={args.expect_link_type}, got: {received[0]}"
        )

    print(json.dumps(received[0], indent=2))


if __name__ == "__main__":
    main()
