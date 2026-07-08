#!/usr/bin/env python3

import argparse

import rospy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix

from airsim_ros_pkgs.msg import CarState, Environment

from _ros_example_common import detect_settings_path, infer_vehicle_kind, load_settings, selected_vehicles, state_topics


class VehicleStateMonitor:
    def __init__(self, vehicle_map, namespace):
        self.snapshots = {}
        for vehicle_name, vehicle_config in vehicle_map.items():
            vehicle_kind = infer_vehicle_kind(vehicle_config)
            self.snapshots[vehicle_name] = {
                "kind": vehicle_kind,
                "odom": None,
                "env": None,
                "gps": None,
                "car_state": None,
            }

            topics = state_topics(vehicle_name, vehicle_kind, namespace)
            rospy.Subscriber(topics["odom"], Odometry, self._odom_cb, callback_args=vehicle_name, queue_size=1)
            rospy.Subscriber(topics["environment"], Environment, self._env_cb, callback_args=vehicle_name, queue_size=1)
            rospy.Subscriber(topics["global_gps"], NavSatFix, self._gps_cb, callback_args=vehicle_name, queue_size=1)
            if vehicle_kind == "car":
                rospy.Subscriber(topics["car_state"], CarState, self._car_state_cb, callback_args=vehicle_name, queue_size=1)

    def _odom_cb(self, msg, vehicle_name):
        self.snapshots[vehicle_name]["odom"] = msg

    def _env_cb(self, msg, vehicle_name):
        self.snapshots[vehicle_name]["env"] = msg

    def _gps_cb(self, msg, vehicle_name):
        self.snapshots[vehicle_name]["gps"] = msg

    def _car_state_cb(self, msg, vehicle_name):
        self.snapshots[vehicle_name]["car_state"] = msg

    def print_summary(self, event):
        print("\n=== Vehicle State Snapshot ===")
        for vehicle_name, snapshot in self.snapshots.items():
            odom = snapshot["odom"]
            gps = snapshot["gps"]
            env = snapshot["env"]
            car_state = snapshot["car_state"]

            if odom is None:
                print(f"{vehicle_name}: waiting for odom")
                continue

            position = odom.pose.pose.position
            linear = odom.twist.twist.linear
            text = (
                f"{vehicle_name} [{snapshot['kind']}] "
                f"pos=({position.x:.2f}, {position.y:.2f}, {position.z:.2f}) "
                f"vel=({linear.x:.2f}, {linear.y:.2f}, {linear.z:.2f})"
            )
            if gps is not None:
                text += f" gps=({gps.latitude:.6f}, {gps.longitude:.6f}, {gps.altitude:.2f})"
            if env is not None:
                text += f" temp={env.temperature:.2f}C air={env.air_density:.3f}"
            if car_state is not None:
                text += f" speed={car_state.speed:.2f} gear={car_state.gear} rpm={car_state.rpm:.1f}"
            print(text)


def main():
    parser = argparse.ArgumentParser(description="Monitor ROS vehicle states from AirSim_Multi.")
    parser.add_argument("--settings", default=None, help="Path to settings.json inside WSL.")
    parser.add_argument("--vehicle", action="append", help="Only monitor the specified vehicle. Repeatable.")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--print-rate", type=float, default=2.0)
    args = parser.parse_args()

    settings_path = detect_settings_path(args.settings)
    settings = load_settings(settings_path)
    vehicle_map = selected_vehicles(settings, args.vehicle)

    rospy.init_node("airsim_multi_vehicle_state_monitor_ros")
    monitor = VehicleStateMonitor(vehicle_map, args.namespace)
    rospy.Timer(rospy.Duration(max(0.1, 1.0 / args.print_rate)), monitor.print_summary)
    rospy.spin()


if __name__ == "__main__":
    main()

