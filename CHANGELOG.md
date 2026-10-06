# Changelog

## V1.6 (2026-10-06)

- 将程序化场景、网页配置和 UE 导入提取为根目录 `SceneGen`，信道地图与 LAESim API 桥接提取为 `RadioSim`；导航应用保留在 `Examples/RadioMapNav`，统一从根目录安装 `laesim-tools`。
- 新增 `Examples/RadioMapNav`，解压交付 WirelessCityFactory 源码、配置、文档和原始使用说明。
- 支持程序化城市及基站部署、Sionna RT 离线信道地图、RSS/SINR 查询和通信约束路径规划。
- 提供独立 UE 4.27 场景导入、LAESim Python API 实飞、JSONL 日志与网页同步；刷新页面优先恢复当前任务。
- 完成 RTX 3090 / Sionna RT 2.1.0 的真实地图生成和 UE 飞行验收，结果见 `Examples/RadioMapNav/README.md` 的验收结果。
- 增加 V1.6 核心验证和 CI，继承 V1.5 检查；可移植源码打包排除新示例的虚拟环境、生成地图和外部插件。
- 更新版本、软件引用信息及文档发布分支；不改变原有 ns-3 后端。

## V1.5 (development)

V1.5 以 LAESim V1.4 为基线，保留其空天地海混合载具、SceneMap、Python/ROS 接口、ns-3 runner、项目文档站和 quickstart 实验，并增加：

- 修复 ROS LiDAR 点云 `frame_id` 固定为 `body` 的问题，按 `DataFrame` 动态标记车辆惯性帧或传感器局部帧，并移除 ENU 转换中的重复位姿变换。
- 补充多载具 LiDAR 坐标说明：`VehicleInertialFrame` 以各载具出生点为原点，跨载具融合必须通过 TF 统一到公共世界帧。
- 修正 SceneMap 动态根组件注册后丢失 Actor 位置/旋转的问题，并通过实拍配准将 `NorthUp` 的 UE 显示补偿修正为 +90 度。
- 新增 GeoTIFF 覆盖飞行与稳定下视数据采集 quickstart，输出图像、GPS、物理真值、估计轨迹和采集频率统计。
- 增加稳定云台 settings 模板，并补充相机安装姿态与世界系 `Gimbal` 目标姿态说明。
- TLE/SGP4、CSV、mock 与可选 Orekit 天基任务后端。
- 多卫星、多目标、覆盖窗口、重访时间、最佳星选择和链路切换分析。
- 与 UE 显示坐标解耦的星地链路预算、星间链路和多跳路由。
- NetworkSim 结构化丢包诊断、统一仿真时钟和交付验证脚本。
- V1.4 发布文档、团队信息、引用文件、展示资源和 quickstart 的完整承接。

## V1.4

- 空天地海异构载具、SceneMap、ROS Noetic 与 ns-3 消息级网络仿真。
- 可复现的异构载具和 ns-3 快速入门实验。
- 项目展示页、中文文档站、团队与软件引用信息。

Microsoft AirSim 上游历史记录见 [AirSim changelog](https://github.com/microsoft/AirSim/blob/main/docs/CHANGELOG.md)。
