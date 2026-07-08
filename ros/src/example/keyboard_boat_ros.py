#!/usr/bin/env python3

import argparse
import math
import sys

import pygame
import rospy

from airsim_ros_pkgs.msg import BoatControls, BoatState

from _ros_example_common import topic_name


def quaternion_to_yaw(quaternion):
    siny_cosp = 2.0 * ((quaternion.w * quaternion.z) + (quaternion.x * quaternion.y))
    cosy_cosp = 1.0 - (2.0 * ((quaternion.y * quaternion.y) + (quaternion.z * quaternion.z)))
    return math.atan2(siny_cosp, cosy_cosp)


def create_ui_font(size=16):
    pygame.font.init()
    for family in ("consolas", "couriernew"):
        try:
            return pygame.font.SysFont(family, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


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

    anchor = bool(keys[pygame.K_SPACE])
    brake = 1.0 if keys[pygame.K_b] else (args.idle_brake if abs(throttle) < 1e-6 else 0.0)
    return throttle, steering, brake, anchor


def draw_status(screen, font, lines):
    screen.fill((8, 10, 14))
    for index, line in enumerate(lines):
        screen.blit(font.render(line, True, (120, 220, 255)), (12, 12 + index * 23))
    pygame.display.flip()


def main():
    parser = argparse.ArgumentParser(description="ROS pygame control example for LAESim boats.")
    parser.add_argument("--vehicle", default="Boat")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--rate", type=float, default=30.0)
    parser.add_argument("--throttle", type=float, default=0.75)
    parser.add_argument("--reverse-throttle", type=float, default=0.35)
    parser.add_argument("--steering", type=float, default=0.45)
    parser.add_argument("--idle-brake", type=float, default=0.0)
    args = parser.parse_args()

    rospy.init_node("airsim_multi_keyboard_boat_ros")

    cmd_topic = topic_name(args.namespace, args.vehicle, "boat_cmd")
    state_topic = topic_name(args.namespace, args.vehicle, "boat_state")
    publisher = rospy.Publisher(cmd_topic, BoatControls, queue_size=1)

    latest_state = {
        "speed": None,
        "forward_speed": None,
        "lateral_speed": None,
        "yaw_rate": None,
        "x": None,
        "y": None,
        "z": None,
        "yaw_deg": None,
    }

    def boat_state_callback(message):
        latest_state["speed"] = message.speed
        latest_state["forward_speed"] = message.forward_speed
        latest_state["lateral_speed"] = message.lateral_speed
        latest_state["yaw_rate"] = message.yaw_rate
        latest_state["x"] = message.pose.pose.position.x
        latest_state["y"] = message.pose.pose.position.y
        latest_state["z"] = message.pose.pose.position.z
        latest_state["yaw_deg"] = math.degrees(quaternion_to_yaw(message.pose.pose.orientation))

    rospy.Subscriber(state_topic, BoatState, boat_state_callback, queue_size=1)

    pygame.init()
    screen = pygame.display.set_mode((1020, 185))
    pygame.display.set_caption(f"AirSim ROS {args.vehicle} boat keyboard control")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    print(f"ROS boat pygame control started for {args.vehicle}.")
    print("Keep the pygame window focused, and switch input method to English.")

    try:
        while not rospy.is_shutdown():
            quit_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    quit_requested = True

            if quit_requested:
                break

            keys = pygame.key.get_pressed()
            throttle, steering, brake, anchor = read_controls(keys, args)

            message = BoatControls()
            message.throttle = throttle
            message.steering = steering
            message.brake = brake
            message.anchor = anchor
            publisher.publish(message)

            if latest_state["speed"] is None:
                state_line = "state: waiting for boat_state..."
                pose_line = ""
            else:
                state_line = (
                    f"state speed={latest_state['speed']:.2f} m/s "
                    f"u={latest_state['forward_speed']:.2f} v={latest_state['lateral_speed']:.2f} "
                    f"r={latest_state['yaw_rate']:.3f} rad/s"
                )
                pose_line = (
                    "state pose=("
                    f"{latest_state['x']:.2f}, {latest_state['y']:.2f}, {latest_state['z']:.2f}) "
                    f"yaw={latest_state['yaw_deg']:.1f} deg"
                )

            draw_status(
                screen,
                font,
                [
                    "AirSim ROS boat keyboard control - pygame",
                    "W/S: ahead/reverse   A/D: rudder left/right   Space: anchor   B: brake   ESC/Q: quit",
                    f"cmd throttle={throttle:.2f} steering={steering:.2f} brake={brake:.2f} anchor={anchor}",
                    state_line,
                    pose_line,
                    f"ROS topic={cmd_topic}",
                ],
            )

            clock.tick(args.rate)
    finally:
        stop_message = BoatControls()
        stop_message.throttle = 0.0
        stop_message.steering = 0.0
        stop_message.brake = 1.0
        stop_message.anchor = True
        publisher.publish(stop_message)
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
