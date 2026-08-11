#!/usr/bin/env python3
"""Send packets through the currently selected constellation satellite."""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid

import rospy
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="Car")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--size-bytes", type=int, default=1024)
    parser.add_argument("--require-handover", action="store_true")
    args = parser.parse_args(rospy.myargv()[1:])
    if args.duration <= 0.0 or args.interval <= 0.0 or args.size_bytes <= 0:
        raise SystemExit("duration, interval, and size-bytes must be positive")

    rospy.init_node("laesim_constellation_handover_test", anonymous=True)
    prefix = f"constellation-{uuid.uuid4().hex[:10]}"
    lock = threading.RLock()
    current_selection = {}
    sent = {}
    delivered = []
    dropped = []
    selected_sources = set()
    max_handover_count = 0

    def selection_callback(message):
        nonlocal max_handover_count
        data = json.loads(message.data)
        with lock:
            current_selection.clear()
            current_selection.update(data)
            max_handover_count = max(max_handover_count, int(data.get("handover_count", 0)))

    def receive_callback(message):
        data = json.loads(message.data)
        packet_id = str(data.get("packet_id", ""))
        if packet_id.startswith(prefix):
            with lock:
                data["wall_latency_ms"] = (time.monotonic() - sent.get(packet_id, time.monotonic())) * 1000.0
                delivered.append(data)

    def drop_callback(message):
        data = json.loads(message.data)
        packet_id = str(data.get("packet_id", ""))
        if packet_id.startswith(prefix):
            with lock:
                data["wall_latency_ms"] = (time.monotonic() - sent.get(packet_id, time.monotonic())) * 1000.0
                dropped.append(data)

    selection_topic = f"/space/selection/{args.target}"
    rospy.Subscriber(selection_topic, String, selection_callback, queue_size=10)
    rospy.Subscriber(f"/network_sim/rx/{args.target}", String, receive_callback, queue_size=100)
    rospy.Subscriber("/network_sim/drop", String, drop_callback, queue_size=100)
    publisher = rospy.Publisher("/network_sim/tx", String, queue_size=10)

    deadline = time.monotonic() + min(15.0, args.duration)
    while time.monotonic() < deadline and not rospy.is_shutdown():
        with lock:
            selected = current_selection.get("selected_satellite", "")
        if selected and publisher.get_num_connections() > 0:
            break
        rospy.sleep(0.1)
    if not selected:
        raise RuntimeError(f"no visible satellite was selected on {selection_topic}")
    if publisher.get_num_connections() == 0:
        raise RuntimeError("network bridge did not subscribe to /network_sim/tx")

    started = time.monotonic()
    sequence = 0
    while time.monotonic() - started < args.duration and not rospy.is_shutdown():
        with lock:
            selected = current_selection.get("selected_satellite", "")
        if selected:
            packet_id = f"{prefix}-{sequence}"
            selected_sources.add(selected)
            sent[packet_id] = time.monotonic()
            publisher.publish(String(data=json.dumps({
                "packet_id": packet_id,
                "src": selected,
                "dst": args.target,
                "size_bytes": args.size_bytes,
                "payload": "laesim-constellation-handover",
            }, separators=(",", ":"))))
            sequence += 1
        rospy.sleep(args.interval)

    rospy.sleep(2.0)
    with lock:
        summary = {
            "target": args.target,
            "sent_count": len(sent),
            "delivered_count": len(delivered),
            "dropped_count": len(dropped),
            "selected_sources": sorted(selected_sources),
            "handover_count": max_handover_count,
            "delivery_ratio": len(delivered) / len(sent) if sent else 0.0,
            "last_delivery": delivered[-1] if delivered else None,
            "last_drop": dropped[-1] if dropped else None,
        }
    print(json.dumps(summary, indent=2, allow_nan=False))
    if not delivered:
        raise RuntimeError("no packet was delivered through a selected satellite")
    if args.require_handover and max_handover_count < 1:
        raise RuntimeError("no satellite handover occurred during the test interval")


if __name__ == "__main__":
    main()
