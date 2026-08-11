#!/usr/bin/env python3
"""Verify one blocked and one delivered packet across a live TLE access pass."""

import argparse
import json
import threading
import time
import uuid

import rospy
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceAccessState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="Satellite")
    parser.add_argument("--destination", default="Car")
    parser.add_argument("--access-topic", default="")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--stable-seconds", type=float, default=0.3)
    args = parser.parse_args(rospy.myargv()[1:])

    rospy.init_node("laesim_tle_network_transition_test", anonymous=True)
    access_topic = args.access_topic or f"/space/{args.source}/access/{args.destination}"
    lock = threading.RLock()
    current_access = {"valid": False, "access": False, "changed_at": time.monotonic()}
    pending = {}
    results = {}

    def access_callback(message):
        with lock:
            value = bool(message.valid and message.access)
            if current_access["valid"] != message.valid or current_access["access"] != value:
                current_access.update(
                    valid=bool(message.valid),
                    access=value,
                    changed_at=time.monotonic(),
                )

    def receive_callback(message):
        data = json.loads(message.data)
        with lock:
            expected = pending.get(data.get("packet_id"))
            if expected is not None:
                results[expected] = {"outcome": "delivered", "packet": data}

    def drop_callback(message):
        data = json.loads(message.data)
        with lock:
            expected = pending.get(data.get("packet_id"))
            if expected is not None:
                results[expected] = {"outcome": "dropped", "packet": data}

    access_subscriber = rospy.Subscriber(access_topic, SpaceAccessState, access_callback, queue_size=1)
    receive_subscriber = rospy.Subscriber(
        f"/network_sim/rx/{args.destination}", String, receive_callback, queue_size=1
    )
    drop_subscriber = rospy.Subscriber("/network_sim/drop", String, drop_callback, queue_size=1)
    publisher = rospy.Publisher("/network_sim/tx", String, queue_size=1)

    deadline = time.monotonic() + args.timeout
    sent = set()
    while time.monotonic() < deadline and not rospy.is_shutdown():
        if publisher.get_num_connections() == 0:
            rospy.sleep(0.05)
            continue
        with lock:
            state = dict(current_access)
            ready = state["valid"] and time.monotonic() - state["changed_at"] >= args.stable_seconds
            expectation = "delivered" if state["access"] else "dropped"
            if ready and expectation not in sent:
                packet_id = f"tle-transition-{expectation}-{uuid.uuid4().hex[:10]}"
                pending[packet_id] = expectation
                sent.add(expectation)
                publisher.publish(String(data=json.dumps({
                    "packet_id": packet_id,
                    "src": args.source,
                    "dst": args.destination,
                    "size_bytes": 1024,
                    "payload": f"laesim-tle-{expectation}",
                })))
        if set(results) == {"dropped", "delivered"}:
            break
        rospy.sleep(0.05)

    access_subscriber.unregister()
    receive_subscriber.unregister()
    drop_subscriber.unregister()

    missing = {"dropped", "delivered"} - set(results)
    if missing:
        raise RuntimeError(
            f"TLE transition test timed out; missing={sorted(missing)} sent={sorted(sent)} topic={access_topic}"
        )
    if results["dropped"]["outcome"] != "dropped":
        raise RuntimeError(f"inaccessible packet was unexpectedly delivered: {results['dropped']}")
    if results["delivered"]["outcome"] != "delivered":
        raise RuntimeError(f"accessible packet was unexpectedly dropped: {results['delivered']}")
    drop_packet = results["dropped"]["packet"]
    if drop_packet.get("drop_stage") != "space_access_policy":
        raise RuntimeError(f"packet was dropped by the wrong stage: {drop_packet}")

    print(json.dumps({
        "access_topic": access_topic,
        "blocked_phase": results["dropped"]["packet"],
        "visible_phase": results["delivered"]["packet"],
    }, indent=2))


if __name__ == "__main__":
    main()
