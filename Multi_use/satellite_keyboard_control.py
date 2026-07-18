#!/usr/bin/env python3

import argparse
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYCLIENT = os.path.join(ROOT, "PythonClient")
if PYCLIENT not in sys.path:
    sys.path.insert(0, PYCLIENT)

import airsim


def create_ui_font(size=18):
    pygame.font.init()
    for family in ("consolas", "couriernew"):
        try:
            return pygame.font.SysFont(family, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def parse_args():
    parser = argparse.ArgumentParser(description="Keyboard velocity controller for LAESim SimpleSatellite vehicles.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=airsim.RPCLIB_PORT_SATELLITE)
    parser.add_argument("--vehicle", default="Satellite")
    parser.add_argument("--speed", type=float, default=20.0, help="Commanded axis speed in m/s.")
    parser.add_argument("--yaw-rate", type=float, default=0.6, help="Commanded yaw rate in rad/s.")
    parser.add_argument("--rate", type=float, default=30.0)
    return parser.parse_args()


def main():
    global pygame
    try:
        import pygame
    except ImportError:
        raise SystemExit("pygame is required: pip install pygame")

    args = parse_args()
    client = airsim.SatelliteClient(ip=args.host, port=args.port)
    client.confirmConnection()
    client.enableApiControl(True, args.vehicle)
    client.armDisarm(True, args.vehicle)

    pygame.init()
    screen = pygame.display.set_mode((620, 220))
    pygame.display.set_caption(f"LAESim satellite control: {args.vehicle}")
    font = create_ui_font(18)
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        keys = pygame.key.get_pressed()
        vx = (1.0 if keys[pygame.K_w] else 0.0) + (-1.0 if keys[pygame.K_s] else 0.0)
        vy = (1.0 if keys[pygame.K_d] else 0.0) + (-1.0 if keys[pygame.K_a] else 0.0)
        vz = (1.0 if keys[pygame.K_f] else 0.0) + (-1.0 if keys[pygame.K_r] else 0.0)
        yaw_rate = (1.0 if keys[pygame.K_e] else 0.0) + (-1.0 if keys[pygame.K_q] else 0.0)

        controls = airsim.SatelliteControls(
            vx=vx * args.speed,
            vy=vy * args.speed,
            vz=vz * args.speed,
            yaw_rate=yaw_rate * args.yaw_rate)
        client.setSatelliteControls(controls, vehicle_name=args.vehicle)
        state = client.getSatelliteState(vehicle_name=args.vehicle)

        screen.fill((18, 22, 28))
        lines = [
            "W/S: NED X  A/D: NED Y  R/F: up/down  Q/E: yaw  ESC: quit",
            f"cmd vx={controls.vx:.2f} vy={controls.vy:.2f} vz={controls.vz:.2f} yaw_rate={controls.yaw_rate:.2f}",
            f"state speed={state.speed:.2f} pos=({state.kinematics_estimated.position.x_val:.2f}, "
            f"{state.kinematics_estimated.position.y_val:.2f}, {state.kinematics_estimated.position.z_val:.2f})",
        ]
        for i, line in enumerate(lines):
            screen.blit(font.render(line, True, (220, 230, 240)), (20, 25 + i * 36))
        pygame.display.flip()
        clock.tick(max(1.0, args.rate))

    client.setSatelliteControls(airsim.SatelliteControls(), vehicle_name=args.vehicle)
    pygame.quit()


if __name__ == "__main__":
    main()
