#!/usr/bin/env python3
"""Smoke tests for both LAESim network backends."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from network_backend import DirectBackend, Ns3Backend, PacketRequest  # noqa: E402


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
        max_range=250.0,
        warmup_seconds=3.0,
    )
    try:
        ns3.update_pose("UAV", 0.0, 0.0, 10.0)
        ns3.update_pose("Car", 10.0, 0.0, 0.0)
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
        max_range=25.0,
        warmup_seconds=3.0,
        packet_timeout_seconds=5.0,
    )
    try:
        loss_backend.update_pose("UAV", 0.0, 0.0, 0.0)
        loss_backend.update_pose("Car", 1000.0, 0.0, 0.0)
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
