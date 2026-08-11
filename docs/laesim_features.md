# LAESim 核心特色

LAESim 的目标不是重新维护一份 AirSim 通用文档，而是在 AirSim 的仿真、传感器和 API 基础上，提供空天地海混合载具、图片地图与可选通信网络仿真。

## 空天地海混合载具

原版 AirSim 常用的 `SimMode` 会在 `Multirotor`、`Car` 等模式之间选择，同一个模式主要承载同类载具。LAESim 新增 `AirGround` 模式，使无人机、汽车、船和卫星能够在同一个 UE 场景中同时运行。

| 载具 | `VehicleType` | 默认 RPC 端口 | 控制接口 |
| --- | --- | --- | --- |
| 无人机 | `SimpleFlight` | `41471` | Python API、ROS 速度/起降接口 |
| 汽车 | `PhysXCar` | `41461` | Python API、ROS `car_cmd` |
| 船 | `SimpleBoat` / `PhysXBoat` | `41481` | Python API、ROS 船控制与状态接口 |
| 卫星 | `SimpleSatellite` | `41491` | Python API、ROS 三维速度与状态接口 |
| 通用/CV | 不限定 | `41451` | 相机和通用仿真接口 |

不同类型载具可以共享以下能力：

- 相机、IMU、GPS 和 Lidar
- 载具位姿与碰撞状态
- 多实例命名和独立初始位置
- Windows Python API
- WSL2 中的 ROS Noetic topic/service

下面是一份经过验证的混合配置结构：

```json
{
  "SettingsVersion": 1.2,
  "SimMode": "AirGround",
  "ApiServerPortCV": 41451,
  "ApiServerPortCar": 41461,
  "ApiServerPortMultirotor": 41471,
  "ApiServerPortBoat": 41481,
  "ApiServerPortSatellite": 41491,
  "Vehicles": {
    "UAV": { "VehicleType": "SimpleFlight" },
    "Car": { "VehicleType": "PhysXCar" },
    "Boat": { "VehicleType": "SimpleBoat" },
    "Satellite": { "VehicleType": "SimpleSatellite" }
  }
}
```

## Boat 载具链路

LAESim 增加了 AirSim 原版没有提供的 Boat 类型、Pawn、状态结构、Python API、ROS topic、控制示例和默认 052B 船模型。

当前 Boat 使用简化的平面三自由度模型：

- `u`：船体纵向速度
- `v`：横向漂移速度
- `r`：艏向角速度

该模型保留转向惯性和横向漂移，适合验证 USV/舰船编队、任务规划、传感器和协同通信。它不是水动力仿真，不计算波浪、水流、浮力、横摇或纵摇；场景可以使用蓝色平面表示水域。

## Satellite 载具链路

Satellite 提供独立 Pawn、状态结构、Python API、ROS topic、控制示例和默认模型。当前运动模型是三维空间理想质点，控制量为 NED 速度 `vx/vy/vz` 与 `yaw_rate`；停止发送持续移动指令后会静止悬停。该模型适合任务规划、空间协同、感知与通信研究，不模拟轨道摄动、重力或推进器动力学。

## 天基任务桥接

如果需要卫星轨道、星下点、目标可见性或链路几何量，LAESim 使用外部 Python 桥接进程读取 TLE/SGP4、CSV 或 mock 数据，再通过 AirSim RPC 调用 `simSetVehiclePose` 驱动 UE 中的 `SimpleSatellite` 显示模型。

这种设计区分两套坐标：

- 真实计算坐标：由天基任务桥接脚本保持经纬高、ECEF、局部 NED 和任务时间。
- 任务窗口：支持采样统计，也支持 Orekit 仰角事件检测生成亚秒边界的升起/落下窗口。
- 网络联动：可用实时 `/space/<satellite>/access/<target>` 状态门控指定 NetworkSim/ns-3 应用层链路。
- UE 显示坐标：按比例缩放后的局部 NED，仅用于让场景中“看得见卫星”。

真实星地距离、仰角、方位角和 Access 状态应以桥接脚本输出为准，不建议从 UE 中显示模型的距离反推。当前已提供实时桥接脚本和离线任务分析脚本：前者用于驱动 UE 里的 `SimpleSatellite` 模型，后者用于统计多星、多目标、区域网格覆盖、覆盖窗口、重访时间和可见时间段报告，并可导出供网络联动使用的链路窗口和 GeoJSON 可视化文件。

## SceneMap 图片地图

SceneMap 可以在启动时或运行时把图片加载为 UE 平面地图，支持：

- 任意长宽比图片、米/像素比例尺和可选碰撞
- `NorthUp`/`NED` 像素坐标约定
- `GeoReference` 经纬度与图片像素配准
- 按像素、地图局部米制坐标或 GPS 设置载具出生位置
- Python API 与 ROS 服务进行加载、卸载、查询和坐标转换

配置模板见仓库中的 `settings_scene_map_1uav_1car_1boat.json` 和 `settings_satellite_map_gps_start.json`。

## 可选 ns-3 自组织网络

LAESim 将通信后端做成可配置能力：

| 后端 | 行为 | 适用场景 |
| --- | --- | --- |
| `none` | 消息立即到达，不考虑网络影响 | 复用原有算法、调试控制与感知 |
| `ns3` | 经过 Wi-Fi ad hoc 和 OLSR/AODV | 研究时延、吞吐量、丢包和拓扑变化 |

AirSim/UE 提供载具位置，ROS 网络桥接器把位置和应用消息交给 ns-3。这样可以研究网络状态对空地海协同算法的影响，同时不改变 UE 的物理和画面生成职责。

当前已经完成：

- `none` 与 `ns3` 后端切换
- AirSim odometry 到 ns-3 节点位置更新
- ROS `UAV -> Car` 消息往返
- 通信范围内正常交付与范围外超时丢包
- OLSR 两节点冒烟测试

完整环境、接口和限制见[WSL2、ROS 与 ns-3](laesim_wsl_ros_ns3.md)。

## 继承的 AirSim 能力

相机类型、通用 API、坐标系、PX4、传感器参数等基础能力继续遵循 AirSim。相关内容直接查阅 [AirSim 官方文档](https://microsoft.github.io/AirSim/)，本站只维护 LAESim 的差异和扩展。
