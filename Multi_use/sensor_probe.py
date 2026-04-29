import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent


def bootstrap_python_client():
    candidates = []

    env_python_client = os.environ.get("AIRSIM_PYTHON_CLIENT")
    if env_python_client:
        candidates.append(Path(env_python_client))

    env_repo_root = os.environ.get("AIRSIM_REPO_ROOT")
    if env_repo_root:
        candidates.append(Path(env_repo_root) / "PythonClient")

    for parent in [SCRIPT_DIR, *SCRIPT_DIR.parents]:
        candidates.append(parent / "PythonClient")

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)

        if candidate.is_dir():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
            return

    raise ModuleNotFoundError(
        "Cannot find AirSim PythonClient. Set AIRSIM_PYTHON_CLIENT or AIRSIM_REPO_ROOT, "
        "or place this script inside an AirSim_Multi repository."
    )


bootstrap_python_client()

import airsim


SETTINGS_PATH = Path.home() / "Documents" / "AirSim" / "settings.json"
OUTPUT_ROOT = SCRIPT_DIR / "sensor_probe_outputs"
MULTIROTOR_TYPES = {"simpleflight", "px4multirotor", "arducopter", "arducoptersolo"}
CAR_TYPES = {"physxcar", "ardurover"}
FLOAT_IMAGE_TYPES = {airsim.ImageType.DepthPlanar, airsim.ImageType.DepthPerspective}
IMAGE_TYPE_NAMES = {
    airsim.ImageType.Scene: "Scene",
    airsim.ImageType.DepthPlanar: "DepthPlanar",
    airsim.ImageType.DepthPerspective: "DepthPerspective",
    airsim.ImageType.DepthVis: "DepthVis",
    airsim.ImageType.DisparityNormalized: "DisparityNormalized",
    airsim.ImageType.Segmentation: "Segmentation",
    airsim.ImageType.SurfaceNormals: "SurfaceNormals",
    airsim.ImageType.Infrared: "Infrared",
    airsim.ImageType.OpticalFlow: "OpticalFlow",
    airsim.ImageType.OpticalFlowVis: "OpticalFlowVis",
}


def load_settings(settings_path: Path) -> dict:
    return json.loads(settings_path.read_text(encoding="utf-8-sig"))


def infer_vehicle_kind(vehicle_config: dict) -> str:
    vehicle_type = str(vehicle_config.get("VehicleType", "")).strip().lower()
    if vehicle_type in MULTIROTOR_TYPES:
        return "multirotor"
    if vehicle_type in CAR_TYPES:
        return "car"
    return "unknown"


def connect_clients(host: str, settings: dict):
    api_port = int(settings.get("ApiServerPort", 41451))
    api_port_cv = int(settings.get("ApiServerPortCV", api_port))
    api_port_car = int(settings.get("ApiServerPortCar", 41461))
    api_port_multirotor = int(settings.get("ApiServerPortMultirotor", api_port))

    generic = airsim.VehicleClient(ip=host, port=api_port_cv)
    generic.confirmConnection()

    multi = airsim.MultirotorClient(ip=host, port=api_port_multirotor)
    car = airsim.CarClient(ip=host, port=api_port_car)
    return generic, multi, car


def build_vehicle_map(settings: dict, selected_vehicles: list[str] | None) -> dict:
    vehicles = settings.get("Vehicles", {})
    if not selected_vehicles:
        return vehicles

    selected = {}
    for vehicle_name in selected_vehicles:
        if vehicle_name not in vehicles:
            raise KeyError(f"{vehicle_name!r} is not present in settings.json Vehicles")
        selected[vehicle_name] = vehicles[vehicle_name]
    return selected


def validate_subwindows(settings: dict) -> list[str]:
    messages = []
    vehicles = settings.get("Vehicles", {})
    for subwindow in settings.get("SubWindows", []):
        window_id = subwindow.get("WindowID", "?")
        vehicle_name = subwindow.get("VehicleName", "")
        camera_name = subwindow.get("CameraName", "")

        vehicle_cfg = vehicles.get(vehicle_name)
        if not isinstance(vehicle_cfg, dict):
            messages.append(f"[WARN] SubWindow {window_id}: vehicle {vehicle_name!r} is missing in Vehicles")
            continue

        camera_cfg = vehicle_cfg.get("Cameras", {}).get(camera_name)
        if not isinstance(camera_cfg, dict):
            messages.append(
                f"[WARN] SubWindow {window_id}: camera {camera_name!r} is not configured under vehicle {vehicle_name!r}"
            )
            continue

        messages.append(f"[OK] SubWindow {window_id}: {vehicle_name}/{camera_name}")

    return messages


def collect_image_types(camera_cfg: dict) -> list[int]:
    image_types = []
    for capture_setting in camera_cfg.get("CaptureSettings", []):
        image_type = int(capture_setting.get("ImageType", airsim.ImageType.Scene))
        if image_type not in image_types:
            image_types.append(image_type)
    if not image_types:
        image_types.append(airsim.ImageType.Scene)
    return image_types


def image_request(camera_name: str, image_type: int) -> airsim.ImageRequest:
    if image_type in FLOAT_IMAGE_TYPES:
        return airsim.ImageRequest(camera_name, image_type, pixels_as_float=True, compress=False)
    return airsim.ImageRequest(camera_name, image_type, pixels_as_float=False, compress=True)


def image_suffix(image_type: int) -> str:
    if image_type in FLOAT_IMAGE_TYPES:
        return ".pfm"
    return ".png"


def pose_to_dict(pose) -> dict:
    return {
        "position": {
            "x": pose.position.x_val,
            "y": pose.position.y_val,
            "z": pose.position.z_val,
        },
        "orientation": {
            "x": pose.orientation.x_val,
            "y": pose.orientation.y_val,
            "z": pose.orientation.z_val,
            "w": pose.orientation.w_val,
        },
    }


def save_image_response(output_dir: Path, vehicle_name: str, camera_name: str, response) -> dict:
    image_type = int(response.image_type)
    image_name = IMAGE_TYPE_NAMES.get(image_type, f"ImageType{image_type}")
    file_path = output_dir / f"{vehicle_name}__{camera_name}__{image_name}{image_suffix(image_type)}"

    if image_type in FLOAT_IMAGE_TYPES:
        pfm_array = airsim.get_pfm_array(response).astype(np.float32)
        airsim.write_pfm(str(file_path), pfm_array)
        stats = {
            "min": float(np.min(pfm_array)),
            "max": float(np.max(pfm_array)),
            "mean": float(np.mean(pfm_array)),
        }
    else:
        airsim.write_file(str(file_path), response.image_data_uint8)
        stats = {
            "bytes": len(response.image_data_uint8),
        }

    return {
        "camera_name": camera_name,
        "image_type": image_type,
        "image_type_name": image_name,
        "file": str(file_path),
        "width": int(response.width),
        "height": int(response.height),
        "stats": stats,
        "camera_pose": {
            "position": {
                "x": response.camera_position.x_val,
                "y": response.camera_position.y_val,
                "z": response.camera_position.z_val,
            },
            "orientation": {
                "x": response.camera_orientation.x_val,
                "y": response.camera_orientation.y_val,
                "z": response.camera_orientation.z_val,
                "w": response.camera_orientation.w_val,
            },
        },
    }


def save_lidar_points(output_dir: Path, vehicle_name: str, lidar_name: str, lidar_data) -> dict:
    points = np.array(lidar_data.point_cloud, dtype=np.float32)
    if points.size == 0:
        point_count = 0
        file_path = None
    else:
        points = points.reshape((-1, 3))
        point_count = int(points.shape[0])
        file_path = output_dir / f"{vehicle_name}__{lidar_name}__pointcloud.xyz"
        np.savetxt(file_path, points, fmt="%.6f")

    return {
        "lidar_name": lidar_name,
        "point_count": point_count,
        "file": str(file_path) if file_path else None,
        "time_stamp": int(lidar_data.time_stamp),
        "pose": pose_to_dict(lidar_data.pose),
    }


def get_vehicle_client(kind: str, multirotor_client, car_client):
    if kind == "multirotor":
        return multirotor_client
    if kind == "car":
        return car_client
    raise ValueError(f"Unsupported vehicle kind for typed sensor access: {kind}")


def probe_vehicle(
    generic_client,
    multirotor_client,
    car_client,
    vehicle_name: str,
    vehicle_cfg: dict,
    output_dir: Path,
) -> dict:
    kind = infer_vehicle_kind(vehicle_cfg)
    vehicle_summary = {
        "vehicle_name": vehicle_name,
        "vehicle_kind": kind,
        "cameras": [],
        "lidars": [],
    }

    print(f"\n[{vehicle_name}] kind={kind}")
    vehicle_pose = generic_client.simGetVehiclePose(vehicle_name=vehicle_name)
    print(
        f"  pose=({vehicle_pose.position.x_val:.2f}, {vehicle_pose.position.y_val:.2f}, {vehicle_pose.position.z_val:.2f})"
    )
    vehicle_summary["vehicle_pose"] = pose_to_dict(vehicle_pose)

    camera_configs = vehicle_cfg.get("Cameras", {})
    if camera_configs:
        for camera_name, camera_cfg in camera_configs.items():
            camera_info = generic_client.simGetCameraInfo(camera_name, vehicle_name=vehicle_name)
            image_types = collect_image_types(camera_cfg)
            requests = [image_request(camera_name, image_type) for image_type in image_types]
            responses = generic_client.simGetImages(requests, vehicle_name=vehicle_name)
            print(f"  camera {camera_name}: fov={camera_info.fov:.1f}, requests={len(requests)}")

            for response in responses:
                image_record = save_image_response(output_dir, vehicle_name, camera_name, response)
                vehicle_summary["cameras"].append(
                    {
                        "camera_info": {
                            "fov": float(camera_info.fov),
                            "pose": pose_to_dict(camera_info.pose),
                        },
                        **image_record,
                    }
                )
                print(
                    f"    - {image_record['image_type_name']}: {image_record['width']}x{image_record['height']} -> {image_record['file']}"
                )
    else:
        print("  no camera config in settings")

    sensor_configs = vehicle_cfg.get("Sensors", {})
    lidar_names = [name for name, cfg in sensor_configs.items() if int(cfg.get("SensorType", -1)) == 6 and cfg.get("Enabled", True)]
    if lidar_names:
        typed_client = get_vehicle_client(kind, multirotor_client, car_client)
        for lidar_name in lidar_names:
            lidar_data = typed_client.getLidarData(lidar_name=lidar_name, vehicle_name=vehicle_name)
            lidar_record = save_lidar_points(output_dir, vehicle_name, lidar_name, lidar_data)
            vehicle_summary["lidars"].append(lidar_record)
            print(
                f"  lidar {lidar_name}: points={lidar_record['point_count']} -> {lidar_record['file'] or '(empty point cloud)'}"
            )
    else:
        print("  no lidar config in settings")

    return vehicle_summary


def parse_args():
    parser = argparse.ArgumentParser(description="Probe AirSim camera/lidar sensors and save one-shot samples.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--settings", default=str(SETTINGS_PATH))
    parser.add_argument("--vehicle", action="append", help="Only probe the specified vehicle name. Repeatable.")
    parser.add_argument("--list-only", action="store_true", help="Only validate settings and list sensors, do not grab samples.")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    return parser.parse_args()


def main():
    args = parse_args()
    settings_path = Path(args.settings)
    settings = load_settings(settings_path)
    selected_vehicles = build_vehicle_map(settings, args.vehicle)

    print(f"Using airsim module: {airsim.__file__}")
    print(f"Loaded settings: {settings_path}")
    print(f"SimMode: {settings.get('SimMode', '(unset)')}")
    print("SubWindow validation:")
    for message in validate_subwindows(settings):
        print(f"  {message}")

    for vehicle_name, vehicle_cfg in selected_vehicles.items():
        kind = infer_vehicle_kind(vehicle_cfg)
        camera_names = list(vehicle_cfg.get("Cameras", {}).keys())
        lidar_names = [
            name
            for name, cfg in vehicle_cfg.get("Sensors", {}).items()
            if int(cfg.get("SensorType", -1)) == 6 and cfg.get("Enabled", True)
        ]
        print(f"- {vehicle_name}: kind={kind}, cameras={camera_names or '[]'}, lidars={lidar_names or '[]'}")

    if args.list_only:
        return

    generic_client, multirotor_client, car_client = connect_clients(args.host, settings)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / f"sensor_probe_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "settings_path": str(settings_path),
        "sim_mode": settings.get("SimMode", ""),
        "output_dir": str(output_dir),
        "vehicles": [],
    }

    for vehicle_name, vehicle_cfg in selected_vehicles.items():
        report["vehicles"].append(
            probe_vehicle(
                generic_client,
                multirotor_client,
                car_client,
                vehicle_name,
                vehicle_cfg,
                output_dir,
            )
        )

    report_path = output_dir / "sensor_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved probe report to: {report_path}")


if __name__ == "__main__":
    main()
