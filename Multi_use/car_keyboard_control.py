import argparse
import math
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
        "or place this script inside an AirSim_Multi repository."
    )


bootstrap_python_client()

import airsim
import pygame


DEFAULT_PORT = 41461
DEFAULT_VEHICLE = "Car"


def create_ui_font(size=16):
    pygame.font.init()
    for family in ("consolas", "couriernew"):
        try:
            return pygame.font.SysFont(family, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def connect_client(args):
    client = airsim.CarClient(ip=args.host, port=args.port)
    client.confirmConnection()

    vehicles = client.listVehicles()
    if args.vehicle not in vehicles:
        raise RuntimeError(f"{args.vehicle!r} not found on port {args.port}. Detected vehicles: {vehicles}")

    client.enableApiControl(True, vehicle_name=args.vehicle)
    return client


def read_controls(keys, args):
    throttle = 0.0
    steering = 0.0
    reverse = False

    if keys[pygame.K_w]:
        throttle += args.throttle
    if keys[pygame.K_s]:
        throttle = args.reverse_throttle
        reverse = True
    if keys[pygame.K_a]:
        steering -= args.steering
    if keys[pygame.K_d]:
        steering += args.steering

    handbrake = bool(keys[pygame.K_SPACE])
    brake = args.idle_brake if abs(throttle) < 1e-6 and not handbrake else 0.0

    return throttle, steering, brake, handbrake, reverse


def draw_status(screen, font, lines):
    screen.fill((8, 10, 12))
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (90, 235, 170)), (12, 12 + i * 23))
    pygame.display.flip()


def run_loop(client, args, screen, font, clock):
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

        throttle, steering, brake, handbrake, reverse = read_controls(keys, args)

        controls = airsim.CarControls()
        if reverse:
            controls.is_manual_gear = True
            controls.manual_gear = -1
            controls.gear_immediate = True
            controls.throttle = -abs(throttle)
        else:
            controls.is_manual_gear = False
            controls.manual_gear = 0
            controls.gear_immediate = True
            controls.throttle = max(throttle, 0.0)
        controls.steering = steering
        controls.brake = brake
        controls.handbrake = handbrake
        client.setCarControls(controls, vehicle_name=args.vehicle)

        state = client.getCarState(vehicle_name=args.vehicle)
        pose = client.simGetVehiclePose(vehicle_name=args.vehicle)
        _, _, yaw = airsim.to_eularian_angles(pose.orientation)

        draw_status(
            screen,
            font,
            [
                "AirSim car keyboard control",
                "W/S: throttle forward/back   A/D: steer left/right   Space: handbrake   ESC: stop and quit",
                f"cmd throttle={controls.throttle:.2f} steering={steering:.2f} brake={brake:.2f} handbrake={handbrake} reverse={reverse}",
                f"state speed={state.speed:.2f} m/s gear={getattr(state, 'gear', '?')} rpm={getattr(state, 'rpm', '?')}",
                f"pose=({pose.position.x_val:.2f}, {pose.position.y_val:.2f}, {pose.position.z_val:.2f}) yaw={math.degrees(yaw):.1f} deg",
            ],
        )
        clock.tick(args.hz)

    controls = airsim.CarControls()
    controls.throttle = 0.0
    controls.steering = 0.0
    controls.brake = 1.0
    controls.handbrake = False
    client.setCarControls(controls, vehicle_name=args.vehicle)


def parse_args():
    parser = argparse.ArgumentParser(description="AirSim pygame keyboard controller for cars.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--vehicle", default=DEFAULT_VEHICLE)
    parser.add_argument("--throttle", type=float, default=0.7)
    parser.add_argument("--reverse-throttle", type=float, default=0.5)
    parser.add_argument("--steering", type=float, default=0.4)
    parser.add_argument("--idle-brake", type=float, default=0.0)
    parser.add_argument("--hz", type=float, default=30.0)
    return parser.parse_args()


def main():
    args = parse_args()

    pygame.init()
    screen = pygame.display.set_mode((860, 160))
    pygame.display.set_caption(f"AirSim {args.vehicle} car keyboard control")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    client = connect_client(args)
    print(f"Connected to AirSim car {args.vehicle} on {args.host}:{args.port}.")

    try:
        run_loop(client, args, screen, font, clock)
    finally:
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
