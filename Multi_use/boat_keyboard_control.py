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
        "or place this script inside a LAESim repository."
    )


bootstrap_python_client()

import airsim
import pygame


DEFAULT_PORT = 41481
DEFAULT_VEHICLE = "Boat"


def create_ui_font(size=16):
    pygame.font.init()
    for family in ("consolas", "couriernew"):
        try:
            return pygame.font.SysFont(family, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def connect_client(args):
    client = airsim.BoatClient(ip=args.host, port=args.port)
    client.confirmConnection()

    vehicles = client.listVehicles()
    if args.vehicle not in vehicles:
        raise RuntimeError(f"{args.vehicle!r} not found on port {args.port}. Detected vehicles: {vehicles}")

    client.enableApiControl(True, vehicle_name=args.vehicle)
    return client


def read_controls(keys, args):
    throttle = 0.0
    steering = 0.0

    if keys[pygame.K_w]:
        throttle += args.throttle
    if keys[pygame.K_s]:
        throttle -= args.reverse_throttle
    if keys[pygame.K_a]:
        steering -= args.steering
    if keys[pygame.K_d]:
        steering += args.steering

    brake = args.idle_brake if abs(throttle) < 1e-6 else 0.0
    anchor = bool(keys[pygame.K_SPACE])
    return throttle, steering, brake, anchor


def draw_status(screen, font, lines):
    screen.fill((8, 10, 14))
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, (120, 220, 255)), (12, 12 + i * 23))
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

        throttle, steering, brake, anchor = read_controls(keys, args)

        controls = airsim.BoatControls()
        controls.throttle = throttle
        controls.steering = steering
        controls.brake = brake
        controls.anchor = anchor
        client.setBoatControls(controls, vehicle_name=args.vehicle)

        state = client.getBoatState(vehicle_name=args.vehicle)
        pose = client.simGetVehiclePose(vehicle_name=args.vehicle)
        _, _, yaw = airsim.to_eularian_angles(pose.orientation)

        draw_status(
            screen,
            font,
            [
                "AirSim boat keyboard control",
                "W/S: ahead/reverse   A/D: steer left/right   Space: anchor/brake   ESC: stop and quit",
                f"cmd throttle={controls.throttle:.2f} steering={steering:.2f} brake={brake:.2f} anchor={anchor}",
                (
                    f"state speed={state.speed:.2f} m/s u={state.forward_speed:.2f} "
                    f"v={state.lateral_speed:.2f} r={state.yaw_rate:.3f} rad/s"
                ),
                f"pose=({pose.position.x_val:.2f}, {pose.position.y_val:.2f}, {pose.position.z_val:.2f}) yaw={math.degrees(yaw):.1f} deg",
            ],
        )
        clock.tick(args.hz)

    controls = airsim.BoatControls()
    controls.throttle = 0.0
    controls.steering = 0.0
    controls.brake = 1.0
    controls.anchor = True
    client.setBoatControls(controls, vehicle_name=args.vehicle)


def parse_args():
    parser = argparse.ArgumentParser(description="AirSim pygame keyboard controller for boats.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--vehicle", default=DEFAULT_VEHICLE)
    parser.add_argument("--throttle", type=float, default=0.75)
    parser.add_argument("--reverse-throttle", type=float, default=0.35)
    parser.add_argument("--steering", type=float, default=0.45)
    parser.add_argument("--idle-brake", type=float, default=0.0)
    parser.add_argument("--hz", type=float, default=30.0)
    return parser.parse_args()


def main():
    args = parse_args()

    pygame.init()
    screen = pygame.display.set_mode((880, 160))
    pygame.display.set_caption(f"AirSim {args.vehicle} boat keyboard control")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    client = connect_client(args)
    print(f"Connected to AirSim boat {args.vehicle} on {args.host}:{args.port}.")

    try:
        run_loop(client, args, screen, font, clock)
    finally:
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
