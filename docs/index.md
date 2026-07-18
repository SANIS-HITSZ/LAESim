# LAESim 中文文档

LAESim 是面向空地协同研究的多载具仿真工程。Windows 端负责 UE 4.27 场景、物理和传感器仿真；WSL2 端可运行 ROS Noetic，并按配置选择理想通信或 ns-3 自组织网络。

## 快速入口

- [在 Windows 上构建 AirSim](build_windows.md)
- [多载具配置](multi_vehicle.md)
- [AirSim ROS Wrapper](airsim_ros_pkgs.md)
- [WSL2、ROS 与 ns-3 完整复现流程](laesim_wsl_ros_ns3.md)
- [配置文件参考](settings.md)
- [Python API 参考](api_docs/html/index.html)

## 系统组成

![AirSim 系统架构](images/overview.PNG)

| 组件 | 运行位置 | 职责 |
| --- | --- | --- |
| UE 4.27 与 LAESim | Windows | 空地载具、物理环境、相机和传感器 |
| AirSim RPC | Windows | 向外部控制器提供载具状态和控制接口 |
| ROS Noetic | WSL2 | 多机状态、控制算法和消息接口 |
| ns-3.48 | WSL2 | 可选的 Wi-Fi ad hoc、自组网路由、时延和丢包仿真 |

## 网络模式

`settings.json` 中的 `NetworkSimulation.Backend` 控制通信后端：

| 配置值 | 行为 |
| --- | --- |
| `none` | 保持原有理想通信，消息立即到达 |
| `ns3` | 消息经过 ns-3 Wi-Fi ad hoc 网络，计算时延、吞吐量和丢包 |

当前工程已验证 Windows UE/AirSim 与 WSL2 ROS 的六载具联动，以及 `UAV -> Car` 在 `none` 和 `ns3` 后端中的 ROS 消息往返。详细安装步骤、配置字段、测试结果和当前限制见[网络仿真复现文档](laesim_wsl_ros_ns3.md)。

## 相关项目

LAESim 基于 Microsoft AirSim 扩展，保留其核心 API、载具模型、ROS Wrapper 和原始技术文档。项目源码与问题跟踪位于 [SANIS-HITSZ/LAESim](https://github.com/SANIS-HITSZ/LAESim)。
