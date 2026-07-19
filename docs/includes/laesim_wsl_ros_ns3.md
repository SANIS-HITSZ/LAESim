<a id="wsl-ros-ns3"></a>
## WSL2、ROS Noetic 与 ns-3

本文说明如何在 Windows 中运行 LAESim/UE4，同时在 WSL2 中运行 ROS Noetic 和可选的 ns-3 网络仿真。所有路径均使用环境变量或通用占位符，不依赖某台电脑的用户名、盘符或目录结构。

### 1. 系统结构

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

### 2. 已验证的软件版本

| 组件 | 版本 |
| --- | --- |
| Windows | Windows 11 + WSL2 |
| Unreal Engine | UE 4.27 |
| Linux | Ubuntu 20.04 (focal) |
| ROS | ROS Noetic |
| ns-3 | ns-3.48，提交 `d2add90b452d600cfb4859baed8e9ea633519447` |
| ns-3 编译器 | GCC/G++ 11 |
| LAESim ROS 编译器 | GCC/G++ 8 |

ROS Noetic 与 Ubuntu 20.04 已离开标准支持周期。当前组合用于兼容 LAESim 的 ROS1 工程；在项目完成 ROS 2 迁移前，不要直接用其他 Ubuntu 或 ROS 版本替换。

### 3. 创建 LAESim WSL2 发行版

#### 3.1 定义本机参数

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

#### 3.2 导入发行版

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

### 4. 安装 ROS Noetic

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

### 5. 在 WSL 中编译 LAESim ROS

建议将用于 Linux 编译的源码克隆到 WSL 的 ext4 文件系统中。不要直接在 `/mnt/c`、`/mnt/d` 等 Windows 挂载目录中编译大量 Linux 小文件。

在 PowerShell 中进入刚创建的发行版：

```powershell
wsl -d $DistroName
```

进入 WSL 后执行：

```bash
export LAESIM_HOME="${HOME}/LAESim"
git clone --branch V1.4 https://github.com/SANIS-HITSZ/LAESim.git "${LAESIM_HOME}"
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

### 6. 验证 Windows LAESim 与 WSL ROS

#### 6.1 启动 Windows 仿真端

1. 将多机配置保存为 `%USERPROFILE%\Documents\AirSim\settings.json`。
2. 使用 UE 4.27 打开 LAESim 环境。
3. 点击 Play，等待场景和 AirSim RPC 服务启动。
4. 根据 `settings.json` 中配置的 RPC 端口检查监听状态。

例如，默认 RPC 端口可通过 PowerShell 检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 41451
```

#### 6.2 启动 WSL ROS

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

### 7. 安装与构建 ns-3

在 WSL 内执行仓库脚本：

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

需要改用其他目录时，在运行两个脚本前设置同一个 `NS3_ROOT`：

```bash
export NS3_ROOT="${HOME}/simulators/ns-3.48"
```

运行后端冒烟测试：

```bash
source /opt/ros/noetic/setup.bash
python3 "${HOME}/LAESim/NetworkSim/tests/smoke_backend.py"
```

测试应分别覆盖有效通信距离内成功送达，以及超出通信距离后丢包的情况。

### 8. 配置可选网络后端

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
  "RunnerPath": "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"
}
```

| `Backend` | 行为 |
| --- | --- |
| `none` | 保持理想通信，ROS 消息立即转发，不计算网络时延、丢包和路由 |
| `ns3` | 消息经过 ns-3 Wi-Fi ad hoc 网络，节点位置由配置出生偏移与 LAESim 局部 odometry 合成 |

当前 runner 支持 `olsr` 和 `aodv`。`MaxRangeMeters` 是当前实现使用的硬通信范围，`PacketTimeoutSeconds` 到期后未送达的包会被记录为 `DROP`。

### 9. 启动网络桥接器

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

### 10. ROS 消息接口与端到端测试

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
source "${HOME}/LAESim/ros/devel/setup.bash"
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py"
```

应分别用 `none` 和 `ns3` 后端测试。`none` 模式的网络仿真时间为 0；`ns3` 模式应返回非零仿真时间，链路不可达时应输出丢包结果。

### 11. 图像传输与网络栈边界

ns-3 可以模拟承载图像的字节流，但不会替代 UE 生成画面，也不会自动把 `sensor_msgs/Image` 转换成真实操作系统 socket 流量。当前集成采用消息级网络仿真：

- UE/LAESim 生成仿真画面。
- 应用压缩并分片图像，再按分片实际字节数提交给 `/network_sim/tx`。
- ns-3 决定分片何时到达或是否丢失。
- 接收应用根据数据包和分片序号重组并解码图像。

当前单个 ns-3 包上限为 60000 字节，大图像必须分片。这种方式适合研究自组织网络对感知和协同算法的影响，并可统计时延、吞吐量、丢包率和路由变化。

如果必须让未经修改的 ROS/TCP/UDP 程序直接经过网络仿真，需要进一步接入 TAP/EMU 或 DCE。这会增加 Linux 网络接口、权限和时钟同步要求，不属于当前集成范围。

### 12. 当前限制

- runner 当前使用 IEEE 802.11g ad hoc、固定发送功率、RangePropagationLoss 和 OLSR/AODV。
- ROS 时钟与 ns-3 离散事件时钟使用固定 `StepMs` 软同步。
- 自动出生偏移当前读取 `Vehicles.<name>.X/Y/Z`；使用 `StartOnSceneMap` 时应同时提供等价的 `X/Y/Z` 供网络桥接器定位。
- 指标尚未发布为 ROS 指标主题或持久化为 CSV。
- 路由变化尚未导出到 ROS。
- 视频传输仍需补充编码、分片、重传和接收缓冲策略。
- WSL 发行版的 `ext4.vhdx` 可以放在非系统盘，但 Windows 自身的 WSL 组件仍可能占用少量系统盘空间。

### 13. 官方参考

- [Microsoft：导入任意 Linux 发行版供 WSL 使用](https://learn.microsoft.com/windows/wsl/use-custom-distro)
- [ns-3 官方文档](https://www.nsnam.org/documentation/)
- [ROS Noetic 安装说明](https://wiki.ros.org/noetic/Installation/Ubuntu)
- [Ubuntu 官方云镜像](https://cloud-images.ubuntu.com/)
