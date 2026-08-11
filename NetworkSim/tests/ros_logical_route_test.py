#!/usr/bin/env python3
"""Verify a two-hop satellite logical route through the ROS network bridge."""

from __future__ import annotations

import json
import threading
import time
import uuid

import rospy
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceAccessState


def make_access(source, destination, range_m):
    message = SpaceAccessState()
    message.header.frame_id = "earth_ecef"
    message.vehicle_name = source
    message.target_name = destination
    message.target_kind = "satellite" if destination.startswith("Satellite") else "ground"
    message.source = "logical-route-test"
    message.valid = True
    message.access = True
    message.azimuth_deg = float("nan")
    message.elevation_deg = 30.0
    message.range_m = range_m
    return message


def main():
    rospy.init_node("laesim_logical_route_test", anonymous=True)
    packet_id = f"logical-route-{uuid.uuid4().hex[:12]}"
    delivered = []
    dropped = []
    event = threading.Event()

    def receive_callback(message):
        data = json.loads(message.data)
        if data.get("packet_id") == packet_id:
            delivered.append(data)
            event.set()

    def drop_callback(message):
        data = json.loads(message.data)
        if data.get("packet_id") == packet_id:
            dropped.append(data)
            event.set()

    rospy.Subscriber("/network_sim/rx/Car", String, receive_callback, queue_size=1)
    rospy.Subscriber("/network_sim/drop", String, drop_callback, queue_size=1)
    tx_publisher = rospy.Publisher("/network_sim/tx", String, queue_size=1)
    isl_publisher = rospy.Publisher(
        "/space/Satellite/access/Satellite2", SpaceAccessState, queue_size=1
    )
    downlink_publisher = rospy.Publisher(
        "/space/Satellite2/access/Car", SpaceAccessState, queue_size=1
    )

    isl = make_access("Satellite", "Satellite2", 1_000_000.0)
    downlink = make_access("Satellite2", "Car", 500_000.0)
    deadline = time.monotonic() + 10.0
    sent = False
    while time.monotonic() < deadline and not rospy.is_shutdown() and not event.is_set():
        stamp = rospy.Time.now()
        isl.header.stamp = stamp
        downlink.header.stamp = stamp
        isl_publisher.publish(isl)
        downlink_publisher.publish(downlink)
        ready = (
            tx_publisher.get_num_connections() > 0
            and isl_publisher.get_num_connections() > 0
            and downlink_publisher.get_num_connections() > 0
        )
        if ready and not sent:
            rospy.sleep(0.3)
            tx_publisher.publish(String(data=json.dumps({
                "packet_id": packet_id,
                "src": "Satellite",
                "dst": "Car",
                "route": ["Satellite", "Satellite2", "Car"],
                "size_bytes": 1024,
                "payload": "laesim-two-hop-route",
            }, separators=(",", ":"))))
            sent = True
        rospy.sleep(0.05)

    if not sent:
        raise RuntimeError("network or access subscribers were not ready")
    if not event.is_set():
        raise RuntimeError("logical route packet timed out")
    if dropped:
        raise RuntimeError(f"logical route was dropped: {dropped[0]}")

    result = delivered[0]
    if result.get("link_type") != "satellite_route":
        raise RuntimeError(f"unexpected link type: {result}")
    if result.get("route_hop_count") != 2:
        raise RuntimeError(f"unexpected route hop count: {result}")
    if result.get("route_nodes") != ["Satellite", "Satellite2", "Car"]:
        raise RuntimeError(f"unexpected route: {result}")
    if abs(float(result.get("true_range_m", 0.0)) - 1_500_000.0) > 1.0:
        raise RuntimeError(f"unexpected aggregate route range: {result}")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
