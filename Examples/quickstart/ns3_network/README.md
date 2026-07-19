# 实验二：LAESim 节点与 ns-3 通信范围

## 实验目标

- 了解 `Vehicles` 如何自动映射为同名 ns-3 节点。
- 观察 LAESim 里程计如何持续更新 ns-3 节点位置。
- 使用 `/network_sim/tx` 和 `/network_sim/rx/<载具名>` 传输业务消息。
- 通过修改 `MaxRangeMeters` 复现“全部交付”和“全部丢包”。

本实验使用两个出生点相距约 20 米的节点：`UAV` 与 `Car`。AirSim 的 odometry 以各自出生点为局部原点，网络桥接器会将配置中的 `X/Y/Z` 出生偏移加回局部里程计，再更新 ns-3 节点。

## 1. 前置条件

先完成项目文档中的 [WSL2、ROS 与 ns-3 安装](https://sanis-hitsz.github.io/LAESim/laesim_build/#wsl-ros-ns3)，并确认以下文件存在：

```text
$HOME/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner
$HOME/LAESim/ros/devel/setup.bash
```

## 2. 准备 Windows 配置

在 Windows 仓库根目录执行：

```powershell
$AirSimDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AirSim'
New-Item -ItemType Directory -Force $AirSimDir | Out-Null
$Settings = Join-Path $AirSimDir 'settings.json'
if (Test-Path $Settings) { Copy-Item $Settings "$Settings.backup" -Force }
Copy-Item .\Examples\quickstart\ns3_network\settings.json $Settings -Force
```

配置中的关键关系是：

```json
"Vehicles": {
  "UAV": { "X": 0.0 },
  "Car": { "X": 20.0 }
},
"NetworkSimulation": {
  "Backend": "ns3",
  "MaxRangeMeters": 100.0
}
```

`Vehicles` 中的键就是网络节点名称。桥接器启动时创建两个 ns-3 节点，后续消息中的 `src` 和 `dst` 必须使用这些名称。

## 3. 启动 LAESim、ROS 和桥接器

Windows 中打开 UE 4.27 环境并点击 **Play**。然后在 WSL2 的三个终端中分别执行：

终端 A：

```bash
source /opt/ros/noetic/setup.bash
roscore
```

终端 B：

```bash
export WINDOWS_HOST="$(ip route show default | awk '{print $3}')"
source /opt/ros/noetic/setup.bash
source "${HOME}/LAESim/ros/devel/setup.bash"
roslaunch airsim_ros_pkgs airsim_node.launch host:="${WINDOWS_HOST}"
```

终端 C：

```bash
export LAESIM_HOME="${HOME}/LAESim"
export ROS_WORKSPACE="${LAESIM_HOME}/ros"
unset BACKEND
bash "${LAESIM_HOME}/NetworkSim/scripts/run_ros_network_bridge.sh"
```

必须 `unset BACKEND`，否则旧的环境变量可能覆盖 `settings.json` 中的 `Backend: ns3`。

## 4. 验证范围内交付

新开 WSL2 终端：

```bash
source /opt/ros/noetic/setup.bash
source "${HOME}/LAESim/ros/devel/setup.bash"
python3 "${HOME}/LAESim/Examples/quickstart/ns3_network/run_experiment.py" \
  --expect delivered
```

脚本会等待 `UAV`、`Car` 的 odometry 和网络桥接器，发送 5 个 1024 字节消息，并要求全部从 `/network_sim/rx/Car` 收到。成功结果应包含：

```text
"sent": 5
"delivered": 5
"dropped": 0
expectation 'delivered' passed
```

`simulation_time_ns` 应全部大于 0；如果为 0，说明实际使用的是 `Backend: none`。

## 5. 修改配置并验证丢包

将 Windows `settings.json` 中的：

```json
"MaxRangeMeters": 100.0
```

改为：

```json
"MaxRangeMeters": 5.0
```

配置只在桥接器启动时读取，因此需要停止并重新运行终端 C，然后执行：

```bash
python3 "${HOME}/LAESim/Examples/quickstart/ns3_network/run_experiment.py" \
  --expect dropped
```

`UAV` 和 `Car` 的出生点相距约 20 米，超过 5 米硬通信范围，因此预期 `delivered: 0`、`dropped: 5`，并输出 `expectation 'dropped' passed`。

## 排查

- 一直等待 odometry：确认 UE 已 Play，且 `airsim_node` 能看到 `/airsim_node/UAV/odom_local_ned` 和 `/airsim_node/Car/odom_local_ned`。
- `/network_sim/tx` 没有订阅者：网络桥接器未启动或启动失败。
- 预期丢包却收到消息：确认修改的是 Windows 活动配置，并在修改后重启了桥接器。
- runner 找不到：检查 `RunnerPath`，或重新运行 `NetworkSim/scripts/build_ns3_runner.sh`。
