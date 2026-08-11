#!/usr/bin/env python3
"""Deterministic DOWN/acquire/handover/DOWN acceptance for the space link."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import rospy
from std_msgs.msg import String

from airsim_ros_pkgs.msg import SpaceAccessState


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "NetworkSim" / "python"))

from satellite_selector import BestSatelliteSelector, SatelliteCandidate  # noqa: E402


SATELLITES = ("Satellite", "Satellite2")
TARGET = "Car"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a deterministic LAESim space-delivery acceptance sequence."
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--output", default="")
    return parser.parse_args(rospy.myargv()[1:])


def make_access_message(satellite, access, elevation_deg, range_m, phase):
    message = SpaceAccessState()
    message.header.stamp = rospy.Time.now()
    message.header.frame_id = "earth_ecef"
    message.vehicle_name = satellite
    message.target_name = TARGET
    message.target_kind = "ground"
    message.source = "deterministic-acceptance"
    message.valid = True
    message.access = bool(access)
    message.azimuth_deg = 180.0
    message.elevation_deg = float(elevation_deg)
    message.range_m = float(range_m)
    message.message = "" if access else f"{phase}_space_access_unavailable"
    return message


def main():
    args = parse_args()
    if args.timeout <= 0.0:
        raise SystemExit("--timeout must be positive")

    rospy.init_node("laesim_space_delivery_acceptance", anonymous=True)
    lock = threading.RLock()
    outcomes = {}
    access_publishers = {
        satellite: rospy.Publisher(
            f"/space/{satellite}/access/{TARGET}", SpaceAccessState, queue_size=10,
        )
        for satellite in SATELLITES
    }
    selection_publisher = rospy.Publisher(
        f"/space/selection/{TARGET}", String, queue_size=10, latch=True
    )
    tx_publisher = rospy.Publisher("/network_sim/tx", String, queue_size=10)

    def receive_callback(message):
        data = json.loads(message.data)
        packet_id = str(data.get("packet_id", ""))
        if packet_id.startswith("delivery-acceptance-"):
            with lock:
                outcomes[packet_id] = {"outcome": "delivered", "packet": data}

    def drop_callback(message):
        data = json.loads(message.data)
        packet_id = str(data.get("packet_id", ""))
        if packet_id.startswith("delivery-acceptance-"):
            with lock:
                outcomes[packet_id] = {"outcome": "dropped", "packet": data}

    rospy.Subscriber(f"/network_sim/rx/{TARGET}", String, receive_callback, queue_size=10)
    rospy.Subscriber("/network_sim/drop", String, drop_callback, queue_size=10)

    connection_deadline = time.monotonic() + args.timeout
    while time.monotonic() < connection_deadline and not rospy.is_shutdown():
        access_ready = all(pub.get_num_connections() > 0 for pub in access_publishers.values())
        if access_ready and tx_publisher.get_num_connections() > 0:
            break
        rospy.sleep(0.05)
    else:
        raise RuntimeError("network bridge did not subscribe to access and tx topics")

    phases = [
        {
            "name": "initial_down",
            "states": {
                "Satellite": (False, -5.0, 2_500_000.0),
                "Satellite2": (False, -8.0, 2_800_000.0),
            },
            "source": "Satellite",
            "expected_selection": "",
            "expected_outcome": "dropped",
        },
        {
            "name": "acquire_satellite",
            "states": {
                "Satellite": (True, 28.0, 800_000.0),
                "Satellite2": (False, -2.0, 2_200_000.0),
            },
            "source": "Satellite",
            "expected_selection": "Satellite",
            "expected_outcome": "delivered",
        },
        {
            "name": "handover_satellite2",
            "states": {
                "Satellite": (True, 10.0, 1_300_000.0),
                "Satellite2": (True, 40.0, 650_000.0),
            },
            "source": "Satellite2",
            "expected_selection": "Satellite2",
            "expected_outcome": "delivered",
        },
        {
            "name": "final_down",
            "states": {
                "Satellite": (False, -4.0, 2_400_000.0),
                "Satellite2": (False, -6.0, 2_600_000.0),
            },
            "source": "Satellite2",
            "expected_selection": "",
            "expected_outcome": "dropped",
        },
    ]

    selector = BestSatelliteSelector(hysteresis_deg=2.0, minimum_hold_s=0.0)
    report_phases = []
    for index, phase in enumerate(phases):
        candidates = []
        for satellite, (access, elevation_deg, range_m) in phase["states"].items():
            if access:
                candidates.append(SatelliteCandidate(satellite, elevation_deg, range_m))
            message = make_access_message(
                satellite, access, elevation_deg, range_m, phase["name"]
            )
            for _ in range(3):
                access_publishers[satellite].publish(message)
                rospy.sleep(0.03)

        selection = selector.update(TARGET, candidates, now_s=index * 10.0)
        selection_data = {
            "scenario_time_s": index * 10.0,
            "target": TARGET,
            "selected_satellite": selection.selected_satellite,
            "previous_satellite": selection.previous_satellite,
            "changed": selection.changed,
            "outage": selection.outage,
            "handover_count": selection.handover_count,
            "acquisition_count": selection.acquisition_count,
            "interruption_s": selection.interruption_s,
            "candidates": [asdict(candidate) for candidate in selection.candidates],
        }
        selection_publisher.publish(String(data=json.dumps(selection_data, allow_nan=True)))
        if selection.selected_satellite != phase["expected_selection"]:
            raise RuntimeError(
                f"{phase['name']} selected {selection.selected_satellite!r}, "
                f"expected {phase['expected_selection']!r}"
            )

        rospy.sleep(0.15)
        packet_id = f"delivery-acceptance-{index}-{phase['name']}"
        tx_publisher.publish(String(data=json.dumps({
            "packet_id": packet_id,
            "src": phase["source"],
            "dst": TARGET,
            "size_bytes": 1024,
            "payload": phase["name"],
        }, separators=(",", ":"))))

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and not rospy.is_shutdown():
            with lock:
                outcome = outcomes.get(packet_id)
            if outcome is not None:
                break
            rospy.sleep(0.02)
        else:
            raise RuntimeError(f"timed out waiting for packet result in {phase['name']}")

        if outcome["outcome"] != phase["expected_outcome"]:
            raise RuntimeError(
                f"{phase['name']} produced {outcome['outcome']}, "
                f"expected {phase['expected_outcome']}: {outcome['packet']}"
            )
        packet = outcome["packet"]
        if outcome["outcome"] == "delivered":
            if packet.get("link_type") != "satellite" or int(packet.get("latency_ns", 0)) <= 0:
                raise RuntimeError(f"{phase['name']} did not use the satellite link: {packet}")
        elif packet.get("drop_stage") != "space_access_policy":
            raise RuntimeError(f"{phase['name']} was blocked by the wrong stage: {packet}")

        report_phases.append({
            "phase": phase["name"],
            "selected_satellite": selection.selected_satellite,
            "handover_count": selection.handover_count,
            "expected_outcome": phase["expected_outcome"],
            "actual_outcome": outcome["outcome"],
            "packet": packet,
        })

    summary = selector.summary(now_s=len(phases) * 10.0)[TARGET]
    if summary["handover_count"] != 1:
        raise RuntimeError(f"expected exactly one handover, got {summary['handover_count']}")
    report = {
        "passed": True,
        "event_sequence": ["DOWN", "UP:Satellite", "HANDOVER:Satellite2", "DOWN"],
        "phase_count": len(report_phases),
        "selection_summary": summary,
        "phases": report_phases,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    print(output)
    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
