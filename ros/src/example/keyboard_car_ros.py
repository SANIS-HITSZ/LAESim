#!/usr/bin/env python3

import argparse
import math
import sys

import pygame
import rospy

from airsim_ros_pkgs.msg import CarControls, CarState

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
    brake = 0.0
    handbrake = bool(keys[pygame.K_SPACE])
    reverse = False

    if keys[pygame.K_w]:
        throttle = args.throttle
    elif keys[pygame.K_s]:
        throttle = -abs(args.reverse_throttle)
        reverse = True

    if keys[pygame.K_a]:
        steering -= abs(args.steering)
    if keys[pygame.K_d]:
        steering += abs(args.steering)

    if keys[pygame.K_b]:
        throttle = 0.0
        brake = 1.0
        reverse = False
    elif abs(throttle) < 1e-6 and not handbrake:
        brake = args.idle_brake

    return throttle, steering, brake, handbrake, reverse


def draw_status(screen, font, lines):
    screen.fill((8, 10, 12))
    for index, line in enumerate(lines):
        screen.blit(font.render(line, True, (90, 235, 170)), (12, 12 + index * 23))
    pygame.display.flip()


def main():
    parser = argparse.ArgumentParser(description="ROS pygame control example for AirSim_Multi cars.")
    parser.add_argument("--vehicle", default="Car")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--rate", type=float, default=30.0)
    parser.add_argument("--throttle", type=float, default=0.7)
    parser.add_argument("--reverse-throttle", type=float, default=0.5)
    parser.add_argument("--steering", type=float, default=0.4)
    parser.add_argument("--idle-brake", type=float, default=0.0)
    args = parser.parse_args()

    rospy.init_node("airsim_multi_keyboard_car_ros")

    cmd_topic = topic_name(args.namespace, args.vehicle, "car_cmd")
    state_topic = topic_name(args.namespace, args.vehicle, "car_state")
    publisher = rospy.Publisher(cmd_topic, CarControls, queue_size=1)

    latest_state = {
        "speed": None,
        "gear": None,
        "rpm": None,
        "x": None,
        "y": None,
        "z": None,
        "yaw_deg": None,
    }

    def car_state_callback(message):
        latest_state["speed"] = message.speed
        latest_state["gear"] = message.gear
        latest_state["rpm"] = message.rpm
        latest_state["x"] = message.pose.pose.position.x
        latest_state["y"] = message.pose.pose.position.y
        latest_state["z"] = message.pose.pose.position.z
        latest_state["yaw_deg"] = math.degrees(quaternion_to_yaw(message.pose.pose.orientation))

    rospy.Subscriber(state_topic, CarState, car_state_callback, queue_size=1)

    pygame.init()
    screen = pygame.display.set_mode((980, 170))
    pygame.display.set_caption(f"AirSim ROS {args.vehicle} car keyboard control")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    print(f"ROS car pygame control started for {args.vehicle}.")
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
            throttle, steering, brake, handbrake, reverse = read_controls(keys, args)

            message = CarControls()
            message.throttle = throttle
            message.steering = steering
            message.brake = brake
            message.handbrake = handbrake
            message.manual = reverse
            message.manual_gear = -1 if reverse else 0
            message.gear_immediate = True
            publisher.publish(message)

            if latest_state["speed"] is None:
                state_line = "state: waiting for car_state..."
                pose_line = ""
            else:
                state_line = (
                    f"state speed={latest_state['speed']:.2f} m/s "
                    f"gear={latest_state['gear']} rpm={latest_state['rpm']:.1f}"
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
                    "AirSim ROS car keyboard control - pygame",
                    "W/S: throttle forward/back   A/D: steer left/right   Space: handbrake   B: brake   ESC/Q: quit",
                    f"cmd throttle={throttle:.2f} steering={steering:.2f} brake={brake:.2f} handbrake={handbrake} reverse={reverse}",
                    state_line,
                    pose_line,
                    f"ROS topic={cmd_topic}",
                ],
            )

            clock.tick(args.rate)
    finally:
        stop_message = CarControls()
        stop_message.throttle = 0.0
        stop_message.steering = 0.0
        stop_message.brake = 1.0
        stop_message.handbrake = False
        stop_message.manual = False
        stop_message.manual_gear = 0
        stop_message.gear_immediate = True
        publisher.publish(stop_message)
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
