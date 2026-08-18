# 使用 LAESim

LAESim 的主要使用入口是 Windows 侧 `settings.json`、UE 场景，以及仓库提供的 Python/ROS 示例。

## 选择配置模板

运行时配置固定放在：

```text
%USERPROFILE%\Documents\AirSim\settings.json
```

仓库提供以下常用模板：

- [单无人机与传感器](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_single_uav_with_sensors.json)
- [无人机前视与稳定下视相机](https://github.com/SANIS-HITSZ/LAESim/blob/V1.5/how_to_use_settings/settings_uav_stable_nadir_camera.json)
- [单汽车与传感器](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_single_car_with_sensors.json)
- [3 架无人机 + 3 辆汽车](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_airground_3uav_3car_with_sensors.json)
- [2 架无人机 + 1 辆汽车 + 1 艘船](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_airground_2uav_1car_1boat_with_sensors.json)
- [空天地海混合载具](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_airground_2uav_1car_1boat_1satellite_with_sensors.json)
- [SceneMap 空地海场景](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_scene_map_1uav_1car_1boat.json)
- [卫星与 GPS 配准地图](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_satellite_map_gps_start.json)
- [天基任务桥接显示](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_space_mission_bridge.json)
- [可选网络仿真配置](https://github.com/SANIS-HITSZ/LAESim/blob/main/NetworkSim/config/network-simulation.example.json)

混合载具场景必须使用：

```json
"SimMode": "AirGround"
```

建议从模板复制完整配置，再修改载具名称、初始位置和传感器，不要从空 JSON 手工拼接。

## 启动场景

1. 把选定模板复制为用户目录中的 `settings.json`。
2. 用 UE 4.27 打开已接入 LAESim 插件的工程。
3. 点击 Play。
4. 检查场景中载具数量、类型和初始位置。
5. 使用 Python API 或 ROS 示例验证控制与状态。

修改 `settings.json` 后需要重新开始 Play，运行中的场景不会自动重载完整载具配置。

## 稳定云台相机

相机级 `Pitch/Roll/Yaw` 是相对载具的安装姿态，`Gimbal` 是世界坐标系稳定目标。正射采集、地图匹配、巡检和着陆观测可在保留前视相机的同时增加稳定下视相机：

```json
"nadir_stabilized": {
  "Pitch": -90,
  "Roll": 0,
  "Yaw": 0,
  "Gimbal": {
    "Stabilization": 1.0,
    "Pitch": -90,
    "Roll": 0,
    "Yaw": 0
  },
  "CaptureSettings": [
    { "ImageType": 0, "Width": 640, "Height": 480, "FOV_Degrees": 90 }
  ]
}
```

完整配置见上面的稳定下视模板。只稳定俯仰/横滚、让画面航向随机头变化时，省略 `Gimbal.Yaw`。完整 GeoTIFF 覆盖采集流程见[仿真案例](simulation_cases.md#geotiff)。

## Windows Python API

`Multi_use` 目录提供不依赖 ROS 的控制和传感器工具：

```powershell
python .\Multi_use\keyboard_control.py --vehicle UAV
python .\Multi_use\car_keyboard_control.py --vehicle Car
python .\Multi_use\boat_keyboard_control.py --vehicle Boat
python .\Multi_use\satellite_keyboard_control.py --vehicle Satellite
python .\Multi_use\scene_map_tools.py info
python .\Multi_use\sensor_probe.py
```

默认端口分别是：

| 对象 | 端口 |
| --- | --- |
| 通用/CV | `41451` |
| Car | `41461` |
| Multirotor | `41471` |
| Boat | `41481` |
| Satellite | `41491` |

完整参数见仓库中的 [Multi_use 使用说明](https://github.com/SANIS-HITSZ/LAESim/blob/main/Multi_use/README_zh.md)。

## ROS Noetic

ROS 工作空间位于 `ros/`。在 WSL2 中编译：

```bash
cd ~/LAESim/ros
source /opt/ros/noetic/setup.bash
catkin_make \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-8 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-8
source devel/setup.bash
```

Windows UE 已进入 Play 后连接：

```bash
bash src/example/connect_ue_ros.sh
```

常用示例：

```bash
python3 src/example/keyboard_uav_ros.py --vehicle UAV
python3 src/example/keyboard_car_ros.py --vehicle Car
python3 src/example/keyboard_boat_ros.py --vehicle Boat
python3 src/example/keyboard_satellite_ros.py --vehicle Satellite
python3 src/example/vehicle_state_monitor_ros.py
```

详细参数和 topic/service 见 [LAESim ROS 示例说明](https://github.com/SANIS-HITSZ/LAESim/blob/main/ros/src/example/README_zh.md)。

<a id="ros-lidar-frames"></a>
### LiDAR DataFrame 与多载具坐标

LiDAR 的 `DataFrame` 决定点坐标本身所在的坐标系，也决定 ROS `PointCloud2.header.frame_id`：

| `DataFrame` | 点坐标含义 | ROS `frame_id` |
| --- | --- | --- |
| `VehicleInertialFrame` | 以该载具出生点为原点的固定 NED/ENU 惯性系 | `<vehicle>` |
| `SensorLocalFrame` | LiDAR 传感器局部坐标系 | `<vehicle>/<lidar>` |

推荐在 settings 中显式填写，避免下游只看话题名猜坐标系：

```json
"Lidar1": {
  "SensorType": 6,
  "Enabled": true,
  "DataFrame": "VehicleInertialFrame"
}
```

当前 TF 链为 `world_ned -> <vehicle> -> <vehicle>/odom_local_ned -> <vehicle>/<lidar>`。其中 `<vehicle>` 是 settings 出生位姿对应的固定帧，`odom_local_ned` 随载具运动。多机点云融合时，各机惯性点云仍然具有不同出生点原点，必须通过 TF 转到 `world_ned`/`world_enu`；不能把数组直接拼接，也不能再次按机体位姿手工变换。

修改 ROS wrapper 源码或切换运行副本后，需要重新编译并重启 wrapper；UE 插件不需要为这个 ROS 元数据修复重新编译：

```bash
cd ~/LAESim/ros
source /opt/ros/noetic/setup.bash
catkin_make --pkg airsim_ros_pkgs -j2
source devel/setup.bash
bash src/example/connect_ue_ros.sh
```

验证实际 header：

```bash
rostopic echo -n 1 /airsim_node/UAV/lidar/Lidar1/header
rosrun tf tf_echo world_ned UAV
```

本节表格即为 LAESim ROS wrapper 的完整 `DataFrame` 映射；更多 ROS 话题检查示例见仓库中的 `ros/src/example/README_zh.md`。

## 启用或关闭 ns-3

默认保持理想通信：

```json
"NetworkSimulation": {
  "Backend": "none"
}
```

完成 WSL2/ns-3 安装后，可以改为：

```json
"NetworkSimulation": {
  "Backend": "ns3"
}
```

并启动 ROS 网络桥接器。完整配置和验证命令见[WSL2、ROS 与 ns-3](laesim_wsl_ros_ns3.md)。

## Boat 使用边界

Boat 在地面平面上使用简化三自由度模型运动，不要求 UE 水体，也不模拟波浪、水流和浮力。它适合任务规划、编队控制、感知与通信研究；需要高保真船舶水动力时，应接入专用水动力模型。

## Satellite、天基任务与 SceneMap

Satellite 使用三维理想质点模型，不等同于轨道动力学仿真。需要卫星轨道、星下点、可见性和任务几何量时，使用 `Multi_use/space_mission_bridge.py` 连接 TLE/SGP4、CSV 或 mock 数据源，LAESim 只负责缩放显示和传感器挂载。SceneMap 的 `ImagePath` 必须指向 Windows UE 进程能够读取的真实图片；模板中的 `C:/path/to/...` 是需要替换的占位路径。详细配置与 API 见仓库中的 [图片场景地图说明](https://github.com/SANIS-HITSZ/LAESim/blob/main/%E5%A6%82%E4%BD%95%E5%8A%A0%E5%85%A5%E5%9B%BE%E7%89%87%E5%9C%BA%E6%99%AF%E5%9C%B0%E5%9B%BE%E5%8A%9F%E8%83%BD.md) 和 [天基任务桥接说明](space_mission_bridge.md)。
