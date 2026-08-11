# 天基任务桥接说明

本文说明如何在不依赖商业授权软件的情况下，把卫星轨道、星下点、可见性和任务几何量接入 LAESim。设计目标是让 Python 后端负责天基任务计算，LAESim/UE 负责演示性显示、相机和传感器挂载。

## 1. 总体架构

```text
TLE / CSV / Mock
  -> Multi_use/space_mission_bridge.py
  -> LAESim PythonClient / AirSim RPC
  -> simSetVehiclePose
  -> UE 里的 SimpleSatellite 模型
```

第一阶段覆盖这些功能面：

- TLE/SGP4 轨道传播：通过 `sgp4` 包读取 TLE 并计算卫星位置。
- CSV/mock 数据源：没有额外依赖时也能做冒烟测试和演示。
- 坐标转换：经纬高、ECEF、局部 NED、缩放后的 LAESim 显示坐标。
- 任务可见性：对固定目标输出方位角、仰角、距离和是否满足最小仰角阈值。
- ROS 输出：发布卫星真值和每个目标的 Access 状态。

第二阶段增加任务分析脚本，用于多颗卫星、多类目标、覆盖窗口、重访时间、可见时间段报告和 ns-3 联动接口文件。第三阶段继续补充星座批量载入、区域网格覆盖、访问约束、GeoJSON 导出、Orekit 升起/落下事件检测、基础传感器视场和星地链路预算，使输出形态更接近专业任务分析软件。它仍不是完整的航天任务分析平台；轨道机动优化、高保真姿态动力学、专业雷达和 EOIR 属于可选后续能力。

## 2. 坐标与尺度

真实轨道采用地球尺度，LEO 高度通常是数百公里。UE/AirSim 更适合局部米级场景，因此桥接脚本区分两套坐标：

- 真实计算坐标：经纬高、ECEF、局部 NED，保持真实米制。
- UE 显示坐标：按比例缩放后的 LAESim NED，只用于视觉显示。

默认缩放：

```text
LAESim_X = Real_North * 0.001
LAESim_Y = Real_East  * 0.001
LAESim_Z = -max(80, (Altitude - ReferenceAltitude) * 0.001)
```

例如 500 km 高度默认显示成约 500 m。真实距离、覆盖和链路可见性应以桥接脚本输出为准，不建议用 UE 中模型之间的几何距离代表真实星地距离。

## 3. 快速验证

先复制模板：

```powershell
cd <LAESim 源码目录>
Copy-Item .\how_to_use_settings\settings_space_mission_bridge.json "$env:USERPROFILE\Documents\AirSim\settings.json"
```

不依赖第三方包的 CSV 回放：

```powershell
conda activate <AirSim Python环境名>
python .\Multi_use\space_mission_bridge.py --provider csv --csv .\Multi_use\space_mission_sample.csv --vehicle Satellite --rate 1
```

不连接 UE，只检查计算链路：

```powershell
python .\Multi_use\space_mission_bridge.py --provider mock --vehicle Satellite --target Island:22.591164:113.975317:0 --rate 2 --duration 5 --no-airsim --print-every 1
```

## 4. TLE/SGP4

TLE 模式需要安装 `sgp4` 包：

```powershell
conda activate <AirSim Python环境名>
pip install sgp4
```

使用示例 TLE：

```powershell
python .\Multi_use\space_mission_bridge.py --provider tle --tle .\Multi_use\space_mission_sample.tle --vehicle Satellite --rate 2
```

指定目标并输出可见性：

```powershell
python .\Multi_use\space_mission_bridge.py --provider tle --tle .\Multi_use\space_mission_sample.tle --target Island:22.591164:113.975317:0:ground --rate 2 --print-every 1
```

注意：当前 TLE 模式使用 SGP4 输出 TEME 坐标，并用 GMST 做 MVP 级地固转换，适合演示和工程验证；如果后续需要高精度地球定向参数、摄动建模、事件检测和覆盖统计，建议升级为 Orekit 后端。

## 5. 常用参数

- `--provider tle/csv/mock`：选择轨道来源。
- `--tle`：TLE 文件路径。
- `--satellite-name` / `--satellite-index`：从多星 TLE 文件中选择卫星。
- `--display-mode scaled-ned`：默认，水平和高度都按比例缩放。
- `--display-mode fixed-overhead`：卫星固定在场景上方，适合只想表现“天上有卫星”。
- `--display-mode subpoint-only`：水平显示星下点运动，高度固定。
- `--horizontal-scale`：真实水平 NED 到 UE 显示 NED 的比例。
- `--vertical-scale`：真实高度到 UE 显示高度的比例。
- `--min-display-altitude`：防止卫星显示太低。
- `--yaw-mode course`：按星下点运动方向给模型偏航。
- `--clock-speed`：任务时间推进倍率。
- `--target NAME:LAT:LON[:ALT[:KIND]]`：增加一个任务目标，输出可见性、方位、仰角、距离。
- `--min-elevation-deg`：Access 的最小仰角阈值。
- `--mission-report-jsonl`：把每帧星历和 Access 状态写成 JSONL。

## 6. ROS 接口

新增 ROS 消息：

```text
airsim_ros_pkgs/SpaceSatelliteState
airsim_ros_pkgs/SpaceAccessState
```

话题：

```text
/space/<vehicle>/space_satellite_state
/space/<vehicle>/state
/space/<vehicle>/access/<target>
```

运行 ROS 版 CSV 回放：

```bash
cd "$HOME/LAESim/ros"
source devel/setup.bash
python3 src/example/space_mission_bridge_ros.py --provider csv --csv ../Multi_use/space_mission_sample.csv --vehicle Satellite
```

如果要同时驱动 UE 里的卫星模型：

```bash
python3 src/example/space_mission_bridge_ros.py --provider csv --csv ../Multi_use/space_mission_sample.csv --vehicle Satellite --drive-laesim --host <Windows主机IP>
```

发布目标 Access 状态：

```bash
python3 src/example/space_mission_bridge_ros.py --provider mock --vehicle Satellite --target Island:22.591164:113.975317:0
```

将 LAESim 中正在运动的载具作为动态目标：

```bash
python3 src/example/space_mission_bridge_ros.py \
  --provider tle \
  --tle ../Multi_use/space_mission_sample.tle \
  --vehicle Satellite \
  --target-vehicle Car:ground \
  --target-vehicle Boat:sea \
  --target-vehicle UAV:air
```

`--target-vehicle VEHICLE[:KIND]` 会订阅 `/airsim_node/<vehicle>/global_gps`。这里使用 `global_gps`，而不是直接使用 `odom_local_ned`：AirSim 多载具的 local odometry 以各自 starting point 为原点，直接比较会遗漏 settings 初始偏移；`global_gps` 已包含统一地理原点和车辆初始位置。动态 GPS 超过 `--dynamic-target-max-age` 未更新时，access 会变为 `valid=false`，避免继续使用陈旧位置。

完整多星模板位于 `how_to_use_settings/settings_space_dynamic_targets.json`，其中配置了 `UAV`、`UAV2`、`Car`、`Boat`、`Satellite`、`Satellite2`、`Satellite3`，以及三颗卫星到四类目标的 12 条 `SpaceAccessPolicy` 规则。

### 6.1 多卫星实时运行与切换

`space_constellation_bridge_ros.py` 同时传播多份 TLE，并把每颗卫星映射到独立的 `SimpleSatellite` 载具。原来的 `space_mission_bridge_ros.py` 保持单星入口，不受影响。

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

默认下载并校验三颗当前 TLE：`Satellite:25544`、`Satellite2:25338`、`Satellite3:39084`。可按任务替换目录号和目标：

```bash
SATELLITES="Satellite:25544,Satellite2:48274,Satellite3:39084" \
TARGET_VEHICLES="UAV:air,Car:ground,Boat:sea" CLOCK_SPEED=120 \
  bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

每颗卫星继续发布原有接口：

```text
/space/<SatelliteN>/state
/space/<SatelliteN>/space_satellite_state
/space/<SatelliteN>/access/<target>
```

多星桥额外发布：

```text
/space/selection/<target>
/space/constellation/state
```

`/space/selection/<target>` 是 `std_msgs/String` JSON。候选卫星按仰角从高到低排序，仰角相同时选择真实斜距更短者；`--selection-hysteresis-deg` 和 `--selection-min-hold-s` 用于抑制频繁切换。消息包含当前/上一颗卫星、候选列表、切换次数、捕获次数和本次中断时间。

运行摘要写入 `.runtime/constellation_demo/space_constellation_summary.json`，包括：

- `handover_count`：目标业务链路在不同卫星之间的切换次数。
- `outage_count`：没有可用卫星的覆盖空窗次数。
- `last_interruption_s`：最近一次重新捕获前的中断时间。
- `mean_revisit_s` / `max_revisit_s`：已完成覆盖空窗的平均/最大持续时间。
- `selection_events`：每次捕获、切换或进入空窗时的场景时间和卫星名称。

在多星桥与 NetworkSim 都运行时，可让测试程序始终从当前最佳卫星向目标发包：

```bash
python3 NetworkSim/tests/ros_constellation_handover_test.py \
  --target Car --duration 60
```

加 `--require-handover` 后，测试期间至少发生一次卫星切换才算通过。场景时间倍率较高时，60 秒墙钟时间可能已覆盖数小时轨道过程。

### 6.2 星间链路与多跳中继

多星一键脚本默认传入 `--publish-isl`。星座桥根据每颗卫星的真实地理位置计算星间距离，并发布三组双向 ISL access：

```text
/space/Satellite/access/Satellite2
/space/Satellite/access/Satellite3
/space/Satellite2/access/Satellite3
```

默认最大星间作用距离为 5000 km，可通过环境变量修改：

```bash
MAX_ISL_RANGE_M=4000000 PUBLISH_ISL=1 \
  bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

当前 ISL 判据只包含有效几何和最大作用距离，不加入日照、阴影等额外条件。逐帧 `isl_links` 记录会写入 `space_constellation_runtime.jsonl`。

应用在 `/network_sim/tx` 数据包中增加 `route`，即可显式指定星间中继：

```json
{
  "packet_id": "relay-0001",
  "src": "Satellite",
  "dst": "Car",
  "route": ["Satellite", "Satellite2", "Car"],
  "size_bytes": 1024,
  "payload": "mission-data"
}
```

NetworkSim 会逐跳检查 `SpaceAccessPolicy`。任一跳不可见、状态缺失或过期时，`/network_sim/drop` 会增加 `route` 和 `failed_hop`；所有跳可用时，ns-3 runner 对各有向链路分别排队并按存储转发顺序调度。成功结果包含：

```text
link_type=satellite_route
route_hop_count
route_nodes
true_range_m                 # 各跳真实距离之和
propagation_delay_ns         # 各跳传播时延之和
serialization_delay_ns       # 各跳串行化时延之和
packet_error_rate            # 各跳联合包错误率
```

自动验证：

```bash
bash NetworkSim/tests/ros_constellation_integration_test.sh
```

当前验收用例 `Satellite -> Satellite2 -> Car` 为两跳、总斜距 1500 km，返回传播时延约 5.003 ms、串行化时延 8.192 ms、总 ns-3 时延约 13.195 ms。

## 7. 任务分析

`Multi_use/space_mission_analyzer.py` 用于离线统计多星多目标任务窗口。输入是 mission JSON：

```powershell
python .\Multi_use\space_mission_analyzer.py --mission .\Multi_use\space_mission.example.json --out .\Multi_use\space_mission_report --print-summary
```

输出文件：

```text
space_mission_report_summary.json
space_mission_report_windows.csv
space_mission_report_samples.csv
space_mission_report_network_links.json
space_mission_report_geojson.json
space_mission_report_area_coverage.csv
```

含义：

- `summary.json`：每个目标点和目标组的窗口数量、累计可见时长、覆盖比例、空间覆盖率和重访时间。
- `windows.csv`：每颗卫星对每个目标的可见开始、结束、持续时间、最大仰角、最近距离和窗口计算方法。
- `samples.csv`：每个时间步的仰角、方位角、距离和 access 状态。
- `network_links.json`：把可见窗口转换成通信链路启停时间，供后续与 `NetworkSim` / ns-3 联动。
- `geojson.json`：导出卫星末帧位置、目标点、区域网格点和窗口要素，便于在 GIS/Web 地图工具中查看。
- `area_coverage.csv`：按场景时间、卫星和区域统计当前覆盖点数、瞬时覆盖率及区域阈值是否满足。

mission JSON 支持点目标、区域网格目标和访问约束：

```json
{
  "analysis": {
    "start_time": "2026-07-23T00:00:00Z",
    "duration_s": 300,
    "step_s": 30,
    "min_elevation_deg": 5
  },
  "satellites": [
    {
      "name": "Satellite",
      "provider": "csv",
      "csv": "space_mission_sample.csv"
    }
  ],
  "targets": [
    {
      "name": "Island",
      "kind": "ground",
      "latitude_deg": 22.591164,
      "longitude_deg": 113.975317,
      "altitude_m": 0,
      "min_elevation_deg": 5
    },
    {
      "name": "SeaArea",
      "kind": "sea",
      "type": "area_grid",
      "center_latitude_deg": 22.50,
      "center_longitude_deg": 114.05,
      "width_km": 8,
      "height_km": 6,
      "spacing_km": 2
    }
  ]
}
```

星座批量载入可以使用 `constellations`：

```json
{
  "constellations": [
    {
      "name_prefix": "Sat",
      "provider": "tle",
      "tle": "my_constellation.tle",
      "count": 8
    }
  ]
}
```

安装 Orekit 后，可以使用事件检测定位窗口边界，而不是把边界限制在固定 `step_s` 采样点上。可直接运行已提供的 24 小时示例：

```powershell
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python .\Multi_use\space_mission_analyzer.py --mission .\Multi_use\space_mission_orekit.example.json --out .\Multi_use\space_mission_orekit_report --print-summary
```

相关 mission 配置：

```json
{
  "analysis": {
    "access_window_method": "orekit-events",
    "event_max_check_s": 60,
    "event_threshold_s": 0.1
  },
  "orekit_data": "../../orekit-data.zip",
  "satellites": [
    {
      "name": "Satellite",
      "provider": "orekit-tle",
      "tle": "space_mission_sample.tle"
    }
  ]
}
```

- `access_window_method=auto`：`orekit-tle` 使用 Orekit 事件检测，其他 provider 使用步长采样；这是默认行为。
- `access_window_method=sampled`：所有窗口都按 `step_s` 采样生成。
- `access_window_method=orekit-events`：已配置 Orekit 的卫星使用事件检测，其他 provider 仍使用采样。
- `event_max_check_s`：Orekit 搜索事件根的最大检查间隔。
- `event_threshold_s`：窗口边界收敛阈值，单位为秒。

当目标同时配置 `max_range_m` 时，当前版本会退回采样法处理“仰角 + 最大距离”的组合约束，并在 summary 的 `orekit_event_fallbacks` 中说明原因。`windows.csv` 的 `method` 列可用于确认每个窗口实际采用 `sampled` 还是 `orekit-events`。

### 7.1 传感器、侧摆、驻留与区域约束

专用示例：

```powershell
python .\Multi_use\space_mission_analyzer.py `
  --mission .\Multi_use\space_mission_constraints.example.json `
  --out .\Multi_use\space_mission_constraints_report `
  --print-summary
```

每个点目标或 `area_grid` 可配置：

```json
{
  "min_elevation_deg": 5,
  "max_range_m": 1800000,
  "sensor_pointing_mode": "target-track",
  "sensor_half_angle_deg": 2,
  "side_look_angle_deg": 0,
  "max_off_nadir_deg": 35,
  "min_dwell_s": 30,
  "min_area_coverage_fraction": 0.6
}
```

- `sensor_pointing_mode=none`：兼容默认行为，不施加传感器视场约束。
- `nadir`：传感器波束中心指向星下点，目标离轴角等于目标视线的离天底角。
- `side-look`：波束中心按 `side_look_angle_deg` 侧摆，当前使用“离天底角差”作为圆锥视场近似。
- `target-track`：波束中心跟踪目标，传感器离轴角为 0，但目标真实离天底角仍必须小于 `max_off_nadir_deg`。
- `sensor_half_angle_deg`：传感器圆锥半视场角。
- `max_off_nadir_deg`：平台或载荷允许的最大侧摆能力。
- `min_dwell_s`：几何窗口短于该值时，不进入最终窗口和 network link 报告，并记录到 `dwell_rejections`。
- `min_area_coverage_fraction`：区域网格在一个采样时刻必须达到的覆盖率阈值；逐时结果见 `area_coverage.csv`。

`samples.csv` 新增 `off_nadir_deg`、`sensor_off_axis_deg` 和 `constraint_reason`，可判断样本是因仰角、距离、侧摆还是视场被拒绝。带最大距离、侧摆或传感器视场的 Orekit 任务会退回组合约束采样；最小驻留时间在窗口生成后统一过滤。

实时单星/多星桥也支持相同的全局参数：

```bash
--max-range-m 1800000 \
--max-off-nadir-deg 35 \
--sensor-pointing-mode target-track \
--sensor-half-angle-deg 2
```

实时 CLI 参数对该进程的全部目标生效；需要每个目标使用不同约束时，使用 mission JSON 做离线任务分析。当前约束集不加入日照、阴影或太阳高度条件。

### 7.2 统一场景时钟、暂停与单步

需要确定性复现任务时，可由 `space_sim_clock.py` 统一发布 `/clock`。天基实时桥通过 `--clock-source ros` 使用该时间，NetworkSim 在 `UnifiedClock.Enabled=true` 时也只按 `/clock` 的正向增量推进 ns-3。默认配置保持 `Enabled=false`，原有墙钟驱动方式不受影响。

在 WSL 中启动：

```bash
cd "${HOME}/LAESim"
source /opt/ros/noetic/setup.bash
source ros/devel/setup.bash

python3 ros/src/example/space_sim_clock.py \
  --start-time 2026-07-23T00:00:00Z --rate 60
```

天基桥使用同一时间轴时增加：

```bash
--clock-source ros --clock-topic /clock
```

另开终端发送控制命令：

```bash
python3 ros/src/example/space_clock_control.py pause
python3 ros/src/example/space_clock_control.py step --seconds 10
python3 ros/src/example/space_clock_control.py set_rate --rate 120
python3 ros/src/example/space_clock_control.py resume
python3 ros/src/example/space_clock_control.py reset
```

相关话题：

```text
/clock                 rosgraph_msgs/Clock，统一场景时刻
/space_clock/control   std_msgs/String，JSON 控制命令
/space_clock/status    std_msgs/String，暂停、倍率和当前时刻
```

边界说明：

- `/clock` 统一的是天基任务计算和 ns-3 离散事件时间，不会自动暂停或单步 UE4 物理世界。
- 不要为了这个功能给 AirSim ROS wrapper 全局设置 `/use_sim_time=true`；两个桥接器会显式订阅 `/clock`。
- 严格按场景时刻查询应使用 `tle` 或 `orekit-tle` provider。CSV provider 当前按行顺序回放，不适合验证任意时刻跳转。
- ns-3 时间不能倒退。执行 `reset` 或 `set_time` 回到更早时刻后，应重启 NetworkSim bridge，才能获得可重复的网络事件时间轴。

自动验收：

```bash
bash NetworkSim/tests/ros_unified_clock_integration_test.sh
```

该测试使用独立 ROS master，不需要启动 UE。当前固定验收结果为：暂停期间状态不前进，单步 2 秒后 TLE 状态精确从 `00:00:00` 变为 `00:00:02`，同一时钟还会释放等待中的 ns-3 数据包。

## 8. 与 NetworkSim/ns-3 实时联动

离线的 `network_links.json` 适合任务排程；实时演示使用 ROS access 话题控制 NetworkSim。数据流如下：

```text
space_mission_bridge_ros.py
  -> /space/Satellite/access/Car
  -> SpaceAccessPolicy
  -> access=true  时将 /network_sim/tx 交给 none/ns3 后端
  -> access=false 时发布 /network_sim/drop
```

在 `settings.json` 的 `NetworkSimulation` 中配置：

```json
"SpaceAccessPolicy": {
  "Enabled": true,
  "FailMode": "closed",
  "MaxStateAgeSeconds": 2.0,
  "Rules": [
    {
      "Source": "Satellite",
      "Destination": "Car",
      "AccessTopic": "/space/Satellite/access/Car",
      "Bidirectional": true
    }
  ]
}
```

`Source` 和 `Destination` 必须都是 `settings.json/Vehicles` 中的载具名。`Bidirectional=true` 表示同一个 access 状态同时控制上下行。`FailMode=closed` 时，状态尚未收到、无效或超过 `MaxStateAgeSeconds` 都会阻断；调试阶段可以改为 `open`。

首次启用前，在 WSL 的 `ros` 工作空间重新运行 `catkin_make`，并用 `rosmsg show airsim_ros_pkgs/SpaceAccessState` 确认自定义消息已经生成。若 WSL 使用 `/home/<user>/LAESim` 副本，应先把 Windows 工程中的当前 `ros/src` 和 `NetworkSim` 同步过去。

先启动 ROS 天基桥接并确保发布目标名与目标载具名一致：

```bash
cd "${HOME}/LAESim"
source /opt/ros/noetic/setup.bash
source ros/devel/setup.bash
python3 ros/src/example/space_mission_bridge_ros.py \
  --provider mock \
  --vehicle Satellite \
  --target Car:22.591164:113.975317:0:ground
```

这个 mock 配置的卫星位于目标上空，默认 `--min-elevation-deg 5` 时应可见。再启动 NetworkSim bridge 并验证投递：

```bash
bash "${HOME}/LAESim/NetworkSim/scripts/run_ros_network_bridge.sh"
python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source Satellite --destination Car
```

要稳定验证阻断，停止并重新启动天基桥接，把门限改为 `89.9` 度：

```bash
python3 ros/src/example/space_mission_bridge_ros.py \
  --provider mock \
  --vehicle Satellite \
  --target Car:22.591164:113.975317:0:ground \
  --min-elevation-deg 89.9

python3 "${HOME}/LAESim/NetworkSim/tests/ros_roundtrip_test.py" --source Satellite --destination Car --expect-drop
```

`--expect-drop` 会监听 `/network_sim/drop`，输出 `drop_stage` 和 `drop_reason`。天基策略阻断使用 `drop_stage=space_access_policy` 并附带仰角和真实星地距离；通过策略后又在网络内部丢失的包使用 `drop_stage=ns3`，并附带网络拓扑距离、路由协议和 ns-3 仿真时间。两类距离属于不同坐标与模型，不能直接混用。

### 真实 TLE 一键演示

在 UE 已进入 Play、AirSim ROS wrapper 正常发布配置中的载具话题后，可以用一条命令启动单星真实 TLE、动态目标、UE 卫星显示和 ns-3 门控：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_space_network_demo.sh
```

首次使用需要安装轻量 Python 依赖：

```bash
python3 -m pip install --user sgp4 msgpack-rpc-python
```

脚本默认行为如下：

- 从 CelesTrak 刷新 NORAD `25544` 的当前 ISS TLE，并校验两行数据的校验和。
- 检查 TLE 历元与场景时间；超过 14 天时拒绝正式演示，避免把陈旧 TLE 当作实时星历。
- 自动搜索参考点未来 48 小时内的下一次可见窗口，并从窗口前 300 秒开始。
- 默认使用 60 倍场景时间，使过境和链路切换能在短时间内演示。
- 从 `/airsim_node/UAV/UAV2/Car/Boat/global_gps` 读取动态目标位置。
- 通过卫星 RPC `41491` 驱动 UE 中的 `Satellite`，并持续发布四条 access 话题。
- 检测并复用已经运行的 NetworkSim bridge；没有运行时会自动启动。

常用覆盖参数通过环境变量设置：

```bash
CLOCK_SPEED=20 ACCESS_LEAD_S=300 DURATION=40 \
  bash NetworkSim/scripts/run_tle_space_network_demo.sh

CATALOG_NUMBER=48274 TARGET_VEHICLES="UAV:air,Car:ground,Boat:sea" \
  bash NetworkSim/scripts/run_tle_space_network_demo.sh
```

输出保存在：

```text
${HOME}/LAESim/.runtime/tle_demo/current.tle
${HOME}/LAESim/.runtime/tle_demo/current.tle.json
${HOME}/LAESim/.runtime/tle_demo/space_tle_bridge.log
${HOME}/LAESim/.runtime/tle_demo/space_tle_runtime.jsonl
${HOME}/LAESim/.runtime/tle_demo/space_tle_summary.json
```

`space_tle_summary.json` 按目标记录有效样本数、可见样本比例、窗口起止、总可见时长、最大仰角和最小真实斜距。单独刷新 TLE 可运行：

```bash
python3 Multi_use/update_tle.py \
  --catalog-number 25544 \
  --output "${HOME}/LAESim/.runtime/current_iss.tle"
```

要自动验证一次完整的 DOWN/UP 转换，在 TLE 演示运行期间执行：

```bash
source /opt/ros/noetic/setup.bash
source "${HOME}/LAESim/ros/devel/setup.bash"
python3 NetworkSim/tests/ros_tle_network_transition_test.py \
  --source Satellite --destination Car --timeout 120
```

测试必须同时得到：不可见阶段 `drop_stage=space_access_policy`，以及可见阶段带非零 `latency_ns` 的 ns-3 投递结果。

真实计算坐标和演示坐标必须分开理解：

- TLE 经纬高、仰角和 `range_m` 使用真实地球尺度。
- `global-track` 把全球地面轨迹正交压缩到 UE 场景的有限圆盘内，只用于显示。
- `SatelliteLinkModel.Enabled=false` 时，NetworkSim 仍会把所有节点当作普通 Wi-Fi 节点，此时星地包会受到 UE `odom_local_ned` 演示距离影响。
- `SatelliteLinkModel.Enabled=true` 时，命中 `SpaceAccessPolicy` 的星地包使用 access 中的真实斜距、自由空间损耗、传播时延、天线增益、SNR、带宽和误码率；UE 显示坐标不参与链路预算。
- 一键脚本默认 UE 显示半径为 80 m、显示高度为 300 m，可以通过 `DISPLAY_RADIUS` 和 `DISPLAY_ALTITUDE` 修改而不改变星地通信结果。

### 多星可视化与交付脚本

交付演示优先使用完整启动器。前提是 UE 已进入 Play、AirSim ROS wrapper 已运行，且 `/airsim_node/Satellite/odom_local_ned` 的时间戳确实在推进：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/start_space_demo.sh
```

启动器先运行 `ros_ue_clock_progress_test.py`。如果编辑器只是打开、Play 被暂停，或者 ROS 只在重复旧时间戳，它会直接停止并提示修正，不会留下一个“话题齐全但模型不动”的假正常状态。通过检查后，它会启动真实 TLE 多星桥、NetworkSim 和 UE 可视化器。

可视化器 `space_mission_visualizer_ros.py` 显示：

- 每颗卫星的显示位置、星下点和卫星到星下点的垂线。
- 按卫星高度和最低仰角估算的覆盖圈。
- 当前最佳星到目标载具的绿色 `UP` 链路线。
- 没有可用卫星时目标处的红色 `DOWN` 标签。

多星任务桥默认以 2 Hz 计算和发布 ROS 状态，但一键演示通过 `POSE_RATE_HZ=0.5` 把 UE 卫星模型更新限制为 0.5 Hz；可视化器也默认以 0.5 Hz 刷新并批量提交绘图。目标位置直接订阅 `/airsim_node/<target>/odom_local_ned`，避免对每个目标重复调用 pose RPC。可通过 `RATE_HZ`、`POSE_RATE_HZ` 和 `VISUAL_RATE_HZ` 分别修改，但提高后两者会直接增加 UE RPC 负载，交付演示建议保留默认值。

可视化器会监视 `/space/constellation/state`：连续 10 秒没有上游状态，或者连续 3 次 UE RPC 失败时自动退出，避免 UE 已暂停、退出或卡死后仍无限重试。可通过 `CONSTELLATION_TIMEOUT` 和 `VISUAL_MAX_ERRORS` 调整。

覆盖圈和链路线是 UE 演示标记；真实 access、斜距和链路预算仍由 TLE/任务桥与 ns-3 计算。标记不会参与可见性判定。

运行状态、停止和报告导出：

```bash
bash NetworkSim/scripts/space_demo_status.sh
bash NetworkSim/scripts/stop_space_demo.sh
python3 NetworkSim/python/export_space_demo_report.py \
  --runtime-dir "${HOME}/LAESim/.runtime/constellation_demo"
```

默认停止脚本保留共享的 AirSim ROS wrapper 和 NetworkSim；增加 `--include-network` 才会一并停止 NetworkSim。导出目录包含：

```text
report/space_demo_report.md
report/target_statistics.csv
report/selection_events.csv
report/isl_statistics.csv
```

每轮启动会清除上一轮的 summary，只有本轮桥接器正常退出后才重新写入；因此导出器不会把旧 summary 与新 JSONL 混合。卫星 RPC 默认 5 秒超时，UE 停止响应时桥会退出并尽量写出截至故障前的报告。可通过 `RPC_TIMEOUT` 调整，但不建议恢复到 AirSim 客户端原本的 3600 秒长等待。

需要单独启动可视化器时运行：

```bash
bash NetworkSim/scripts/run_space_visualization.sh
```

常用显示覆盖变量为 `SURFACE_Z`、`GLOBAL_TRACK_RADIUS`、`MIN_ELEVATION_DEG`、`SATELLITES` 和 `TARGETS`。其中 `GLOBAL_TRACK_RADIUS` 与多星桥的 `DISPLAY_RADIUS` 应保持一致。

## 9. 专业后端接口

第三阶段之后，LAESim 增加了面向专业任务分析工具的可选接口。它们不替代当前默认 `sgp4/csv/mock` 链路，也不会成为 LAESim 编译或运行的强制依赖。

建议把环境分成两类：

- `airsim_agent`：用于连接 UE/LAESim、运行 AirSim PythonClient、驱动 `SimpleSatellite`。这个环境只建议安装轻量依赖，例如 `sgp4`。
- `laesim_space`：用于专业天基任务分析后端，例如 Orekit 和 Basilisk。它可以离线生成星历、姿态或任务窗口，再把结果导出给 `airsim_agent` 使用。

不要把 Basilisk 直接装进 `airsim_agent`。Basilisk 的可视化依赖会拉入新版 `tornado`，而 AirSim RPC 依赖的 `msgpack-rpc-python` 对 `tornado` 版本比较敏感，放在同一个环境里容易出现隐蔽冲突。

先检查当前环境：

```powershell
python .\Multi_use\space_backend_probe.py
```

推荐的基础验证：

```powershell
conda activate airsim_agent
python .\Multi_use\space_mission_bridge.py --provider tle --tle .\Multi_use\space_mission_sample.tle --no-airsim --duration 2 --rate 1 --print-every 1
```

如果能输出 `src=tle-sgp4`、经纬高和 `laesim=(...)`，说明不依赖专业后端的第一版链路已经可用。

### Orekit

Orekit 用于更高精度的轨道传播、坐标系、时间系统和事件检测。当前接口提供 `orekit-tle` provider：

推荐单独创建环境：

```powershell
conda create -n laesim_space -c conda-forge python=3.10 orekit sgp4 --yes --solver=libmamba
conda activate laesim_space
```

如果 `--solver=libmamba` 不可用，可以去掉这个参数：

```powershell
conda create -n laesim_space -c conda-forge python=3.10 orekit sgp4 --yes
```

验证 Orekit 是否安装成功：

```powershell
conda activate laesim_space
python -c "import orekit; orekit.initVM(); print('orekit ok')"
python .\Multi_use\space_backend_probe.py
```

Orekit 还需要 `orekit-data` 才能进行严肃的时间系统和坐标系计算。最省事的做法是在希望保存数据的目录里调用 Orekit 的下载 helper：

```powershell
Set-Location <任务数据目录>
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python -c "import orekit; orekit.initVM(); from orekit.pyhelpers import download_orekit_data_curdir; download_orekit_data_curdir()"
```

该命令会在当前目录生成 `orekit-data.zip`。桥接器接受这个 zip 文件本身，也接受一个内部包含 `orekit-data.zip` 的目录。建议保留 zip，不需要解压：

```text
<任务数据目录>\orekit-data.zip
```

运行 `orekit-tle` provider 时可以指定解压目录：

```powershell
conda activate laesim_space
python .\Multi_use\space_mission_bridge.py --provider orekit-tle --tle .\Multi_use\space_mission_sample.tle --orekit-data <任务数据目录>\orekit-data.zip --no-airsim --duration 5 --rate 1 --print-every 1
```

如果当前工作目录下已经有 `orekit-data.zip`，也可以不传 `--orekit-data`：

```powershell
Set-Location <LAESim 源码目录>
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python .\Multi_use\space_mission_bridge.py --provider orekit-tle --tle .\Multi_use\space_mission_sample.tle --no-airsim --duration 2 --rate 1 --print-every 1
```

如果没有安装 Orekit Python wrapper 或没有配置 `orekit-data`，该 provider 会明确报错；默认 `tle` provider 仍使用 `sgp4`，不受影响。

### GMAT

GMAT 更适合作为离线任务设计工具，而不是实时后端。LAESim 提供 mission JSON 到 GMAT handoff script 的导出：

GMAT 不是 Python 包，不能通过 `pip install` 安装。需要下载 Windows 版 GMAT，安装或解压后，把 `GMAT.exe` 所在目录加入 `PATH`，或者在使用时记录它的绝对路径。

验证系统是否能找到 GMAT：

```powershell
where GMAT
where GMAT.exe
```

即使没有安装 GMAT，也可以先生成 handoff script：

```powershell
python .\Multi_use\space_mission_export_gmat.py --mission .\Multi_use\space_mission.example.json --out .\Multi_use\space_mission_gmat.script
```

生成的 `.script` 是任务设计起点，包含卫星对象、传播器、分析时间和 LAESim 摘要注释。真正用于工程设计时，应在 GMAT 中替换为经过设计的轨道状态或导入星历。

### Basilisk

Basilisk 更适合做航天器姿态、反作用轮、推进器等部件级动力学仿真。LAESim 当前先支持读取 Basilisk 或自定义脚本导出的姿态 CSV：

建议装在 `laesim_space`，不要装进 `airsim_agent`：

```powershell
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python -m pip install --no-user bsk
```

`PYTHONNOUSERSITE=1` 用于避免 Python 误加载 `C:\Users\<用户名>\AppData\Roaming\Python\Python310\site-packages` 里的用户级包。遇到“明明激活了环境，却还是从用户目录加载包”的情况时，这个变量很有用。

验证 Basilisk 是否安装成功：

```powershell
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python -c "import Basilisk; print(Basilisk.__path__)"
python .\Multi_use\space_backend_probe.py
```

LAESim 不要求实时嵌入 Basilisk。更稳的流程是：Basilisk 离线输出姿态 CSV，LAESim 桥接脚本读取这个 CSV 并驱动 UE 模型姿态。

```powershell
python .\Multi_use\space_mission_bridge.py --provider csv --csv .\Multi_use\space_mission_sample.csv --attitude-csv .\Multi_use\space_mission_attitude_sample.csv --vehicle Satellite
```

姿态 CSV 支持四元数列 `qx/qy/qz/qw`，也支持欧拉角列 `roll_deg/pitch_deg/yaw_deg`。接入后，UE 中 `SimpleSatellite` 的显示姿态由 CSV 决定，轨道位置仍由 `tle/csv/mock/orekit-tle` provider 决定。

## 10. 开发环境验证状态

在本机已经验证：

- `airsim_agent`：`sgp4` 可用，`space_mission_bridge.py --provider tle --no-airsim` 可正常输出星历和 LAESim 显示坐标。
- `laesim_space`：Orekit、Basilisk、SGP4 均可 import，`space_backend_probe.py` 可识别为可用；配置 `orekit-data.zip` 后，`space_mission_bridge.py --provider orekit-tle --no-airsim` 已验证可输出星历，24 小时任务分析已验证 Orekit 能生成亚秒精度的升起/落下窗口。
- WSL ROS Noetic + ns-3：已安装 `sgp4 2.25`，TLE/SGP4 传播验证通过。`ros_space_access_integration_test.sh` 已使用动态 GPS 目标验证完整闭环：500.1 km 星地包返回 `link_type=satellite`、FSPL、SNR、传播/串行化时延；不可见链路发布到 `/network_sim/drop`，`drop_stage=space_access_policy`。
- WSL 真实 TLE 在线演示：已使用当前 ISS TLE 自动定位下一可见窗口，驱动 UE 卫星模型并记录四个动态目标的窗口。实测不可见阶段在真实斜距 2594.9 km、仰角 -2.26 度时阻断；可见阶段 `Satellite -> Car` 在真实斜距 1820.7 km 时经逻辑星地链路投递，传播时延 6.073 ms、总时延 10.169 ms、SNR 7.51 dB。
- WSL 多星与中继：三颗 TLE 已同时传播并完成最佳星捕获/空窗统计；无 UE 测试中 7/7 个选择链路数据包送达，两跳 `Satellite -> Satellite2 -> Car` 返回总斜距 1500 km 和约 13.195 ms 总时延。
- 任务约束：传感器视场、侧摆/目标跟踪、最大离天底角、最大距离、最小驻留和瞬时区域覆盖率均有确定性示例与单元测试。
- 统一时钟：`ros_unified_clock_integration_test.sh` 已验证暂停、2 秒单步、TLE 按时刻查询和 ns-3 同步推进；测试包返回约 1.338 ms 仿真链路时延。
- 可视化与交付：已增加星下点、覆盖圈、选中链路和 UP/DOWN 标记节点，以及启动、状态、停止和 Markdown/CSV 报告导出脚本；纯几何、settings 坐标组合和报告聚合测试均已在 Windows/WSL 通过。
- UE 三星现场验收：`Satellite/Satellite2/Satellite3` 已同时被 TLE 桥驱动到不同显示位置；低负载配置下可视化状态连续推进到 176 帧，UE 始终可响应，3 颗卫星、4 个目标和 4 DOWN 空窗状态持续有效，日志无 RPC/Python 异常。该轮正常退出后 JSONL 与 summary 均为 677 条，报告聚合一致。此前已验证 4 UP 画面状态和实时最佳星链路 6/6 包送达，最后一包真实斜距约 2154 km、ns-3 时延约 11.281 ms。
- UE/通信坐标解耦：投递测试时 UE 中 Satellite 与 Car 的显示距离约 306.4 m，已超过普通 Wi-Fi 的 `MaxRangeMeters=250`，数据包仍按 `true_range_m=1820747.8` 的链路预算正常送达，证明星地通信不再依赖 UE 显示距离。
- LAESim 实时动态目标：已从正在运行的 `/airsim_node/Satellite/global_gps` 读取位置并发布 `source=ros-global-gps`、`valid=true` 的 access 状态，证明实时载具 GPS 接口可用。
- GMAT：当前未安装，`where GMAT` / `where GMAT.exe` 没有找到可执行文件。
- 交付闭环：关键文件清单 `40/40` 通过；活动 settings 校验为 `0` 错误、`0` 警告；独立 ROS/ns-3 四阶段验收固定得到 `DOWN -> UP:Satellite -> HANDOVER:Satellite2 -> DOWN`，两个 UP 包分别返回约 6.76 ms 和 6.26 ms 仿真时延；实时环境自检已确认 UE、ROS、三星状态、NetworkSim、可视化和 ns-3 runner 全部可用。
- UE 长时运行保护复验：一键演示采用任务状态 2 Hz、UE 位姿 0.5 Hz、标记 0.5 Hz；主动停止星座桥后，可视化器在 10 秒内自动退出且 UE 保持响应。恢复演示后连续 60 秒内可视化帧由 24 增至 54，3 星/4 目标完整、连续错误数为 0，doctor 全部必需项通过，日志无 RPC 超时或 traceback。

交付时建议把专业后端作为可选增强项说明：没有 Orekit/Basilisk/GMAT 时，仍然可以用 `sgp4/csv/mock` 完成实时卫星显示、星地几何计算和任务可见性演示；装好专业后端后，再用于高精度传播、离线轨道设计和姿态动力学数据生成。

## 11. 官方入口

- Orekit Python wrapper：`https://anaconda.org/conda-forge/orekit`
- Basilisk：`https://github.com/AVSLab/basilisk`
- GMAT：`https://software.nasa.gov/software/GSC-17177-1`，下载页通常跳转到 `https://sourceforge.net/projects/gmat/`

## 12. 交付状态与可选扩展

面向 LAESim 演示与研究的第一版天基任务模块已经闭环。交付前依次运行配置校验、确定性四阶段验收、环境自检和真实 UE 验收，完整步骤见 `space_delivery_checklist.md`。

以下属于后续专业增强，不是第一版交付阻塞项：

1. 将 `max_range_m`、传感器视场等组合约束改为 Orekit 复合事件检测，减少采样回退。
2. 将当前 AirSim 调试绘图标记升级为可打包的 UE 组件，用于更复杂的样式、图例和持久化轨迹。
3. 增加跨 UE 物理、ROS 和任务后端的完整锁步模式；当前统一时钟只控制任务计算与 ns-3。
4. 在确有任务需求时扩展轨道机动优化、高保真姿态动力学、专业雷达或 EOIR，而不是把它们作为标准演示依赖。
