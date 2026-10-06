# LAESim

面向空天地海协同研究的多载具仿真平台

[![V1.6 Core Verification](https://github.com/SANIS-HITSZ/LAESim/actions/workflows/verify_v16_core.yml/badge.svg?branch=V1.6)](https://github.com/SANIS-HITSZ/LAESim/actions/workflows/verify_v16_core.yml?query=branch%3AV1.6)
[![Documentation Build & Deploy](https://github.com/SANIS-HITSZ/LAESim/actions/workflows/test_docs.yml/badge.svg?branch=V1.6)](https://github.com/SANIS-HITSZ/LAESim/actions/workflows/test_docs.yml?query=branch%3AV1.6)

**维护单位：哈尔滨工业大学（深圳）广东省空天网络与智能感知重点实验室**

[项目展示页](https://sanis-hitsz.github.io/LAESim/) · [项目文档](https://sanis-hitsz.github.io/LAESim/documentation/) · [安装与构建](https://sanis-hitsz.github.io/LAESim/laesim_build/) · [仿真案例](https://sanis-hitsz.github.io/LAESim/simulation_cases/)

![LAESim 岛屿场景中的卫星、无人机、车辆与舰船](docs/assets/showcase/laesim-air-space-sea-overview.png)

LAESim 基于 Microsoft AirSim 和 Unreal Engine 4.27 扩展，面向无人机、车辆、舰船与卫星协同任务。项目将多类型载具、图片地图、Python/ROS 接口、天基任务分析和可选 ns-3 网络仿真组织在同一套场景配置与实验流程中。

当前版本为 **`V1.6`**，在 `V1.5` 基础上新增 RadioMapNav：程序化城市、Sionna RT 离线信道地图，以及信道质量约束下的无人机路径规划与 LAESim 飞行示例。

通用场景生成与 UE 导入位于 [SceneGen](SceneGen/README.md)，通用信道地图构建与查询位于 [RadioSim](RadioSim/README.md)；RadioMapNav 作为依赖这些平台能力的应用示例。

## 核心能力

| 能力 | LAESim V1.6 |
| --- | --- |
| 混合载具 | 同一 `AirGround` 场景运行无人机、车辆、舰船和卫星 |
| SceneMap | 将图片加载为可碰撞地图，支持比例尺、GPS 配准和坐标转换 |
| 仿真接口 | Windows Python API、ROS Noetic topic/service、多实例独立端口 |
| 天基任务 | TLE/SGP4、CSV、Orekit 可选后端，多星多目标覆盖与任务窗口分析 |
| 网络后端 | `none` 理想通信、ns-3 Wi-Fi ad hoc，或使用真实斜距预算的星地/星间逻辑链路 |
| 无线地图与导航 | Sionna RT 生成场景相关 RSS/SINR 地图，对比几何基线与通信约束路径，并通过 Python API 执行飞行 |
| 实验指标 | 时延、吞吐量、丢包、覆盖窗口、重访时间、链路切换与丢包原因 |
| 可复现工程 | settings 模板、构建脚本、ROS/ns-3 安装脚本和冒烟测试 |

## 系统架构

```mermaid
flowchart LR
    Map[SceneMap / UE 场景] --> Sim[LAESim / Unreal Engine 4.27]
    Fleet[无人机 · 车辆 · 舰船 · 卫星] --> Sim
    Orbit[TLE / CSV / Orekit] --> Space[天基任务桥接]
    Space --> Sim
    Sim --> Py[Python API]
    Sim --> ROS[ROS Noetic]
    Space --> ROS
    ROS --> Net{通信后端}
    Net --> Ideal[none / 理想通信]
    Net --> NS3[ns-3.48]
```

Windows 负责 UE 场景、物理、画面和传感器生成；WSL2 可选运行 ROS Noetic 与 ns-3。不开启 ns-3 时，现有控制和感知流程仍按理想通信运行。

## 支持的载具

| 载具 | `VehicleType` | 默认 RPC 端口 | 模型边界 |
| --- | --- | --- | --- |
| 无人机 | `SimpleFlight` | `41471` | 继承 AirSim 多旋翼能力 |
| 车辆 | `PhysXCar` | `41461` | PhysX 地面车辆 |
| 舰船 | `SimpleBoat` / `PhysXBoat` | `41481` | 简化平面三自由度，不模拟完整水动力 |
| 卫星 | `SimpleSatellite` | `41491` | UE 内为显示模型；真实轨道与任务几何由可选天基任务桥接计算 |
| 通用/CV | 不限定 | `41451` | 场景、相机与通用仿真 API |

## SceneMap

SceneMap 将任务图片或卫星图转换为 UE 中的可碰撞平面地图，并建立三套坐标之间的关系：

- 图片像素坐标 `U/V`
- 地图局部米制坐标 `MapX/MapY`
- GPS 经纬度与海拔

载具可以通过 `StartOnSceneMap` 按像素、米制坐标或 GPS 出生；Python API 和 ROS 服务可以在运行时加载、卸载、查询地图并进行坐标转换。

配置与接口说明见[使用 LAESim](https://sanis-hitsz.github.io/LAESim/laesim_use/)和[图片场景地图说明](如何加入图片场景地图功能.md)。

## 天基任务桥接

V1.5 将真实任务计算与 UE 演示坐标分离：TLE/SGP4、CSV 或可选 Orekit 后端负责卫星星历、目标可见性、覆盖窗口和重访统计，`SimpleSatellite` 只在 UE 中显示缩放后的轨迹。多星实时桥接、最佳卫星选择、链路切换、星地链路预算和星间多跳均作为可选流程启用，不启动相关脚本时不会改变原有载具仿真。

使用和验证方法见[天基任务桥接](docs/space_mission_bridge.md)与[交付检查清单](docs/space_delivery_checklist.md)。

## ROS 与 ns-3

LAESim 保留两种可切换的通信模式：

- `Backend: none`：消息直接转发，用于算法基线和常规控制/感知调试。
- `Backend: ns3`：地面节点消息可经过 ns-3 Wi-Fi ad hoc + OLSR/AODV；受 `SpaceAccessPolicy` 管理的星地/星间消息可按真实斜距、传播时延、链路预算和误码模型处理。

当前集成采用消息级网络仿真。UE 仍负责生成画面和传感器数据，应用按真实字节数向网络桥接器提交消息；图像和视频需要由应用完成压缩、分片、重组与解码。网络丢包统一发布到 `/network_sim/drop`，便于区分 access、链路预算、路由、范围和超时等阶段。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `AirLib/` | 通用仿真、载具 API、RPC 类型与设置解析 |
| `Unreal/Plugins/AirSim/` | UE 4.27 插件、Pawn、SimMode 与 SceneMap 实现 |
| `PythonClient/` | AirSim/LAESim Python 客户端 |
| `Multi_use/` | 无 ROS 控制、传感器、SceneMap 和天基任务工具 |
| `ros/` | ROS Noetic 工作空间、消息、服务与示例 |
| `NetworkSim/` | 可选 ns-3 runner、ROS 网络桥接器和测试 |
| `Examples/quickstart/` | 异构载具、ns-3 与 GeoTIFF 稳定下视采集实验 |
| `SceneGen/` | 通用程序化场景、统一几何、网页配置与 UE 导入 |
| `RadioSim/` | Sionna RT 信道地图构建、查询与 LAESim API 桥接 |
| `Examples/RadioMapNav/` | 依赖平台模块的通信约束导航、飞行与实验结果 |
| `how_to_use_settings/` | 单载具、混合载具、卫星和 SceneMap 配置模板 |
| `docs/` | LAESim 中文文档与展示页内容 |

## 文档导航

- [核心特色](https://sanis-hitsz.github.io/LAESim/laesim_features/)
- [安装与构建 LAESim](https://sanis-hitsz.github.io/LAESim/laesim_build/)
- [使用 LAESim](https://sanis-hitsz.github.io/LAESim/laesim_use/)
- [仿真案例](https://sanis-hitsz.github.io/LAESim/simulation_cases/)
- [天基任务桥接](docs/space_mission_bridge.md)
- [快速入门实验](Examples/quickstart/README.md)
- [RadioMapNav：信道地图与无人机导航](Examples/RadioMapNav/README.md)
- [Multi_use 使用说明](Multi_use/README_zh.md)
- [ROS 示例说明](ros/src/example/README_zh.md)

安装步骤、编译问题、WSL2、ROS Noetic 与 ns-3 环境配置统一维护在“安装与构建 LAESim”页面，根 README 不再重复维护安装教程。

## 验证状态

V1.6 继承 V1.5 的验证入口，并新增 RadioMapNav 验收。原有验证覆盖以下链路：

- Windows AirLib Release 与 UE 4.27 `BlocksEditor Win64 Development` 编译
- ROS Noetic 消息、服务和 wrapper 编译
- Python/JSON 配置语法检查
- ns-3 通信范围内交付与范围外超时丢包
- TLE/SGP4、多星多目标任务分析、覆盖窗口和重访报告
- 星地真实斜距链路预算、星间多跳、统一时钟和结构化丢包诊断
- GitHub Pages 文档构建与发布

仓库提供一个 Windows/Linux 通用的核心验证入口：

```bash
python -m pip install -e ".[dev]"
python NetworkSim/scripts/verify_v16_core.py
```

命令返回码为 `0` 且最后输出 `V1.6 CORE VERIFICATION: PASS` 时，表示原有可移植源码、配置、quickstart、33 个确定性单元测试和理想通信冒烟测试，以及 RadioMapNav 的 CPU 测试全部通过。页首 `V1.6 Core Verification` 徽章对应此验证入口，Actions 保留完整日志。

RadioMapNav 已在 Windows、RTX 3090、Sionna RT 2.1.0 与 UE 4.27 上完成真实信道地图生成、路径规划、场景导入和 API 飞行：378 个飞行采样点无碰撞、无低于 0 dB SINR 门限的采样点，终点误差约 0.44 米。该 SINR 来自固定 65 米高度的离线地图查询，不是每帧重新射线追踪，也不等同于 ns-3 包级投递验证。配置、对照指标和边界统一见 [RadioMapNav README](Examples/RadioMapNav/README.md#验收结果)。

该绿勾不代表 GitHub 云端启动了 UE、ROS 或真实 ns-3 runner。这些需要外部进程和特定开发环境的链路，应按[WSL2、ROS 与 ns-3](docs/laesim_wsl_ros_ns3.md)和[交付检查清单](docs/space_delivery_checklist.md)运行现场验收；只有得到具体包投递、非零时延、链路转换和 UE 位姿进展证据，才能说明对应的运行时链路 work。

运行时模型外观、碰撞、SceneMap 坐标方向和具体任务算法仍应在目标 UE 场景中按实验配置验证。

## 开源与上游

LAESim 基于 [Microsoft AirSim](https://github.com/microsoft/AirSim) 扩展。仓库主体许可见 [LICENSE](LICENSE)；`NetworkSim/ns3/laesim-ns3-runner.cc` 声明为 `GPL-2.0-only`，并依赖同为 GPLv2 体系的 ns-3。分发或修改相关代码时应分别遵循对应许可。

## 项目团队

**开发与维护单位：哈尔滨工业大学（深圳）广东省空天网络与智能感知重点实验室**（实验室负责人：张霆廷、梁天豪）

### 项目协调人

平雨奇 · [pingyq@stu.hit.edu.cn](mailto:pingyq@stu.hit.edu.cn)

### 团队成员

| 姓名 | 联系方式 |
| --- | --- |
| 吴俊炜 | [220210419@stu.hit.edu.cn](mailto:220210419@stu.hit.edu.cn) |
| 雷光宇 | [guangyulei@stu.hit.edu.cn](mailto:guangyulei@stu.hit.edu.cn) |
| 李修如 | [m15336370867@163.com](mailto:m15336370867@163.com) |

团队名单与署名原则见 [CONTRIBUTORS.md](CONTRIBUTORS.md)。

## 引用

在论文、报告或其他项目中使用 LAESim 时，请引用所使用的版本，并在方法或实验环境中提供仓库链接。机器可读的引用信息见 [CITATION.cff](CITATION.cff)。平台论文公开后，将在该文件中增加论文的 `preferred-citation`。

## 维护与贡献

问题反馈和功能讨论请优先通过 [GitHub Issues](https://github.com/SANIS-HITSZ/LAESim/issues) 提交，代码与文档改进请通过 Pull Requests 参与；V1.6 的变更范围见 [CHANGELOG.md](CHANGELOG.md)。
