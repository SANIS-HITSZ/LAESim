# LAESim 文档

LAESim 文档面向仿真平台使用者和贡献者，集中记录项目自身的混合载具、SceneMap、构建流程、ROS/ns-3 集成与可复现实验。AirSim 通用 API、传感器和飞控内容直接引用上游官方文档。

## 从这里开始

| 目标 | 文档入口 |
| --- | --- |
| 了解 LAESim 相比 AirSim 增加了什么 | [核心特色](laesim_features.md) |
| 在 Windows 中构建 UE 4.27 插件 | [安装与构建 LAESim](laesim_build.md) |
| 安装 WSL2、ROS Noetic 和 ns-3 | [WSL2、ROS 与 ns-3](laesim_build.md#wsl-ros-ns3) |
| 选择配置并启动混合载具场景 | [使用 LAESim](laesim_use.md) |
| 查看已验证的协同与通信实验 | [仿真案例](simulation_cases.md) |

## 核心组成

- `AirGround` 混合模式：在同一场景运行无人机、车辆、舰船和卫星。
- SceneMap：导入图片地图，支持比例尺、GPS 配准和坐标转换。
- Python/ROS 接口：控制载具并采集状态、相机、IMU、GPS 和 Lidar。
- 可选 ns-3 后端：模拟 Wi-Fi ad hoc、路由、时延、吞吐量与丢包。

## 上游资料

LAESim 基于 Microsoft AirSim 扩展。通用功能参见 [AirSim 官方文档](https://microsoft.github.io/AirSim/)，网络模型与模块参见 [ns-3 官方文档](https://www.nsnam.org/documentation/)。
