#!/usr/bin/env python3
"""Smoke tests for both LAESim network backends."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from network_backend import (  # noqa: E402
    DirectBackend,
    Ns3Backend,
    PacketRequest,
    configured_vehicle_origins,
    network_pose_from_local_ned,
)


def make_packet(packet_id: str) -> PacketRequest:
    return PacketRequest(
        source="UAV",
        destination="Car",
        payload="smoke-test",
        size_bytes=1024,
        packet_id=packet_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runner",
        default=str(Path.home() / "opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"),
    )
    args = parser.parse_args()

    origins = configured_vehicle_origins(
        {
            "Vehicles": {
                "UAV": {"X": 0.0, "Y": 5.0, "Z": -2.0},
                "Car": {"X": 20.0, "Y": 0.0, "Z": 0.0},
            }
        }
    )
    assert origins["Car"] == (20.0, 0.0, 0.0)
    assert network_pose_from_local_ned(
        origins["UAV"], (1.0, 2.0, -3.0)
    ) == (1.0, 7.0, 5.0)
    uav_pose = network_pose_from_local_ned(origins["UAV"], (0.0, 0.0, 0.0))
    car_pose = network_pose_from_local_ned(origins["Car"], (0.0, 0.0, 0.0))

    direct = DirectBackend(["UAV", "Car"])
    direct.send(make_packet("direct-smoke"))
    direct_deliveries = direct.step(20)
    assert len(direct_deliveries) == 1
    assert direct_deliveries[0].destination == "Car"
    try:
        direct.send(
            PacketRequest(
                source="UAV",
                destination="Unknown",
                payload="invalid",
                size_bytes=1,
            )
        )
        raise AssertionError("DirectBackend accepted an unknown destination")
    except ValueError:
        pass

    ns3 = Ns3Backend(
        node_names=["UAV", "Car"],
        runner_path=args.runner,
        routing="olsr",
        max_range=100.0,
        warmup_seconds=3.0,
    )
    try:
        ns3.update_pose("UAV", *uav_pose)
        ns3.update_pose("Car", *car_pose)
        ns3.send(make_packet("ns3-smoke"))
        ns3_deliveries = ns3.step(100)
        assert len(ns3_deliveries) == 1
        assert ns3_deliveries[0].packet_id == "ns3-smoke"
        metrics = ns3.metrics()
    finally:
        ns3.close()

    loss_backend = Ns3Backend(
        node_names=["UAV", "Car"],
        runner_path=args.runner,
        routing="olsr",
        max_range=5.0,
        warmup_seconds=3.0,
        packet_timeout_seconds=5.0,
    )
    try:
        loss_backend.update_pose("UAV", *uav_pose)
        loss_backend.update_pose("Car", *car_pose)
        loss_backend.send(make_packet("ns3-timeout"))
        loss_deliveries = loss_backend.step(5100)
        assert not loss_deliveries
        assert not loss_backend.pending
        loss_metrics = loss_backend.metrics()
    finally:
        loss_backend.close()

    print(
        json.dumps(
            {
                "direct_delivery_count": len(direct_deliveries),
                "ns3_delivery_count": len(ns3_deliveries),
                "ns3_metrics": metrics,
                "ns3_timeout_delivery_count": len(loss_deliveries),
                "ns3_timeout_metrics": loss_metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
