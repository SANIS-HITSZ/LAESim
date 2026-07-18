# LAESim 的 WSL2、ROS Noetic 与 ns-3 集成

本文说明如何在 Windows 上保留 UE4/AirSim 图形与物理仿真，同时把 ROS 和可选的 ns-3 网络仿真放到 WSL2。文中的主机路径、版本和测试结果均来自一次完整实测。

## 1. 最终结构

```text
Windows 11
  UE 4.27 + LAESim/AirSim
  C:\Users\<用户>\Documents\AirSim\settings.json
                | AirSim RPC (WSL2 网关地址)
                v
H:\WSL\LAESim\ext4.vhdx
  Ubuntu 20.04 + ROS Noetic
  airsim_node
  laesim_network_bridge
       | Backend=none  -> 理想网络，消息立即到达
       ` Backend=ns3   -> ns-3.48 Wi-Fi ad hoc + OLSR/AODV
```

WSL 的 Linux 文件系统保存在 `H:\WSL\LAESim\ext4.vhdx`，不会使用 C 盘的默认 WSL 发行版目录。本次实测 VHDX 约为 8 GB，后续编译缓存会继续增长。

## 2. 已验证版本

| 组件 | 版本或位置 |
| --- | --- |
| Windows 仿真端 | UE 4.27，LAESim AirGround 六机配置 |
| WSL | WSL2，发行版名 `LAESim` |
| Linux | Ubuntu 20.04 (focal) |
| ROS | ROS Noetic |
| AirSim ROS 工作空间 | `/home/pyq/LAESim/ros` |
| ns-3 | `ns-3.48`，提交 `d2add90b452d600cfb4859baed8e9ea633519447` |
| ns-3 编译器 | GCC/G++ 11 |
| AirSim ROS 编译器 | GCC/G++ 8 |

ROS Noetic 与 Ubuntu 20.04 都已离开标准支持周期。这一组合是为了兼容当前 AirSim ROS1 工程；新项目长期应评估 Ubuntu 22.04/24.04 与 ROS 2，但不要在本工程尚未迁移时直接替换。

## 3. 在 H 盘创建 LAESim WSL2

### 3.1 准备 Ubuntu 20.04 rootfs

本次使用的是一个干净 Ubuntu 20.04 WSL 发行版的导出文件：

```powershell
wsl --export Formation-tracking H:\WSL\Formation-tracking\Ubuntu-20.04.tar
Get-FileHash H:\WSL\Formation-tracking\Ubuntu-20.04.tar -Algorithm SHA256
```

本次归档的 SHA256 为：

```text
FB9EC23B9AC9D1FB1B09CA8FBC9924E288BAADE1E206887C9AB6DA42AE520CBC
```

该哈希只用于识别本次实测归档，不是 Ubuntu 官方发布哈希。其他开发者可以从自己的干净 Ubuntu 20.04 WSL 导出，或者从微软的 Ubuntu 20.04 WSL 安装包中提取 `install.tar.gz`。rootfs 文件自身也应保存在 H 盘。

### 3.2 导入并设置默认用户

在仓库根目录用管理员 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\NetworkSim\scripts\create_laesim_wsl.ps1 `
  -RootfsPath H:\WSL\Formation-tracking\Ubuntu-20.04.tar `
  -InstallRoot H:\WSL\LAESim `
  -DistroName LAESim `
  -DefaultUser pyq
```

脚本会执行 `wsl --import ... --version 2`，创建用户（若不存在），并写入：

```ini
[boot]
systemd=true

[user]
default=pyq

[interop]
appendWindowsPath=false
```

验证发行版和磁盘位置：

```powershell
wsl -l -v
Get-Item H:\WSL\LAESim\ext4.vhdx
wsl -d LAESim -- id
```

`wsl -l -v` 应显示 `LAESim` 的 VERSION 为 `2`，`id` 应显示用户 `pyq`。

## 4. 安装 ROS Noetic 和编译 LAESim ROS

### 4.1 安装依赖

本机访问 ROS 官方软件源曾超时，因此脚本默认使用中科大 ROS 镜像，并采用 FishROS 提供的密钥镜像和 `rosdepc` 作为网络故障回退。也可以先运行用户提供的 FishROS 安装器，但为了可重复性，建议项目安装使用已固定步骤的脚本。

```powershell
wsl -d LAESim -u root -- env TARGET_USER=pyq `
  bash /mnt/h/LAESim/NetworkSim/scripts/bootstrap_wsl_ros.sh
```

如需换软件源：

```powershell
wsl -d LAESim -u root -- env TARGET_USER=pyq `
  ROS_APT_MIRROR=https://packages.ros.org/ros/ubuntu `
  bash /mnt/h/LAESim/NetworkSim/scripts/bootstrap_wsl_ros.sh
```

### 4.2 克隆与编译

源码建议放在 WSL 的 ext4 内，而不是 `/mnt/h`，以减少大量小文件编译时的跨文件系统开销：

```bash
wsl -d LAESim
git clone https://github.com/SANIS-HITSZ/LAESim.git ~/LAESim
cd ~/LAESim
./setup.sh
cd ros
source /opt/ros/noetic/setup.bash
catkin_make \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-8 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-8
source devel/setup.bash
```

若 `setup.sh` 因网络问题未获得依赖，先确认以下目录存在，再重新编译：

```text
~/LAESim/AirLib/deps/eigen3
~/LAESim/external/rpclib
```

## 5. 验证 Windows UE 与 WSL ROS 联动

### 5.1 Windows 端

1. 确认 `C:\Users\<用户>\Documents\AirSim\settings.json` 是需要测试的多机配置。
2. 用 UE 4.27 打开 LAESim 环境。
3. 点击 Play，等待场景和 AirSim RPC 服务完成启动。

本次六机配置使用了 `41451`、`41461`、`41471`、`41481` 等 RPC 端口。可以在 Windows PowerShell 检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 41451
```

### 5.2 WSL 端

WSL2 NAT 模式下不能把 Windows AirSim 当作 WSL 内的 `localhost`。从默认路由获取 Windows 主机地址：

```bash
export ROS_WS=~/LAESim/ros
source /opt/ros/noetic/setup.bash
source "$ROS_WS/devel/setup.bash"
export WINDOWS_HOST="$(ip route show default | awk '{print $3}')"

roscore
```

另开一个 WSL 终端：

```bash
source /opt/ros/noetic/setup.bash
source ~/LAESim/ros/devel/setup.bash
export WINDOWS_HOST="$(ip route show default | awk '{print $3}')"
roslaunch airsim_ros_pkgs airsim_node.launch host:="$WINDOWS_HOST"
```

验证主题：

```bash
rostopic list | grep /airsim_node
rostopic hz /airsim_node/Car/odom_local_ned
```

本次实测成功收到 `UAV`、`UAV2`、`UAV3`、`Car`、`Car2`、`Car3` 六个载具的位姿、GPS 和传感器主题，Car 状态约为 17 Hz。车载 TF 可能出现 `TF_REPEATED_DATA` 警告，这是重复时间戳告警，不代表 RPC 连接失败。

## 6. 安装与构建 ns-3

安装脚本固定 ns-3.48 的 tag 对象和提交，避免以后同名远端内容变化：

```bash
wsl -d LAESim
bash /mnt/h/LAESim/NetworkSim/scripts/bootstrap_ns3.sh
bash /mnt/h/LAESim/NetworkSim/scripts/build_ns3_runner.sh
```

脚本会把 ns-3 放在 `~/opt/ns-3.48`，构建 examples/tests，运行 `hello-simulator` 和 `core-example-simulator`，然后编译 LAESim runner：

```text
~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner
```

独立后端冒烟测试：

```bash
source /opt/ros/noetic/setup.bash
python3 /mnt/h/LAESim/NetworkSim/tests/smoke_backend.py
```

本次实测 1024 字节包的输出为：发送 1、到达 1、丢包率 0、平均时延 10 ms。

## 7. 可配置网络后端

在 AirSim `settings.json` 顶层加入：

```json
"NetworkSimulation": {
  "Backend": "none",
  "StepMs": 20,
  "Routing": "olsr",
  "MaxRangeMeters": 250.0,
  "TxPowerDbm": 16.0,
  "WarmupSeconds": 3.0,
  "PacketTimeoutSeconds": 5.0,
  "RunnerPath": "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"
}
```

`Backend` 的含义：

| 值 | 行为 |
| --- | --- |
| `none` | 保持原有理想通信，ROS 消息立即转发，不计算时延、丢包和路由 |
| `ns3` | 经过 ns-3 Wi-Fi ad hoc 网络；位置来自 AirSim odometry |

当前 runner 支持 `olsr` 和 `aodv` 路由。`MaxRangeMeters` 是当前 MVP 的硬通信范围，便于稳定复现实验；后续可以替换为 Friis、LogDistance、Nakagami 等传播/衰落模型。
`PacketTimeoutSeconds` 到期后，未送达包会被记为 `DROP` 并释放桥接器状态。

启动桥接器：

```bash
export SETTINGS=/mnt/c/Users/<Windows用户>/Documents/AirSim/settings.json
export ROS_WORKSPACE=~/LAESim/ros
export BACKEND=none    # 或 ns3；该环境变量会覆盖 settings.json
bash /mnt/h/LAESim/NetworkSim/scripts/run_ros_network_bridge.sh
```

不设置 `BACKEND` 时使用 `settings.json` 中的配置。

## 8. ROS 消息接口

发送端向 `/network_sim/tx` 发布 `std_msgs/String`，内容是 JSON：

```json
{
  "packet_id": "frame-0001",
  "src": "UAV",
  "dst": "Car",
  "size_bytes": 1024,
  "payload": "application-data"
}
```

接收端订阅 `/network_sim/rx/<载具名>`。输出会增加 ns-3 的 `simulation_time_ns`：

```json
{
  "packet_id": "frame-0001",
  "src": "UAV",
  "dst": "Car",
  "size_bytes": 1024,
  "simulation_time_ns": 19787694150,
  "payload": "application-data"
}
```

端到端测试：

```bash
source /opt/ros/noetic/setup.bash
source ~/LAESim/ros/devel/setup.bash
python3 /mnt/h/LAESim/NetworkSim/tests/ros_roundtrip_test.py
```

本次测试中，`none` 和 `ns3` 两种后端都完成了 `UAV -> Car` 的 ROS 往返；`none` 的仿真时间为 0，`ns3` 的输出带非零 ns-3 仿真时间。

## 9. 图像与“真实网络栈”的边界

ns-3 可以模拟承载图像的字节流，但不会替代 UE 生成画面，也不会自动把 `sensor_msgs/Image` 变成真实操作系统 socket 流量。当前集成采用“消息级网络仿真”：

- UE/AirSim 仍生成真实仿真画面。
- 应用把图像压缩、分片后，以每个分片的真实字节数提交给 `/network_sim/tx`。
- ns-3 决定分片何时到达或是否丢失。
- 接收应用按 `packet_id`/分片序号重组，再解码图像。

当前单个 ns-3 包的上限为 60000 字节，大图像必须分片。此方式适合研究自组网对感知/协同算法的影响，也能取得时延、吞吐量、丢包率和路由变化指标。

如果必须让未经修改的 ROS/TCP/UDP 程序直接经过网络仿真，则需要 TAP/EMU 或 DCE 一类“真实网络栈/网络仿真接入”。该路线需要额外 Linux 网络接口、权限和时钟同步；WSL2 下部署复杂度明显更高，不属于当前 MVP。

## 10. 当前限制与下一步

- runner 当前使用 IEEE 802.11g ad hoc、固定发送功率、RangePropagationLoss 和 OLSR/AODV。
- AirSim 的 ROS 时钟与 ns-3 离散事件时钟目前是软同步：每个 ROS timer 推进固定 `StepMs`。
- `METRICS` 已提供发送数、到达数、丢包率、吞吐量和平均时延，但尚未发布为 ROS 指标主题或落盘 CSV。
- 路由变化尚未导出到 ROS；可通过 ns-3 routing table trace 增加。
- 视频应增加编码、分片、重传策略和接收端缓冲，不能把一帧直接当成一个 UDP 包。
- 当前 WSL 仍会使用少量 Windows 自身的 WSL 组件空间，但发行版的主要 Linux 磁盘和编译产物位于 H 盘。

建议下一阶段先固定一个实验场景和指标格式，再增加传播模型、网络指标 ROS topic/CSV、图像分片器，以及仿真时钟同步策略。

## 11. 官方参考

- [Microsoft：导入任意 Linux 发行版供 WSL 使用](https://learn.microsoft.com/windows/wsl/use-custom-distro)
- [ns-3 官方文档入口](https://www.nsnam.org/documentation/)
- [ROS Noetic 在 Ubuntu 上的安装说明](https://wiki.ros.org/noetic/Installation/Ubuntu)
- [Ubuntu 官方云镜像](https://cloud-images.ubuntu.com/)
