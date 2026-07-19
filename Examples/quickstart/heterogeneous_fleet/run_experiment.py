#!/usr/bin/env python3
"""Minimal UAV, car, and boat Python API experiment for LAESim."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "PythonClient"))


EXPECTED_VEHICLES = {
    "UAV": "simpleflight",
    "Car": "physxcar",
    "Boat": "simpleboat",
}


def load_and_validate_settings(path: Path) -> dict:
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    if settings.get("SimMode", "").lower() != "airground":
        raise ValueError("SimMode must be 'AirGround'")

    vehicles = settings.get("Vehicles", {})
    for name, expected_type in EXPECTED_VEHICLES.items():
        actual_type = str(vehicles.get(name, {}).get("VehicleType", "")).lower()
        if actual_type != expected_type:
            raise ValueError(
                f"Vehicles.{name}.VehicleType must be '{expected_type}'"
            )
    return settings


def position_text(position) -> str:
    return f"({position.x_val:6.2f}, {position.y_val:6.2f}, {position.z_val:6.2f})"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Control one UAV, one car, and one boat in LAESim."
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path.home() / "Documents" / "AirSim" / "settings.json",
    )
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.duration <= 0.0:
        parser.error("--duration must be positive")
    settings = load_and_validate_settings(args.settings)
    ports = {
        "uav": int(settings.get("ApiServerPortMultirotor", 41471)),
        "car": int(settings.get("ApiServerPortCar", 41461)),
        "boat": int(settings.get("ApiServerPortBoat", 41481)),
    }
    print(f"settings: {args.settings}")
    print(f"vehicles: {', '.join(EXPECTED_VEHICLES)}")
    print(f"RPC ports: UAV={ports['uav']} Car={ports['car']} Boat={ports['boat']}")
    if args.check_only:
        print("configuration check passed")
        return 0

    try:
        import airsim
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "AirSim Python dependencies are missing; run "
            "'py -3 -m pip install msgpack-rpc-python numpy opencv-contrib-python' "
            "from the repository root"
        ) from error

    uav = airsim.MultirotorClient(args.ip, port=ports["uav"])
    car = airsim.CarClient(args.ip, port=ports["car"])
    boat = airsim.BoatClient(args.ip, port=ports["boat"])
    for client in (uav, car, boat):
        client.confirmConnection()

    uav_enabled = car_enabled = boat_enabled = False
    try:
        uav.enableApiControl(True, "UAV")
        uav_enabled = True
        uav.armDisarm(True, "UAV")
        uav.takeoffAsync(timeout_sec=20, vehicle_name="UAV").join()

        car.enableApiControl(True, "Car")
        car_enabled = True
        boat.enableApiControl(True, "Boat")
        boat_enabled = True

        car.setCarControls(
            airsim.CarControls(throttle=0.55, steering=0.12), "Car"
        )
        boat.setBoatControls(
            airsim.BoatControls(throttle=0.70, steering=-0.18), "Boat"
        )
        uav_motion = uav.moveByVelocityAsync(
            2.0,
            0.0,
            0.0,
            args.duration,
            vehicle_name="UAV",
        )

        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            uav_position = uav.getMultirotorState("UAV").kinematics_estimated.position
            car_state = car.getCarState("Car")
            boat_state = boat.getBoatState("Boat")
            print(
                f"UAV local NED={position_text(uav_position)} | "
                f"Car speed={car_state.speed:5.2f} m/s | "
                f"Boat speed={boat_state.speed:5.2f} m/s "
                f"sway={boat_state.lateral_speed:5.2f} m/s"
            )
            time.sleep(min(1.0, max(deadline - time.monotonic(), 0.0)))
        uav_motion.join()
        print("experiment completed")
        return 0
    finally:
        if car_enabled:
            car.setCarControls(
                airsim.CarControls(brake=1.0, handbrake=True), "Car"
            )
            car.enableApiControl(False, "Car")
        if boat_enabled:
            boat.setBoatControls(
                airsim.BoatControls(brake=1.0, anchor=True), "Boat"
            )
            boat.enableApiControl(False, "Boat")
        if uav_enabled:
            try:
                uav.hoverAsync(vehicle_name="UAV").join()
                uav.landAsync(timeout_sec=30, vehicle_name="UAV").join()
            finally:
                uav.armDisarm(False, "UAV")
                uav.enableApiControl(False, "UAV")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
