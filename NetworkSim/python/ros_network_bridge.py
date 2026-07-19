#!/usr/bin/env python3
"""ROS message-level bridge for optional ns-3 network simulation."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

import rospy
from nav_msgs.msg import Odometry
from std_msgs.msg import String

from network_backend import (
    Delivery,
    PacketRequest,
    configured_vehicle_origins,
    create_backend,
    network_pose_from_local_ned,
)


class RosNetworkBridge:
    def __init__(self, settings: dict, backend_override: str = ""):
        self.vehicle_origins = configured_vehicle_origins(settings)
        self.vehicle_names = list(self.vehicle_origins.keys())

        self.config = settings.get("NetworkSimulation", {})
        self.step_ms = float(self.config.get("StepMs", 20.0))
        self.backend = create_backend(self.config, self.vehicle_names, backend_override)
        self.lock = threading.RLock()
        self.latest_poses = {}
        self.publishers = {
            name: rospy.Publisher(f"/network_sim/rx/{name}", String, queue_size=100)
            for name in self.vehicle_names
        }

        for name in self.vehicle_names:
            rospy.Subscriber(
                f"/airsim_node/{name}/odom_local_ned",
                Odometry,
                self._odom_callback,
                callback_args=name,
                queue_size=1,
            )
        rospy.Subscriber("/network_sim/tx", String, self._tx_callback, queue_size=100)
        self.timer = rospy.Timer(rospy.Duration(self.step_ms / 1000.0), self._step_callback)
        rospy.on_shutdown(self.backend.close)

    def _odom_callback(self, message: Odometry, vehicle_name: str) -> None:
        position = message.pose.pose.position
        network_pose = network_pose_from_local_ned(
            self.vehicle_origins[vehicle_name],
            (position.x, position.y, position.z),
        )
        with self.lock:
            self.latest_poses[vehicle_name] = network_pose

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
                self.backend.send(request)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            rospy.logerr("Rejected /network_sim/tx message: %s", error)

    def _publish_delivery(self, delivery: Delivery) -> None:
        message = {
            "packet_id": delivery.packet_id,
            "src": delivery.source,
            "dst": delivery.destination,
            "size_bytes": delivery.size_bytes,
            "simulation_time_ns": delivery.simulation_time_ns,
            "payload": delivery.payload,
        }
        self.publishers[delivery.destination].publish(
            String(data=json.dumps(message, separators=(",", ":")))
        )

    def _step_callback(self, _event) -> None:
        try:
            with self.lock:
                for name, pose in self.latest_poses.items():
                    self.backend.update_pose(name, *pose)
                deliveries = self.backend.step(self.step_ms)
            for delivery in deliveries:
                self._publish_delivery(delivery)
        except Exception as error:
            rospy.logfatal("Network backend failed: %s", error)
            rospy.signal_shutdown(str(error))


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
