# 实验一：无人机、汽车与船异构协同

## 实验目标

- 使用一个 `settings.json` 创建三种载具。
- 理解 `VehicleType`、实例名称、出生位置和独立 RPC 端口。
- 使用 Python API 同时控制无人机、汽车和船并读取状态。

该实验只需要 Windows LAESim，不需要 ROS 和 ns-3。Boat 使用 LAESim 的简化平面三自由度模型，可在普通平面场景中运行，不要求 UE 水体。

## 1. 准备配置

在仓库根目录打开 PowerShell，先备份当前配置，再复制实验配置：

```powershell
$AirSimDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AirSim'
New-Item -ItemType Directory -Force $AirSimDir | Out-Null
$Settings = Join-Path $AirSimDir 'settings.json'
if (Test-Path $Settings) { Copy-Item $Settings "$Settings.backup" -Force }
Copy-Item .\Examples\quickstart\heterogeneous_fleet\settings.json $Settings -Force
```

配置中的 `UAV`、`Car`、`Boat` 是后续 API 使用的实例名称。`X/Y/Z` 决定各载具相对于场景原点的出生位置。

## 2. 安装 Python 客户端

```powershell
py -3 -m pip install msgpack-rpc-python numpy opencv-contrib-python
```

实验脚本会直接加载当前仓库中的 `PythonClient/airsim`，不依赖系统里可能存在的其他 AirSim Python 包。

只检查活动配置而不连接 UE：

```powershell
py -3 .\Examples\quickstart\heterogeneous_fleet\run_experiment.py --check-only
```

看到 `configuration check passed` 表示载具类型和 RPC 端口配置正确。

## 3. 运行实验

1. 使用 UE 4.27 打开 LAESim 环境。
2. 点击 **Play**，等待 AirSim RPC 服务启动。
3. 在仓库根目录执行：

```powershell
py -3 .\Examples\quickstart\heterogeneous_fleet\run_experiment.py
```

脚本会让无人机起飞并沿 NED X 方向飞行，同时给汽车和船发送油门、转向控制。终端每秒输出一次无人机局部坐标、汽车速度以及船的纵向/横向速度，约 8 秒后停止载具并让无人机降落。

## 4. 配置与 API 练习

- 将 `Car.Y` 从 `-8` 改为 `-12`，重启 Play 后观察出生位置变化。
- 将脚本中的 `CarControls(throttle=0.55)` 改为较小值，比较汽车速度。
- 将 `BoatControls.steering` 的符号反转，观察船的转向和横向速度。
- 把配置或脚本中的实例名改错，观察“配置校验失败”和“RPC 找不到载具”的差别。

## 预期结果与排查

- 三种载具应同时出现在场景中，且终端持续输出三类状态。
- `Connection refused`：UE 尚未 Play，或者端口与配置不一致。
- `Vehicle ... not found`：脚本实例名与 `Vehicles` 中的键不一致。
- 船没有真实水体效果属于预期；本实验验证的是异构接口和基础运动，而不是水动力。
