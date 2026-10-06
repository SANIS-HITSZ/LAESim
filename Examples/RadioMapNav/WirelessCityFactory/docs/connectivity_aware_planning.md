# 通信连接约束轨迹规划与 LAESim 接入

## 1. 这部分实现了什么

本用例把程序化城市、Sionna RT 离线信道地图和 LAESim 无人机串成一条闭环：

```text
城市与基站 -> Sionna RT 离线信道地图 -> 生成候选轨迹
          -> 建筑/边界/动力学检查 -> 沿轨迹查询 RSS 与 SINR
          -> 选出满足通信约束的路线 -> LAESim RPC 执行并记录实测位姿
```

可以对照两种模式：

- `baseline`：只考虑目标距离、路径长度和几何安全，不用无线指标参与选路。
- `connectivity`：先在离线无线网格上搜索满足门限的全局走廊，再生成密集可执行航点，并对整条路线重新查询无线指标验收。

这能用于展示：普通路线较短，但经过弱覆盖区域；通信感知路线稍长，却具有更高的最低/平均 RSS、SINR 和更低的中断比例。网页同步 LAESim 时会同时显示灰色虚线普通路线和青色实线通信约束路线。

## 2. 和论文 Neural-Primitive 的关系

当前实现借用了论文的专家规划结构，而不是复现论文训练好的神经网络：

- 使用五次多项式生成满足起点/终点位置、速度和加速度约束的 minimum-jerk 运动基元。
- 默认每个运动基元持续 `2 s`，并按 `0.05 s` 采样检查。
- 候选轨迹先做动力学、边界和建筑碰撞过滤，再计算代价并选择。
- 滚动执行基元的一部分，然后用新状态重新规划。
- 为避免局部基元看不到远处弱覆盖区，通信用例增加了 RF 网格全局引导层；它使用 A* 搜索并对网格边逐点做 SINR/RSS、边界和碰撞检查。
- 全局路线会做可见性简化并按飞行采样间距重新采样，最终整条路线再次验收。任何超出允许中断比例的结果都会明确失败。

论文原始专家代价主要包含目标代价和长度代价。本工程新增：

```text
Ctotal = wt*Ctarget + wl*Clength + wrf*Cradio + wh*Chandover
```

其中 `Cradio` 表示相对 SINR/RSS 门限的不足，`Chandover` 表示服务小区切换次数。当前代码没有论文中的点云神经网络 Npe2eNet、模仿学习训练或模型权重，因此成果名称应写成“Neural-Primitive-inspired 通信感知专家规划器”。

## 3. 关键文件

- `src/wireless_city_factory/planning.py`：五次运动基元、RF 网格全局引导、安全过滤、无线代价和整条路线验收。
- `src/wireless_city_factory/laesim_bridge.py`：LAESim/AirSim RPC、坐标转换、位姿/碰撞/LiDAR 读取和路线执行。
- `scripts/plan_connectivity_aware_route.py`：不启动 UE 的离线双路线比较。
- `scripts/run_laesim_connectivity_mission.py`：在已运行的 UE/LAESim 中执行通信约束路线。
- `tests/test_planning.py`、`tests/test_laesim_bridge.py`：算法和接口的确定性测试。

## 4. 坐标与数据流

程序化城市和无线地图使用右手、`+Z` 向上、单位为米的 scene 坐标。LAESim/AirSim 使用相对任务起点的 NED 坐标：

```text
north = scene_x - start_x
east  = start_y - scene_y
down  = start_z - scene_z
```

规划和无线查询始终在 scene 坐标完成；只有把路线发给 LAESim 时才转为 NED。LiDAR 保留 LAESim 返回的原始传感器坐标帧，本版本不猜测传感器外参或把点云伪装成世界坐标。

## 5. 离线比较怎么运行

先使用当前代码重新生成一个 `radio.enabled=true` 的 run。不要使用基站字段标准化之前生成的旧目录。

```powershell
$ROOT = "C:\Users\lenovo\Desktop\hgs\wireless_city_factory\wireless_city_factory"
$PYTHON = "$ROOT\.venv-sionna310\Scripts\python.exe"
$env:PYTHONPATH = "$ROOT\src"

& $PYTHON -m wireless_city_factory generate `
  --config "$ROOT\configs\connectivity_usecase.yaml" `
  --project-root $ROOT

$RUN = Get-ChildItem "$ROOT\examples\outputs" -Directory -Filter "connectivity_usecase-*" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

& $PYTHON "$ROOT\scripts\plan_connectivity_aware_route.py" `
  --run-dir $RUN `
  --output "$ROOT\route_comparison.json" `
  --mode both `
  --flight-altitude-m 65 `
  --minimum-sinr-db 0
```

结果文件的 `routes.baseline` 和 `routes.connectivity` 分别含有三维轨迹点、路线长度、中断比例、最低/平均 SINR、最低/平均服务小区 RSS、切换次数和重规划次数。

## 6. 在 LAESim 中执行

先把同一个 run 导入 UE 工程，复制该 run 的 `ue_bundle/settings.json`，打开地图并点击 Play。另行启动网页可视化器，在“无线与无人机”页保持“显示无人机”开启，再打开“同步 LAESim”。网页会等待实时任务，不需要在网页里重新计算一份无线地图。

确认 AirSim RPC 已连接后再运行：

```powershell
$AIRSIM_PYTHON = "$ROOT\.venv-airsim310\Scripts\python.exe"
$env:PYTHONPATH = "$ROOT\src"

& $AIRSIM_PYTHON "$ROOT\scripts\run_laesim_connectivity_mission.py" `
  --run-dir $RUN `
  --output "$ROOT\laesim_connectivity_mission.jsonl" `
  --flight-altitude-m 65 `
  --cruise-speed-mps 5 `
  --minimum-sinr-db 0
```

脚本会依次连接、取得控制权、解锁、起飞到无线地图高度、读取实际起点、规划路线、转换为 NED、执行路线，并周期记录真实位姿、碰撞和无线观测。只有 UE/LAESim 已运行时才执行这条命令。

运行期间应同时看到：

- UE/LAESim 窗口中的无人机真实运动；
- 网页自动切换到同一个 run 的城市和信道热力图；
- 网页无人机跟随 LAESim 实际位姿，而不是播放独立动画；
- 网页同时显示普通最短路线、通信约束路线，以及距离、最低/平均 SINR、中断比例和切换次数对比；
- 轨迹进度、RSS、SINR、服务小区和连接状态约每 `250 ms` 更新一次。

规划终点采用 `3 m` 默认到达容差。若最后一小段因为边界或动力学约束无法安全精确贴到目标点，但当前位置已经进入到达圈，任务会成功，并在 `final_error_m` 中保留实际误差，不再把合法到达误判为失败。

## 7. 参数怎么理解

- `--minimum-sinr-db`：硬连接门限，演示脚本默认 `0 dB`。整条通信路线的中断比例超过允许值就会被拒绝。
- `--minimum-rss-dbm`：可选的服务小区宽带接收功率门限。这里是带宽内 RSS，不应写成严格的 3GPP RSRP。
- `--maximum-outage-fraction`：一条候选基元允许中断的采样比例，默认 `0`。
- `--radio-weight`：信号不足惩罚的权重，只影响满足硬约束后的偏好。
- `--handover-weight`：服务小区切换惩罚权重。
- `--cruise-speed-mps`：规划速度和 LAESim 跟踪速度。
- `--maximum-speed-mps`、`--maximum-acceleration-mps2`：候选轨迹的峰值动力学上限；默认值与 `2 s`、`8 m/s` 的默认运动基元相容，正式实验应按机型冻结。
- `--flight-altitude-m`：规划、无线查询和飞行使用的统一高度，必须落在 radio map 的高度范围内。

`-125 dBm` 是检测门限，只决定一个小区是否进入可检测集合，不是规划质量门限。正式实验应根据目标设备、业务和论文协议冻结 RSS/SINR 门限。

## 8. 怎么验收

1. 运行测试，确认多项式、碰撞、无线约束、坐标转换和 RPC 参数测试通过。
2. 用同一个 run 输出 baseline 与 connectivity 两条路线。
3. 比较路线长度、中断比例、最低/平均 RSS 与 SINR、切换次数。
4. 在 LAESim 中执行 connectivity 路线，画面应看到无人机移动。
5. 检查 JSONL 中真实位姿随时间变化、无碰撞、最终误差在容差内，且每个位置都有无线观测。

## 9. 当前限制

- 使用预计算 Sionna RT 地图查表，飞行时不重新射线追踪；静态城市和基站下这样更快、可复现。
- 普通路线使用局部运动基元专家；通信路线增加 RF 网格 A* 全局引导。它是确定性专家规划示例，不是论文训练后的 Npe2eNet。
- 碰撞模型使用城市建筑 AABB；LAESim 的动态障碍和原生碰撞仍作为执行期第二层检查。
- 地形、风场、动态遮挡、链路调度、真实设备标定和训练网络尚未纳入。
- 未经 UE/LAESim 实际运行验证时，只能声称离线规划和模拟 RPC 测试通过，不能声称真实飞行闭环已经完成。

## 10. 论文 use case 导出

完成一次 LAESim 任务后，可用 `scripts/export_paper_usecase.py` 将同源双路线规划结果和真实飞行日志导出为论文证据包。导出器要求日志以 `type=complete` 结束，并校验城市、基站、Sionna RT、UE bundle 和 UE 导入结果的指纹一致性。详细实验协议、命令和表述边界见 `docs/paper_use_case.md`。
