# LAESim ROS 示例使用说明

这个目录放的是 `LAESim + UE + ROS Noetic` 的示例脚本。目标不是做一个大而全的单体程序，而是把最常见的联调任务拆成若干小工具，方便接手的人逐步定位问题。

默认假设使用环境满足下面几件事：

- Windows 上的 UE 工程已经打开并 `Play`
- WSL 里已经把整个 `LAESim` 放在 ext4 路径中，例如 `/home/ag/LAESim`
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

## 6. space_mission_bridge_ros.py

这个脚本发布 TLE/SGP4、CSV 或 mock 卫星真值，并可选地把缩放后的显示坐标同步到 LAESim 的 `SimpleSatellite` 模型。

消息类型：

```text
airsim_ros_pkgs/SpaceSatelliteState
airsim_ros_pkgs/SpaceAccessState
```

默认话题：

```text
/space/<vehicle>/space_satellite_state
/space/<vehicle>/state
/space/<vehicle>/access/<target>
```

CSV 回放，只发布 ROS 真值：

```bash
python3 src/example/space_mission_bridge_ros.py --provider csv --csv ../Multi_use/space_mission_sample.csv --vehicle Satellite
```

CSV 回放，同时驱动 UE 里的卫星显示：

```bash
python3 src/example/space_mission_bridge_ros.py --provider csv --csv ../Multi_use/space_mission_sample.csv --vehicle Satellite --drive-laesim --host <Windows主机IP>
```

TLE/SGP4 模式需要安装 `sgp4`。从 WSL 驱动 Windows UE 还需要 AirSim RPC 的 `msgpack-rpc-python`：

```bash
python3 -m pip install --user sgp4 msgpack-rpc-python
```

如果要驱动 Windows UE，需要通过 `--host <Windows主机IP>` 连接 LAESim RPC。`NetworkSim/scripts/run_tle_space_network_demo.sh` 会自动从 WSL 默认路由解析该 IP。

如果传入目标：

```bash
python3 src/example/space_mission_bridge_ros.py --provider mock --vehicle Satellite --target Island:22.591164:113.975317:0
```

会额外发布：

```text
/space/Satellite/access/Island
```

里面包含 `access / azimuth_deg / elevation_deg / range_m`，可用于演示卫星是否看得到岛、船、无人机或地面站。

也可以把 LAESim 中的移动载具直接作为目标：

```bash
python3 src/example/space_mission_bridge_ros.py \
  --provider tle \
  --tle ../Multi_use/space_mission_sample.tle \
  --vehicle Satellite \
  --target-vehicle Car:ground \
  --target-vehicle Boat:sea \
  --target-vehicle UAV:air
```

每个 `--target-vehicle` 都会订阅 `/airsim_node/<vehicle>/global_gps` 并实时更新 access。不要直接比较多辆载具的 `odom_local_ned`，因为该位置以各自 starting point 为原点；`global_gps` 才适合统一的星地几何计算。超过 `--dynamic-target-max-age` 没有收到新 GPS 时会发布 `valid=false`。

真实 TLE 一键演示：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_space_network_demo.sh
```

该脚本会刷新并校验当前 TLE、自动定位下一次可见窗口、加速场景时间、驱动 UE 卫星、发布动态 access，并把逐帧记录与窗口摘要写到 `${HOME}/LAESim/.runtime/tle_demo/`。核心新增参数包括：

- `--auto-next-access`：自动把场景起点放到下一窗口之前。
- `--clock-speed`：场景时间相对墙钟时间的倍率。
- `--max-tle-age-days` / `--require-fresh-tle`：检查或强制限制 TLE 历元偏差。
- `--display-mode global-track`：把全球地面轨迹压缩为 UE 场景内的有界轨迹。
- `--mission-report-jsonl` / `--runtime-summary-json`：记录逐帧状态和访问窗口摘要。
- `--max-range-m`：全局最大作用距离；0 表示不限制。
- `--max-off-nadir-deg`：全局最大离天底角，限制载荷侧摆能力。
- `--sensor-pointing-mode`：`none/nadir/side-look/target-track`。
- `--sensor-half-angle-deg` / `--side-look-angle-deg`：圆锥半视场和固定侧摆角。

### 6.1 space_constellation_bridge_ros.py

这个脚本是可选的多星实时入口。每个 `--satellite VEHICLE=TLE_PATH` 创建一个独立传播器，发布该卫星的 state/access，并可同时驱动 UE 中同名的 `SimpleSatellite`：

```bash
python3 src/example/space_constellation_bridge_ros.py \
  --satellite Satellite=../Multi_use/sat1.tle \
  --satellite Satellite2=../Multi_use/sat2.tle \
  --target-vehicle Car:ground \
  --clock-speed 120 --drive-laesim --host <Windows主机IP>
```

通常直接使用一键脚本，它会下载当前 TLE、解析 Windows 主机 IP、启动或复用 NetworkSim，并写运行报告：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

新增话题：

```text
/space/selection/<target>       # 最佳卫星、候选、切换和中断信息
/space/constellation/state      # 星座数量与各目标当前选择摘要
```

选择器默认优先最高仰角，并用 2 度迟滞和 10 秒最短保持时间抑制来回切换。`space_constellation_summary.json` 记录 handover、outage、interruption 和 revisit 统计。

默认一键脚本还会加 `--publish-isl`，发布卫星两两之间的 `SpaceAccessState`。`--max-isl-range-m` 控制最大星间作用距离，默认 5000000 m；当前判据只使用真实星间距离。

按当前选择结果自动验证星地 ns-3 链路：

```bash
python3 NetworkSim/tests/ros_constellation_handover_test.py --target Car --duration 60
```

两跳中继数据包在 `/network_sim/tx` JSON 中增加：

```json
"route": ["Satellite", "Satellite2", "Car"]
```

完整构造、逐跳门控和 ns-3 验证见 `docs/laesim_wsl_ros_ns3.md`。

### 6.2 space_sim_clock.py 与 space_clock_control.py

这两个脚本为天基任务桥和 NetworkSim 提供可控场景时间。默认不开启，不影响原有 ROS、UE、SceneMap 或载具控制。

启动时钟：

```bash
cd "${HOME}/LAESim"
source /opt/ros/noetic/setup.bash
source ros/devel/setup.bash
python3 ros/src/example/space_sim_clock.py \
  --start-time 2026-07-23T00:00:00Z --rate 60
```

控制示例：

```bash
python3 ros/src/example/space_clock_control.py pause
python3 ros/src/example/space_clock_control.py step --seconds 2
python3 ros/src/example/space_clock_control.py set_rate --rate 120
python3 ros/src/example/space_clock_control.py resume
```

天基桥增加 `--clock-source ros` 后，TLE/Orekit 会按 `/clock` 的时刻查询。NetworkSim 还需在 settings 中设置 `NetworkSimulation.UnifiedClock.Enabled=true`。不要给 AirSim ROS wrapper 全局启用 `/use_sim_time`；当前统一的是任务计算和 ns-3，不是 UE 物理线程。

自动验证：

```bash
bash NetworkSim/tests/ros_unified_clock_integration_test.sh
```

### 6.3 space_mission_visualizer_ros.py

该节点订阅多星 state 和 `/space/selection/<target>`，通过 AirSim 世界绘图 API 在 UE 中显示星下点、覆盖圈、当前 UP 链路和 DOWN 标签。推荐用启动脚本自动解析 Windows 主机 IP 与 settings 路径：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_space_visualization.sh
```

默认卫星是 `Satellite,Satellite2,Satellite3`，目标是 `UAV,UAV2,Car,Boat`。可覆盖：

```bash
SATELLITES="Satellite,Satellite2" TARGETS="Car,Boat" \
GLOBAL_TRACK_RADIUS=80 SURFACE_Z=0 \
  bash NetworkSim/scripts/run_space_visualization.sh
```

可视化器会把 ROS odom 的载具局部坐标与 settings 出生点组合成全局 NED，只用于绘制。覆盖圈是全球轨迹压缩图上的近似显示，不代替任务桥的真实几何判断。

当前多星任务桥默认以 2 Hz 计算并发布 ROS 状态；一键演示把 UE 卫星位姿和可视化器刷新都限制为 0.5 Hz。可视化器使用 32 段覆盖圈，并把同类点和线合并为批量 AirSim 绘图 RPC。目标局部坐标来自 `/airsim_node/<target>/odom_local_ned`，再与 settings 出生点组合；不会为每个目标反复查询 `simGetVehiclePose()`。上游状态中断 10 秒或连续 3 次 UE RPC 失败时，可视化器会自动退出，避免无限重试。

首次交付联调建议直接使用：

```bash
bash NetworkSim/scripts/start_space_demo.sh
bash NetworkSim/scripts/space_demo_status.sh
bash NetworkSim/scripts/stop_space_demo.sh
```

`space_demo_status.sh` 会检查 ROS 话题和 UE 消息时间戳是否真的推进，而不只检查话题名是否存在。
可视化器还会发布 `/space/visualization/status`，其中 `frame_count`、`satellite_count`、`up_link_count` 和 `last_error` 可用于判断 UE 绘图 RPC 是否真正执行。

交付前建议先运行不依赖 UE 的固定四阶段验收，再运行实时环境自检：

```bash
bash NetworkSim/tests/ros_space_delivery_acceptance.sh
bash NetworkSim/scripts/check_space_demo_environment.sh \
  --settings /mnt/c/Users/<Windows用户名>/Documents/AirSim/settings.json \
  --require-ros --require-ns3 --live
```

第一条命令使用独立 ROS master，不会打断当前 UE；第二条命令为只读检查。完整清单见 `docs/space_delivery_checklist.md`。

## 7. vehicle_state_monitor_ros.py

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

## 11. 可选 ns-3 网络桥接

`NetworkSim` 是从 LAESim-1.4 合入的可选通信网络仿真模块。它不替代 `airsim_node`，而是在 ROS 应用消息层增加一层网络仿真：

```text
ROS 应用节点 -> /network_sim/tx -> NetworkSim bridge -> /network_sim/rx/<目标载具>
```

默认可先使用理想通信后端：

```bash
export LAESIM_HOME=$HOME/LAESim
export BACKEND=none
bash "${LAESIM_HOME}/NetworkSim/scripts/run_ros_network_bridge.sh"
```

安装并构建 ns-3.48 后，可以切换到真实离散事件网络后端：

```bash
export LAESIM_HOME=$HOME/LAESim

# 推荐：一键下载/构建 ns-3.48，编译 runner，并做 smoke 测试
bash "${LAESIM_HOME}/NetworkSim/scripts/build_and_verify_ns3_runner.sh"

# 或者分步执行：
bash "${LAESIM_HOME}/NetworkSim/scripts/bootstrap_ns3.sh"
bash "${LAESIM_HOME}/NetworkSim/scripts/build_ns3_runner.sh"

# 默认产物路径，应与 settings.json 的 NetworkSimulation.RunnerPath 一致
ls -l "$HOME/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"

export BACKEND=ns3
bash "${LAESIM_HOME}/NetworkSim/scripts/run_ros_network_bridge.sh"
```

如果 ns-3 安装在自定义目录，先设置 `NS3_ROOT`，再运行上面两个构建脚本；对应的 `RunnerPath` 也要改成同一个目录下的 `build/scratch/ns3.48-laesim-ns3-runner`。

常用话题：

- `/network_sim/tx`：应用层发送入口
- `/network_sim/rx/<载具名>`：指定载具的接收出口

常用验证：

```bash
python3 "${LAESIM_HOME}/NetworkSim/tests/smoke_backend.py" --require-ns3
python3 "${LAESIM_HOME}/NetworkSim/tests/ros_roundtrip_test.py"
```

`ros_roundtrip_test.py` 会向 `/network_sim/tx` 发布一个 JSON 测试包，并监听 `/network_sim/rx/<目标载具>` 是否收到结果，用来验证 ROS bridge 到网络后端再回到 ROS 的完整链路。默认不传参数时，脚本会从当前已有的 `/network_sim/rx/<vehicle>` 话题里自动选择两个真实存在的载具。

如果想手动指定两个载具，可以这样写：

```bash
python3 "${LAESIM_HOME}/NetworkSim/tests/ros_roundtrip_test.py" --source F1 --destination F2
python3 "${LAESIM_HOME}/NetworkSim/tests/ros_roundtrip_test.py" --source Boat --destination Boat2
```

如果在 `NetworkSimulation.SpaceAccessPolicy` 中启用了天基链路门控，先运行 `space_mission_bridge_ros.py` 发布 `/space/<卫星>/access/<目标>`。可见时仍用普通命令；不可见时使用：

```bash
python3 "${LAESIM_HOME}/NetworkSim/tests/ros_roundtrip_test.py" --source Satellite --destination Car --expect-drop
```

该模式监听 `/network_sim/drop`，用于确认包是被天基可见性策略阻断，而不是把它和 ns-3 的距离或路由超时混在一起。完整规则配置见 `docs/laesim_wsl_ros_ns3.md`。

输出中的 `simulation_time_ns` 是 ns-3 runner 的累计仿真时钟，不是终端等待时间；新版 runner 还会输出 `latency_ns`，表示该包在 ns-3 中从发送到送达的仿真时延。

没有构建 ns-3 runner 时，去掉 `--require-ns3` 后 `smoke_backend.py` 会只验证 `none` 后端并打印 `ns3_skipped`；交付前建议保留 `--require-ns3`，确保真实 ns-3 后端能启动。

对应的 `settings.json` 顶层字段是 `NetworkSimulation`，示例文件在 `NetworkSim/config/network-simulation.example.json`。完整 WSL2、ROS Noetic、ns-3 安装和限制说明见 `docs/laesim_wsl_ros_ns3.md`。

## 12. 建议的联调顺序

如果第一次联调，建议按下面顺序走：

1. Windows 端打开 UE 并 `Play`
2. WSL 里运行 `bash src/example/connect_ue_ros.sh`
3. 新开一个终端，`source devel/setup.bash`
4. 运行 `python3 src/example/sensor_config_report_ros.py`
5. 运行 `python3 src/example/vehicle_state_monitor_ros.py`
6. 运行 `python3 src/example/camera_record_ros.py`
7. 运行 `python3 src/example/lidar_record_ros.py`
8. 如果需要通信网络仿真，运行 `NetworkSim/scripts/run_ros_network_bridge.sh`
9. 最后再用 `keyboard_uav_ros.py`、`keyboard_car_ros.py`、`keyboard_boat_ros.py` 和 `keyboard_satellite_ros.py` 做控制联调
