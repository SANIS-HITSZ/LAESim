# 使用 LAESim

LAESim 的主要使用入口是 Windows 侧 `settings.json`、UE 场景，以及仓库提供的 Python/ROS 示例。

## 选择配置模板

运行时配置固定放在：

```text
C:\Users\<用户名>\Documents\AirSim\settings.json
```

仓库提供四套模板：

- [单无人机与传感器](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_single_uav_with_sensors.json)
- [单汽车与传感器](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_single_car_with_sensors.json)
- [3 架无人机 + 3 辆汽车](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_airground_3uav_3car_with_sensors.json)
- [2 架无人机 + 1 辆汽车 + 1 艘船](https://github.com/SANIS-HITSZ/LAESim/blob/main/how_to_use_settings/settings_airground_2uav_1car_1boat_with_sensors.json)

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

## Windows Python API

`Multi_use` 目录提供不依赖 ROS 的控制和传感器工具：

```powershell
python .\Multi_use\keyboard_control.py --vehicle UAV
python .\Multi_use\car_keyboard_control.py --vehicle Car
python .\Multi_use\boat_keyboard_control.py --vehicle Boat
python .\Multi_use\sensor_probe.py
```

默认端口分别是：

| 对象 | 端口 |
| --- | --- |
| 通用/CV | `41451` |
| Car | `41461` |
| Multirotor | `41471` |
| Boat | `41481` |

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
python3 src/example/vehicle_state_monitor_ros.py
```

详细参数和 topic/service 见 [LAESim ROS 示例说明](https://github.com/SANIS-HITSZ/LAESim/blob/main/ros/src/example/README_zh.md)。

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
