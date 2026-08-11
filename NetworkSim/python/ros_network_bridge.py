#!/usr/bin/env python3
"""ROS message-level bridge for optional ns-3 network simulation."""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from pathlib import Path

import rospy
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String

from network_backend import (
    Delivery,
    LogicalRoute,
    NetworkDrop,
    PacketRequest,
    create_backend,
    validate_request,
)
from satellite_link_model import SatelliteLinkModel
from space_access_policy import SpaceAccessPolicy


class RosNetworkBridge:
    def __init__(self, settings: dict, backend_override: str = ""):
        self.vehicle_names = list(settings.get("Vehicles", {}).keys())
        if not self.vehicle_names:
            raise ValueError("settings.json does not define any vehicles")

        self.config = settings.get("NetworkSimulation", {})
        self.step_ms = float(self.config.get("StepMs", 20.0))
        self.backend_name = backend_override or str(self.config.get("Backend", "none")).lower()
        self.backend = create_backend(self.config, self.vehicle_names, backend_override)
        self.space_access_policy = SpaceAccessPolicy(self.config, self.vehicle_names)
        self.satellite_link_model = SatelliteLinkModel(self.config)
        unified_clock_config = self.config.get("UnifiedClock", {})
        self.unified_clock_enabled = bool(unified_clock_config.get("Enabled", False))
        self.clock_topic = str(unified_clock_config.get("ClockTopic", "/clock"))
        self.clock_max_step_ms = float(unified_clock_config.get("MaxStepMs", 1000.0))
        if self.clock_max_step_ms <= 0.0:
            raise ValueError("NetworkSimulation.UnifiedClock.MaxStepMs must be positive")
        self.last_clock_ns = None
        if self.satellite_link_model.enabled and not self.space_access_policy.enabled:
            raise ValueError("SatelliteLinkModel requires SpaceAccessPolicy.Enabled=true")
        self.satellite_link_active = (
            self.satellite_link_model.enabled and self.backend_name == "ns3"
        )
        self.lock = threading.RLock()
        self.latest_poses = {}
        self.publishers = {
            name: rospy.Publisher(f"/network_sim/rx/{name}", String, queue_size=100)
            for name in self.vehicle_names
        }
        self.drop_publisher = rospy.Publisher("/network_sim/drop", String, queue_size=100)

        for name in self.vehicle_names:
            rospy.Subscriber(
                f"/airsim_node/{name}/odom_local_ned",
                Odometry,
                self._odom_callback,
                callback_args=name,
                queue_size=1,
            )
        rospy.Subscriber("/network_sim/tx", String, self._tx_callback, queue_size=100)
        self.access_subscribers = []
        if self.space_access_policy.subscription_topics:
            try:
                from airsim_ros_pkgs.msg import SpaceAccessState
            except ImportError as error:
                raise RuntimeError(
                    "SpaceAccessPolicy requires airsim_ros_pkgs/SpaceAccessState. "
                    "Sync the current LAESim ros/src tree and rerun catkin_make."
                ) from error
            self.access_subscribers = [
                rospy.Subscriber(
                    topic,
                    SpaceAccessState,
                    self._access_callback,
                    callback_args=topic,
                    queue_size=1,
                )
                for topic in self.space_access_policy.subscription_topics
            ]
        self.timer = None
        self.clock_subscriber = None
        if self.unified_clock_enabled:
            self.clock_subscriber = rospy.Subscriber(
                self.clock_topic, Clock, self._clock_callback, queue_size=10
            )
        else:
            self.timer = rospy.Timer(
                rospy.Duration(self.step_ms / 1000.0), self._step_callback
            )
        rospy.on_shutdown(self.backend.close)
        rospy.loginfo(
            "LAESim network bridge started: backend=%s, vehicles=%d, step_ms=%.1f",
            self.backend_name,
            len(self.vehicle_names),
            self.step_ms,
        )
        rospy.loginfo("Listening on /network_sim/tx and publishing /network_sim/rx/<vehicle>")
        rospy.loginfo("Subscribed odometry topics under /airsim_node/<vehicle>/odom_local_ned")
        if self.space_access_policy.enabled:
            rospy.loginfo(
                "Space-access policy enabled: rules=%d, fail_mode=%s, max_state_age_s=%.1f",
                len(self.space_access_policy.rules),
                self.space_access_policy.fail_mode,
                self.space_access_policy.max_state_age_s,
            )
            for topic in self.space_access_policy.subscription_topics:
                rospy.loginfo("Subscribed space-access state: %s", topic)
        if self.satellite_link_model.enabled:
            rospy.loginfo(
                "Satellite logical-link model: active=%s, frequency_hz=%.0f, bandwidth_hz=%.0f, data_rate_bps=%.0f",
                self.satellite_link_active,
                self.satellite_link_model.frequency_hz,
                self.satellite_link_model.bandwidth_hz,
                self.satellite_link_model.data_rate_bps,
            )
        if self.unified_clock_enabled:
            rospy.loginfo(
                "Unified clock enabled: topic=%s, max_step_ms=%.1f",
                self.clock_topic,
                self.clock_max_step_ms,
            )

    def _odom_callback(self, message: Odometry, vehicle_name: str) -> None:
        position = message.pose.pose.position
        with self.lock:
            first_pose = vehicle_name not in self.latest_poses
            self.latest_poses[vehicle_name] = (position.x, position.y, -position.z)
        if first_pose:
            rospy.loginfo(
                "Received first odometry for %s (%d/%d vehicles seen)",
                vehicle_name,
                len(self.latest_poses),
                len(self.vehicle_names),
            )

    def _access_callback(self, message, topic: str) -> None:
        with self.lock:
            self.space_access_policy.update(
                topic=topic,
                valid=message.valid,
                access=message.access,
                elevation_deg=message.elevation_deg,
                range_m=message.range_m,
                message=message.message,
            )

    def _tx_callback(self, message: String) -> None:
        try:
            data = json.loads(message.data)
            payload = data.get("payload", "")
            if not isinstance(payload, str):
                payload = json.dumps(payload, separators=(",", ":"))
            request = PacketRequest(
                source=str(data["src"]),
                destination=str(data["dst"]),
                payload=payload,
                size_bytes=int(data.get("size_bytes", max(len(payload.encode("utf-8")), 1))),
                packet_id=str(data.get("packet_id", "")),
            )
            with self.lock:
                validate_request(request, self.vehicle_names)
                request.packet_id = request.packet_id or uuid.uuid4().hex
                route = data.get("route")
                if route is not None:
                    self._send_logical_route(request, route)
                    return
                decision = self.space_access_policy.decide(
                    request.source, request.destination
                )
                if not decision.allowed:
                    self._publish_policy_drop(request, decision)
                    return
                logical_link = (
                    self.satellite_link_model.build(request, decision)
                    if self.satellite_link_active
                    else None
                )
                self.backend.send(request, logical_link=logical_link)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            rospy.logerr("Rejected /network_sim/tx message: %s", error)

    def _send_logical_route(self, request: PacketRequest, route) -> None:
        if not self.satellite_link_active:
            raise ValueError("route requires active ns3 SatelliteLinkModel")
        if not isinstance(route, list) or len(route) < 2:
            raise ValueError("route must be a JSON list with at least two vehicle names")
        route = [str(name) for name in route]
        if route[0] != request.source or route[-1] != request.destination:
            raise ValueError("route endpoints must match src and dst")
        if len(set(route)) != len(route):
            raise ValueError("route must not contain repeated vehicles")
        unknown = [name for name in route if name not in self.vehicle_names]
        if unknown:
            raise ValueError("route references unknown vehicles: " + ", ".join(unknown))

        links = []
        for source, destination in zip(route, route[1:]):
            decision = self.space_access_policy.decide(source, destination)
            if not decision.allowed:
                self._publish_policy_drop(
                    request, decision, route=route, failed_hop=[source, destination]
                )
                return
            hop_request = PacketRequest(
                source=source,
                destination=destination,
                payload=request.payload,
                size_bytes=request.size_bytes,
                packet_id=request.packet_id,
            )
            link = self.satellite_link_model.build(hop_request, decision)
            if link is None:
                raise ValueError(
                    f"route hop {source}->{destination} has no SpaceAccessPolicy rule"
                )
            links.append(link)
        self.backend.send(
            request,
            logical_route=LogicalRoute(tuple(route), tuple(links)),
        )

    def _publish_policy_drop(
        self, request: PacketRequest, decision, route=None, failed_hop=None
    ) -> None:
        message = {
            "packet_id": request.packet_id,
            "src": request.source,
            "dst": request.destination,
            "size_bytes": request.size_bytes,
            "dropped": True,
            "drop_stage": "space_access_policy",
            "drop_reason": decision.reason,
            "access_topic": decision.topic,
            "elevation_deg": decision.elevation_deg,
            "range_m": decision.range_m,
            "payload": request.payload,
        }
        if route is not None:
            message["route"] = route
            message["failed_hop"] = failed_hop
        self.drop_publisher.publish(
            String(data=json.dumps(message, separators=(",", ":"), allow_nan=True))
        )
        rospy.logwarn_throttle(
            1.0,
            "Network packet blocked by space-access policy: %s -> %s (%s)",
            request.source,
            request.destination,
            decision.reason,
        )

    def _publish_backend_drop(self, drop: NetworkDrop) -> None:
        message = {
            "packet_id": drop.packet_id,
            "src": drop.source,
            "dst": drop.destination,
            "size_bytes": drop.size_bytes,
            "dropped": True,
            "drop_stage": "ns3",
            "drop_reason": drop.reason,
            "simulation_time_ns": drop.simulation_time_ns,
            "packet_age_ns": drop.packet_age_ns,
            "node_distance_m": drop.node_distance_m,
            "topology_hop_count": drop.topology_hop_count,
            "route_available": drop.route_available,
            "routing_protocol": drop.routing_protocol,
            "max_range_m": drop.max_range_m,
            "source_position_m": drop.source_position_m,
            "destination_position_m": drop.destination_position_m,
            "payload": drop.payload,
        }
        if drop.link_type in ("satellite", "satellite_route"):
            message.update({
                "link_type": drop.link_type,
                "propagation_delay_ns": drop.propagation_delay_ns,
                "serialization_delay_ns": drop.serialization_delay_ns,
                "data_rate_bps": drop.data_rate_bps,
                "packet_error_rate": drop.packet_error_rate,
                "true_range_m": drop.true_range_m,
                "fspl_db": drop.fspl_db,
                "rx_power_dbm": drop.rx_power_dbm,
                "snr_db": drop.snr_db,
                "frequency_hz": drop.frequency_hz,
                "bandwidth_hz": drop.bandwidth_hz,
                "route_hop_count": drop.route_hop_count,
                "route_nodes": drop.route_nodes,
            })
        self.drop_publisher.publish(
            String(data=json.dumps(message, separators=(",", ":"), allow_nan=False))
        )
        rospy.logwarn(
            "Network packet dropped by ns-3: %s -> %s (%s, distance=%s m, routing=%s, sim_time_ns=%d)",
            drop.source,
            drop.destination,
            drop.reason,
            "unknown" if drop.node_distance_m is None else f"{drop.node_distance_m:.3f}",
            drop.routing_protocol or "unknown",
            drop.simulation_time_ns,
        )

    def _publish_delivery(self, delivery: Delivery) -> None:
        message = {
            "packet_id": delivery.packet_id,
            "src": delivery.source,
            "dst": delivery.destination,
            "size_bytes": delivery.size_bytes,
            "simulation_time_ns": delivery.simulation_time_ns,
            "latency_ns": delivery.latency_ns,
            "payload": delivery.payload,
        }
        if delivery.link_type in ("satellite", "satellite_route"):
            message.update({
                "link_type": delivery.link_type,
                "propagation_delay_ns": delivery.propagation_delay_ns,
                "serialization_delay_ns": delivery.serialization_delay_ns,
                "data_rate_bps": delivery.data_rate_bps,
                "packet_error_rate": delivery.packet_error_rate,
                "true_range_m": delivery.true_range_m,
                "fspl_db": delivery.fspl_db,
                "rx_power_dbm": delivery.rx_power_dbm,
                "snr_db": delivery.snr_db,
                "frequency_hz": delivery.frequency_hz,
                "bandwidth_hz": delivery.bandwidth_hz,
                "route_hop_count": delivery.route_hop_count,
                "route_nodes": delivery.route_nodes,
            })
        self.publishers[delivery.destination].publish(
            String(data=json.dumps(message, separators=(",", ":")))
        )

    def _advance_backend(self, milliseconds: float) -> None:
        try:
            deliveries = []
            drops = []
            with self.lock:
                for name, pose in self.latest_poses.items():
                    self.backend.update_pose(name, *pose)
                remaining_ms = milliseconds
                while remaining_ms > 1e-9:
                    chunk_ms = min(remaining_ms, self.clock_max_step_ms)
                    deliveries.extend(self.backend.step(chunk_ms))
                    drops.extend(self.backend.pop_drops())
                    remaining_ms -= chunk_ms
            for delivery in deliveries:
                self._publish_delivery(delivery)
            for drop in drops:
                self._publish_backend_drop(drop)
        except Exception as error:
            rospy.logfatal("Network backend failed: %s", error)
            rospy.signal_shutdown(str(error))

    def _step_callback(self, _event) -> None:
        self._advance_backend(self.step_ms)

    def _clock_callback(self, message: Clock) -> None:
        clock_ns = message.clock.to_nsec()
        if self.last_clock_ns is None:
            self.last_clock_ns = clock_ns
            rospy.loginfo("Received first unified clock sample: %d ns", clock_ns)
            return
        delta_ns = clock_ns - self.last_clock_ns
        self.last_clock_ns = clock_ns
        if delta_ns < 0:
            rospy.logwarn(
                "Unified clock moved backwards; ns-3 keeps its current time. "
                "Restart NetworkSim for a deterministic replay reset."
            )
            return
        if delta_ns == 0:
            return
        self._advance_backend(delta_ns / 1.0e6)


def main() -> None:
    parser = argparse.ArgumentParser(description="LAESim optional ns-3 ROS bridge")
    parser.add_argument("--settings", required=True, help="Path to AirSim settings.json")
    parser.add_argument("--backend", choices=("none", "ns3"), default="")
    args = parser.parse_args(rospy.myargv()[1:])

    settings = json.loads(Path(args.settings).read_text(encoding="utf-8"))
    rospy.init_node("laesim_network_bridge")
    RosNetworkBridge(settings, args.backend)
    rospy.spin()


if __name__ == "__main__":
    main()
