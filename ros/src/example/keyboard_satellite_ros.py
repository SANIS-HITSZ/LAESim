#!/usr/bin/env python3

import argparse

import rospy

from airsim_ros_pkgs.msg import SatelliteControls, SatelliteState
from _ros_example_common import topic_name


def parse_args():
    parser = argparse.ArgumentParser(description="ROS pygame control example for LAESim satellites.")
    parser.add_argument("--vehicle", default="Satellite")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--speed", type=float, default=20.0)
    parser.add_argument("--yaw-rate", type=float, default=0.6)
    parser.add_argument("--rate", type=float, default=30.0)
    return parser.parse_args()


def main():
    try:
        import pygame
    except ImportError:
        raise SystemExit("pygame is required: pip install pygame")

    args = parse_args()
    rospy.init_node("airsim_multi_keyboard_satellite_ros")

    cmd_topic = topic_name(args.namespace, args.vehicle, "satellite_cmd")
    state_topic = topic_name(args.namespace, args.vehicle, "satellite_state")
    publisher = rospy.Publisher(cmd_topic, SatelliteControls, queue_size=1)
    latest_state = {"msg": None}

    def state_callback(message):
        latest_state["msg"] = message

    rospy.Subscriber(state_topic, SatelliteState, state_callback, queue_size=1)

    pygame.init()
    screen = pygame.display.set_mode((650, 220))
    pygame.display.set_caption(f"LAESim ROS satellite control: {args.vehicle}")
    font = pygame.font.SysFont("consolas", 18)
    clock = pygame.time.Clock()
    rate_hz = max(1.0, args.rate)

    while not rospy.is_shutdown():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                rospy.signal_shutdown("window closed")
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                rospy.signal_shutdown("escape")

        keys = pygame.key.get_pressed()
        msg = SatelliteControls()
        msg.header.stamp = rospy.Time.now()
        msg.vx = ((1.0 if keys[pygame.K_w] else 0.0) + (-1.0 if keys[pygame.K_s] else 0.0)) * args.speed
        msg.vy = ((1.0 if keys[pygame.K_d] else 0.0) + (-1.0 if keys[pygame.K_a] else 0.0)) * args.speed
        msg.vz = ((1.0 if keys[pygame.K_f] else 0.0) + (-1.0 if keys[pygame.K_r] else 0.0)) * args.speed
        msg.yaw_rate = ((1.0 if keys[pygame.K_e] else 0.0) + (-1.0 if keys[pygame.K_q] else 0.0)) * args.yaw_rate
        publisher.publish(msg)

        screen.fill((18, 22, 28))
        lines = [
            "W/S: NED X  A/D: NED Y  R/F: up/down  Q/E: yaw  ESC: quit",
            f"topic: {cmd_topic}",
            f"cmd vx={msg.vx:.2f} vy={msg.vy:.2f} vz={msg.vz:.2f} yaw_rate={msg.yaw_rate:.2f}",
        ]
        state = latest_state["msg"]
        if state is not None:
            lines.append(f"state speed={state.speed:.2f} v=({state.vx:.2f}, {state.vy:.2f}, {state.vz:.2f})")
        else:
            lines.append("state: waiting for satellite_state")
        for i, line in enumerate(lines):
            screen.blit(font.render(line, True, (220, 230, 240)), (20, 20 + i * 34))
        pygame.display.flip()
        clock.tick(rate_hz)

    stop_msg = SatelliteControls()
    stop_msg.header.stamp = rospy.Time.now()
    publisher.publish(stop_msg)
    pygame.quit()


if __name__ == "__main__":
    main()
