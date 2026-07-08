import argparse
import math
import os
import sys
import time
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
        "or place this script inside an AirSim_Multi repository."
    )


bootstrap_python_client()

import airsim
import pygame


DEFAULT_PORT = 41471
DEFAULT_VEHICLE = "UAV"


def create_ui_font(size=16):
    pygame.font.init()
    for family in ("consolas", "couriernew"):
        try:
            return pygame.font.SysFont(family, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def copy_vec(v):
    return airsim.Vector3r(v.x_val, v.y_val, v.z_val)


def body_to_world(vx_body, vy_body, yaw):
    vx_world = (vx_body * math.cos(yaw)) - (vy_body * math.sin(yaw))
    vy_world = (vx_body * math.sin(yaw)) + (vy_body * math.cos(yaw))
    return vx_world, vy_world


def make_kinematics(position, yaw, vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0):
    kin = airsim.KinematicsState()
    kin.position = copy_vec(position)
    kin.orientation = airsim.to_quaternion(0.0, 0.0, yaw)
    kin.linear_velocity = airsim.Vector3r(vx, vy, vz)
    kin.angular_velocity = airsim.Vector3r(0.0, 0.0, yaw_rate)
    kin.linear_acceleration = airsim.Vector3r(0.0, 0.0, 0.0)
    kin.angular_acceleration = airsim.Vector3r(0.0, 0.0, 0.0)
    return kin


def send_kinematics(client, vehicle, position, yaw, vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0):
    client.simSetKinematics(
        make_kinematics(position, yaw, vx, vy, vz, yaw_rate),
        True,
        vehicle_name=vehicle,
    )


def connect_client(args):
    client = airsim.MultirotorClient(ip=args.host, port=args.port)
    client.confirmConnection()

    vehicles = client.listVehicles()
    if args.vehicle not in vehicles:
        raise RuntimeError(f"{args.vehicle!r} not found on port {args.port}. Detected vehicles: {vehicles}")

    return client


def get_ground_truth(client, vehicle):
    kin = client.simGetGroundTruthKinematics(vehicle_name=vehicle)
    _, _, yaw = airsim.to_eularian_angles(kin.orientation)
    return copy_vec(kin.position), yaw


def smooth_move(client, vehicle, start_pos, end_pos, yaw, seconds, hz):
    dt = 1.0 / hz
    start_time = time.perf_counter()
    while True:
        t = (time.perf_counter() - start_time) / max(seconds, 0.001)
        if t >= 1.0:
            send_kinematics(client, vehicle, end_pos, yaw)
            return

        a = t * t * (3.0 - 2.0 * t)
        pos = airsim.Vector3r(
            start_pos.x_val + (end_pos.x_val - start_pos.x_val) * a,
            start_pos.y_val + (end_pos.y_val - start_pos.y_val) * a,
            start_pos.z_val + (end_pos.z_val - start_pos.z_val) * a,
        )
        send_kinematics(client, vehicle, pos, yaw)
        time.sleep(dt)


def draw_status(screen, font, lines):
    screen.fill((8, 10, 12))
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (90, 235, 170)), (12, 12 + i * 23))
    pygame.display.flip()


def read_controls(keys, args):
    scale = args.boost_ratio if keys[pygame.K_SPACE] else 1.0
    vx_body = 0.0
    vy_body = 0.0
    vz = 0.0
    yaw_rate_deg = 0.0

    if keys[pygame.K_UP]:
        vx_body += args.speed * scale
    if keys[pygame.K_DOWN]:
        vx_body -= args.speed * scale
    if keys[pygame.K_LEFT]:
        vy_body -= args.speed * scale
    if keys[pygame.K_RIGHT]:
        vy_body += args.speed * scale
    if keys[pygame.K_w]:
        vz -= args.vertical_speed * scale
    if keys[pygame.K_s]:
        vz += args.vertical_speed * scale
    if keys[pygame.K_a]:
        yaw_rate_deg -= args.yaw_rate_deg * scale
    if keys[pygame.K_d]:
        yaw_rate_deg += args.yaw_rate_deg * scale

    return vx_body, vy_body, vz, yaw_rate_deg


def apply_gain_profile(client, args):
    if args.gain_profile == "none":
        return

    if args.gain_profile == "soft":
        velocity_xy_p = 0.05
        angle_level_xy_p = 0.8
        angle_rate_xy_p = 0.10
    elif args.gain_profile == "very-soft":
        velocity_xy_p = 0.02
        angle_level_xy_p = 0.4
        angle_rate_xy_p = 0.05
    else:
        raise ValueError(f"unknown gain profile: {args.gain_profile}")

    client.setVelocityControllerGains(
        airsim.VelocityControllerGains(
            x_gains=airsim.PIDGains(velocity_xy_p, 0.0, 0.0),
            y_gains=airsim.PIDGains(velocity_xy_p, 0.0, 0.0),
            z_gains=airsim.PIDGains(2.0, 2.0, 0.0),
        ),
        vehicle_name=args.vehicle,
    )
    client.setAngleLevelControllerGains(
        airsim.AngleLevelControllerGains(
            roll_gains=airsim.PIDGains(angle_level_xy_p, 0.0, 0.0),
            pitch_gains=airsim.PIDGains(angle_level_xy_p, 0.0, 0.0),
            yaw_gains=airsim.PIDGains(2.5, 0.0, 0.0),
        ),
        vehicle_name=args.vehicle,
    )
    client.setAngleRateControllerGains(
        airsim.AngleRateControllerGains(
            roll_gains=airsim.PIDGains(angle_rate_xy_p, 0.0, 0.0),
            pitch_gains=airsim.PIDGains(angle_rate_xy_p, 0.0, 0.0),
            yaw_gains=airsim.PIDGains(0.25, 0.0, 0.0),
        ),
        vehicle_name=args.vehicle,
    )
    print(
        f"Applied {args.gain_profile} gains: "
        f"velocity_xy_p={velocity_xy_p}, angle_level_xy_p={angle_level_xy_p}, "
        f"angle_rate_xy_p={angle_rate_xy_p}"
    )


def send_physics_velocity(client, args, vx_body, vy_body, vz, yaw_rate_deg, duration):
    if args.velocity_api == "body":
        client.moveByVelocityBodyFrameAsync(
            vx=vx_body,
            vy=vy_body,
            vz=vz,
            duration=duration,
            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=airsim.YawMode(True, yaw_rate_deg),
            vehicle_name=args.vehicle,
        )
        return vx_body, vy_body

    _, yaw = get_ground_truth(client, args.vehicle)
    vx_world, vy_world = body_to_world(vx_body, vy_body, yaw)
    client.moveByVelocityAsync(
        vx_world,
        vy_world,
        vz,
        duration,
        airsim.DrivetrainType.MaxDegreeOfFreedom,
        airsim.YawMode(True, yaw_rate_deg),
        vehicle_name=args.vehicle,
    )
    return vx_world, vy_world


def init_physics_mode(client, args):
    client.enableApiControl(True, vehicle_name=args.vehicle)
    client.armDisarm(True, vehicle_name=args.vehicle)
    apply_gain_profile(client, args)

    if not args.no_takeoff:
        ground_pos, _ = get_ground_truth(client, args.vehicle)
        target_z = ground_pos.z_val - args.takeoff_altitude
        print(f"Taking off with SimpleFlight to z={target_z:.2f}...")
        client.takeoffAsync(timeout_sec=20, vehicle_name=args.vehicle).join()
        client.moveToZAsync(
            target_z,
            args.vertical_speed,
            timeout_sec=30,
            yaw_mode=airsim.YawMode(True, 0.0),
            vehicle_name=args.vehicle,
        ).join()


def run_physics_mode(client, args, screen, font, clock):
    init_physics_mode(client, args)
    dt = 1.0 / args.hz

    print(f"Physics mode: using {args.velocity_api} velocity API.")
    print("Keep the pygame window focused, and switch input method to English.")

    while True:
        quit_requested = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_requested = True

        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            quit_requested = True
        if quit_requested:
            break

        vx_body, vy_body, vz, yaw_rate_deg = read_controls(keys, args)
        vx_sent, vy_sent = send_physics_velocity(
            client,
            args,
            vx_body,
            vy_body,
            vz,
            yaw_rate_deg,
            max(dt * 2.0, 0.05),
        )

        pos, yaw = get_ground_truth(client, args.vehicle)
        draw_status(
            screen,
            font,
            [
                "AirSim multirotor keyboard control - physics mode",
                f"API={args.velocity_api}. Input method must be English. ESC/window close: hover and quit.",
                "Arrow keys: forward/back/left/right   W/S: up/down   A/D: yaw left/right",
                "Space: boost",
                f"cmd body vel=({vx_body:.2f}, {vy_body:.2f}, {vz:.2f}) sent xy=({vx_sent:.2f}, {vy_sent:.2f})",
                f"truth pos=({pos.x_val:.2f}, {pos.y_val:.2f}, {pos.z_val:.2f}) yaw={math.degrees(yaw):.1f} deg",
            ],
        )
        clock.tick(args.hz)

    try:
        client.hoverAsync(vehicle_name=args.vehicle).join()
    except Exception:
        pass
    if args.land_on_exit:
        client.landAsync(timeout_sec=30, vehicle_name=args.vehicle).join()


def init_kinematic_mode(client, args):
    try:
        client.armDisarm(False, vehicle_name=args.vehicle)
    except Exception:
        pass
    try:
        client.enableApiControl(False, vehicle_name=args.vehicle)
    except Exception:
        pass

    ground_pos, yaw = get_ground_truth(client, args.vehicle)
    target_pos = copy_vec(ground_pos)
    target_pos.z_val -= args.takeoff_altitude

    if not args.no_takeoff:
        print(f"Kinematic takeoff to {args.takeoff_altitude:.1f}m above start...")
        smooth_move(client, args.vehicle, ground_pos, target_pos, yaw, args.takeoff_seconds, args.kinematic_hz)

    return ground_pos, target_pos, yaw


def run_kinematic_mode(client, args, screen, font, clock):
    ground_pos, target_pos, yaw = init_kinematic_mode(client, args)
    last_time = time.perf_counter()

    print("Kinematic mode: using simSetKinematics fallback.")
    print("This mode can still show small vertical jitter because physics runs between pose updates.")

    try:
        while True:
            quit_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True

            keys = pygame.key.get_pressed()
            if keys[pygame.K_ESCAPE]:
                quit_requested = True
            if quit_requested:
                return

            now = time.perf_counter()
            dt = min(now - last_time, 0.05)
            last_time = now

            vx_body, vy_body, vz, yaw_rate_deg = read_controls(keys, args)
            yaw_rate = math.radians(yaw_rate_deg)
            vx_world, vy_world = body_to_world(vx_body, vy_body, yaw)

            target_pos.x_val += vx_world * dt
            target_pos.y_val += vy_world * dt
            target_pos.z_val += vz * dt
            target_pos.z_val = min(target_pos.z_val, ground_pos.z_val)
            target_pos.z_val = max(target_pos.z_val, ground_pos.z_val - args.max_altitude)
            yaw += yaw_rate * dt

            send_kinematics(client, args.vehicle, target_pos, yaw, vx_world, vy_world, vz, yaw_rate)
            draw_status(
                screen,
                font,
                [
                    "AirSim multirotor keyboard control - kinematic mode",
                    "This bypasses SimpleFlight, but may jitter if UE physics/render is slow.",
                    "Arrow keys: forward/back/left/right   W/S: up/down   A/D: yaw left/right",
                    "Space: boost   ESC: descend and quit",
                    f"target pos=({target_pos.x_val:.2f}, {target_pos.y_val:.2f}, {target_pos.z_val:.2f})",
                    f"world vel=({vx_world:.2f}, {vy_world:.2f}, {vz:.2f}) yaw={math.degrees(yaw):.1f} deg",
                ],
            )
            clock.tick(args.kinematic_hz)
    finally:
        if args.land_on_exit:
            current = copy_vec(target_pos)
            current_ground = copy_vec(current)
            current_ground.z_val = ground_pos.z_val
            smooth_move(client, args.vehicle, current, current_ground, yaw, args.land_seconds, args.kinematic_hz)


def parse_args():
    parser = argparse.ArgumentParser(description="AirSim pygame keyboard controller for multirotors.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--vehicle", default=DEFAULT_VEHICLE)
    parser.add_argument("--mode", choices=("physics", "kinematic"), default="physics")
    parser.add_argument(
        "--gain-profile",
        choices=("none", "soft", "very-soft"),
        default="none",
        help="Runtime SimpleFlight PID softening for roll/pitch horizontal velocity control.",
    )
    parser.add_argument(
        "--velocity-api",
        choices=("ros-like", "body"),
        default="ros-like",
        help="ros-like mirrors AG ROS wrapper: body-frame input -> world-frame moveByVelocityAsync.",
    )
    parser.add_argument("--speed", type=float, default=5)
    parser.add_argument("--vertical-speed", type=float, default=1.0)
    parser.add_argument("--yaw-rate-deg", type=float, default=20.0)
    parser.add_argument("--boost-ratio", type=float, default=2.0)
    parser.add_argument("--hz", type=float, default=30.0)
    parser.add_argument("--kinematic-hz", type=float, default=120.0)
    parser.add_argument("--takeoff-altitude", type=float, default=5.0)
    parser.add_argument("--takeoff-seconds", type=float, default=3.0)
    parser.add_argument("--land-seconds", type=float, default=2.5)
    parser.add_argument("--max-altitude", type=float, default=100.0)
    parser.add_argument("--no-takeoff", action="store_true")
    parser.add_argument("--land-on-exit", action="store_true")
    parser.add_argument(
        "--official-ros-values",
        action="store_true",
        help="Use AG keyboard_ctrl.py values: speed=2, vertical_speed=2, yaw_rate=1 rad/s, hz=20.",
    )
    args = parser.parse_args()
    if args.official_ros_values:
        args.velocity_api = "ros-like"
        args.speed = 2.0
        args.vertical_speed = 2.0
        args.yaw_rate_deg = math.degrees(1.0)
        args.hz = 20.0
    return args


def main():
    args = parse_args()

    pygame.init()
    screen = pygame.display.set_mode((760, 175))
    pygame.display.set_caption(f"AirSim {args.vehicle} keyboard control ({args.mode})")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    client = connect_client(args)
    print(f"Connected to AirSim {args.vehicle} on {args.host}:{args.port}.")

    try:
        if args.mode == "physics":
            run_physics_mode(client, args, screen, font, clock)
        else:
            run_kinematic_mode(client, args, screen, font, clock)
    finally:
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
