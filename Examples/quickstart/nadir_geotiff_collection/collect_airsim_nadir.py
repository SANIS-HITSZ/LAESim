from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "PythonClient"))

import airsim
from PIL import Image

from coverage_mission import (
    MissionConfig,
    TRAJECTORY_FIELDNAMES,
    build_coverage_route,
    default_tif_path,
    draw_route_preview,
    load_geotiff_reference,
    write_mission_summary,
    write_planned_trajectory_csv,
)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Fly an AirSim UAV coverage route and collect 10 Hz nadir images plus GPS."
    )
    parser.add_argument("--host", default="", help="AirSim server IP; empty means localhost.")
    parser.add_argument("--port", type=int, default=41471)
    parser.add_argument("--world-port", type=int, default=41451)
    parser.add_argument("--vehicle", default="UAV")
    parser.add_argument("--camera", default="nadir")
    parser.add_argument("--gps", default="gps")
    parser.add_argument("--tif", type=Path, default=default_tif_path())
    parser.add_argument("--output", type=Path, default=script_dir / "output" / "airsim_dataset")
    parser.add_argument("--distance-m", type=float, default=1000.0)
    parser.add_argument("--speed-mps", type=float, default=4.6)
    parser.add_argument("--altitude-m", type=float, default=35.0)
    parser.add_argument("--duration-s", type=float, default=218.0)
    parser.add_argument("--rate-hz", type=float, default=10.0)
    parser.add_argument("--fov-deg", type=float, default=90.0)
    parser.add_argument("--lanes", type=int, default=5)
    parser.add_argument("--cross-track-overlap", type=float, default=0.10)
    parser.add_argument("--turn-segments", type=int, default=12)
    parser.add_argument("--yaw-deg", type=float, default=0.0)
    parser.add_argument(
        "--image-rotation-deg",
        type=int,
        choices=(0, 90, 180, 270),
        default=0,
        help="Clockwise rotation applied to saved camera frames for GeoTIFF alignment.",
    )
    parser.add_argument("--preposition-speed-mps", type=float, default=6.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--no-land-after",
        action="store_true",
        help="Leave the UAV hovering after collection instead of landing and disarming.",
    )
    return parser.parse_args()


def prepare_output_directory(output_dir: Path, overwrite: bool) -> None:
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is not empty: {output_dir}; use --overwrite to replace it"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def vector_values(vector) -> tuple[float, float, float]:
    return float(vector.x_val), float(vector.y_val), float(vector.z_val)


@dataclass(frozen=True)
class SceneMapTransform:
    enabled: bool = False
    center_north_m: float = 0.0
    center_east_m: float = 0.0
    center_down_m: float = 0.0
    yaw_deg: float = 0.0

    def map_to_api(self, position: tuple[float, float, float]) -> tuple[float, float, float]:
        yaw_rad = math.radians(self.yaw_deg)
        cos_yaw = math.cos(yaw_rad)
        sin_yaw = math.sin(yaw_rad)
        north_m, east_m, down_m = position
        return (
            self.center_north_m + cos_yaw * north_m - sin_yaw * east_m,
            self.center_east_m + sin_yaw * north_m + cos_yaw * east_m,
            self.center_down_m + down_m,
        )

    def api_to_map(self, position: tuple[float, float, float]) -> tuple[float, float, float]:
        yaw_rad = math.radians(self.yaw_deg)
        cos_yaw = math.cos(yaw_rad)
        sin_yaw = math.sin(yaw_rad)
        delta_north_m = position[0] - self.center_north_m
        delta_east_m = position[1] - self.center_east_m
        return (
            cos_yaw * delta_north_m + sin_yaw * delta_east_m,
            -sin_yaw * delta_north_m + cos_yaw * delta_east_m,
            position[2] - self.center_down_m,
        )

    def api_vector_to_map(self, vector: tuple[float, float, float]) -> tuple[float, float, float]:
        yaw_rad = math.radians(self.yaw_deg)
        cos_yaw = math.cos(yaw_rad)
        sin_yaw = math.sin(yaw_rad)
        return (
            cos_yaw * vector[0] + sin_yaw * vector[1],
            -sin_yaw * vector[0] + cos_yaw * vector[1],
            vector[2],
        )


def quaternion_values(quaternion) -> tuple[float, float, float, float]:
    return (
        float(quaternion.x_val),
        float(quaternion.y_val),
        float(quaternion.z_val),
        float(quaternion.w_val),
    )


def kinematics_trajectory_row(
    kinematics,
    *,
    sample_index: int,
    schedule_frame_index: int,
    scheduled_time_s: float,
    actual_elapsed_s: float,
    wall_time_utc: str,
    state_timestamp_ns: int,
    image_timestamp_ns: int,
    source: str,
    reference,
    scene_map_transform: SceneMapTransform,
) -> dict[str, object]:
    position = scene_map_transform.api_to_map(vector_values(kinematics.position))
    velocity = scene_map_transform.api_vector_to_map(
        vector_values(kinematics.linear_velocity)
    )
    acceleration = scene_map_transform.api_vector_to_map(
        vector_values(kinematics.linear_acceleration)
    )
    orientation = quaternion_values(kinematics.orientation)
    angular_velocity = vector_values(kinematics.angular_velocity)
    angular_acceleration = vector_values(kinematics.angular_acceleration)
    longitude_deg, latitude_deg = reference.local_to_lon_lat(position[1], position[0])
    return {
        "sample_index": sample_index,
        "schedule_frame_index": schedule_frame_index,
        "scheduled_time_s": f"{scheduled_time_s:.3f}",
        "actual_elapsed_s": f"{actual_elapsed_s:.6f}",
        "wall_time_utc": wall_time_utc,
        "state_timestamp_ns": state_timestamp_ns,
        "image_timestamp_ns": image_timestamp_ns,
        "source": source,
        "position_north_m": f"{position[0]:.6f}",
        "position_east_m": f"{position[1]:.6f}",
        "position_down_m": f"{position[2]:.6f}",
        "velocity_north_mps": f"{velocity[0]:.6f}",
        "velocity_east_mps": f"{velocity[1]:.6f}",
        "velocity_down_mps": f"{velocity[2]:.6f}",
        "acceleration_north_mps2": f"{acceleration[0]:.6f}",
        "acceleration_east_mps2": f"{acceleration[1]:.6f}",
        "acceleration_down_mps2": f"{acceleration[2]:.6f}",
        "orientation_qx": f"{orientation[0]:.9f}",
        "orientation_qy": f"{orientation[1]:.9f}",
        "orientation_qz": f"{orientation[2]:.9f}",
        "orientation_qw": f"{orientation[3]:.9f}",
        "angular_velocity_x_radps": f"{angular_velocity[0]:.9f}",
        "angular_velocity_y_radps": f"{angular_velocity[1]:.9f}",
        "angular_velocity_z_radps": f"{angular_velocity[2]:.9f}",
        "angular_acceleration_x_radps2": f"{angular_acceleration[0]:.9f}",
        "angular_acceleration_y_radps2": f"{angular_acceleration[1]:.9f}",
        "angular_acceleration_z_radps2": f"{angular_acceleration[2]:.9f}",
        "longitude_deg": f"{longitude_deg:.10f}",
        "latitude_deg": f"{latitude_deg:.10f}",
        "altitude_m": f"{-position[2]:.3f}",
    }


def metric_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "mean": 0.0, "rmse": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "rmse": math.sqrt(sum(value * value for value in values) / len(values)),
        "max": max(values),
    }


def configure_nadir_camera(client: airsim.MultirotorClient, camera_name: str, vehicle_name: str) -> None:
    camera_pose = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, 0.0),
        airsim.to_quaternion(math.radians(-90.0), 0.0, 0.0),
    )
    client.simSetCameraPose(camera_name, camera_pose, vehicle_name=vehicle_name)
    camera_info = client.simGetCameraInfo(camera_name, vehicle_name=vehicle_name)
    print(f"Camera {camera_name}: fov={float(camera_info.fov):.2f} deg")


def save_scene_response(response, output_path: Path, rotation_deg: int = 0) -> None:
    if int(response.width) <= 0 or int(response.height) <= 0:
        raise RuntimeError("AirSim returned an empty camera frame")
    image_bytes = bytes(response.image_data_uint8)
    if rotation_deg == 0:
        output_path.write_bytes(image_bytes)
        return
    transpose_by_clockwise_rotation = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.transpose(transpose_by_clockwise_rotation[rotation_deg]).save(output_path)


def make_client(host: str, port: int) -> airsim.MultirotorClient:
    client = airsim.MultirotorClient(ip=host, port=port, timeout_value=3600)
    client.confirmConnection()
    return client


def get_scene_map_transform(host: str, port: int) -> SceneMapTransform:
    client = airsim.VehicleClient(ip=host, port=port, timeout_value=30)
    client.confirmConnection()
    if hasattr(client, "simGetSceneMapInfo"):
        info = client.simGetSceneMapInfo()
        info_value = lambda name: getattr(info, name)
    else:
        info = client.client.call("simGetSceneMapInfo")
        info_value = lambda name: info["z_val" if name == "z" else name]
    if not info_value("enabled"):
        print("SceneMap is disabled; using the vehicle-local NED frame without an offset.")
        return SceneMapTransform()
    object_name = str(info_value("object_name"))
    pixel_coordinate_frame = str(info_value("pixel_coordinate_frame"))
    actor_pose = client.simGetObjectPose(object_name)
    if actor_pose.containsNan():
        raise RuntimeError(f"SceneMap actor is unavailable: {object_name}")
    actor_position = vector_values(actor_pose.position)
    configured_position = (
        float(info_value("center_x")),
        float(info_value("center_y")),
        float(info_value("z")),
    )
    position_error_m = math.dist(actor_position, configured_position)
    if position_error_m > 0.1:
        raise RuntimeError(
            "SceneMap actor pose does not match SceneMapInfo: "
            f"actor={actor_position}, configured={configured_position}, "
            f"error={position_error_m:.3f} m. Rebuild the LAESim V1.5 AirSim plugin."
        )
    orientation = actor_pose.orientation
    actor_yaw_deg = math.degrees(
        math.atan2(
            2.0
            * (
                float(orientation.w_val) * float(orientation.z_val)
                + float(orientation.x_val) * float(orientation.y_val)
            ),
            1.0
            - 2.0
            * (
                float(orientation.y_val) * float(orientation.y_val)
                + float(orientation.z_val) * float(orientation.z_val)
            ),
        )
    )
    north_up_frames = {
        "northup",
        "north_up",
        "googleearth",
        "google_earth",
        "satellite",
    }
    configured_yaw_deg = float(info_value("yaw"))
    expected_actor_yaw_deg = configured_yaw_deg + (
        90.0 if pixel_coordinate_frame.lower() in north_up_frames else 0.0
    )
    yaw_error_deg = (
        actor_yaw_deg - expected_actor_yaw_deg + 180.0
    ) % 360.0 - 180.0
    if abs(yaw_error_deg) > 0.1:
        raise RuntimeError(
            "SceneMap actor yaw does not match its pixel coordinate frame: "
            f"actor={actor_yaw_deg:.3f} deg, expected={expected_actor_yaw_deg:.3f} deg, "
            f"frame={pixel_coordinate_frame}. Rebuild the LAESim V1.5 AirSim plugin."
        )
    transform = SceneMapTransform(
        enabled=True,
        center_north_m=float(info_value("center_x")),
        center_east_m=float(info_value("center_y")),
        center_down_m=float(info_value("z")),
        yaw_deg=configured_yaw_deg,
    )
    print(
        "SceneMap transform: "
        f"center=({transform.center_north_m:.3f}, "
        f"{transform.center_east_m:.3f}, {transform.center_down_m:.3f}) m, "
        f"yaw={transform.yaw_deg:.3f} deg"
    )
    return transform


def collect(args: argparse.Namespace) -> Path:
    output_dir = args.output.expanduser().resolve()
    prepare_output_directory(output_dir, args.overwrite)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    reference = load_geotiff_reference(args.tif)
    config = MissionConfig(
        distance_m=args.distance_m,
        speed_mps=args.speed_mps,
        altitude_m=args.altitude_m,
        duration_s=args.duration_s,
        rate_hz=args.rate_hz,
        horizontal_fov_deg=args.fov_deg,
        lane_count=args.lanes,
        cross_track_overlap=args.cross_track_overlap,
        turn_segments=args.turn_segments,
    )
    route = build_coverage_route(reference, config)
    scene_map_transform = get_scene_map_transform(args.host, args.world_port)
    draw_route_preview(route, output_dir / "route_preview.jpg")
    write_planned_trajectory_csv(route, output_dir / "planned_trajectory.csv")
    write_mission_summary(
        route,
        output_dir / "mission_summary.json",
        {
            "collection": {
                "backend": "airsim",
                "vehicle": args.vehicle,
                "camera": args.camera,
                "gps": args.gps,
                "host": args.host or "localhost",
                "port": args.port,
                "world_port": args.world_port,
                "fixed_yaw_deg": args.yaw_deg,
                "saved_image_rotation_deg": args.image_rotation_deg,
                "scene_map_transform": {
                    "enabled": scene_map_transform.enabled,
                    "center_north_m": scene_map_transform.center_north_m,
                    "center_east_m": scene_map_transform.center_east_m,
                    "center_down_m": scene_map_transform.center_down_m,
                    "yaw_deg": scene_map_transform.yaw_deg,
                },
            }
        },
    )

    client = make_client(args.host, args.port)
    client.enableApiControl(True, vehicle_name=args.vehicle)
    client.armDisarm(True, vehicle_name=args.vehicle)
    configure_nadir_camera(client, args.camera, args.vehicle)

    first_east_m, first_north_m = route.local_east_north_points[0]
    first_api_position = scene_map_transform.map_to_api(
        (first_north_m, first_east_m, -config.altitude_m)
    )
    fixed_yaw = airsim.YawMode(is_rate=False, yaw_or_rate=args.yaw_deg)
    print(f"Taking off {args.vehicle}...")
    client.takeoffAsync(timeout_sec=30.0, vehicle_name=args.vehicle).join()
    print("Pre-positioning at the first coverage waypoint...")
    client.moveToPositionAsync(
        first_api_position[0],
        first_api_position[1],
        first_api_position[2],
        args.preposition_speed_mps,
        timeout_sec=120.0,
        drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
        yaw_mode=fixed_yaw,
        vehicle_name=args.vehicle,
    ).join()

    path = [
        airsim.Vector3r(
            *scene_map_transform.map_to_api(
                (north_m, east_m, -config.altitude_m)
            )
        )
        for east_m, north_m in route.local_east_north_points[1:]
    ]
    metadata_path = output_dir / "metadata.csv"
    groundtruth_path = output_dir / "groundtruth.csv"
    estimated_path = output_dir / "estimated_trajectory.csv"
    error_path = output_dir / "trajectory_error.csv"
    fieldnames = [
        "capture_sequence",
        "schedule_frame_index",
        "scheduled_time_s",
        "actual_elapsed_s",
        "schedule_lateness_s",
        "wall_time_utc",
        "image_timestamp_ns",
        "image_file",
        "image_width_px",
        "image_height_px",
        "airsim_longitude_deg",
        "airsim_latitude_deg",
        "airsim_altitude_m",
        "groundtruth_longitude_deg",
        "groundtruth_latitude_deg",
        "groundtruth_north_m",
        "groundtruth_east_m",
        "groundtruth_down_m",
        "estimated_north_m",
        "estimated_east_m",
        "estimated_down_m",
        "estimated_position_error_3d_m",
        "planned_tracking_error_3d_m",
        "planned_path_distance_m",
        "planned_segment_index",
        "has_collided",
        "collision_object_name",
        "collision_object_id",
    ]
    error_fieldnames = [
        "capture_sequence",
        "schedule_frame_index",
        "scheduled_time_s",
        "actual_elapsed_s",
        "estimated_error_north_m",
        "estimated_error_east_m",
        "estimated_error_down_m",
        "estimated_position_error_horizontal_m",
        "estimated_position_error_3d_m",
        "estimated_velocity_error_3d_mps",
        "planned_tracking_error_north_m",
        "planned_tracking_error_east_m",
        "planned_tracking_error_down_m",
        "planned_tracking_error_horizontal_m",
        "planned_tracking_error_3d_m",
    ]

    image_request = airsim.ImageRequest(
        args.camera,
        airsim.ImageType.Scene,
        pixels_as_float=False,
        compress=True,
    )
    captured_count = 0
    skipped_schedule_frames = 0
    actual_distance_m = 0.0
    last_position: tuple[float, float, float] | None = None
    first_capture_elapsed_s: float | None = None
    last_capture_elapsed_s: float | None = None
    start_perf = time.perf_counter()
    start_wall_utc = utc_now_text()
    schedule_index = 0
    collection_error: str | None = None
    estimated_position_errors_m: list[float] = []
    estimated_velocity_errors_mps: list[float] = []
    planned_tracking_errors_m: list[float] = []

    print(
        f"Starting collection: duration={config.duration_s:.1f}s, "
        f"target={config.frame_count} frames at {config.rate_hz:.1f} Hz"
    )
    client.moveOnPathAsync(
        path,
        config.speed_mps,
        timeout_sec=config.duration_s + 60.0,
        drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
        yaw_mode=fixed_yaw,
        lookahead=max(1.0, config.speed_mps),
        adaptive_lookahead=1,
        vehicle_name=args.vehicle,
    )

    try:
        with ExitStack() as stack:
            metadata_stream = stack.enter_context(
                metadata_path.open("w", newline="", encoding="utf-8")
            )
            groundtruth_stream = stack.enter_context(
                groundtruth_path.open("w", newline="", encoding="utf-8")
            )
            estimated_stream = stack.enter_context(
                estimated_path.open("w", newline="", encoding="utf-8")
            )
            error_stream = stack.enter_context(
                error_path.open("w", newline="", encoding="utf-8")
            )
            writer = csv.DictWriter(metadata_stream, fieldnames=fieldnames)
            groundtruth_writer = csv.DictWriter(
                groundtruth_stream, fieldnames=TRAJECTORY_FIELDNAMES
            )
            estimated_writer = csv.DictWriter(
                estimated_stream, fieldnames=TRAJECTORY_FIELDNAMES
            )
            error_writer = csv.DictWriter(error_stream, fieldnames=error_fieldnames)
            writer.writeheader()
            groundtruth_writer.writeheader()
            estimated_writer.writeheader()
            error_writer.writeheader()
            while schedule_index < config.frame_count:
                target_elapsed_s = schedule_index / config.rate_hz
                remaining_s = start_perf + target_elapsed_s - time.perf_counter()
                if remaining_s > 0.0:
                    time.sleep(remaining_s)
                before_capture_s = time.perf_counter()
                if before_capture_s - start_perf > config.duration_s + 0.5 / config.rate_hz:
                    skipped_schedule_frames += config.frame_count - schedule_index
                    break

                responses = client.simGetImages([image_request], vehicle_name=args.vehicle)
                if len(responses) != 1:
                    raise RuntimeError(f"expected one image response, received {len(responses)}")
                response = responses[0]
                state = client.getMultirotorState(vehicle_name=args.vehicle)
                groundtruth = client.simGetGroundTruthKinematics(vehicle_name=args.vehicle)
                gps_data = client.getGpsData(args.gps, vehicle_name=args.vehicle)
                collision = client.simGetCollisionInfo(vehicle_name=args.vehicle)
                after_capture_s = time.perf_counter()
                actual_elapsed_s = 0.5 * (before_capture_s + after_capture_s) - start_perf
                if first_capture_elapsed_s is None:
                    first_capture_elapsed_s = actual_elapsed_s
                last_capture_elapsed_s = actual_elapsed_s

                image_name = f"frame_{schedule_index:06d}.png"
                relative_image_path = Path("images") / image_name
                save_scene_response(
                    response,
                    output_dir / relative_image_path,
                    args.image_rotation_deg,
                )

                groundtruth_position_api = vector_values(groundtruth.position)
                estimated_position_api = vector_values(state.kinematics_estimated.position)
                groundtruth_position = scene_map_transform.api_to_map(
                    groundtruth_position_api
                )
                estimated_position = scene_map_transform.api_to_map(
                    estimated_position_api
                )
                groundtruth_velocity = scene_map_transform.api_vector_to_map(
                    vector_values(groundtruth.linear_velocity)
                )
                estimated_velocity = scene_map_transform.api_vector_to_map(
                    vector_values(state.kinematics_estimated.linear_velocity)
                )
                if last_position is not None:
                    actual_distance_m += math.dist(groundtruth_position, last_position)
                last_position = groundtruth_position
                mapped_lon, mapped_lat = reference.local_to_lon_lat(
                    groundtruth_position[1], groundtruth_position[0]
                )
                planned = route.sample_at(schedule_index)
                geo_point = gps_data.gnss.geo_point
                wall_time_utc = utc_now_text()
                state_timestamp_ns = int(state.timestamp)
                image_timestamp_ns = int(response.time_stamp)
                groundtruth_writer.writerow(
                    kinematics_trajectory_row(
                        groundtruth,
                        sample_index=captured_count,
                        schedule_frame_index=schedule_index,
                        scheduled_time_s=target_elapsed_s,
                        actual_elapsed_s=actual_elapsed_s,
                        wall_time_utc=wall_time_utc,
                        state_timestamp_ns=state_timestamp_ns,
                        image_timestamp_ns=image_timestamp_ns,
                        source="airsim_ground_truth",
                        reference=reference,
                        scene_map_transform=scene_map_transform,
                    )
                )
                estimated_writer.writerow(
                    kinematics_trajectory_row(
                        state.kinematics_estimated,
                        sample_index=captured_count,
                        schedule_frame_index=schedule_index,
                        scheduled_time_s=target_elapsed_s,
                        actual_elapsed_s=actual_elapsed_s,
                        wall_time_utc=wall_time_utc,
                        state_timestamp_ns=state_timestamp_ns,
                        image_timestamp_ns=image_timestamp_ns,
                        source="airsim_estimated",
                        reference=reference,
                        scene_map_transform=scene_map_transform,
                    )
                )
                estimated_delta = tuple(
                    estimated_position[axis] - groundtruth_position[axis]
                    for axis in range(3)
                )
                velocity_delta = tuple(
                    estimated_velocity[axis] - groundtruth_velocity[axis]
                    for axis in range(3)
                )
                planned_position = (
                    planned.local_north_m,
                    planned.local_east_m,
                    planned.local_down_m,
                )
                tracking_delta = tuple(
                    groundtruth_position[axis] - planned_position[axis]
                    for axis in range(3)
                )
                estimated_error_3d_m = math.dist(estimated_position, groundtruth_position)
                estimated_velocity_error_3d_mps = math.dist(
                    estimated_velocity, groundtruth_velocity
                )
                planned_tracking_error_3d_m = math.dist(
                    groundtruth_position, planned_position
                )
                estimated_position_errors_m.append(estimated_error_3d_m)
                estimated_velocity_errors_mps.append(estimated_velocity_error_3d_mps)
                planned_tracking_errors_m.append(planned_tracking_error_3d_m)
                error_writer.writerow(
                    {
                        "capture_sequence": captured_count,
                        "schedule_frame_index": schedule_index,
                        "scheduled_time_s": f"{target_elapsed_s:.3f}",
                        "actual_elapsed_s": f"{actual_elapsed_s:.6f}",
                        "estimated_error_north_m": f"{estimated_delta[0]:.6f}",
                        "estimated_error_east_m": f"{estimated_delta[1]:.6f}",
                        "estimated_error_down_m": f"{estimated_delta[2]:.6f}",
                        "estimated_position_error_horizontal_m": (
                            f"{math.hypot(estimated_delta[0], estimated_delta[1]):.6f}"
                        ),
                        "estimated_position_error_3d_m": f"{estimated_error_3d_m:.6f}",
                        "estimated_velocity_error_3d_mps": (
                            f"{estimated_velocity_error_3d_mps:.6f}"
                        ),
                        "planned_tracking_error_north_m": f"{tracking_delta[0]:.6f}",
                        "planned_tracking_error_east_m": f"{tracking_delta[1]:.6f}",
                        "planned_tracking_error_down_m": f"{tracking_delta[2]:.6f}",
                        "planned_tracking_error_horizontal_m": (
                            f"{math.hypot(tracking_delta[0], tracking_delta[1]):.6f}"
                        ),
                        "planned_tracking_error_3d_m": f"{planned_tracking_error_3d_m:.6f}",
                    }
                )
                writer.writerow(
                    {
                        "capture_sequence": captured_count,
                        "schedule_frame_index": schedule_index,
                        "scheduled_time_s": f"{target_elapsed_s:.3f}",
                        "actual_elapsed_s": f"{actual_elapsed_s:.6f}",
                        "schedule_lateness_s": f"{actual_elapsed_s - target_elapsed_s:.6f}",
                        "wall_time_utc": wall_time_utc,
                        "image_timestamp_ns": image_timestamp_ns,
                        "image_file": relative_image_path.as_posix(),
                        "image_width_px": int(response.width),
                        "image_height_px": int(response.height),
                        "airsim_longitude_deg": f"{float(geo_point.longitude):.10f}",
                        "airsim_latitude_deg": f"{float(geo_point.latitude):.10f}",
                        "airsim_altitude_m": f"{float(geo_point.altitude):.3f}",
                        "groundtruth_longitude_deg": f"{mapped_lon:.10f}",
                        "groundtruth_latitude_deg": f"{mapped_lat:.10f}",
                        "groundtruth_north_m": f"{groundtruth_position[0]:.6f}",
                        "groundtruth_east_m": f"{groundtruth_position[1]:.6f}",
                        "groundtruth_down_m": f"{groundtruth_position[2]:.6f}",
                        "estimated_north_m": f"{estimated_position[0]:.6f}",
                        "estimated_east_m": f"{estimated_position[1]:.6f}",
                        "estimated_down_m": f"{estimated_position[2]:.6f}",
                        "estimated_position_error_3d_m": f"{estimated_error_3d_m:.6f}",
                        "planned_tracking_error_3d_m": f"{planned_tracking_error_3d_m:.6f}",
                        "planned_path_distance_m": f"{planned.path_distance_m:.6f}",
                        "planned_segment_index": planned.segment_index,
                        "has_collided": int(bool(collision.has_collided)),
                        "collision_object_name": str(collision.object_name),
                        "collision_object_id": int(collision.object_id),
                    }
                )
                captured_count += 1
                if captured_count % 100 == 0:
                    print(
                        f"Captured {captured_count} images, "
                        f"elapsed={actual_elapsed_s:.1f}s, skipped={skipped_schedule_frames}"
                    )

                schedule_index += 1
                latest_due_index = int(
                    math.floor((time.perf_counter() - start_perf) * config.rate_hz)
                )
                if latest_due_index > schedule_index:
                    skipped_schedule_frames += latest_due_index - schedule_index
                    schedule_index = latest_due_index
    except Exception as exc:
        collection_error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        client.hoverAsync(vehicle_name=args.vehicle).join()
        end_elapsed_s = time.perf_counter() - start_perf
        if not args.no_land_after:
            print("Landing...")
            client.landAsync(timeout_sec=60.0, vehicle_name=args.vehicle).join()
            client.armDisarm(False, vehicle_name=args.vehicle)
            client.enableApiControl(False, vehicle_name=args.vehicle)
        capture_span_s = (
            last_capture_elapsed_s - first_capture_elapsed_s
            if first_capture_elapsed_s is not None
            and last_capture_elapsed_s is not None
            and captured_count > 1
            else 0.0
        )
        summary = {
            "start_wall_time_utc": start_wall_utc,
            "end_wall_time_utc": utc_now_text(),
            "actual_collection_duration_s": end_elapsed_s,
            "captured_frame_count": captured_count,
            "scheduled_frame_count": config.frame_count,
            "skipped_schedule_frame_count": skipped_schedule_frames,
            "achieved_capture_rate_hz": (
                (captured_count - 1) / capture_span_s if capture_span_s > 0.0 else 0.0
            ),
            "sampled_actual_distance_m": actual_distance_m,
            "scene_map_transform": {
                "enabled": scene_map_transform.enabled,
                "center_north_m": scene_map_transform.center_north_m,
                "center_east_m": scene_map_transform.center_east_m,
                "center_down_m": scene_map_transform.center_down_m,
                "yaw_deg": scene_map_transform.yaw_deg,
            },
            "estimated_vs_groundtruth_position_error_m": metric_summary(
                estimated_position_errors_m
            ),
            "estimated_vs_groundtruth_velocity_error_mps": metric_summary(
                estimated_velocity_errors_mps
            ),
            "groundtruth_vs_planned_tracking_error_m": metric_summary(
                planned_tracking_errors_m
            ),
            "collection_error": collection_error,
        }
        (output_dir / "runtime_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "metadata_csv": metadata_path.name,
        "planned_trajectory_csv": "planned_trajectory.csv",
        "groundtruth_csv": groundtruth_path.name,
        "estimated_trajectory_csv": estimated_path.name,
        "trajectory_error_csv": error_path.name,
        "runtime_summary_json": "runtime_summary.json",
        "route_preview": "route_preview.jpg",
        "images_directory": image_dir.name,
        "captured_frame_count": captured_count,
    }
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"AirSim dataset written to: {output_dir}")
    print(
        f"Captured={captured_count}, skipped={skipped_schedule_frames}, "
        f"sampled distance={actual_distance_m:.2f} m"
    )
    return output_dir


def main() -> None:
    collect(parse_args())


if __name__ == "__main__":
    main()
