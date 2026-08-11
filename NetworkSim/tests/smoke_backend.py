#!/usr/bin/env python3
"""Smoke tests for both LAESim network backends."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from network_backend import (  # noqa: E402
    DirectBackend,
    LogicalLink,
    LogicalRoute,
    Ns3Backend,
    PacketRequest,
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
    parser.add_argument(
        "--require-ns3",
        action="store_true",
        help="Fail if the ns-3 runner executable is unavailable.",
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

    runner_path = Path(args.runner).expanduser()
    runner_available = runner_path.is_file() or shutil.which(args.runner) is not None
    if not runner_available:
        if args.require_ns3:
            raise FileNotFoundError(f"ns-3 runner not found: {args.runner}")
        print(
            json.dumps(
                {
                    "direct_delivery_count": len(direct_deliveries),
                    "ns3_skipped": True,
                    "ns3_skip_reason": f"runner not found: {args.runner}",
                },
                indent=2,
            )
        )
        return

    ns3 = Ns3Backend(
        node_names=["UAV", "Car"],
        runner_path=str(runner_path),
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
        runner_path=str(runner_path),
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
        loss_drops = loss_backend.pop_drops()
        assert not loss_deliveries
        assert not loss_backend.pending
        assert len(loss_drops) == 1
        assert loss_drops[0].reason == "range"
        assert loss_drops[0].node_distance_m == 1000.0
        assert loss_drops[0].routing_protocol == "olsr"
        assert loss_drops[0].simulation_time_ns > 0
        loss_metrics = loss_backend.metrics()
    finally:
        loss_backend.close()

    routing_backend = Ns3Backend(
        node_names=["UAV", "Car"],
        runner_path=str(runner_path),
        routing="olsr",
        max_range=250.0,
        warmup_seconds=0.0,
        packet_timeout_seconds=1.0,
    )
    try:
        routing_backend.update_pose("UAV", 0.0, 0.0, 0.0)
        routing_backend.update_pose("Car", 10.0, 0.0, 0.0)
        routing_backend.send(make_packet("ns3-routing"))
        assert not routing_backend.step(1100)
        routing_drops = routing_backend.pop_drops()
        assert len(routing_drops) == 1
        assert routing_drops[0].reason == "routing"
        assert routing_drops[0].topology_hop_count == 1
        assert routing_drops[0].route_available is False
    finally:
        routing_backend.close()

    timeout_backend = Ns3Backend(
        node_names=["UAV", "Car"],
        runner_path=str(runner_path),
        routing="olsr",
        max_range=250.0,
        warmup_seconds=3.0,
        packet_timeout_seconds=1.0,
    )
    try:
        timeout_backend.update_pose("UAV", 0.0, 0.0, 0.0)
        timeout_backend.update_pose("Car", 100.0, 0.0, 0.0)
        timeout_backend.send(make_packet("ns3-timeout"))
        assert not timeout_backend.step(1100)
        timeout_drops = timeout_backend.pop_drops()
        assert len(timeout_drops) == 1
        assert timeout_drops[0].reason == "timeout"
        assert timeout_drops[0].topology_hop_count == 1
        assert timeout_drops[0].route_available is True
        assert timeout_drops[0].packet_age_ns >= 1_000_000_000
    finally:
        timeout_backend.close()

    logical_backend = Ns3Backend(
        node_names=["Satellite", "Car"],
        runner_path=str(runner_path),
        routing="olsr",
        max_range=1.0,
        warmup_seconds=0.0,
        packet_timeout_seconds=1.0,
    )
    logical_request = PacketRequest(
        source="Satellite",
        destination="Car",
        payload="logical-link-test",
        size_bytes=1024,
        packet_id="ns3-logical-delivery",
    )
    logical_link = LogicalLink(
        propagation_delay_ns=1_000_000,
        data_rate_bps=1_000_000.0,
        packet_error_rate=0.0,
        failure_reason="link_error",
        true_range_m=500_000.0,
        fspl_db=153.28,
        rx_power_dbm=-85.28,
        snr_db=18.73,
        frequency_hz=2.2e9,
        bandwidth_hz=5.0e6,
    )
    try:
        logical_backend.update_pose("Satellite", 0.0, 0.0, 0.0)
        logical_backend.update_pose("Car", 1000.0, 0.0, 0.0)
        logical_backend.send(logical_request, logical_link=logical_link)
        queued_request = PacketRequest(
            source="Satellite",
            destination="Car",
            payload="logical-link-queued-test",
            size_bytes=1024,
            packet_id="ns3-logical-queued-delivery",
        )
        logical_backend.send(queued_request, logical_link=logical_link)
        logical_deliveries = logical_backend.step(30)
        assert len(logical_deliveries) == 2
        assert logical_deliveries[0].link_type == "satellite"
        assert logical_deliveries[0].latency_ns == 9_192_000
        assert logical_deliveries[1].latency_ns == 17_384_000
        assert logical_deliveries[0].true_range_m == 500_000.0

        failing_request = make_packet("ns3-logical-drop")
        failing_request.source = "Satellite"
        failing_link = LogicalLink(
            propagation_delay_ns=1_000_000,
            data_rate_bps=1_000_000.0,
            packet_error_rate=1.0,
            failure_reason="link_budget",
            true_range_m=3_000_000.0,
            fspl_db=168.84,
            rx_power_dbm=-100.84,
            snr_db=3.17,
            frequency_hz=2.2e9,
            bandwidth_hz=5.0e6,
        )
        logical_backend.send(failing_request, logical_link=failing_link)
        assert not logical_backend.step(20)
        logical_drops = logical_backend.pop_drops()
        assert len(logical_drops) == 1
        assert logical_drops[0].reason == "link_budget"
        assert logical_drops[0].link_type == "satellite"
        assert logical_drops[0].true_range_m == 3_000_000.0
    finally:
        logical_backend.close()

    route_backend = Ns3Backend(
        node_names=["Satellite", "Satellite2", "Car"],
        runner_path=str(runner_path),
        routing="olsr",
        max_range=1.0,
        warmup_seconds=0.0,
        packet_timeout_seconds=1.0,
    )
    route_request = PacketRequest(
        source="Satellite",
        destination="Car",
        payload="logical-route-test",
        size_bytes=1024,
        packet_id="ns3-logical-route-delivery",
    )
    route = LogicalRoute(
        node_names=("Satellite", "Satellite2", "Car"),
        links=(logical_link, logical_link),
    )
    try:
        route_backend.send(route_request, logical_route=route)
        route_deliveries = route_backend.step(30)
        assert len(route_deliveries) == 1
        assert route_deliveries[0].link_type == "satellite_route"
        assert route_deliveries[0].route_hop_count == 2
        assert route_deliveries[0].route_nodes == ["Satellite", "Satellite2", "Car"]
        assert route_deliveries[0].latency_ns == 18_384_000
        assert route_deliveries[0].propagation_delay_ns == 2_000_000
        assert route_deliveries[0].serialization_delay_ns == 16_384_000
        assert route_deliveries[0].true_range_m == 1_000_000.0
    finally:
        route_backend.close()

    print(
        json.dumps(
            {
                "direct_delivery_count": len(direct_deliveries),
                "ns3_delivery_count": len(ns3_deliveries),
                "ns3_metrics": metrics,
                "ns3_timeout_delivery_count": len(loss_deliveries),
                "ns3_drop": loss_drops[0].__dict__,
                "ns3_routing_drop": routing_drops[0].__dict__,
                "ns3_timeout_drop": timeout_drops[0].__dict__,
                "ns3_logical_delivery": logical_deliveries[0].__dict__,
                "ns3_logical_drop": logical_drops[0].__dict__,
                "ns3_logical_route_delivery": route_deliveries[0].__dict__,
                "ns3_timeout_metrics": loss_metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
