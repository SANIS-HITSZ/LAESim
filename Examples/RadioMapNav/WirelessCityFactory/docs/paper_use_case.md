# 论文 use case：通信连接约束下的低空无人机航迹规划

## 1. 研究问题

在同一程序化城市、任务点和基站部署下，几何上安全且较短的无人机航迹可能穿过无线弱覆盖区域。本 use case 检验：利用 Sionna RT 离线信道地图加入最低 SINR、最低服务小区 RSS 和最大中断比例约束后，规划器能否以可量化的距离代价换取更可靠的通信连接，并在 LAESim/UE 中完成实际航迹执行。

## 2. 公平对比

实验只改变规划模式，其他输入必须完全相同：

- `baseline`：几何基线，只考虑边界、建筑碰撞、动力学、目标距离和路径长度；
- `connectivity`：通信约束方法，在相同几何约束上增加 Sionna RT 网格引导、SINR/RSS 硬门限、无线代价和切换代价。

两条路线共享同一 `scene_fingerprint`、`base_station_fingerprint`、`radio_fingerprint`、任务起终点、飞行高度、速度和动力学上限。网页中的比较表和导出工具均读取同一任务日志中的 `routes.baseline` 与 `routes.connectivity`，不会把不同城市或不同无线地图混在一起。

## 3. 观察指标

| 类别 | 指标 |
| --- | --- |
| 效率 | 路径长度、任务时间、重规划次数 |
| 通信可靠性 | 最低 SINR、平均 SINR、中断比例、最低服务小区 RSS |
| 网络稳定性 | 小区切换次数 |
| 执行安全 | 碰撞采样数、终点误差、是否正常完成 |

论文解释应优先关注最低 SINR 和中断比例。通信约束路线可能为了避开局部弱覆盖而经过较长的中等覆盖走廊，因此“最低 SINR 提升、零中断，但平均 SINR略低”并不矛盾，也不应删去不利指标。

## 4. 闭环流程

```text
程序化城市和基站
  -> Sionna RT 离线信道地图
  -> 同源 baseline/connectivity 规划
  -> 运行前指纹、碰撞和无线约束检查
  -> LAESim/AirSim RPC 执行 connectivity 航迹
  -> 真实位姿逐点查询离线无线地图
  -> JSONL 日志
  -> 论文 use case 证据包
```

## 5. 导出论文证据包

任务必须正常结束，JSONL 最后一行必须是 `type=complete`。然后运行：

```powershell
$ROOT = "C:\Users\lenovo\Desktop\hgs\wireless_city_factory\wireless_city_factory"
$RUN = "$env:LOCALAPPDATA\WirelessCityFactory\outputs\interactive_city-32b142975d79"
$LOG = "$ROOT\runtime\missions\interactive_city-32b142975d79-20261003T141854Z.jsonl"
$OUT = "$ROOT\runtime\paper_usecases\interactive_city-32b142975d79"

& "$ROOT\.venv\Scripts\python.exe" `
  "$ROOT\scripts\export_paper_usecase.py" `
  --run-dir "$RUN" `
  --mission-log "$LOG" `
  --output-dir "$OUT"
```

输出内容：

- `README.md`：根据本次真实结果生成的中文 use case 报告；
- `summary.json`：场景指纹、实验参数、两条路线指标、差值和 LAESim 执行验证；
- `route_metrics.csv`：论文表格数据；
- `trajectory_points.csv`：两条规划航迹，可用于绘图；
- `flight_samples.csv`：LAESim 实际位置、SINR、服务小区 RSS、连接和碰撞状态。

导出前会重新检查城市、基站、无线地图、UE bundle 和最近一次 UE 导入结果的指纹。日志不完整或来源不一致时拒绝生成论文证据，避免把失败运行包装成成功案例。

## 6. 当前证据边界

网页快速预览使用 40 m 网格，适合 use case 演示和功能验收，不足以支撑高精度数值结论。正式论文实验应冻结生产级无线网格与业务门限，至少覆盖三个城市类型、多个城市随机种子和多个起终点任务，并报告均值、标准差、成功率及规划耗时。

本实现是 Neural-Primitive-inspired 确定性专家规划器，没有复现论文的 Npe2eNet、模仿学习训练或模型权重。论文中应将它描述为 LAESim 通信感知应用示例，而不是学习算法复现结果。
