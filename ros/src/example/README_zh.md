# LAESim ROS 示例使用说明

这个目录放的是 `LAESim + UE + ROS Noetic` 的示例脚本。目标不是做一个大而全的单体程序，而是把最常见的联调任务拆成若干小工具，方便接手的人逐步定位问题。

默认假设使用环境满足下面几件事：

- Windows 上的 UE 工程已经打开并 `Play`
- WSL 里已经把整个 `LAESim` 放在 ext4 路径中，例如 `$HOME/LAESim`
- `ros/` 已经 `catkin_make`
- 当前终端已经 `source /opt/ros/noetic/setup.bash` 和 `source devel/setup.bash`

如果机器上没有 `/usr/bin/g++-8`，可以先用默认 `catkin_make` 编译；当前船相关 ROS 消息和 wrapper 已经按默认 g++ 通过过一次构建。

ROS 示例默认读取 `/mnt/c/Users/.../Documents/AirSim/settings.json` 这份 Windows 侧配置在 WSL 中的挂载路径，不需要再单独维护一份 WSL 本地副本。

## 1. connect_ue_ros.sh

这个脚本可以：

- 自动获取 Windows 主机在 WSL 里的可访问 IP
- 用这个 IP 启动 `airsim_node`

命令：

```bash
bash src/example/connect_ue_ros.sh
```

它等价于：

```bash
WIN_IP=$(ip route | awk '/default/ {print $3; exit}')
echo $WIN_IP
roslaunch airsim_ros_pkgs airsim_node.launch output:=screen host:=$WIN_IP
```

建议这样用：

- Windows 端先 `Play`
- 再运行这个脚本
- 连上后先 `rostopic list | grep airsim_node` 看一眼话题是否出来

## 2. keyboard_uav_ros.py

这个脚本可以：

- 基于 ROS 话题控制无人机
- 使用 `pygame` 窗口，而不是终端逐字输入
- 可以发 `takeoff` / `land` 服务

命令：

```bash
python3 src/example/keyboard_uav_ros.py --vehicle UAV
```

常用参数：

- `--vehicle`：控制哪架无人机
- `--namespace`：默认 `/airsim_node`
- `--rate`：发布频率
- `--speed`：水平速度
- `--vertical-speed`：上下速度
- `--yaw-rate-deg`：偏航角速度
- `--boost-ratio`：按住 `Space` 的加速倍率
- `--auto-takeoff`：启动脚本后自动起飞

按键：

- `Up/Down`：前进 / 后退
- `Left/Right`：左 / 右平移
- `W/S`：上升 / 下降
- `A/D`：左 / 右偏航
- `Space`：加速
- `T`：起飞
- `L`：降落
- `ESC/Q`：退出

它对应的 ROS 接口是：

- 发布：`/airsim_node/<vehicle>/vel_cmd_body_frame`
- 订阅：`/airsim_node/<vehicle>/odom_local_ned`
- 服务：`/airsim_node/<vehicle>/takeoff`、`/airsim_node/<vehicle>/land`

## 3. keyboard_car_ros.py

这个脚本可以：

- 基于 ROS 话题控制汽车
- 使用 `pygame` 窗口
- 支持油门、倒车、转向、刹车、手刹

命令：

```bash
python3 src/example/keyboard_car_ros.py --vehicle Car
```

常用参数：

- `--vehicle`：控制哪辆车
- `--rate`：发布频率
- `--throttle`：前进油门
- `--reverse-throttle`：倒车油门
- `--steering`：转向量
- `--idle-brake`：空挡时轻微刹车

按键：

- `W`：前进
- `S`：倒车
- `A/D`：左 / 右打轮
- `Space`：手刹
- `B`：刹车
- `ESC/Q`：退出

它对应的 ROS 接口是：

- 发布：`/airsim_node/<vehicle>/car_cmd`
- 订阅：`/airsim_node/<vehicle>/car_state`

## 4. keyboard_boat_ros.py

这个脚本可以：

- 基于 ROS 话题控制船 / 水面载具
- 使用 `pygame` 窗口
- 支持推进、倒退、舵角、刹车、抛锚
- 显示船的 `speed / forward_speed / lateral_speed / yaw_rate`

船在 UE 地面平面上运动，不要求场景里有真实水体。运动模型按简化船舶平面三自由度来做，保留转向惯性和横向漂移，不做波浪、水流、浮力等水相互作用。

命令：

```bash
python3 src/example/keyboard_boat_ros.py --vehicle Boat
```

常用参数：

- `--vehicle`：控制哪艘船
- `--rate`：发布频率
- `--throttle`：前进推进量
- `--reverse-throttle`：倒退推进量
- `--steering`：舵角 / 转向量
- `--idle-brake`：空挡时轻微刹车

按键：

- `W`：前进
- `S`：倒退
- `A/D`：左 / 右舵
- `Space`：抛锚
- `B`：刹车
- `ESC/Q`：退出

它对应的 ROS 接口是：

- 发布：`/airsim_node/<vehicle>/boat_cmd`
- 订阅：`/airsim_node/<vehicle>/boat_state`

`boat_cmd` 使用 `airsim_ros_pkgs/BoatControls`：

- `throttle`
- `steering`
- `brake`
- `anchor`

`boat_state` 使用 `airsim_ros_pkgs/BoatState`，核心字段是：

- `speed`
- `forward_speed`
- `lateral_speed`
- `yaw_rate`
- `pose`
- `twist`

## 5. keyboard_satellite_ros.py

这个脚本可以：

- 基于 ROS 话题控制 `SimpleSatellite`
- 使用 `pygame` 窗口
- 直接发送三维 NED 速度 `vx / vy / vz`
- 发送 `yaw_rate` 控制偏航角速度
- 松开按键时发送零速度，使卫星静止悬停

命令：

```bash
python3 src/example/keyboard_satellite_ros.py --vehicle Satellite
```

常用参数：

- `--vehicle`：控制哪个卫星实例
- `--rate`：发布频率
- `--speed`：单轴速度，单位 m/s
- `--yaw-rate`：偏航角速度，单位 rad/s

按键：

- `W/S`：NED X 正 / 负方向
- `A/D`：NED Y 负 / 正方向
- `R/F`：上升 / 下降，其中 `vz` 为 NED 速度，正数表示向下
- `Q/E`：左 / 右偏航
- `ESC`：退出

它对应的 ROS 接口是：

- 发布：`/airsim_node/<vehicle>/satellite_cmd`
- 订阅：`/airsim_node/<vehicle>/satellite_state`

`satellite_cmd` 使用 `airsim_ros_pkgs/SatelliteControls`：

- `vx`
- `vy`
- `vz`
- `yaw_rate`

`satellite_state` 使用 `airsim_ros_pkgs/SatelliteState`，核心字段是：

- `speed`
- `vx`
- `vy`
- `vz`
- `yaw_rate`
- `pose`
- `twist`

## 6. vehicle_state_monitor_ros.py

这个脚本可以：

- 按固定频率打印各实例的状态
- 适合先确认 ROS 和 UE 是否真的连上

命令：

```bash
python3 src/example/vehicle_state_monitor_ros.py
```

常用参数：

- `--settings`：手动指定 `settings.json`
- `--vehicle`：只监视指定实例
- `--namespace`：默认 `/airsim_node`
- `--print-rate`：打印频率

它会去看的话题有：

- `/airsim_node/<vehicle>/odom_local_ned`
- `/airsim_node/<vehicle>/environment`
- `/airsim_node/<vehicle>/global_gps`
- `/airsim_node/<vehicle>/car_state`（仅汽车）
- `/airsim_node/<vehicle>/boat_state`（仅船）
- `/airsim_node/<vehicle>/satellite_state`（仅卫星）

## 7. sensor_config_report_ros.py

这个脚本可以：

- 读取 `settings.json`
- 推导每个实例应该出现的相机 / 雷达 / 状态话题
- 对照当前 ROS master 实际话题

命令：

```bash
python3 src/example/sensor_config_report_ros.py
```

常用参数：

- `--settings`：指定 WSL 内可访问的 `settings.json`
- `--vehicle`：只检查指定实例
- `--namespace`：默认 `/airsim_node`
- `--wait-secs`：等待 ROS master 话题刷新的时间
- `--json`：输出 JSON 报告

适合做什么：

- 看 `settings.json` 是否写漏了相机或雷达
- 看 `PublishToRos` 是否开了
- 看话题命名是否和预期一致

## 8. camera_record_ros.py

这个脚本可以：

- 根据 `settings.json` 自动订阅相机话题
- 每个 topic 默认保存一张图片

命令：

```bash
python3 src/example/camera_record_ros.py
```

常用参数：

- `--settings`
- `--vehicle`
- `--namespace`
- `--output-root`
- `--max-per-topic`
- `--timeout`

输出默认会保存到：

```text
./camera_record_ros_outputs/camera_record_<timestamp>/
```

适合做什么：

- 快速验证 ROS 相机图像是否正常发布
- 对照 Windows 侧 `sensor_probe.py` 的结果

## 9. lidar_record_ros.py

这个脚本可以：

- 根据 `settings.json` 自动订阅 lidar 话题
- 每个 lidar topic 默认保存 1 个 `.pcd`

命令：

```bash
python3 src/example/lidar_record_ros.py
```

常用参数：

- `--settings`
- `--vehicle`
- `--namespace`
- `--output-root`
- `--max-per-topic`
- `--timeout`

输出默认会保存到：

```text
./lidar_record_ros_outputs/lidar_record_<timestamp>/
```

## 10. _ros_example_common.py

这是内部公共模块，不是给别人直接运行的脚本。它负责：

- 自动找 Windows `settings.json` 在 WSL 里的挂载路径
- 兼容带 BOM 的 `settings.json`
- 推导 topic 名字
- 从 `settings.json` 里枚举相机和传感器
- 保存 ASCII `pcd`

## 11. 建议的联调顺序

如果第一次联调，建议按下面顺序走：

1. Windows 端打开 UE 并 `Play`
2. WSL 里运行 `bash src/example/connect_ue_ros.sh`
3. 新开一个终端，`source devel/setup.bash`
4. 运行 `python3 src/example/sensor_config_report_ros.py`
5. 运行 `python3 src/example/vehicle_state_monitor_ros.py`
6. 运行 `python3 src/example/camera_record_ros.py`
7. 运行 `python3 src/example/lidar_record_ros.py`
8. 最后再用 `keyboard_uav_ros.py`、`keyboard_car_ros.py`、`keyboard_boat_ros.py` 和 `keyboard_satellite_ros.py` 做控制联调
