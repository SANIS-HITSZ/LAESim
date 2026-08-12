#!/usr/bin/env python3
"""Convert a GeoTIFF to a SceneMap image and generate LAESim settings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from coverage_mission import default_tif_path, load_geotiff_reference


def parse_args() -> argparse.Namespace:
    example_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Prepare a NorthUp SceneMap and stable nadir-camera settings."
    )
    parser.add_argument("--tif", type=Path, default=default_tif_path())
    parser.add_argument(
        "--scene-image", type=Path, default=example_dir / "scene_map.png"
    )
    parser.add_argument(
        "--settings-output", type=Path, default=example_dir / "settings.generated.json"
    )
    parser.add_argument("--vehicle", default="UAV")
    parser.add_argument("--camera", default="nadir")
    parser.add_argument("--scene-z", type=float, default=-200.0)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--fov-deg", type=float, default=90.0)
    parser.add_argument("--collision", action="store_true")
    return parser.parse_args()


def build_settings(args: argparse.Namespace) -> dict:
    reference = load_geotiff_reference(args.tif)
    center_lon, center_lat = reference.center_lon_lat()
    meters_per_pixel = 0.5 * (
        reference.ground_width_m / reference.width_px
        + reference.ground_height_m / reference.height_px
    )
    image_path = args.scene_image.expanduser().resolve().as_posix()

    return {
        "SettingsVersion": 1.2,
        "SimMode": "AirGround",
        "ClockType": "ScalableClock",
        "ClockSpeed": 1.0,
        "ApiServerPortCV": 41451,
        "ApiServerPortMultirotor": 41471,
        "OriginGeopoint": {
            "Latitude": center_lat,
            "Longitude": center_lon,
            "Altitude": args.scene_z,
        },
        "SceneMap": {
            "Enabled": True,
            "ImagePath": image_path,
            "ObjectName": "LAESimNadirCollectionMap",
            "MetersPerPixel": meters_per_pixel,
            "PixelCoordinateFrame": "NorthUp",
            "CenterX": 0.0,
            "CenterY": 0.0,
            "Z": args.scene_z,
            "Yaw": 0.0,
            "CollisionEnabled": bool(args.collision),
            "SegmentationId": 21,
            "GeoReference": {
                "Enabled": True,
                "ReferenceLatitude": center_lat,
                "ReferenceLongitude": center_lon,
                "ReferenceAltitude": 0.0,
                "ReferenceU": reference.width_px / 2.0,
                "ReferenceV": reference.height_px / 2.0,
            },
        },
        "Vehicles": {
            args.vehicle: {
                "VehicleType": "SimpleFlight",
                "AutoCreate": True,
                "X": 0.0,
                "Y": 0.0,
                "Z": 0.0,
                "Yaw": 0.0,
                "Sensors": {
                    "gps": {"SensorType": 3, "Enabled": True},
                    "imu": {"SensorType": 2, "Enabled": True},
                },
                "Cameras": {
                    args.camera: {
                        "X": 0.0,
                        "Y": 0.0,
                        "Z": 0.0,
                        "Pitch": -90.0,
                        "Roll": 0.0,
                        "Yaw": 0.0,
                        "Gimbal": {
                            "Stabilization": 1.0,
                            "Pitch": -90.0,
                            "Roll": 0.0,
                            "Yaw": 0.0,
                        },
                        "CaptureSettings": [
                            {
                                "ImageType": 0,
                                "Width": args.width,
                                "Height": args.height,
                                "FOV_Degrees": args.fov_deg,
                                "AutoExposureSpeed": 100.0,
                                "MotionBlurAmount": 0.0,
                            }
                        ],
                    }
                },
            }
        },
        "SubWindows": [
            {
                "WindowID": 0,
                "ImageType": 0,
                "CameraName": args.camera,
                "VehicleName": args.vehicle,
                "Visible": True,
            }
        ],
    }


def main() -> int:
    args = parse_args()
    if args.width <= 0 or args.height <= 0 or not 1.0 < args.fov_deg < 179.0:
        raise ValueError("camera width/height must be positive and FOV must be in (1, 179)")

    args.scene_image = args.scene_image.expanduser().resolve()
    args.settings_output = args.settings_output.expanduser().resolve()
    args.scene_image.parent.mkdir(parents=True, exist_ok=True)
    args.settings_output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(args.tif.expanduser().resolve()) as source:
        source.convert("RGB").save(args.scene_image, format="PNG")

    settings = build_settings(args)
    args.settings_output.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SceneMap image: {args.scene_image}")
    print(f"Generated settings: {args.settings_output}")
    print("Copy the generated file to Documents/AirSim/settings.json, then restart UE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
