#!/usr/bin/env python3

import glob
import json
import os
from pathlib import Path


MULTIROTOR_TYPES = {"simpleflight", "px4multirotor", "arducopter", "arducoptersolo"}
CAR_TYPES = {"physxcar", "ardurover"}

SENSOR_TYPE_TO_TOPIC = {
    1: "altimeter/{sensor_name}",
    2: "imu/{sensor_name}",
    3: "gps/{sensor_name}",
    4: "magnetometer/{sensor_name}",
    5: "distance/{sensor_name}",
    6: "lidar/{sensor_name}",
}

IMAGE_TYPE_TO_NAME = {
    0: "Scene",
    1: "DepthPlanar",
    2: "DepthPerspective",
    3: "DepthVis",
    4: "DisparityNormalized",
    5: "Segmentation",
    6: "SurfaceNormals",
    7: "Infrared",
    8: "OpticalFlow",
    9: "OpticalFlowVis",
}


def detect_settings_path(cli_value=None):
    candidates = []
    if cli_value:
        candidates.append(Path(cli_value))

    env_value = os.environ.get("AIRSIM_SETTINGS_PATH")
    if env_value:
        candidates.append(Path(env_value))

    for match in sorted(glob.glob("/mnt/c/Users/*/Documents/AirSim/settings.json")):
        candidates.append(Path(match))

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Cannot find AirSim settings.json. Pass --settings or set AIRSIM_SETTINGS_PATH."
    )


def load_settings(settings_path):
    # Windows-side settings.json may be saved with a UTF-8 BOM.
    with open(settings_path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def normalize_namespace(namespace):
    stripped = namespace.strip().strip("/")
    return "/" + stripped if stripped else ""


def topic_name(namespace, *parts):
    base = normalize_namespace(namespace)
    suffix = "/".join(part.strip("/") for part in parts if part)
    return f"{base}/{suffix}" if base else f"/{suffix}"


def infer_vehicle_kind(vehicle_config):
    vehicle_type = str(vehicle_config.get("VehicleType", "")).strip().lower()
    if vehicle_type in MULTIROTOR_TYPES:
        return "multirotor"
    if vehicle_type in CAR_TYPES:
        return "car"
    return "unknown"


def selected_vehicles(settings, selected_names=None):
    vehicles = settings.get("Vehicles", {})
    if not selected_names:
        return vehicles

    selected = {}
    for name in selected_names:
        if name not in vehicles:
            raise KeyError(f"Vehicle {name!r} not found in settings Vehicles")
        selected[name] = vehicles[name]
    return selected


def image_type_name(image_type):
    return IMAGE_TYPE_TO_NAME.get(int(image_type), f"ImageType{int(image_type)}")


def camera_capture_entries(vehicle_name, vehicle_config, namespace):
    entries = []
    for camera_name, camera_config in vehicle_config.get("Cameras", {}).items():
        for capture_setting in camera_config.get("CaptureSettings", []):
            image_type = int(capture_setting.get("ImageType", 0))
            image_name = image_type_name(image_type)
            image_topic = topic_name(namespace, vehicle_name, camera_name, image_name)
            entries.append(
                {
                    "vehicle_name": vehicle_name,
                    "camera_name": camera_name,
                    "image_type": image_type,
                    "image_name": image_name,
                    "image_topic": image_topic,
                    "camera_info_topic": image_topic + "/camera_info",
                    "publish_to_ros": int(capture_setting.get("PublishToRos", 0)),
                    "width": int(capture_setting.get("Width", 0)),
                    "height": int(capture_setting.get("Height", 0)),
                }
            )
    return entries


def sensor_entries(vehicle_name, vehicle_config, namespace):
    entries = []
    for sensor_name, sensor_config in vehicle_config.get("Sensors", {}).items():
        if not sensor_config.get("Enabled", True):
            continue

        sensor_type = int(sensor_config.get("SensorType", -1))
        topic_suffix_template = SENSOR_TYPE_TO_TOPIC.get(sensor_type)
        if not topic_suffix_template:
            continue

        topic = topic_name(namespace, vehicle_name, topic_suffix_template.format(sensor_name=sensor_name))
        entries.append(
            {
                "vehicle_name": vehicle_name,
                "sensor_name": sensor_name,
                "sensor_type": sensor_type,
                "topic": topic,
            }
        )
    return entries


def state_topics(vehicle_name, vehicle_kind, namespace):
    topics = {
        "odom": topic_name(namespace, vehicle_name, "odom_local_ned"),
        "environment": topic_name(namespace, vehicle_name, "environment"),
        "global_gps": topic_name(namespace, vehicle_name, "global_gps"),
    }
    if vehicle_kind == "car":
        topics["car_state"] = topic_name(namespace, vehicle_name, "car_state")
    return topics


def save_ascii_pcd(file_path, points):
    point_count = len(points)
    header = "\n".join(
        [
            "# .PCD v0.7",
            "VERSION 0.7",
            "FIELDS x y z",
            "SIZE 4 4 4",
            "TYPE F F F",
            "COUNT 1 1 1",
            f"WIDTH {point_count}",
            "HEIGHT 1",
            "VIEWPOINT 0 0 0 1 0 0 0",
            f"POINTS {point_count}",
            "DATA ascii",
        ]
    )
    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write(header + "\n")
        for x_val, y_val, z_val in points:
            handle.write(f"{x_val} {y_val} {z_val}\n")
