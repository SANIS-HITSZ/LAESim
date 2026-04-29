#!/usr/bin/env python3

import argparse
import os
from datetime import datetime
from pathlib import Path

import cv2
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image

from _ros_example_common import camera_capture_entries, detect_settings_path, load_settings, selected_vehicles


class CameraRecorder:
    def __init__(self, output_dir, max_per_topic):
        self.output_dir = output_dir
        self.max_per_topic = max_per_topic
        self.bridge = CvBridge()
        self.counts = {}
        self.targets = set()

    def add_target(self, topic_name):
        self.targets.add(topic_name)
        self.counts[topic_name] = 0

    def callback(self, msg, context):
        topic_name = context["image_topic"]
        if self.counts[topic_name] >= self.max_per_topic:
            return

        image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
        file_name = (
            f"{context['vehicle_name']}__{context['camera_name']}__{context['image_name']}__"
            f"{self.counts[topic_name]:03d}.png"
        )
        file_path = self.output_dir / file_name
        cv2.imwrite(str(file_path), image)

        self.counts[topic_name] += 1
        print(f"saved {topic_name} -> {file_path}")

        if all(count >= self.max_per_topic for count in self.counts.values()):
            rospy.signal_shutdown("camera capture completed")


def main():
    parser = argparse.ArgumentParser(description="Record camera topics from AirSim_Multi ROS bridge.")
    parser.add_argument("--settings", default=None, help="Path to settings.json inside WSL.")
    parser.add_argument("--vehicle", action="append", help="Only record the specified vehicle. Repeatable.")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--output-root", default="./camera_record_ros_outputs")
    parser.add_argument("--max-per-topic", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    settings_path = detect_settings_path(args.settings)
    settings = load_settings(settings_path)
    vehicle_map = selected_vehicles(settings, args.vehicle)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / f"camera_record_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    rospy.init_node("airsim_multi_camera_record_ros")
    recorder = CameraRecorder(output_dir, args.max_per_topic)

    for vehicle_name, vehicle_config in vehicle_map.items():
        for entry in camera_capture_entries(vehicle_name, vehicle_config, args.namespace):
            recorder.add_target(entry["image_topic"])
            rospy.Subscriber(entry["image_topic"], Image, recorder.callback, callback_args=entry, queue_size=1)

    if not recorder.targets:
        print("No camera topics defined from settings.")
        return

    print(f"Recording {len(recorder.targets)} camera topics to {output_dir}")
    timeout_time = rospy.Time.now() + rospy.Duration(args.timeout)
    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        if rospy.Time.now() > timeout_time:
            print("Camera recording timed out.")
            break
        rate.sleep()


if __name__ == "__main__":
    main()

