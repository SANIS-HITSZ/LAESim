# 信道地图与无人机导航

V1.6 新增 RadioMapNav 示例：生成城市及基站，使用 Sionna RT 计算离线信道地图，比较几何基线与通信约束路径，再在 LAESim 中执行无人机飞行。此示例是独立的低空通信约束导航应用，不要求串联 ROS、ns-3 或卫星任务。

## 运行入口

源码、原始说明和复现命令见 [RadioMapNav README](https://github.com/SANIS-HITSZ/LAESim/blob/V1.6/Examples/RadioMapNav/README.md)。

- `configs/connectivity_usecase.yaml`：小型可复现城市与导航任务。
- `python -m wireless_city_factory generate`：生成几何、射线追踪地图和 UE 导入包。
- `scripts/plan_connectivity_aware_route.py`：比较几何基线与通信约束路径。
- `scripts/run_laesim_connectivity_mission.py`：经 LAESim Python API 执行路径并记录位姿与无线指标。
- `python -m wireless_city_factory.web_app`：本地三维浏览器视图与任务管理。

实际射线追踪需要兼容的 NVIDIA GPU。UE 导入与飞行需要 Windows、UE 4.27 和已编译的 LAESim 插件；CPU 单元测试不依赖 GPU 或 UE。

## 已验证结果

2026-10-06，在 RTX 3090、Sionna RT 2.1.0 和 UE 4.27 上，400 × 400 米城市、65 米飞行高度、最低 SINR 0 dB 的配置已完成地图生成、离线规划、UE 导入验证和实际 API 飞行。

| 离线对照 | 几何基线 | 通信约束 |
| --- | --- | --- |
| 路径长度 | 411.03 m | 476.53 m |
| 中断比例 | 7.96% | 0% |
| 最低 SINR | -3.23 dB | 0.037 dB |

实际通信约束飞行记录 378 个采样点，无碰撞、无中断采样点，终点误差 0.44 米。详细配置、指纹和验收边界见 [验收记录](https://github.com/SANIS-HITSZ/LAESim/blob/V1.6/Examples/RadioMapNav/VERIFICATION.md)。

## 适用边界

无线指标来自静态离线射线追踪地图，飞行中使用插值查询；本次验收将实际位姿的 XY 投影到 65 米地图层。它不是在线逐帧射线追踪，也不是 ns-3 数据包投递实验。规划器是确定性搜索与运动基元，不是训练得到的神经网络策略。上述结果来自单一固定配置，不能外推为任意城市或门限均能找到可行路径。
