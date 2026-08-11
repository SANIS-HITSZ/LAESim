# LAESim 的 WSL2、ROS Noetic 与 ns-3 集成

本文说明如何在 Windows 中运行 LAESim/UE4，同时在 WSL2 中运行 ROS Noetic 和可选的 ns-3 网络仿真。所有路径均使用环境变量或通用占位符，不依赖某台电脑的用户名、盘符或目录结构。

## 1. 系统结构

```text
Windows 11
  UE 4.27 + LAESim
  %USERPROFILE%\Documents\AirSim\settings.json
                 | AirSim RPC
                 v
WSL2 自定义发行版
  Ubuntu 20.04 + ROS Noetic
  $HOME/LAESim/ros
  $HOME/opt/ns-3.48
  laesim_network_bridge
       | Backend=none -> 理想网络，消息立即到达
       ` Backend=ns3  -> ns-3 Wi-Fi ad hoc + OLSR/AODV
```

WSL2 发行版可以安装到任意空间充足的非系统盘。Windows 项目目录、WSL 虚拟磁盘目录和 Linux 主目录彼此独立，不要求使用相同盘符。

## 2. 已验证的软件版本

| 组件 | 版本 |
| --- | --- |
| Windows | Windows 11 + WSL2 |
| Unreal Engine | UE 4.27 |
| Linux | Ubuntu 20.04 (focal) |
| ROS | ROS Noetic |
| ns-3 | ns-3.48，提交 `d2add90b452d600cfb4859baed8e9ea633519447` |
| ns-3 编译器 | GCC/G++ 11 或更高版本；Ubuntu 20.04 默认 GCC 9 不满足 ns-3.48 要求 |
| LAESim ROS 编译器 | GCC/G++ 8 |

ROS Noetic 与 Ubuntu 20.04 已离开标准支持周期。当前组合用于兼容 LAESim 的 ROS1 工程；在项目完成 ROS 2 迁移前，不要直接用其他 Ubuntu 或 ROS 版本替换。

## 3. 创建 LAESim WSL2 发行版

### 3.1 定义本机参数

在 LAESim 仓库根目录打开管理员 PowerShell。先定义本机使用的参数：

```powershell
$DistroName = "LAESim"
$LinuxUser = "laesim"
$WslInstallRoot = Read-Host "请输入 WSL2 发行版存储目录，例如 D:\WSL\LAESim"
$RootfsPath = Read-Host "请输入 Ubuntu 20.04 rootfs tar 文件路径"
$RepoRoot = (Resolve-Path .).Path
```

- `$WslInstallRoot` 决定 `ext4.vhdx` 的存放位置，应选择空间充足的磁盘。
- `$RootfsPath` 指向 Ubuntu 20.04 的 WSL rootfs 归档。
- `$LinuxUser` 可以改为符合 Linux 用户名规则的其他名称。

如果电脑中已有干净的 Ubuntu 20.04 WSL 发行版，可以导出为 rootfs：

```powershell
$SourceDistro = Read-Host "请输入现有 Ubuntu 20.04 发行版名称"
wsl --export $SourceDistro $RootfsPath
```

也可以使用可信来源提供的 Ubuntu 20.04 WSL rootfs。使用下载文件时，应按发布方说明校验哈希，不要复用其他电脑生成的私有归档哈希。

### 3.2 导入发行版

```powershell
powershell -ExecutionPolicy Bypass -File .\NetworkSim\scripts\create_laesim_wsl.ps1 `
  -RootfsPath $RootfsPath `
  -InstallRoot $WslInstallRoot `
  -DistroName $DistroName `
  -DefaultUser $LinuxUser
```

脚本使用 `wsl --import --version 2` 导入发行版、创建默认用户，并启用 systemd。验证结果：

```powershell
wsl -l -v
Get-Item (Join-Path $WslInstallRoot "ext4.vhdx")
wsl -d $DistroName -- id
```

`wsl -l -v` 中该发行版的 VERSION 应为 `2`，`id` 应显示 `$LinuxUser` 对应的非 root 用户。

## 4. 安装 ROS Noetic

安装脚本位于 Windows 仓库中。先把 Windows 路径转换为当前 WSL 可识别的路径：

```powershell
$RepoRootWsl = (wsl -d $DistroName -- wslpath -a $RepoRoot).Trim()
```

然后安装 ROS 和编译依赖：

```powershell
wsl -d $DistroName -u root -- env TARGET_USER=$LinuxUser `
  bash "$RepoRootWsl/NetworkSim/scripts/bootstrap_wsl_ros.sh"
```

脚本默认使用中科大 ROS 镜像。需要使用 ROS 官方软件源时执行：

```powershell
wsl -d $DistroName -u root -- env TARGET_USER=$LinuxUser `
  ROS_APT_MIRROR=https://packages.ros.org/ros/ubuntu `
  bash "$RepoRootWsl/NetworkSim/scripts/bootstrap_wsl_ros.sh"
```

`TARGET_USER` 必须是将来运行 LAESim 和 ROS 的非 root Linux 用户。

## 5. 在 WSL 中编译 LAESim ROS

建议将用于 Linux 编译的源码克隆到 WSL 的 ext4 文件系统中。不要直接在 `/mnt/c`、`/mnt/d` 等 Windows 挂载目录中编译大量 Linux 小文件。

```bash
wsl -d LAESim

export LAESIM_HOME="${HOME}/LAESim"
git clone https://github.com/SANIS-HITSZ/LAESim.git "${LAESIM_HOME}"
cd "${LAESIM_HOME}"
./setup.sh

cd ros
source /opt/ros/noetic/setup.bash
catkin_make \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-8 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-8
source devel/setup.bash
```

如果发行版名称不是 `LAESim`，把第一条命令中的名称替换为创建时设置的 `$DistroName`。如果目录已经克隆，使用 `git pull --ff-only` 更新，不要再次执行 `git clone`。

编译前应确认以下依赖目录存在：

```text
$HOME/LAESim/AirLib/deps/eigen3
$HOME/LAESim/external/rpclib
```

## 6. 验证 Windows LAESim 与 WSL ROS

### 6.1 启动 Windows 仿真端

1. 将多机配置保存为 `%USERPROFILE%\Documents\AirSim\settings.json`。
2. 使用 UE 4.27 打开 LAESim 环境。
3. 点击 Play，等待场景和 AirSim RPC 服务启动。
4. 根据 `settings.json` 中配置的 RPC 端口检查监听状态。

例如，默认 RPC 端口可通过 PowerShell 检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 41451
```

### 6.2 启动 WSL ROS

WSL2 使用 NAT 网络时，Windows 仿真端通常不能通过 WSL 内的 `localhost` 访问。应从 WSL 默认路由动态获取 Windows 主机地址，不要把某次运行得到的 IP 写死：

```bash
export LAESIM_HOME="${HOME}/LAESim"
export ROS_WORKSPACE="${LAESIM_HOME}/ros"
export WINDOWS_HOST="$(ip route show default | awk '{print $3}')"

source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
roscore
```

另开一个 WSL 终端：

```bash
export ROS_WORKSPACE="${HOME}/LAESim/ros"
export WINDOWS_HOST="$(ip route show default | awk '{print $3}')"

source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
roslaunch airsim_ros_pkgs airsim_node.launch host:="${WINDOWS_HOST}"
```

验证 ROS 主题：

```bash
rostopic list | grep /airsim_node
rostopic hz /airsim_node/Car/odom_local_ned
```

主题名称取决于 `settings.json` 中的载具名称。能够持续收到配置中各载具的位姿、GPS 或传感器主题，即说明 Windows 与 WSL ROS 已连通。`TF_REPEATED_DATA` 表示重复时间戳，不等同于 RPC 连接失败。

## 7. 安装与构建 ns-3

`ns3.48-laesim-ns3-runner` 是 LAESim 调用 ns-3 的外部仿真进程。它必须在 WSL/Linux 环境中构建和运行，不是在 Windows 的 AirSim Python/conda 环境里构建。Windows UE 只负责仿真画面和载具状态；WSL 里的 ROS 网络桥接器会启动这个 runner，把节点位置和应用层数据包交给 ns-3。

推荐先运行一键构建与验证脚本：

```bash
export LAESIM_HOME="${HOME}/LAESim"
bash "${LAESIM_HOME}/NetworkSim/scripts/build_and_verify_ns3_runner.sh"
```

这个脚本会检查 `git`、`python3` 和 C/C++ 编译器。ns-3.48 要求 GNU 编译器版本不低于 11，因此 Ubuntu 20.04 默认的 GCC 9.4.0 不能直接使用；脚本会优先选择 `gcc-11/g++-11`，找不到时先尝试 apt 安装，必要时自动加入 `ppa:ubuntu-toolchain-r/test` 后再安装。随后脚本下载/构建 ns-3.48，编译 runner，并执行 `smoke_backend.py --require-ns3`。

如果需要分步排查，构建过程可以拆成两步：

1. `bootstrap_ns3.sh`：下载并构建指定版本的 ns-3.48。
2. `build_ns3_runner.sh`：把 `NetworkSim/ns3/laesim-ns3-runner.cc` 复制到 ns-3 的 `scratch/` 目录，并编译出 runner 可执行文件。

在 WSL 内手动执行：

```bash
export LAESIM_HOME="${HOME}/LAESim"
bash "${LAESIM_HOME}/NetworkSim/scripts/bootstrap_ns3.sh"
bash "${LAESIM_HOME}/NetworkSim/scripts/build_ns3_runner.sh"
```

默认目录如下，均相对于当前 Linux 用户的主目录：

```text
$HOME/opt/ns-3.48
$HOME/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner
```

如果最后看到类似下面输出，说明 runner 已经构建成功：

```text
LAESim ns-3 runner is ready at /home/<user>/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner.
```

需要改用其他目录时，在运行两个脚本前设置同一个 `NS3_ROOT`：

```bash
export NS3_ROOT="${HOME}/simulators/ns-3.48"
```

此时对应的 runner 路径会变成：

```text
$HOME/simulators/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner
```

后续 `settings.json` 里的 `NetworkSimulation.RunnerPath` 也要改成同一个路径，否则桥接器会找不到 runner。

运行后端冒烟测试：

```bash
source /opt/ros/noetic/setup.bash
python3 "${HOME}/LAESim/NetworkSim/tests/smoke_backend.py" --require-ns3
```

如果当前机器还没有构建 ns-3 runner，去掉 `--require-ns3` 后脚本会只验证 `none` 直连后端并打印 `ns3_skipped`。完成 ns-3 构建后，建议保留 `--require-ns3`，这样 runner 缺失会直接报错，便于交付前检查。新版测试覆盖正常送达、物理拓扑超距 `range`、路由未建立 `routing` 和 PHY 未送达 `timeout`；这些后端测试使用逻辑节点，不需要启动 UE。

## 8. 配置可选网络后端

在 Windows 的 `%USERPROFILE%\Documents\AirSim\settings.json` 顶层加入：

```json
"NetworkSimulation": {
  "Backend": "none",
  "StepMs": 20,
  "Routing": "olsr",
  "MaxRangeMeters": 250.0,
  "TxPowerDbm": 16.0,
  "WarmupSeconds": 3.0,
  "PacketTimeoutSeconds": 5.0,
  "RunnerPath": "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner",
  "SatelliteLinkModel": {
    "Enabled": false,
    "FrequencyHz": 2200000000.0,
    "BandwidthHz": 5000000.0,
    "DataRateBps": 2000000.0,
    "TxPowerDbm": 40.0,
    "TxAntennaGainDbi": 10.0,
    "RxAntennaGainDbi": 20.0,
    "SystemLossDb": 2.0,
    "NoiseFigureDb": 3.0,
    "MinSnrDb": 3.0,
    "PacketErrorModel": "bpsk"
  },
  "SpaceAccessPolicy": {
    "Enabled": false,
    "FailMode": "closed",
    "MaxStateAgeSeconds": 2.0,
    "Rules": [
      {
        "Source": "Satellite",
        "Destination": "Car",
        "AccessTopic": "/space/Satellite/access/Car",
        "Bidirectional": true
      }
    ]
  }
}
```

| `Backend` | 行为 |
| --- | --- |
| `none` | 保持理想通信，ROS 消息立即转发，不计算网络时延、丢包和路由 |
| `ns3` | 消息经过 ns-3 Wi-Fi ad hoc 网络，节点位置来自 LAESim odometry |

当前 runner 支持 `olsr` 和 `aodv`。`MaxRangeMeters` 是传播模型的硬截止上限，不代表范围内一定能够解调；IEEE 802.11g 接收门限、`TxPowerDbm` 和 Yans 默认路径损耗仍会让有效通信距离短于该上限。`PacketTimeoutSeconds` 到期后未送达的包会被记录为 `DROP`。

`SatelliteLinkModel` 默认关闭。启用后，命中 `SpaceAccessPolicy` 规则的星地包使用 access 消息中的真实 `range_m` 和独立链路预算，不再使用 UE `odom_local_ned` 距离或 802.11g；未命中规则的普通空地海链路保持原行为。该模型依赖有效的 `SpaceAccessPolicy` 状态，因此启用时必须同时设置 `SpaceAccessPolicy.Enabled=true`。

`SpaceAccessPolicy` 是可选的天基链路门控。默认 `Enabled=false`，不会改变已有 ns-3 行为。启用后，只有 `Rules` 匹配的源/目标链路会检查 `SpaceAccessState`，其他地面、海上或空中链路仍按原网络后端处理。规则中的载具名必须存在于 `Vehicles`。

第一次同步包含天基消息定义的新版本后，需要在 WSL 的源码副本中重新生成 ROS 消息：

```bash
cd "${HOME}/LAESim/ros"
source /opt/ros/noetic/setup.bash
catkin_make --force-cmake
source devel/setup.bash
rosmsg show airsim_ros_pkgs/SpaceAccessState
```

最后一条能显示 `valid`、`access`、`elevation_deg` 和 `range_m` 等字段后，才能启用 `SpaceAccessPolicy`。策略关闭时，NetworkSim 不强制依赖该消息，原有网络桥接仍可运行。

## 8.1 当前 ns-3 功能完整性

当前合入的 ns-3 功能已经覆盖“ROS 消息级通信网络仿真”的完整闭环：

- 从 `settings.json` 读取所有 LAESim 载具名称和 `NetworkSimulation` 配置。
- 订阅 `/airsim_node/<载具名>/odom_local_ned`，把各载具当前位置同步为 ns-3 节点位置。
- 通过 `/network_sim/tx` 接收应用层 JSON 数据包。
- 支持 `Backend=none` 的理想直连模式，便于和原始算法行为对照。
- 支持 `Backend=ns3`，由外部 `ns3.48-laesim-ns3-runner` 模拟 Wi-Fi ad hoc 网络。
- runner 当前支持 IEEE 802.11g、固定发送功率、`RangePropagationLossModel`、OLSR/AODV 路由、包超时丢弃。
- 输出 `/network_sim/rx/<载具名>`，并在消息中附带 `simulation_time_ns` 和 `latency_ns`。
- 可订阅 `/space/<卫星>/access/<目标>`，在进入 none/ns3 后端前按实时星地可见性放行或阻断指定链路。
- 可选 `SatelliteLinkModel` 把真实星地斜距转换为自由空间路径损耗、传播时延、SNR 和 BPSK 包错误率，并通过 runner 的独立逻辑链路调度，不受 UE 卫星显示坐标影响。
- 天基策略阻断和 ns-3 内部丢包统一发布到 `/network_sim/drop`，通过 `drop_stage` 区分；ns-3 内部可进一步区分 `range/routing/timeout/socket`。
- 提供 `METRICS` 统计入口，可观察发送数、送达数、丢包率、吞吐量和平均时延。
- 提供 `smoke_backend.py` 和 `ros_roundtrip_test.py` 做后端和 ROS 端到端验证。

当前没有做成透明网络栈仿真。也就是说，未经修改的 ROS topic、TCP 或 UDP 程序不会自动经过 ns-3；需要应用主动把希望仿真的数据包发布到 `/network_sim/tx`。如果要让真实 socket 流量透明进入 ns-3，需要后续接入 TAP/EMU/DCE，这不属于当前版本。

## 8.2 星地逻辑链路模型

启用 `SatelliteLinkModel` 后，ROS bridge 只对 `SpaceAccessPolicy` 命中的数据包生成 `LOGICAL_SEND`，普通载具仍使用原 `SEND`。当前计算关系为：

```text
FSPL(dB) = 20 log10(4 pi R f / c)
Pr(dBm) = Pt + Gt + Gr - SystemLoss - FSPL
Noise(dBm) = -174 + 10 log10(BandwidthHz) + NoiseFigure
SNR(dB) = Pr - Noise
PropagationDelay = R / c
SerializationDelay = PacketBits / DataRateBps
```

`PacketErrorModel=bpsk` 时，根据 `Eb/N0` 计算 BPSK BER，再按包长度换算包错误率；低于 `MinSnrDb` 的包直接以 `drop_reason=link_budget` 丢弃。设置为 `none` 时关闭随机误码，但仍保留链路预算、传播时延和带宽排队。

runner 为每个有向逻辑链路维护独立的可用时间，因此连续数据包会按 `DataRateBps` 排队。输出的成功包会增加：

```text
link_type=satellite
true_range_m
propagation_delay_ns
serialization_delay_ns
data_rate_bps
packet_error_rate
fspl_db
rx_power_dbm
snr_db
frequency_hz
bandwidth_hz
```

这些字段描述真实任务几何和逻辑射频链路。`node_distance_m` 只用于普通 Wi-Fi 丢包诊断，不参与星地逻辑链路计算。

## 9. 启动网络桥接器

默认情况下，启动脚本会根据 Windows 的 `%USERPROFILE%` 自动定位 `Documents\AirSim\settings.json`：

```bash
export LAESIM_HOME="${HOME}/LAESim"
export ROS_WORKSPACE="${LAESIM_HOME}/ros"
export BACKEND=none  # 可改为 ns3；该变量会覆盖 settings.json
bash "${LAESIM_HOME}/NetworkSim/scripts/run_ros_network_bridge.sh"
```

不设置 `BACKEND` 时使用 `settings.json` 中的配置。如果配置文件放在自定义位置，先把 Windows 路径转换为 WSL 路径并显式设置 `SETTINGS`：

```bash
export SETTINGS="$(wslpath -u 'D:\path\to\settings.json')"
```

上面的 `D:\path\to\settings.json` 只是格式示例，应替换为实际文件路径。

## 10. ROS 消息接口与端到端测试

发送端向 `/network_sim/tx` 发布 `std_msgs/String`，内容为 JSON：

```json
{
  "packet_id": "frame-0001",
  "src": "UAV",
  "dst": "Car",
  "size_bytes": 1024,
  "payload": "application-data"
}
```

接收端订阅 `/network_sim/rx/<载具名>`。输出会增加 ns-3 的 `simulation_time_ns` 和 `latency_ns`：

```json
{
  "packet_id": "frame-0001",
  "src": "UAV",
  "dst": "Car",
  "size_bytes": 1024,
  "simulation_time_ns": 19787694150,
  "latency_ns": 10000000,
  "payload": "application-data"
}
```

其中 `simulation_time_ns` 是 ns-3 runner 当前累计仿真时钟，表示这个包在 ns-3 时间轴上的送达时刻；它不是从命令行发包到终端打印结果的墙钟耗时，也不是单包网络时延。单包网络时延看 `latency_ns`。如果使用旧版 runner，`latency_ns` 可能为 0，此时应重新运行 `NetworkSim/scripts/build_ns3_runner.sh` 编译新版 runner。

端到端测试：

```bash
source /opt/ros/noetic/setup.bash
source "${HOME}/LAESim/ros/devel/setup.bash"
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py"
```

`ros_roundtrip_test.py` 用来验证 ROS 端到端链路是否打通：测试节点向 `/network_sim/tx` 发布一个 JSON 数据包，再订阅 `/network_sim/rx/<目标载具>` 等待投递结果。如果命令不指定源和目标，脚本会自动从当前 ROS master 中已有的 `/network_sim/rx/<vehicle>` 话题里选择两个真实存在的载具，避免默认载具名和当前 `settings.json` 不一致。

也可以手动指定任意两个已配置载具：

```bash
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source F1 --destination F2
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source Boat --destination Boat2
```

源和目标必须出现在当前 `settings.json` 的 `Vehicles` 中，并且 bridge 已经发布对应的 `/network_sim/rx/<载具名>` 话题。应分别用 `none` 和 `ns3` 后端测试。`none` 模式的网络仿真时间为 0；`ns3` 模式应返回非零仿真时间，链路不可达时应输出丢包结果。

启用 `SpaceAccessPolicy` 后，先运行 `space_mission_bridge_ros.py` 发布规则配置的 access 话题。可见时使用普通命令验证投递：

```bash
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source Satellite --destination Car
```

不可见、状态缺失或状态过期时，使用 `--expect-drop` 验证门控：

```bash
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source Satellite --destination Car --expect-drop
```

成功时会打印 `/network_sim/drop` 中的 JSON，其中 `drop_stage=space_access_policy`，`drop_reason` 用于区分低于仰角门限、状态缺失、无效或过期。`FailMode=closed` 适合正式仿真；若只想在 access 发布器暂时中断时继续调试网络，可设置 `FailMode=open`。

### 10.1 ns-3 内部丢包诊断

runner 发现数据包无法送达后，ROS bridge 同样会把结果发布到 `/network_sim/drop`。这类结果满足：

```text
drop_stage=ns3
drop_reason=range | routing | timeout | socket | link_budget | link_error
```

分类含义：

- `range`：按 `MaxRangeMeters` 构造的当前物理拓扑中，源节点到目标节点不存在可达路径。
- `routing`：物理拓扑存在路径，但当前 OLSR/AODV 路由尚未建立。
- `timeout`：物理拓扑和 IP 路由均存在，但数据包在 `PacketTimeoutSeconds` 内没有到达；常见于路径损耗、接收门限或 MAC/PHY 丢包。
- `socket`：拓扑和路由检查正常，但 ns-3 UDP socket 仍然拒绝发送。
- `link_budget`：星地逻辑链路的 SNR 低于 `MinSnrDb`，链路预算不足。
- `link_error`：星地逻辑链路预算允许通信，但本次数据包按误码率模型判定丢失。

示例输出：

```json
{
  "packet_id": "ros-roundtrip-798b69be726a",
  "src": "UAV",
  "dst": "Car",
  "dropped": true,
  "drop_stage": "ns3",
  "drop_reason": "range",
  "simulation_time_ns": 27880000000,
  "packet_age_ns": 0,
  "node_distance_m": 10.0,
  "topology_hop_count": null,
  "route_available": false,
  "routing_protocol": "olsr",
  "max_range_m": 1.0,
  "source_position_m": [0.0, 0.0, 0.0],
  "destination_position_m": [10.0, 0.0, 0.0]
}
```

`simulation_time_ns` 是事件发生时的 ns-3 累计仿真时刻，`packet_age_ns` 是该包在 ns-3 中已等待的时间。`node_distance_m` 和两端坐标来自 runner 当前使用的网络拓扑坐标，不应与天基任务报告中的真实星地斜距混为一谈。

测试某种预期丢包时可以同时约束阶段和原因：

```bash
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" \
  --source UAV --destination Car \
  --expect-drop \
  --expect-drop-stage ns3 \
  --expect-drop-reason range
```

更新诊断代码后必须重新执行 `NetworkSim/scripts/build_ns3_runner.sh`。新版 Python bridge 可以读取旧 runner 的短格式 `DROP`，但旧格式没有节点距离、路由和仿真时间，相关字段会是空值。

不启动 UE 也可以运行自动化闭环测试。脚本会在独立 ROS master 端口上启动两个逻辑节点、动态目标 GPS 发布器、ns-3 bridge 和 mock 卫星 access 发布器，先验证动态目标可见时送达，再验证不可见时进入 `/network_sim/drop`：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/tests/ros_space_access_integration_test.sh
```

测试使用 `NetworkSim/config/network-simulation-space-access.example.json`，不会读取或修改 Windows 当前的 AirSim `settings.json`，结束后会关闭自己启动的 ROS 和 bridge 进程。

当前 WSL 验证结果：可见链路 `Satellite -> Car` 已经过 ns-3 正常送达并返回非零 `latency_ns`；将最低仰角提高到 `89.9` 度后，同一数据包由 `space_access_policy` 阻断，`/network_sim/drop` 返回实际仰角、距离和阻断原因。

### 真实 TLE 与动态链路转换测试

安装 WSL 侧卫星 RPC 和 SGP4 依赖：

```bash
python3 -m pip install --user sgp4 msgpack-rpc-python
```

UE、ROS wrapper 和当前 `settings.json` 中的 ns-3 配置启动后，运行：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_space_network_demo.sh
```

脚本会刷新当前 TLE、自动定位下一次参考点过境、驱动 UE 卫星、发布动态 access 并复用或启动 NetworkSim bridge。另开终端验证转换：

```bash
source /opt/ros/noetic/setup.bash
source "${HOME}/LAESim/ros/devel/setup.bash"
python3 NetworkSim/tests/ros_tle_network_transition_test.py \
  --source Satellite --destination Car --timeout 120
```

成功输出同时包含 `blocked_phase` 和 `visible_phase`。前者应为 `space_access_unavailable`，后者应包含非零 `latency_ns`。运行记录和窗口摘要保存在 `${HOME}/LAESim/.runtime/tle_demo/`。

当前一键演示默认把 UE 卫星轨迹显示为 80 m 半径、300 m 高度。该尺度只服务画面表现；启用 `SatelliteLinkModel` 后，星地通信使用 TLE/access 的真实斜距，调整 `DISPLAY_RADIUS` 或 `DISPLAY_ALTITUDE` 不会再改变星地链路结果。

本机真实 UE 动态验证中，Satellite 与 Car 的显示坐标距离约 306.4 m，超过普通 Wi-Fi 的 `MaxRangeMeters=250`；同一数据包仍以 `link_type=satellite` 在真实斜距 1820.7 km 下送达。输出为：传播时延 6.073 ms、串行化时延 4.096 ms、总时延 10.169 ms、FSPL 164.50 dB、SNR 7.51 dB、包错误率约 0.000454。该结果直接验证了星地通信与 UE 显示坐标已经解耦。

### 多卫星选择与链路切换

当前多星配置模板包含 `Satellite`、`Satellite2`、`Satellite3`。启动三星实时传播：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

交付时可以使用带运行状态检查和 UE 标记的完整入口：

```bash
bash NetworkSim/scripts/start_space_demo.sh
bash NetworkSim/scripts/space_demo_status.sh
```

`start_space_demo.sh` 会先验证 UE ROS 时间戳正在前进，然后启动多星桥、NetworkSim 和 `space_mission_visualizer_ros.py`。任务计算和 ROS 状态默认 2 Hz，UE 卫星位姿和可视化标记默认 0.5 Hz，以降低编辑器长时间运行时的 RPC 压力。可视化器在上游状态中断 10 秒或连续 3 次 RPC 失败后自动退出，不会无限重试。它在 UE 中画星下点、覆盖圈、当前选择链路和 UP/DOWN 标签；这些标记仅用于显示，不进入 ns-3 链路预算。

交付前先运行不依赖 UE 的确定性验收。它使用独立 ROS master，不会影响当前 ROS wrapper 或正在运行的 UE：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/tests/ros_space_delivery_acceptance.sh
```

测试固定验证 `DOWN -> UP:Satellite -> HANDOVER:Satellite2 -> DOWN`，并要求两个 DOWN 包由 `space_access_policy` 阻断、两个 UP 包通过 ns-3 `satellite` 逻辑链路投递。之后在 UE Play 和 ROS wrapper 已启动时运行实时环境自检：

```bash
bash NetworkSim/scripts/check_space_demo_environment.sh \
  --settings /mnt/c/Users/<Windows用户名>/Documents/AirSim/settings.json \
  --require-ros --require-ns3 --live
```

该脚本只读检查配置、依赖、runner、ROS 节点、三星状态、NetworkSim、可视化话题和卫星时间戳，不会安装软件或修改 settings。完整跨电脑步骤见 `docs/space_delivery_checklist.md`。

首次从单星配置切换到多星配置时，必须依次重启 UE Play、AirSim ROS wrapper 和 NetworkSim bridge。可用以下命令确认三颗星都已进入 ROS/NetworkSim：

```bash
rostopic hz /airsim_node/Satellite2/global_gps
rostopic echo -n 1 /space/Satellite3/state
rostopic echo -n 1 /space/selection/Car
rostopic list | grep '/network_sim/rx/Satellite'
```

`/space/selection/<target>` 选择当前最高仰角卫星，并通过迟滞与最短保持时间抑制切换振荡。NetworkSim 仍逐条订阅每颗卫星的 access；应用要把 `src` 设成 selection 消息中的 `selected_satellite`，才能完成业务链路切换。自动测试为：

```bash
python3 NetworkSim/tests/ros_constellation_handover_test.py \
  --target Car --duration 60
```

脚本输出发送、送达、丢包、使用过的卫星和 handover 次数。需要强制验证实际发生过切换时增加 `--require-handover`。运行报告位于 `${HOME}/LAESim/.runtime/constellation_demo/`，其中 summary 记录切换次数、覆盖中断与重访间隔。

结束演示并导出报告：

```bash
bash NetworkSim/scripts/stop_space_demo.sh
python3 NetworkSim/python/export_space_demo_report.py \
  --runtime-dir "${HOME}/LAESim/.runtime/constellation_demo"
```

报告导出器生成 Markdown 总结以及目标统计、切换事件和 ISL 可用率三个 CSV。若需要连 NetworkSim 一起停止，使用 `stop_space_demo.sh --include-network`；AirSim ROS wrapper 始终保留，避免影响其他载具实验。

不启动 UE 也可以验证“最佳星选择 -> 星地逻辑链路 -> ns-3 -> ROS 接收”闭环：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/tests/ros_constellation_integration_test.sh
```

该测试使用独立 ROS master 和 `NetworkSim/config/network-simulation-constellation.example.json`，不会修改当前 AirSim 配置。三颗测试星使用同一份样例 TLE，因此它验证的是多星接口和选择链路，不用于验证真实星座切换；真实 handover 仍使用三份不同当前 TLE 的一键演示。

### 星间链路与多跳逻辑路由

多星启动器默认发布三颗卫星之间的 ISL access，默认最大作用距离为 5000 km：

```bash
PUBLISH_ISL=1 MAX_ISL_RANGE_M=5000000 \
  bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

应用需要显式给出中继路径：

```bash
rostopic pub -1 /network_sim/tx std_msgs/String \
  '{data: "{\"packet_id\":\"relay-1\",\"src\":\"Satellite\",\"dst\":\"Car\",\"route\":[\"Satellite\",\"Satellite2\",\"Car\"],\"size_bytes\":1024,\"payload\":\"mission-data\"}"}'
```

处理过程：

1. ROS bridge 验证 route 首尾必须等于 `src/dst`，节点必须存在且不得重复。
2. 每一跳分别匹配 `SpaceAccessPolicy`；某一跳失败时 `/network_sim/drop` 返回 `failed_hop`。
3. `SatelliteLinkModel` 按每一跳真实距离分别计算 FSPL、SNR、传播时延和包错误率。
4. ns-3 runner 用每条有向链路的独立队列执行逐跳存储转发，组合各跳错误率后交付或丢弃。

成功包使用 `link_type=satellite_route`，并带 `route_nodes`、`route_hop_count`、各跳距离/传播/串行化时延的汇总值。底层 runner 更新后必须重新构建：

```bash
bash NetworkSim/scripts/build_ns3_runner.sh
python3 NetworkSim/tests/smoke_backend.py --require-ns3
```

ROS 两跳测试已包含在 `ros_constellation_integration_test.sh` 中。当前固定验收链路总斜距 1500 km、两跳总时延约 13.195 ms。

该功能仍属于消息级显式路由：只有带 `route` 的 `/network_sim/tx` 包进入星间中继模型，普通 ROS topic、TCP/UDP 和不带 route 的包保持原行为。

### 10.2 统一场景时钟

默认情况下，NetworkSim 使用墙钟定时器按 `StepMs` 推进 ns-3。需要暂停、单步、倍速和确定性复现时，在 `settings.json` 的 `NetworkSimulation` 中启用：

```json
"UnifiedClock": {
  "Enabled": true,
  "ClockTopic": "/clock",
  "MaxStepMs": 1000.0
}
```

然后先启动统一时钟，再启动 NetworkSim bridge：

```bash
cd "${HOME}/LAESim"
source /opt/ros/noetic/setup.bash
source ros/devel/setup.bash

python3 ros/src/example/space_sim_clock.py \
  --start-time 2026-07-23T00:00:00Z --rate 60

# 另开终端
bash NetworkSim/scripts/run_ros_network_bridge.sh
```

启用后，网络桥不再用 ROS 墙钟 Timer 主动推进后端，而是只消费 `/clock` 的正向增量：

- `pause`：`/clock` 保持不变，ns-3 事件不推进。
- `step --seconds N`：精确推进 N 秒场景时间，释放该时间段内到期的网络事件。
- `set_rate`：只改变后续场景时间相对墙钟的倍率。
- `resume`：恢复连续推进。

`MaxStepMs` 用于把一次较大的 `/clock` 跳变量分块送入后端，避免单次推进过大。它不会改变最终场景时间。`simulation_time_ns` 仍表示 ns-3 累计场景时刻，`latency_ns` 仍表示单包仿真时延。

ns-3 离散事件时间不能回退。如果 `/clock` 跳到更早时刻，网络桥会忽略负增量并告警；需要从过去时刻重新实验时，应重启 NetworkSim bridge。AirSim ROS wrapper 不需要设置 `/use_sim_time=true`，UE 物理本身也不会被此开关暂停。

不依赖 UE 的自动验收命令：

```bash
bash NetworkSim/tests/ros_unified_clock_integration_test.sh
```

该测试同时检查 `/clock`、TLE 状态时刻和 ns-3 投递，避免只验证“话题存在”而没有验证时间语义。

## 11. 图像传输与网络栈边界

ns-3 可以模拟承载图像的字节流，但不会替代 UE 生成画面，也不会自动把 `sensor_msgs/Image` 转换成真实操作系统 socket 流量。当前集成采用消息级网络仿真：

- UE/LAESim 生成仿真画面。
- 应用压缩并分片图像，再按分片实际字节数提交给 `/network_sim/tx`。
- ns-3 决定分片何时到达或是否丢失。
- 接收应用根据数据包和分片序号重组并解码图像。

当前单个 ns-3 包上限为 60000 字节，大图像必须分片。这种方式适合研究自组织网络对感知和协同算法的影响，并可统计时延、吞吐量、丢包率和路由变化。

如果必须让未经修改的 ROS/TCP/UDP 程序直接经过网络仿真，需要进一步接入 TAP/EMU 或 DCE。这会增加 Linux 网络接口、权限和时钟同步要求，不属于当前集成范围。

## 12. 当前限制

- runner 当前使用 IEEE 802.11g ad hoc、固定发送功率、RangePropagationLoss 和 OLSR/AODV。
- `MaxRangeMeters` 只提供硬截止，实际可达距离还受发送功率、接收门限和 Yans 路径损耗影响。
- 星地逻辑链路当前采用自由空间损耗、固定收发增益、固定噪声系数和 BPSK 误码近似；尚未模拟多普勒、天气衰减、自适应调制编码和天线指向动态。
- 默认模式仍由墙钟 Timer 和固定 `StepMs` 软同步；可选统一时钟模式已支持暂停、单步和倍速，但尚未控制 UE 物理时间。
- 指标尚未发布为 ROS 指标主题或持久化为 CSV。
- 当前会在每次丢包事件中导出路由协议、可用状态和拓扑跳数，但尚未持续发布完整路由表变化。
- 天基门控和星间中继当前针对显式提交的应用层消息，不会自动改写任意 ROS/TCP/UDP 程序的网络路径。
- 视频传输仍需补充编码、分片、重传和接收缓冲策略。
- WSL 发行版的 `ext4.vhdx` 可以放在非系统盘，但 Windows 自身的 WSL 组件仍可能占用少量系统盘空间。

## 13. 官方参考

- [Microsoft：导入任意 Linux 发行版供 WSL 使用](https://learn.microsoft.com/windows/wsl/use-custom-distro)
- [ns-3 官方文档](https://www.nsnam.org/documentation/)
- [ROS Noetic 安装说明](https://wiki.ros.org/noetic/Installation/Ubuntu)
- [Ubuntu 官方云镜像](https://cloud-images.ubuntu.com/)
