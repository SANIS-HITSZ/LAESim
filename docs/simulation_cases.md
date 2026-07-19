# 仿真案例

本页汇总基于 LAESim 完成的空、地、海多载具协同仿真案例，以及可选的 ns-3 自组织网络实验。

## 统一岛屿仿真场景

当前开发场景以岛屿地形为基础，可在同一 Unreal Engine 世界中部署卫星、无人机、车辆和舰船。下图展示场景整体地形与可通行区域。

<figure class="laesim-media laesim-media--wide">
  <img src="../assets/showcase/laesim-island-scenemap.png" alt="LAESim 岛屿 SceneMap 仿真场景全景" loading="lazy" />
  <figcaption>LAESim 岛屿场景全景</figcaption>
</figure>

<figure class="laesim-media laesim-media--wide">
  <img src="../assets/showcase/laesim-air-space-sea-overview.png" alt="卫星、无人机、车辆与舰船同时出现在 LAESim 场景中" loading="lazy" />
  <figcaption>空、天、地、海多类型载具的统一场景展示</figcaption>
</figure>

## 空地多机协同与 ROS 联动

当前验证场景同时运行 3 架无人机和 3 辆车辆：

| 载具类型 | 实例名称 |
| --- | --- |
| 无人机 | `UAV`、`UAV2`、`UAV3` |
| 车辆 | `Car`、`Car2`、`Car3` |

LAESim 在 Windows 中运行仿真场景，ROS Noetic 在 WSL2 中运行。ROS 节点可通过 AirSim RPC 获取各载具的状态和里程计数据。

<figure class="laesim-media laesim-media--wide">
  <img src="../assets/showcase/laesim-uav-ground-team.png" alt="三架无人机与三辆车辆组成的空地协同编队" loading="lazy" />
  <figcaption>三架无人机与三辆车辆的空地协同场景</figcaption>
</figure>

## 卫星与舰船编队

卫星和舰船作为 LAESim 的扩展载具，可以与无人机、车辆共享场景和任务时间线。当前画面用于验证载具生成、编队展示和基础运动能力。

<div class="laesim-media-grid">
  <figure class="laesim-media">
    <img src="../assets/showcase/laesim-satellite-formation.png" alt="两颗卫星在岛屿场景上空编队运行" loading="lazy" />
    <figcaption>卫星编队场景</figcaption>
  </figure>
  <figure class="laesim-media">
    <img src="../assets/showcase/laesim-ship-formation.png" alt="三艘舰船在海面编队运行" loading="lazy" />
    <figcaption>舰船编队场景</figcaption>
  </figure>
</div>

## 场景视频演示

<video class="laesim-video" controls preload="metadata" playsinline poster="../assets/showcase/laesim-air-space-sea-overview.png">
  <source src="../assets/showcase/laesim-platform-demo.mp4" type="video/mp4" />
  当前浏览器不支持 HTML5 视频播放。
</video>

视频时长约 41 秒，展示当前开发版本的岛屿环境与多类型载具运行效果。

## 接入 ns-3 的通信实验

同一场景可以选择两种网络模式：

- `Backend: none`：不模拟自组织网络，消息直接传递。
- `Backend: ns3`：由 ns-3 模拟节点间的无线链路、路由和数据包传输。

当前已经验证以下情况：

- 两节点在有效通信距离内使用 OLSR 路由，数据包成功送达并输出时延指标。
- 两节点超过最大通信距离时，数据包丢失并输出丢包率。
- ROS 消息在 `UAV` 与 `Car` 之间分别通过直连模式和 ns-3 模式完成往返传输。

环境配置、启动命令和验证方法参见[安装与构建 LAESim 中的 WSL2、ROS 与 ns-3 部分](laesim_build.md#wsl-ros-ns3)。

## 扩展案例

后续案例可以在本页继续增加，并将配置文件、启动脚本、实验参数和结果一并提交到 LAESim 仓库，以便其他贡献者复现。
