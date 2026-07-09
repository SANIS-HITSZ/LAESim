import argparse
import os
import sys
from pathlib import Path


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
        "or place this script inside a LAESim repository."
    )


bootstrap_python_client()

import airsim


def print_info(info):
    print("enabled:", info.enabled)
    print("object_name:", info.object_name)
    print("image_path:", info.image_path)
    print("meters_per_pixel:", info.meters_per_pixel)
    print("pixel_coordinate_frame:", info.pixel_coordinate_frame)
    print("image_width_px:", info.image_width_px)
    print("image_height_px:", info.image_height_px)
    print("width_px:", info.width_px)
    print("height_px:", info.height_px)
    print("width_meters:", info.width_meters)
    print("height_meters:", info.height_meters)
    print("center_x:", info.center_x)
    print("center_y:", info.center_y)
    print("z:", info.z)
    print("yaw:", info.yaw)
    print("collision_enabled:", info.collision_enabled)
    print("geo_reference_enabled:", info.geo_reference_enabled)
    print("reference_latitude:", info.reference_latitude)
    print("reference_longitude:", info.reference_longitude)
    print("reference_altitude:", info.reference_altitude)
    print("reference_u:", info.reference_u)
    print("reference_v:", info.reference_v)


def main():
    parser = argparse.ArgumentParser(description="Load/query/convert LAESim SceneMap through the CV/world RPC port.")
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=airsim.RPCLIB_PORT_CV)

    subparsers = parser.add_subparsers(dest="command", required=True)

    load_parser = subparsers.add_parser("load")
    load_parser.add_argument("image_path")
    load_parser.add_argument("--meters-per-pixel", type=float, required=True)
    load_parser.add_argument("--center-x", type=float, default=0)
    load_parser.add_argument("--center-y", type=float, default=0)
    load_parser.add_argument("--z", type=float, default=0)
    load_parser.add_argument("--yaw", type=float, default=0)
    load_parser.add_argument("--object-name", default="LAESimSceneMap")
    load_parser.add_argument("--no-collision", action="store_true")

    subparsers.add_parser("info")
    subparsers.add_parser("unload")

    to_world_parser = subparsers.add_parser("to-world")
    to_world_parser.add_argument("--u", type=float, required=True)
    to_world_parser.add_argument("--v", type=float, required=True)
    to_world_parser.add_argument("--z", type=float, default=0)

    to_pixel_parser = subparsers.add_parser("to-pixel")
    to_pixel_parser.add_argument("--x", type=float, required=True)
    to_pixel_parser.add_argument("--y", type=float, required=True)

    args = parser.parse_args()

    client = airsim.VehicleClient(ip=args.ip, port=args.port)
    client.confirmConnection()

    if args.command == "load":
        ok = client.simLoadSceneMap(
            args.image_path,
            args.meters_per_pixel,
            args.center_x,
            args.center_y,
            args.z,
            args.yaw,
            not args.no_collision,
            args.object_name,
        )
        print("load:", ok)
        print_info(client.simGetSceneMapInfo())
    elif args.command == "info":
        print_info(client.simGetSceneMapInfo())
    elif args.command == "unload":
        print("unload:", client.simUnloadSceneMap())
    elif args.command == "to-world":
        point = client.simSceneMapToWorld(args.u, args.v, args.z)
        print("x:", point.x_val)
        print("y:", point.y_val)
        print("z:", point.z_val)
    elif args.command == "to-pixel":
        pixel = client.simWorldToSceneMap(args.x, args.y)
        print("u:", pixel.x_val)
        print("v:", pixel.y_val)


if __name__ == "__main__":
    main()
