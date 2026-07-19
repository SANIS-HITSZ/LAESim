# LAESim

LAESim 是面向空天地海协同研究的多载具仿真平台。在同一个 UE 4.27 场景和同一份 `settings.json` 中，可以同时运行无人机、车辆、船和卫星，并通过 Python API 或 ROS 对不同类型载具进行控制和状态采集。

<img alt="LAESim 空地协同多机仿真场景" src="https://github.com/user-attachments/assets/b6abd8e5-756e-46b6-a82c-31d273962cd5" />

## 核心扩展

### 空天地海混合载具

原版 AirSim 的常用运行模式通常在 `Multirotor` 与 `Car` 之间选择。LAESim 新增 `AirGround` 混合模式和 Boat 载具链路，使以下对象能够出现在同一个仿真场景中：

- 多架 `SimpleFlight` 无人机
- 多辆 `PhysXCar` 汽车
- 多艘 `SimpleBoat` 或 `PhysXBoat` 船
- 多颗 `SimpleSatellite` 卫星

不同类型载具拥有独立 RPC 端口，并共享相机、IMU、GPS、Lidar、Python API 和 ROS 接口。参见[核心特色](laesim_features.md)。

### SceneMap 图片地图

LAESim 可以把卫星图或其他图片加载为 UE 中的可碰撞平面地图，按像素比例尺建立坐标系，并通过 `GeoReference` 完成 GPS 配准。载具既可以在启动时按像素、米制坐标或经纬度出生，也可以通过 Python API 或 ROS 在运行时加载地图、查询状态和转换坐标。

### 可选 ns-3 自组织网络

LAESim 可以保持原来的理想通信，也可以按配置启用 ns-3.48，对 Wi-Fi ad hoc、OLSR/AODV 路由、时延、吞吐量和丢包进行离散事件仿真：

```json
"NetworkSimulation": {
  "Backend": "none"
}
```

将 `Backend` 改为 `ns3` 并启动 ROS 网络桥接器后，应用消息会经过 ns-3。参见[安装与构建 LAESim 中的 WSL2、ROS 与 ns-3 部分](laesim_build.md#wsl-ros-ns3)。

## 开始使用

1. 按[安装与构建 LAESim](laesim_build.md)准备 Windows、UE 4.27 和 Visual Studio，并编译 LAESim 插件。
2. 按[使用 LAESim](laesim_use.md)选择混合载具模板、启动场景并验证 Python API 或 ROS。
3. 需要研究通信网络时，继续完成同一页面中的[WSL2、ROS 与 ns-3 安装](laesim_build.md#wsl-ros-ns3)。

## 与 AirSim 的关系

LAESim 基于 Microsoft AirSim 扩展，继承其仿真环境、传感器和 API 基础能力。通用 AirSim 功能不在本站重复维护，请直接查阅 [AirSim 官方文档](https://microsoft.github.io/AirSim/)；本站只记录 LAESim 的构建、混合载具、Boat、Satellite、SceneMap、ROS 联动和 ns-3 集成。
