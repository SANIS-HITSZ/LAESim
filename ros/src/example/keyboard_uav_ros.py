#!/usr/bin/env python3

import argparse
import math
import sys

import pygame
import rospy

from nav_msgs.msg import Odometry

from airsim_ros_pkgs.msg import VelCmd
from airsim_ros_pkgs.srv import Land, Takeoff

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


def call_service(proxy, label):
    try:
        response = proxy(waitOnLastTask=True)
        print(f"{label}: success={response.success}")
    except rospy.ServiceException as exc:
        print(f"{label}: {exc}")


def read_controls(keys, args):
    scale = args.boost_ratio if keys[pygame.K_SPACE] else 1.0

    vx = 0.0
    vy = 0.0
    vz = 0.0
    yaw_rate = 0.0

    if keys[pygame.K_UP]:
        vx += args.speed * scale
    if keys[pygame.K_DOWN]:
        vx -= args.speed * scale
    if keys[pygame.K_LEFT]:
        vy -= args.speed * scale
    if keys[pygame.K_RIGHT]:
        vy += args.speed * scale
    if keys[pygame.K_w]:
        vz -= args.vertical_speed * scale
    if keys[pygame.K_s]:
        vz += args.vertical_speed * scale
    if keys[pygame.K_a]:
        yaw_rate -= args.yaw_rate_rad * scale
    if keys[pygame.K_d]:
        yaw_rate += args.yaw_rate_rad * scale

    return vx, vy, vz, yaw_rate, scale


def draw_status(screen, font, lines):
    screen.fill((8, 10, 12))
    for index, line in enumerate(lines):
        screen.blit(font.render(line, True, (90, 235, 170)), (12, 12 + index * 23))
    pygame.display.flip()


def main():
    parser = argparse.ArgumentParser(description="ROS pygame control example for AirSim_Multi multirotors.")
    parser.add_argument("--vehicle", default="UAV")
    parser.add_argument("--namespace", default="/airsim_node")
    parser.add_argument("--rate", type=float, default=30.0)
    parser.add_argument("--speed", type=float, default=2.0)
    parser.add_argument("--vertical-speed", type=float, default=2.0)
    parser.add_argument("--yaw-rate-deg", type=float, default=45.0)
    parser.add_argument("--boost-ratio", type=float, default=2.0)
    parser.add_argument("--auto-takeoff", action="store_true")
    args = parser.parse_args()
    args.yaw_rate_rad = math.radians(args.yaw_rate_deg)

    rospy.init_node("airsim_multi_keyboard_uav_ros")

    cmd_topic = topic_name(args.namespace, args.vehicle, "vel_cmd_body_frame")
    odom_topic = topic_name(args.namespace, args.vehicle, "odom_local_ned")
    takeoff_service = topic_name(args.namespace, args.vehicle, "takeoff")
    land_service = topic_name(args.namespace, args.vehicle, "land")

    publisher = rospy.Publisher(cmd_topic, VelCmd, queue_size=1)
    takeoff_proxy = rospy.ServiceProxy(takeoff_service, Takeoff)
    land_proxy = rospy.ServiceProxy(land_service, Land)

    latest_state = {
        "x": None,
        "y": None,
        "z": None,
        "yaw_deg": None,
    }

    def odom_callback(message):
        latest_state["x"] = message.pose.pose.position.x
        latest_state["y"] = message.pose.pose.position.y
        latest_state["z"] = message.pose.pose.position.z
        latest_state["yaw_deg"] = math.degrees(quaternion_to_yaw(message.pose.pose.orientation))

    rospy.Subscriber(odom_topic, Odometry, odom_callback, queue_size=1)

    pygame.init()
    screen = pygame.display.set_mode((980, 175))
    pygame.display.set_caption(f"AirSim ROS {args.vehicle} multirotor keyboard control")
    font = create_ui_font(16)
    clock = pygame.time.Clock()

    if args.auto_takeoff:
        rospy.wait_for_service(takeoff_service, timeout=10.0)
        call_service(takeoff_proxy, "takeoff")

    print(f"ROS UAV pygame control started for {args.vehicle}.")
    print("Keep the pygame window focused, and switch input method to English.")

    try:
        while not rospy.is_shutdown():
            quit_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        quit_requested = True
                    elif event.key == pygame.K_t:
                        rospy.wait_for_service(takeoff_service, timeout=10.0)
                        call_service(takeoff_proxy, "takeoff")
                    elif event.key == pygame.K_l:
                        rospy.wait_for_service(land_service, timeout=10.0)
                        call_service(land_proxy, "land")

            if quit_requested:
                break

            keys = pygame.key.get_pressed()
            vx, vy, vz, yaw_rate, scale = read_controls(keys, args)

            command = VelCmd()
            command.twist.linear.x = vx
            command.twist.linear.y = vy
            command.twist.linear.z = vz
            command.twist.angular.z = yaw_rate
            publisher.publish(command)

            if latest_state["x"] is None:
                pose_line = "state: waiting for odom..."
            else:
                pose_line = (
                    "state pos=("
                    f"{latest_state['x']:.2f}, {latest_state['y']:.2f}, {latest_state['z']:.2f}) "
                    f"yaw={latest_state['yaw_deg']:.1f} deg"
                )

            draw_status(
                screen,
                font,
                [
                    "AirSim ROS multirotor keyboard control - pygame",
                    "Arrow keys: forward/back/left/right   W/S: up/down   A/D: yaw left/right",
                    "Space: boost   T: takeoff   L: land   ESC/Q: quit",
                    f"cmd body vel=({vx:.2f}, {vy:.2f}, {vz:.2f}) yaw_rate={math.degrees(yaw_rate):.1f} deg/s boost={scale:.1f}x",
                    pose_line,
                    f"ROS topic={cmd_topic}",
                ],
            )

            clock.tick(args.rate)
    finally:
        stop_command = VelCmd()
        publisher.publish(stop_command)
        pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
