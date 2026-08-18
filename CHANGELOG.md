# Changelog

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
