#!/usr/bin/env python3
"""Verify paused/stepped scenario time drives both mission and network nodes."""

from __future__ import annotations

import json
import datetime as dt
import threading
import time
import uuid

import rospy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceSatelliteState


def main():
    rospy.init_node("laesim_unified_clock_test", anonymous=True)
    lock = threading.RLock()
    latest_clock_s = None
    latest_scenario_time = ""
    deliveries = []
    delivery_event = threading.Event()
    packet_id = f"clock-step-{uuid.uuid4().hex[:12]}"

    def clock_callback(message):
        nonlocal latest_clock_s
        with lock:
            latest_clock_s = message.clock.to_sec()

    def state_callback(message):
        nonlocal latest_scenario_time
        with lock:
            latest_scenario_time = message.scenario_time

    def receive_callback(message):
        data = json.loads(message.data)
        if data.get("packet_id") == packet_id:
            deliveries.append(data)
            delivery_event.set()

    rospy.Subscriber("/clock", Clock, clock_callback, queue_size=10)
    rospy.Subscriber(
        "/space/Satellite/state", SpaceSatelliteState, state_callback, queue_size=10
    )
    rospy.Subscriber("/network_sim/rx/Car", String, receive_callback, queue_size=10)
    tx_publisher = rospy.Publisher("/network_sim/tx", String, queue_size=1)
    control_publisher = rospy.Publisher("/space_clock/control", String, queue_size=1)

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        with lock:
            ready = latest_clock_s is not None and bool(latest_scenario_time)
        if ready and tx_publisher.get_num_connections() and control_publisher.get_num_connections():
            break
        rospy.sleep(0.05)
    if not ready:
        raise RuntimeError("clock or satellite state was not published")

    with lock:
        before_clock_s = latest_clock_s
        before_scenario_time = latest_scenario_time
    before_scenario_s = dt.datetime.fromisoformat(
        before_scenario_time.replace("Z", "+00:00")
    ).timestamp()
    if abs(before_scenario_s - before_clock_s) > 0.2:
        raise RuntimeError("mission scenario time is not synchronized to /clock")
    tx_publisher.publish(String(data=json.dumps({
        "packet_id": packet_id,
        "src": "Satellite",
        "dst": "Car",
        "size_bytes": 128,
        "payload": "release-on-clock-step",
    }, separators=(",", ":"))))
    if delivery_event.wait(0.5):
        raise RuntimeError("network packet was delivered while scenario clock was paused")

    control_publisher.publish(String(data='{"command":"step","seconds":2.0}'))
    if not delivery_event.wait(5.0):
        raise RuntimeError("network packet was not delivered after clock step")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        with lock:
            clock_delta_s = latest_clock_s - before_clock_s
            scenario_changed = latest_scenario_time != before_scenario_time
        if clock_delta_s >= 1.999 and scenario_changed:
            break
        rospy.sleep(0.05)
    if clock_delta_s < 1.999 or not scenario_changed:
        raise RuntimeError("mission bridge did not advance with the scenario clock")
    after_scenario_s = dt.datetime.fromisoformat(
        latest_scenario_time.replace("Z", "+00:00")
    ).timestamp()
    if abs(after_scenario_s - latest_clock_s) > 0.2:
        raise RuntimeError("mission scenario time diverged from /clock after step")
    if int(deliveries[0].get("simulation_time_ns", 0)) <= 0:
        raise RuntimeError("ns-3 did not advance on the unified clock step")

    result = {
        "before_clock_s": before_clock_s,
        "after_clock_s": latest_clock_s,
        "clock_delta_s": clock_delta_s,
        "before_scenario_time": before_scenario_time,
        "after_scenario_time": latest_scenario_time,
        "delivery": deliveries[0],
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
