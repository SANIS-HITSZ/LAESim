# how_to_use_settings 使用说明

这个目录里放了 9 份可直接起步的 `settings.json` 模板；可选通信网络配置示例放在 `NetworkSim\config\network-simulation.example.json`，可按需叠加到任意模板顶层：

- `settings_single_uav_with_sensors.json`
- `settings_single_car_with_sensors.json`
- `settings_airground_3uav_3car_with_sensors.json`
- `settings_airground_2uav_1car_1boat_with_sensors.json`
- `settings_airground_2uav_1car_1boat_1satellite_with_sensors.json`
- `settings_scene_map_1uav_1car_1boat.json`
- `settings_satellite_map_gps_start.json`
- `settings_space_mission_bridge.json`
- `settings_space_dynamic_targets.json`
- `..\NetworkSim\config\network-simulation.example.json`

推荐使用方法：

1. 选一份最接近需求的模板。
2. 复制到：

```text
C:\Users\<用户名>\Documents\AirSim\settings.json
```

3. 重开 UE 或至少重新 `Play`。

## 1. 模板分别适合什么场景

### 1.1 单无人机

`settings_single_uav_with_sensors.json`

适合：

- 只测一架多旋翼
- 先调无人机 API / 传感器
- 不需要车

特点：

- `SimMode = Multirotor`
- 端口主用 `41471`
- 配了 `imu / gps / magnetometer / barometer / lidar`
- 配了前视、下视相机
- 相机里包含 `Scene / DepthPlanar / Segmentation`

### 1.2 单汽车

`settings_single_car_with_sensors.json`

适合：

- 只测车体控制
- 单独看汽车相机 / 雷达 / GPS

特点：

- `SimMode = Car`
- 端口主用 `41461`
- 配了 `imu / gps / lidar`
- 显式把 `magnetometer` 和 `barometer` 关掉
- 配了前视、下视相机

### 1.3 3 架无人机 + 3 辆汽车

`settings_airground_3uav_3car_with_sensors.json`

适合：

- `AirGround` 混合多实例
- 同时跑无人机和汽车
- 同时给 Windows API 与 ROS 做联调

特点：

- `SimMode = AirGround`
- `41451 / 41461 / 41471` 三端口分离
- 3 架无人机：`UAV`、`UAV2`、`UAV3`
- 3 辆车：`Car`、`Car2`、`Car3`
- 每个实例都配了相机和 lidar
- 车仍然显式关闭 `magnetometer / barometer`

### 1.4 2 架无人机 + 1 辆汽车 + 1 艘船

`settings_airground_2uav_1car_1boat_with_sensors.json`

适合：

- 验证新增船 / 水面载具链路
- 同时跑无人机、汽车和船
- 同时给 Windows API 与 ROS 传感器链路做联调

特点：

- `SimMode = AirGround`
- `41451 / 41461 / 41471 / 41481` 四端口分离
- 2 架无人机：`UAV`、`UAV2`
- 1 辆车：`Car`
- 1 艘船：`Boat`
- 船使用 `VehicleType = SimpleBoat`
- 船默认使用插件内置的 `Type_052B_Destroyer_Combined` 静态网格，不需要也不建议在 `settings.json` 里指定模型路径
- 船的相机、GPS、IMU、lidar 布置仿照汽车模板
- 船显式关闭 `magnetometer / barometer`
- 船在地面平面运动，不要求关卡里真的有水体；可以把地面材质涂成蓝色表示水域

### 1.4.1 AirGround + UAV / Car / Boat / Satellite

`settings_airground_2uav_1car_1boat_1satellite_with_sensors.json`

适合：

- 验证“空天地海”混合载具链路
- 同时跑无人机、汽车、船和卫星
- 验证卫星 Python API、ROS topic、传感器和默认模型

特点：

- `SimMode = AirGround`
- `41451 / 41461 / 41471 / 41481 / 41491` 五端口分离
- 1 个卫星实例：`Satellite`
- 卫星使用 `VehicleType = SimpleSatellite`
- 卫星默认使用插件内置的 `10477_Satellite_v1_L3` 静态网格，不需要在 `settings.json` 里指定模型路径
- 卫星传感器配置仿照车 / 船：相机、GPS、IMU、lidar 可用，`magnetometer / barometer` 默认关闭
- 卫星运动是三维空间理想质点，API / ROS 直接给 `vx / vy / vz / yaw_rate`
- 没有持续移动指令时，卫星控制量归零，会静止悬停

### 1.5 图片地图 + UAV / Car / Boat

`settings_scene_map_1uav_1car_1boat.json`

适合：

- 验证“输入一张图片 + 物理比例尺 -> UE 可碰撞平面地图”
- 做纯视觉 VIO + 2D 地图匹配融合定位仿真平台的初步环境
- 同时验证载具按地图坐标出生

特点：

- 顶层 `SceneMap` 决定启动时加载哪张地图图片、比例尺、中心位置、偏航和碰撞
- UAV 使用 `StartOnSceneMap` 的 `Pixel` 模式，按图片像素坐标出生
- Car / Boat 使用 `StartOnSceneMap` 的 `Meters` 模式，按地图局部米制坐标出生
- 地图会生成 UE 静态网格平面并开启碰撞，车和船可以站在上面
- 地图只是带贴图的平面，不做道路、建筑、语义区域或复杂高度场

### 1.6 卫星图 + GPS 出生

`settings_satellite_map_gps_start.json`

适合：

- 使用 Google Earth / 地图软件导出的干净卫星图作为 2D 卫星底图
- 载具初始位置来自 GPS / 经纬度，而不是像素坐标

特点：

- `PixelCoordinateFrame = NorthUp`：按卫星图/Google Earth 场景处理像素，并使用 LAESim 当前 UE 地图显示层的 -90 度轴向补偿
- `GeoReference`：用一个已知经纬度的参考点把图片配准到 GPS
- `StartOnSceneMap.CoordinateType = GPS`：载具按 `Latitude / Longitude / Altitude` 出生

### 1.7 天基任务桥接显示

`settings_space_mission_bridge.json`

适合：

- 使用 TLE/SGP4、CSV 或 mock 数据源计算卫星轨道和星历
- UE/LAESim 只负责显示卫星模型和挂载相机/传感器
- 先用 CSV 或 mock 数据验证 `simSetVehiclePose` 同步链路

特点：

- 只配置一个 `SimpleSatellite` 实例
- `OriginGeopoint` 与桥接脚本默认参考点一致
- 卫星初始显示在 `Z = -300`，后续由 `Multi_use/space_mission_bridge.py` 按 TLE/CSV/mock 真值刷新
- 真实星地距离、覆盖和可见性不从 UE 模型距离推导，而应使用桥接脚本输出

### 1.8 天基动态目标与 ns-3 联动

`settings_space_dynamic_targets.json`

适合：

- 同时生成 `UAV`、`UAV2`、`Car`、`Boat` 和三颗 `SimpleSatellite`
- 从每个移动载具的 `/airsim_node/<vehicle>/global_gps` 实时计算星地 access
- 用 access 状态分别控制三颗卫星与四个目标之间的 NetworkSim/ns-3 通信

特点：

- 所有载具共用明确的 `OriginGeopoint`
- 15 条 `SpaceAccessPolicy` 规则默认使用 `FailMode=closed`：12 条星地规则和 3 条双向星间规则
- `SatelliteLinkModel.Enabled=true`，命中规则的星地包使用 access 的真实斜距计算 FSPL、传播时延、SNR、带宽排队和误码率，不受 UE 卫星显示坐标影响
- 已包含 WSL ns-3 runner 路径，使用前要确认本机 runner 安装位置一致
- 修改为当前 `settings.json` 后必须重新启动 UE 或重新进入 Play，运行中的 AirSim 不会热加载载具列表

对应的一键真实 TLE 演示命令：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/run_tle_space_network_demo.sh
```

上面是兼容的单星入口。多星同时运行、最佳星选择和链路切换使用：

```bash
bash NetworkSim/scripts/run_tle_constellation_demo.sh
```

多星脚本默认使用 `Satellite/Satellite2/Satellite3` 和 `UAV/UAV2/Car/Boat`。可通过 `SATELLITES="VEHICLE:CATALOG,..."` 与 `TARGET_VEHICLES="VEHICLE:KIND,..."` 覆盖，但载具名必须同步存在于 `Vehicles` 和 `NetworkSimulation.SpaceAccessPolicy.Rules`。修改本模板后必须重启 UE、AirSim ROS wrapper 和 NetworkSim；它们都不会热加载新增载具或规则。

三条星间规则对应 `/space/Satellite/access/Satellite2` 等 ISL 话题。关闭星间链路发布可设置 `PUBLISH_ISL=0`，但 `FailMode=closed` 下再发送带 ISL hop 的 `route` 包会因 access 状态缺失而被阻断。

完整交付演示可直接运行：

```bash
bash NetworkSim/scripts/start_space_demo.sh
```

该脚本会检查 `Satellite` 的 ROS 仿真时间是否正在推进。如果 UE 只打开了编辑器却没有进入 Play，或者 Play 处于暂停状态，它会拒绝继续。可视化器会读取每个载具在 settings 中的 `X/Y/Z` 出生点，把 AirSim 返回的载具局部坐标转换为 UE 全局 NED 后再画链路线，因此这里的出生点与局部 pose 只会组合一次。

可视化覆盖圈使用 `GLOBAL_TRACK_RADIUS`，应与多星启动器的 `DISPLAY_RADIUS` 保持一致；这些显示参数不会改变 TLE 真实斜距或 NetworkSim 链路预算。

## 2. 车、船和卫星的传感器 bug 要怎么规避

当前这套工程已经在源码里修过一层默认传感器逻辑，但为了让使用者拿到模板就尽量少踩坑，仍然建议在车的 `Sensors` 里显式写：

```json
"magnetometer": {
  "SensorType": 4,
  "Enabled": false
},
"barometer": {
  "SensorType": 1,
  "Enabled": false
}
```

原因是过去 `AirGround` 场景里，车 / 船这类地面平面载具被错误注入过更偏无人机的默认传感器包，而磁力计 / 气压计正好触发过运行时问题。模板里已经把这件事做掉了。

船的外加传感器默认按汽车来放：

- `imu`：开启
- `gps`：开启
- `Lidar`：开启，参数和汽车模板一致
- `front_center_scene`：开启 Scene / DepthPlanar / Segmentation，相机参数和汽车模板一致
- `magnetometer / barometer`：显式关闭

## 3. 常用顶层字段怎么理解

- `SettingsVersion`：建议保持 `1.2`
- `SimMode`：决定 UE 这次启动的是 `Multirotor`、`Car` 还是 `AirGround`
- `ClockType`：一般用 `ScalableClock`
- `ApiServerPortCV`：通用 / CV 端口，通常 `41451`
- `ApiServerPortCar`：汽车 API 端口，通常 `41461`
- `ApiServerPortMultirotor`：无人机 API 端口，通常 `41471`
- `ApiServerPortBoat`：船 API 端口，通常 `41481`
- `ApiServerPortSatellite`：卫星 API 端口，通常 `41491`
- `ViewMode`：UE 主视口的默认跟随 / 观察方式，例如 `FlyWithMe`、`Fpv`、`Manual`
- `Vehicles`：具体实例定义
- `SubWindows`：UE 右下角 3 个小窗口显示哪个实例的哪个相机
- `NetworkSimulation`：可选通信网络仿真配置。`Backend = none` 表示理想通信，消息立即转发；`Backend = ns3` 表示 ROS 网络桥接器把应用消息交给 ns-3 Wi-Fi ad hoc + OLSR/AODV 后端，用于计算时延、吞吐量和丢包。

### 3.0 可选 NetworkSimulation 写法

`NetworkSimulation` 是顶层字段，不属于某一个具体载具。需要研究通信链路时，可以从 `NetworkSim\config\network-simulation.example.json` 复制下面结构到正在使用的 `settings.json` 顶层：

```json
"NetworkSimulation": {
  "Backend": "none",
  "StepMs": 20,
  "Routing": "olsr",
  "MaxRangeMeters": 250.0,
  "TxPowerDbm": 16.0,
  "WarmupSeconds": 3.0,
  "PacketTimeoutSeconds": 5.0,
  "RunnerPath": "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner",
  "SatelliteLinkModel": {
    "Enabled": false,
    "FrequencyHz": 2200000000.0,
    "BandwidthHz": 5000000.0,
    "DataRateBps": 2000000.0,
    "TxPowerDbm": 40.0,
    "TxAntennaGainDbi": 10.0,
    "RxAntennaGainDbi": 20.0,
    "SystemLossDb": 2.0,
    "NoiseFigureDb": 3.0,
    "MinSnrDb": 3.0,
    "PacketErrorModel": "bpsk"
  },
  "UnifiedClock": {
    "Enabled": false,
    "ClockTopic": "/clock",
    "MaxStepMs": 1000.0
  }
}
```

说明：

- `Backend = none`：保持原来的理想通信，不引入网络时延和丢包，适合排查算法逻辑。
- `Backend = ns3`：启用 ns-3 后端，应用消息会经过离散事件网络仿真。
- `StepMs`：ROS 网络桥接器推进网络后端的步长。
- `Routing`：当前 runner 支持 `olsr` 和 `aodv`。
- `MaxRangeMeters`：当前实现使用的硬通信范围。
- `PacketTimeoutSeconds`：超过该时间仍未送达的包记为丢包。
- `RunnerPath`：ns-3 runner 的可执行文件路径，默认对应 `NetworkSim\scripts\build_ns3_runner.sh` 的输出。
- `SatelliteLinkModel.Enabled`：是否让 `SpaceAccessPolicy` 命中的星地包改走真实斜距逻辑链路；关闭时保持原 Wi-Fi 拓扑行为。
- `FrequencyHz / BandwidthHz / DataRateBps`：星地载频、接收带宽和逻辑链路数据率。
- `TxPowerDbm / TxAntennaGainDbi / RxAntennaGainDbi / SystemLossDb / NoiseFigureDb`：星地链路预算参数。
- `MinSnrDb / PacketErrorModel`：最低信噪比和包错误率模型；当前支持 `bpsk` 与 `none`。
- `UnifiedClock.Enabled=false`：默认使用原有墙钟 Timer，不改变现有功能。
- `UnifiedClock.Enabled=true`：NetworkSim 只按 `ClockTopic` 的正向时间增量推进，支持暂停、单步和倍速复现。
- `UnifiedClock.MaxStepMs`：把较大的场景时间跳变量拆分为多个后端步长；不改变最终场景时刻。

启用统一时钟前必须先运行 `ros/src/example/space_sim_clock.py`。如果 `/clock` 不发布，NetworkSim 将保持等待，不会自行推进；回退场景时间后还需要重启 NetworkSim，因为 ns-3 事件时间不能倒退。完整命令见 `docs\space_mission_bridge.md` 和 `docs\laesim_wsl_ros_ns3.md`。

完整安装、构建和验证流程见：

```text
docs\laesim_wsl_ros_ns3.md
```

### 3.1 主视角跟随哪一个载具

LAESim / AirSim 的 UE 主视角由 `CameraDirector` 控制，不是普通关卡里的 `CameraActor`。如果不显式指定，AirSim 会自动选择一个默认车辆；在 `AirGround` 多类型场景里，这有时会表现为主视角锁定到某艘船或某辆车上。

推荐在 `settings.json` 里显式指定主视角模式和 FPV / 跟随车辆。例如让主视角跟随 `F5` 无人机：

```json
{
  "ViewMode": "FlyWithMe",
  "Vehicles": {
    "F5": {
      "VehicleType": "SimpleFlight",
      "PawnPath": "BP_FlyingPawn",
      "X": 45.210828,
      "Y": 49.069532,
      "Z": -2.0,
      "Yaw": 0,
      "IsFpvVehicle": true
    }
  }
}
```

注意：

- `IsFpvVehicle` 同一时间只建议给一个车辆设置为 `true`
- 改完 `settings.json` 后需要重新开始 UE Play，或重启 UE，才会重新选择主视角目标
- 常用视角快捷键：`F` 切到 FPV，`B` 切到 `FlyWithMe` 跟随视角，`M` 切到手动视角
- 如果关卡中手动预放了 AirSim Pawn，代码会优先使用已有 Pawn；这时 settings 的自动创建顺序可能不再决定默认车辆，建议仍然用 `IsFpvVehicle` 明确指定目标

### 3.2 多车辆坐标系：不要把 settings 出生点和轨迹坐标混在一起

AirSim 官方接口有一个很容易踩坑的约定：`simGetVehiclePose()`、`simGetGroundTruthKinematics()` 返回的位置，以及 `moveToPositionAsync()`、`moveOnPathAsync()` 等控制接口使用的位置，都是以“该 vehicle 的 starting point”为原点的 NED 坐标。也就是说，每一辆车 / 每一架无人机自己的 API 坐标原点都是 `(0, 0, 0)`。

而 `settings.json` 里的：

```json
"UAV1": { "VehicleType": "SimpleFlight", "X": 0.0, "Y": 0.0, "Z": -2.0, "Yaw": 0 },
"UAV2": { "VehicleType": "SimpleFlight", "X": 50.0, "Y": 0.0, "Z": -2.0, "Yaw": 0 },
"Car1": { "VehicleType": "PhysXCar", "X": 0.0, "Y": 30.0, "Z": 0.0, "Yaw": 90 }
```

这里的 `X / Y / Z / Yaw` 是载具出生点相对于 UE PlayerStart / 世界基准的初始偏移。它会影响画面里的实际出生位置，但不会把这辆车的 API 原点改成别的值。

可以按下面这个关系理解：

```text
UE 画面里的实际位置 ~= settings 出生点偏移 + AirSim API 里的本车局部 NED 位置
```

因此只要涉及多 vehicle、外部轨迹、外部算法或距离计算，都要先统一坐标约定：

- 如果脚本只控制单个 vehicle，可以直接把 API 坐标理解为“从这辆车出生点出发的局部 NED 位移”。例如 `moveToPositionAsync(100, 0, -20, ...)` 表示从本车出生点向北 100 m、上升到 20 m 高度附近。
- 如果两个 vehicle 的 settings 出生点不同，分别读取它们的 `simGetVehiclePose()` 后，不能直接相减当作世界距离；要先把各自的局部坐标加回各自的 settings 出生点偏移，再放到同一个世界坐标系里比较。
- 如果外部 CSV / 路径规划器 / ROS 节点给的是同一套全局坐标，发送给某个 vehicle 前要做转换：`API_position(vehicle) = global_position - settings_start(vehicle)`。
- 如果希望脚本里的路径点可以直接原样发送给多个 vehicle，可以把这些 vehicle 的 settings 出生点设成相同值，让它们共享同一个 API 原点。
- 不要在同一个实验里混用“共享原点”和“每车独立出生点修正”两种写法，否则画面位置、日志位置和算法位置会互相对不上。
- 改完 settings 的出生点后，需要重新开始 UE Play，最好重启一次 UE，确保所有 vehicle 的 starting point 被重新创建。

## 4. SceneMap 图片地图怎么写

`SceneMap` 是仿真环境级功能，不属于某一辆车、某一架无人机或某一艘船。启动时由 `settings.json` 决定是否加载，运行时也可以通过 Python / ROS API 切换。

最小写法：

```json
"SceneMap": {
  "Enabled": true,
  "ImagePath": "C:/Users/<用户名>/Documents/AirSim/maps/demo_map.png",
  "ObjectName": "LAESimSceneMap",
  "MetersPerPixel": 0.05,
  "PixelCoordinateFrame": "NorthUp",
  "CenterX": 0,
  "CenterY": 0,
  "Z": 0,
  "Yaw": 0,
  "CollisionEnabled": true,
  "SegmentationId": 21,
  "GeoReference": {
    "Enabled": true,
    "ReferenceLatitude": 22.591244,
    "ReferenceLongitude": 113.969778,
    "ReferenceAltitude": 21,
    "ReferenceU": 1024,
    "ReferenceV": 450
  }
}
```

字段含义：

- `ImagePath`：UE 所在 Windows 主机能访问到的图片绝对路径，推荐用 `/` 或双反斜杠
- `MetersPerPixel`：每个像素对应多少米，例如 `0.05` 表示 1 像素 = 5 cm
- `PixelCoordinateFrame`：卫星图推荐 `NorthUp`；旧版简单测试图可用默认 `NED`
- `CenterX / CenterY / Z`：地图中心在 AirSim NED 世界坐标里的位置
- `Yaw`：地图绕竖直方向旋转角，单位是度
- `CollisionEnabled`：是否启用碰撞；需要车、船站在图上时应保持 `true`
- `SegmentationId`：可选，给整张地图平面设置语义分割 ID；不需要时可写 `-1`
- `GeoReference`：GPS 配准点，`ReferenceLatitude/Longitude` 是参考点经纬度，`ReferenceU/V` 是该点在原图里的像素坐标

图片和配准参数准备：

- 图片宽高不用写进 `settings.json`，LAESim 会在加载图片时自动读取。
- 图片可以是任意长宽比，推荐提前裁掉 Google logo、比例尺、按钮、图例等 UI。
- `MetersPerPixel` 是 2D 地图匹配最关键的比例尺参数。
- `ReferenceLatitude / ReferenceLongitude` 决定 GPS 如何落到图上。
- `ReferenceU / ReferenceV` 是参考点在图片里的像素坐标，左上角为 `(0, 0)`。
- `ReferenceAltitude` 对二维平面定位不重要，不影响水平出生位置；可以写 Google Earth 给出的海拔，也可以固定写 `0` 或场地平均海拔。

载具出生位置有两种写法。旧写法仍然有效：

```json
"X": 0,
"Y": 5,
"Z": -2,
"Yaw": 90
```

新写法是在载具里加 `StartOnSceneMap`。像素模式：

```json
"StartOnSceneMap": {
  "CoordinateType": "Pixel",
  "U": 800,
  "V": 600,
  "Height": 5,
  "Yaw": 0
}
```

地图米制坐标模式：

```json
"StartOnSceneMap": {
  "CoordinateType": "Meters",
  "MapX": 10,
  "MapY": -5,
  "Height": 0,
  "Yaw": 90
}
```

GPS 模式：

```json
"StartOnSceneMap": {
  "CoordinateType": "GPS",
  "Latitude": 22.591244,
  "Longitude": 113.969778,
  "Altitude": 21,
  "Height": 5,
  "Yaw": 90
}
```

坐标约定：

- `PixelCoordinateFrame = NorthUp` 时，像素模式保持 `U` 沿图面右方、`V` 沿图面下方；GPS 模式会把纬度减小产生的南向位移映射到图面右方，也就是 `U` 增大
- `PixelCoordinateFrame = NED` 时，保持旧版 `U -> +X`、`V -> +Y`
- `NorthUp` 会在 UE 显示层自动补偿 -90 度轴向差；GPS 出生内部使用 `local_x=east, local_y=-north` 对齐当前图面，用户不要再手动给 `SceneMap.Yaw` 加 90 度
- 像素原点在图片左上角，地图中心是 `(图片宽 / 2, 图片高 / 2)`
- `MapX / MapY` 是以地图中心为原点的局部米制坐标
- `Height` 表示离地图平面的高度；无人机通常为正数，车和船通常为 `0`
- `Height` 只管垂直高度，不影响二维地图上的像素 / GPS 水平位置
- GPS 模式里的 `Altitude` 主要用于高度语义；当前 2D 地图匹配主要依赖 `Latitude / Longitude`
- `StartOnSceneMap.Yaw` 会叠加到 `SceneMap.Yaw` 上
- 如果同一辆载具同时写了 `X/Y/Z/Yaw` 和 `StartOnSceneMap`，并且 `StartOnSceneMap.Enabled` 没关，启动时以后者为准

两种出生方式怎么选：

- 如果你只关心 AirSim 世界坐标，继续写旧的 `X/Y/Z/Yaw`。
- 如果你希望载具跟图片地图绑定，写 `StartOnSceneMap`。
- `StartOnSceneMap` 里推荐优先用 `Pixel` 或 `GPS`：`Pixel` 适合直接点图上的像素；`GPS` 适合从 Google Earth / 测绘数据给经纬度；`Meters` 适合已经知道相对地图中心的米制偏移。

## 5. 想新增一架无人机怎么加

最简单的方法是复制现有某个无人机块，比如复制 `UAV2` 改成 `UAV4`：

```json
"UAV4": {
  "VehicleType": "SimpleFlight",
  "X": 0,
  "Y": 14,
  "Z": -2,
  "Yaw": 0,
  "Sensors": {
    "imu": { "SensorType": 2, "Enabled": true },
    "gps": { "SensorType": 3, "Enabled": true },
    "magnetometer": { "SensorType": 4, "Enabled": true },
    "barometer": { "SensorType": 1, "Enabled": true },
    "Lidar": {
      "SensorType": 6,
      "Enabled": true,
      "NumberOfChannels": 16,
      "RotationsPerSecond": 10,
      "PointsPerSecond": 10000,
      "X": 0,
      "Y": 0,
      "Z": -1.2,
      "Roll": 0,
      "Pitch": 0,
      "Yaw": 0,
      "VerticalFOVUpper": 7,
      "VerticalFOVLower": -52,
      "HorizontalFOVStart": -180,
      "HorizontalFOVEnd": 180,
      "DrawDebugPoints": false,
      "DataFrame": "SensorLocalFrame"
    }
  },
  "Cameras": {
    "...": "可以直接复制已有 UAV 的 Cameras"
  }
}
```

新增无人机时要注意：

- 名字不能和现有实例重复
- 出生点不要和别的实例重叠
- 如果要控制它，Windows API 脚本用 `--vehicle UAV4`
- ROS 里也用 `--vehicle UAV4`

## 6. 想新增一辆汽车怎么加

同理，复制 `Car2` 或 `Car3` 的结构：

```json
"Car4": {
  "VehicleType": "PhysXCar",
  "X": 0,
  "Y": 36,
  "Z": 0,
  "Yaw": 0,
  "Sensors": {
    "imu": { "SensorType": 2, "Enabled": true },
    "gps": { "SensorType": 3, "Enabled": true },
    "magnetometer": { "SensorType": 4, "Enabled": false },
    "barometer": { "SensorType": 1, "Enabled": false },
    "Lidar": {
      "SensorType": 6,
      "Enabled": true,
      "NumberOfChannels": 16,
      "RotationsPerSecond": 10,
      "PointsPerSecond": 10000,
      "X": 0,
      "Y": 0,
      "Z": -1.2,
      "Roll": 0,
      "Pitch": 0,
      "Yaw": 0,
      "VerticalFOVUpper": 52,
      "VerticalFOVLower": -7,
      "HorizontalFOVStart": -180,
      "HorizontalFOVEnd": 180,
      "DrawDebugPoints": false,
      "DataFrame": "SensorLocalFrame"
    }
  },
  "Cameras": {
    "...": "可以直接复制已有 Car 的 Cameras"
  }
}
```

新增汽车时要注意：

- `VehicleType` 用 `PhysXCar`
- 出生点不要和别的车 / 无人机重叠
- 仍建议显式关闭 `magnetometer / barometer`
- 控制脚本里用 `--vehicle Car4`

## 7. 想新增一艘船怎么加

这套船模型不是水动力仿真，不依赖水面材质、浮力体或流体交互。它会在地面平面上移动，适合把某块地面涂成蓝色，当成“水域”来跑 USV / 舰船编队逻辑。

运动学上，船使用简化的平面三自由度模型：

- `u`：纵向速度，也就是船体前后方向速度
- `v`：横向漂移速度，模拟船转弯时的侧滑 / 漂移
- `r`：艏向角速度，模拟舵效和船体转向惯性

API / ROS 状态里会同时给出 `speed`、`forward_speed`、`lateral_speed`、`yaw_rate`。这比只用“车式速度 + 直接转角”更接近船的运动特征，但仍然不考虑波浪、水流、浮沉、横摇、纵摇等水体相互作用。

复制模板里的 `Boat` 结构即可：

```json
"Boat2": {
  "VehicleType": "SimpleBoat",
  "X": 0,
  "Y": 52,
  "Z": 0,
  "Yaw": 90,
  "Sensors": {
    "imu": { "SensorType": 2, "Enabled": true },
    "gps": { "SensorType": 3, "Enabled": true },
    "magnetometer": { "SensorType": 4, "Enabled": false },
    "barometer": { "SensorType": 1, "Enabled": false }
  },
  "Cameras": {
    "...": "可以直接复制已有 Boat 的 Cameras"
  }
}
```

新增船时要注意：

- `VehicleType` 推荐用 `SimpleBoat`
- `PhysXBoat` 也会被识别为船类型，目前会走同一套简化船动力
- 默认船模型是插件内容目录里的 `StaticMesh'/AirSim/Models/Boat/Type_052B_Destroyer_Combined.Type_052B_Destroyer_Combined'`
- 这个模型由 `BoatPawn.cpp` 固定加载，和 AirSim 自带无人机 / 汽车模型一样，不需要在单艘船配置里写 `PawnPath` 或模型资源路径
- 052B `.uasset` 源文件放在 `Unreal/Assets/Boat/Models/Boat`，`build.cmd` 会把它复制到 `Unreal/Plugins/AirSim/Content/Models/Boat`
- 如果默认 `.uasset` 没有随插件一起复制，`BoatPawn` 会回退到代码生成的简化舰船；正常部署时应先运行 `BuildAirSimRelease.bat` 或 `build.cmd --Release`
- 传感器建议直接复制汽车的 `Sensors` / `Cameras` 配置
- 控制脚本里用 `--vehicle Boat2`

### 如果确实想换船模型

默认推荐做法是替换源码资产或修改 `BoatPawn.cpp`，而不是在 `settings.json` 里写 StaticMesh 路径：

- 全局替换默认船模型：把新模型导入到 `/AirSim/Models/Boat`，再把生成的 `.uasset` 同步到 `Unreal/Assets/Boat/Models/Boat`，然后在 `BoatPawn.cpp` 里把 `FObjectFinder<UStaticMesh>` 的资源路径改成新资源名。所有 `SimpleBoat` 都会使用新默认模型。
- 不改代码的全局替换：导入新模型后覆盖同名资源 `Type_052B_Destroyer_Combined`，保持 `/AirSim/Models/Boat/Type_052B_Destroyer_Combined` 路径不变，并同步回 `Unreal/Assets/Boat/Models/Boat`。
- 按实例替换整个 Pawn：可以用 AirSim 原生 `PawnPaths` / `PawnPath`，但这里填的是 Pawn 蓝图类名，不是 `.obj`、`.fbx`、`.uasset` 的 StaticMesh 路径。

`PawnPath` 适合这种情况：你做了一个新的 Boat Pawn 蓝图或 C++ Pawn 类，并希望某一艘船使用这个 Pawn。示例结构如下：

```json
{
  "PawnPaths": {
    "MyBoatPawn": {
      "PawnBP": "Class'/Game/Blueprints/BP_MyBoatPawn.BP_MyBoatPawn_C'"
    }
  },
  "Vehicles": {
    "Boat2": {
      "VehicleType": "SimpleBoat",
      "PawnPath": "MyBoatPawn",
      "X": 0,
      "Y": 52,
      "Z": 0,
      "Yaw": 90
    }
  }
}
```

注意：当前 `AirGround` 的 Boat 链路会把 Pawn 转成 `ABoatPawn` 来取相机和碰撞事件，所以自定义 `BP_MyBoatPawn` 应该继承自 `ABoatPawn`。如果只是想换外观模型，优先用前两种方式。

## 8. Satellite / 卫星怎么写

最小实例：

```json
"Satellite": {
  "VehicleType": "SimpleSatellite",
  "X": 0,
  "Y": 0,
  "Z": -80,
  "Yaw": 0,
  "Sensors": {
    "imu": { "SensorType": 2, "Enabled": true },
    "gps": { "SensorType": 3, "Enabled": true },
    "magnetometer": { "SensorType": 4, "Enabled": false },
    "barometer": { "SensorType": 1, "Enabled": false },
    "Lidar": {
      "SensorType": 6,
      "Enabled": true,
      "NumberOfChannels": 16,
      "RotationsPerSecond": 10,
      "PointsPerSecond": 10000,
      "X": 0,
      "Y": 0,
      "Z": 0,
      "VerticalFOVUpper": 52,
      "VerticalFOVLower": -52,
      "HorizontalFOVStart": -180,
      "HorizontalFOVEnd": 180,
      "DataFrame": "SensorLocalFrame"
    }
  },
  "Cameras": {
    "...": "可以直接复制模板里的 Satellite Cameras"
  }
}
```

新增卫星时要注意：

- `VehicleType` 推荐用 `SimpleSatellite`
- 默认卫星模型是插件内容目录里的 `StaticMesh'/AirSim/Models/Satellite/10477_Satellite_v1_L3.10477_Satellite_v1_L3'`
- 这个模型由 `SatellitePawn.cpp` 固定加载，不需要在单个卫星配置里写 `PawnPath` 或 StaticMesh 路径
- 源码资产放在 `Unreal/Assets/Satellite/Models/Satellite`，`build.cmd` 会复制到 `Unreal/Plugins/AirSim/Content/Models/Satellite`
- 控制接口是理想质点速度：`vx / vy / vz` 单位 m/s，使用 AirSim NED 坐标；`yaw_rate` 单位 rad/s
- `Z` 是 AirSim NED 坐标，负数表示在 UE 里更高；例如 `Z = -80` 表示初始挂在空中
- Python 控制脚本：`python .\Multi_use\satellite_keyboard_control.py --vehicle Satellite`
- ROS 控制 topic：`/airsim_node/Satellite/satellite_cmd`
- ROS 状态 topic：`/airsim_node/Satellite/satellite_state`

如果要替换卫星模型，推荐和 Boat 一样走默认资源替换：导入新模型到 `/AirSim/Models/Satellite`，同步 `.uasset` 到 `Unreal/Assets/Satellite/Models/Satellite`，再在 `SatellitePawn.cpp` 中修改 `FObjectFinder<UStaticMesh>` 的资源路径。只有某一个卫星实例要换整套 Pawn 时，才使用 `PawnPaths / PawnPath`，并让蓝图继承自 `ASatellitePawn`。

## 9. 想给实例加相机怎么加

相机统一写在该实例的 `Cameras` 里。一个常用的前视相机写法是：

```json
"front_center_scene": {
  "CaptureSettings": [
    {
      "PublishToRos": 1,
      "ImageType": 0,
      "Width": 640,
      "Height": 480,
      "FOV_Degrees": 120
    },
    {
      "PublishToRos": 1,
      "ImageType": 1,
      "Width": 640,
      "Height": 480,
      "FOV_Degrees": 120
    },
    {
      "PublishToRos": 1,
      "ImageType": 5,
      "Width": 640,
      "Height": 480,
      "FOV_Degrees": 120
    }
  ],
  "Pitch": 0,
  "Roll": 0,
  "Yaw": 0,
  "X": 0.25,
  "Y": 0.0,
  "Z": 0.3
}
```

说明：

- `ImageType 0`：`Scene`
- `ImageType 1`：`DepthPlanar`
- `ImageType 5`：`Segmentation`
- `PublishToRos = 1` 才会让 ROS 示例期待对应图像话题

## 10. 想加 lidar 怎么加

常用 lidar 写法：

```json
"Lidar": {
  "SensorType": 6,
  "Enabled": true,
  "NumberOfChannels": 16,
  "RotationsPerSecond": 10,
  "PointsPerSecond": 10000,
  "X": 0,
  "Y": 0,
  "Z": -1.2,
  "Roll": 0,
  "Pitch": 0,
  "Yaw": 0,
  "VerticalFOVUpper": 7,
  "VerticalFOVLower": -52,
  "HorizontalFOVStart": -180,
  "HorizontalFOVEnd": 180,
  "DrawDebugPoints": false,
  "DataFrame": "SensorLocalFrame"
}
```

如果是车，一般把垂直视场改成更适合地面车辆的范围，例如：

- `VerticalFOVUpper = 52`
- `VerticalFOVLower = -7`

## 11. SensorType 速查表

- `1`：Barometer
- `2`：Imu
- `3`：Gps
- `4`：Magnetometer
- `5`：Distance
- `6`：Lidar

## 12. 改完 settings 后别忘了什么

每次改完 `settings.json`，都建议：

1. 停掉当前 `Play`
2. 重开 UE 或重新 `Play`
3. 先用 Windows 侧 `Multi_use/sensor_probe.py --list-only`
4. 再用 ROS 侧 `sensor_config_report_ros.py`

这样最容易第一时间看出名字、端口、相机或传感器是不是写错了。

如果启用了多卫星和 NetworkSim，还应在启动 UE 前做一次只读配置校验：

```powershell
python NetworkSim\python\space_delivery_validation.py `
  --settings "$env:USERPROFILE\Documents\AirSim\settings.json" `
  --expect-satellite Satellite `
  --expect-satellite Satellite2 `
  --expect-satellite Satellite3 `
  --expect-target UAV --expect-target UAV2 `
  --expect-target Car --expect-target Boat `
  --require-ns3
```

该命令只读取文件，不会自动修改或覆盖 settings。标准多星模板是 `settings_space_dynamic_targets.json`，完整交付验收见 `docs/space_delivery_checklist.md`。
