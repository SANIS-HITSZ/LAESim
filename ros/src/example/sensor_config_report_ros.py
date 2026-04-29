#!/usr/bin/env python3

import argparse
import json

import rospy

from _ros_example_common import (
    camera_capture_entries,
    detect_settings_path,
    image_type_name,
    infer_vehicle_kind,
    load_settings,
    selected_vehicles,
    sensor_entries,
)


def main():
    parser = argparse.ArgumentParser(description="Report AirSim_Multi sensor config and ROS topic visibility.")
    parser.add_argument("--settings", default=None, help="Path to settings.json inside WSL.")
    parser.add_argument("--vehicle", action="append", help="Only inspect the specified vehicle. Repeatable.")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--wait-secs", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="Emit a JSON report instead of plain text.")
    args = parser.parse_args()

    settings_path = detect_settings_path(args.settings)
    settings = load_settings(settings_path)
    vehicle_map = selected_vehicles(settings, args.vehicle)

    rospy.init_node("airsim_multi_sensor_config_report_ros", anonymous=True)
    if args.wait_secs > 0:
        rospy.sleep(args.wait_secs)

    published_topics = dict(rospy.get_published_topics())
    report = {
        "settings_path": str(settings_path),
        "namespace": args.namespace,
        "vehicles": [],
    }

    for vehicle_name, vehicle_config in vehicle_map.items():
        vehicle_kind = infer_vehicle_kind(vehicle_config)
        vehicle_report = {
            "vehicle_name": vehicle_name,
            "vehicle_kind": vehicle_kind,
            "cameras": [],
            "sensors": [],
        }

        for entry in camera_capture_entries(vehicle_name, vehicle_config, args.namespace):
            vehicle_report["cameras"].append(
                {
                    **entry,
                    "image_topic_up": entry["image_topic"] in published_topics,
                    "camera_info_topic_up": entry["camera_info_topic"] in published_topics,
                    "image_topic_type": published_topics.get(entry["image_topic"], ""),
                    "camera_info_topic_type": published_topics.get(entry["camera_info_topic"], ""),
                }
            )

        for entry in sensor_entries(vehicle_name, vehicle_config, args.namespace):
            vehicle_report["sensors"].append(
                {
                    **entry,
                    "topic_up": entry["topic"] in published_topics,
                    "topic_type": published_topics.get(entry["topic"], ""),
                }
            )

        report["vehicles"].append(vehicle_report)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(f"Settings: {settings_path}")
    print(f"Namespace: {args.namespace}")
    for vehicle_report in report["vehicles"]:
        print(f"\n[{vehicle_report['vehicle_name']}] kind={vehicle_report['vehicle_kind']}")
        if vehicle_report["cameras"]:
            print("  Cameras:")
            for camera in vehicle_report["cameras"]:
                image_flag = "UP" if camera["image_topic_up"] else "MISS"
                info_flag = "UP" if camera["camera_info_topic_up"] else "MISS"
                print(
                    f"    - {camera['camera_name']} / {image_type_name(camera['image_type'])}: "
                    f"img[{image_flag}] {camera['image_topic']}  info[{info_flag}] {camera['camera_info_topic']}"
                )
        else:
            print("  Cameras: none")

        if vehicle_report["sensors"]:
            print("  Sensors:")
            for sensor in vehicle_report["sensors"]:
                topic_flag = "UP" if sensor["topic_up"] else "MISS"
                print(f"    - type={sensor['sensor_type']} {sensor['sensor_name']}: [{topic_flag}] {sensor['topic']}")
        else:
            print("  Sensors: none")


if __name__ == "__main__":
    main()

