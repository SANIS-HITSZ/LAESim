# How to Use Lidar in AirSim

AirSim supports Lidar for multirotors and cars.

The enablement of lidar and the other lidar settings can be configured via AirSimSettings json.
Please see [general sensors](sensors.md) for information on configruation of general/shared sensor settings.

## Enabling lidar on a vehicle
* By default, lidars are not enabled. To enable lidar, set the SensorType and Enabled attributes in settings json.

```json
    "Lidar1": {
         "SensorType": 6,
         "Enabled" : true,
    }
```

* Multiple lidars can be enabled on a vehicle.

## Lidar configuration
The following parameters can be configured right now via settings json.

Parameter                 | Description
--------------------------| ------------
NumberOfChannels          | Number of channels/lasers of the lidar
Range                     | Range, in meters
PointsPerSecond           | Number of points captured per second
RotationsPerSecond        | Rotations per second
HorizontalFOVStart        | Horizontal FOV start for the lidar, in degrees
HorizontalFOVEnd          | Horizontal FOV end for the lidar, in degrees
VerticalFOVUpper          | Vertical FOV upper limit for the lidar, in degrees
VerticalFOVLower          | Vertical FOV lower limit for the lidar, in degrees
X Y Z                     | Position of the lidar relative to the vehicle (in NED, in meters)
Roll Pitch Yaw            | Orientation of the lidar relative to the vehicle  (in degrees, yaw-pitch-roll order to front vector +X)
DataFrame                 | Frame for the points in output ("VehicleInertialFrame" or "SensorLocalFrame")
ExternalController        | Whether data is to be sent to external controller such as ArduPilot or PX4 if being used (default `true`) (PX4 doesn't send Lidar data currently)

e.g.

```json
{
    "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
    "SettingsVersion": 1.2,

    "SimMode": "Multirotor",

     "Vehicles": {
		"Drone1": {
			"VehicleType": "simpleflight",
			"AutoCreate": true,
			"Sensors": {
			    "LidarSensor1": {
					"SensorType": 6,
					"Enabled" : true,
					"NumberOfChannels": 16,
					"RotationsPerSecond": 10,
					"PointsPerSecond": 100000,
					"X": 0, "Y": 0, "Z": -1,
					"Roll": 0, "Pitch": 0, "Yaw" : 0,
					"VerticalFOVUpper": -15,
					"VerticalFOVLower": -25,
					"HorizontalFOVStart": -20,
					"HorizontalFOVEnd": 20,
					"DrawDebugPoints": true,
					"DataFrame": "SensorLocalFrame"
				},
				"LidarSensor2": {
				   "SensorType": 6,
					"Enabled" : true,
					"NumberOfChannels": 4,
					"RotationsPerSecond": 10,
					"PointsPerSecond": 10000,
					"X": 0, "Y": 0, "Z": -1,
					"Roll": 0, "Pitch": 0, "Yaw" : 0,
					"VerticalFOVUpper": -15,
					"VerticalFOVLower": -25,
					"DrawDebugPoints": true,
					"DataFrame": "SensorLocalFrame"
				}
			}
		}
    }
}
```

## ROS PointCloud2 frame semantics in LAESim

LAESim's ROS wrapper preserves the configured `DataFrame` in the published
`sensor_msgs/PointCloud2.header.frame_id`:

DataFrame                  | Point coordinates | ROS `frame_id`
---------------------------|-------------------|---------------
`VehicleInertialFrame`     | Fixed NED/ENU frame at this vehicle's starting point | `VEHICLE_NAME`
`SensorLocalFrame`         | Lidar-local frame | `VEHICLE_NAME/SENSOR_NAME`
Unknown value              | Not safely identifiable | Sensor frame, with a throttled warning

The relevant TF chain is:

```text
world_ned -> VEHICLE_NAME -> VEHICLE_NAME/odom_local_ned -> VEHICLE_NAME/SENSOR_NAME
```

`VEHICLE_NAME` is fixed at the position and orientation configured for that
vehicle in `settings.json`; `VEHICLE_NAME/odom_local_ned` moves with the
vehicle. Consequently, `VehicleInertialFrame` data must not be labelled as the
moving odometry or body frame. In a multi-vehicle setup each inertial point
cloud initially has a different starting-point origin. Use TF to transform all
clouds to `world_ned` (or `world_enu`) before merging them.

When `coordinate_system_enu` is enabled, LAESim applies only the NED-to-ENU
basis change `(x, y, z) -> (y, x, -z)` to point values. It does not apply the
vehicle pose a second time. Rebuild and restart `airsim_ros_pkgs` after changing
the wrapper source; restart both UE Play and the wrapper after changing
`DataFrame` in `settings.json`.

## Server side visualization for debugging

By default, the lidar points are not drawn on the viewport. To enable the drawing of hit laser points on the viewport, please enable setting `DrawDebugPoints` via settings json.

```json
    "Lidar1": {
         ...
         "DrawDebugPoints": true
    },
```

**Note:** Enabling `DrawDebugPoints` can cause excessive memory usage and crash in releases `v1.3.1`, `v1.3.0`. This has been fixed in the main branch and should work in later releases

## Client API

Use `getLidarData()` API to retrieve the Lidar data.

* The API returns a Point-Cloud as a flat array of floats along with the timestamp of the capture and lidar pose.
* Point-Cloud:
    * The floats represent [x,y,z] coordinate for each point hit within the range in the last scan.
    * The frame for the points in the output is configurable using "DataFrame" attribute -
        * "" or `VehicleInertialFrame` -- default; returned points are in vehicle inertial frame (in NED, in meters)
        * `SensorLocalFrame` -- returned points are in lidar local frame (in NED, in meters)
* Lidar Pose:
    * Lidar pose in the vehicle inertial frame (in NED, in meters)
    * Can be used to transform points to other frames.
* Segmentation: The segmentation of each lidar point's collided object

### Python Examples
- [drone_lidar.py](https://github.com/microsoft/AirSim/blob/main/PythonClient/multirotor/drone_lidar.py)
- [car_lidar.py](https://github.com/microsoft/AirSim/blob/main/PythonClient/car/car_lidar.py)
- [sensorframe_lidar_pointcloud.py](https://github.com/microsoft/AirSim/blob/main/PythonClient/multirotor/sensorframe_lidar_pointcloud.py)
- [vehicleframe_lidar_pointcloud.py](https://github.com/microsoft/AirSim/blob/main/PythonClient/multirotor/vehicleframe_lidar_pointcloud.py)

## Coming soon
* Visualization of lidar data on client side.
