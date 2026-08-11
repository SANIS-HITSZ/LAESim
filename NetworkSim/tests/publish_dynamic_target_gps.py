#!/usr/bin/env python3
"""Publish a deterministic NavSatFix target for ROS integration tests."""

from __future__ import annotations

import argparse

import rospy
from sensor_msgs.msg import NavSatFix, NavSatStatus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehicle", default="Car")
    parser.add_argument("--latitude", type=float, default=22.591164)
    parser.add_argument("--longitude", type=float, default=113.975317)
    parser.add_argument("--altitude", type=float, default=0.0)
    parser.add_argument("--rate", type=float, default=5.0)
    args = parser.parse_args(rospy.myargv()[1:])

    rospy.init_node("laesim_dynamic_target_gps_test", anonymous=True)
    publisher = rospy.Publisher(
        f"/airsim_node/{args.vehicle}/global_gps", NavSatFix, queue_size=1
    )
    rate = rospy.Rate(max(0.1, args.rate))
    while not rospy.is_shutdown():
        message = NavSatFix()
        message.header.stamp = rospy.Time.now()
        message.header.frame_id = args.vehicle
        message.status.status = NavSatStatus.STATUS_FIX
        message.status.service = NavSatStatus.SERVICE_GPS
        message.latitude = args.latitude
        message.longitude = args.longitude
        message.altitude = args.altitude
        publisher.publish(message)
        rate.sleep()


if __name__ == "__main__":
    main()
