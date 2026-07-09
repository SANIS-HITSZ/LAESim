# how_to_use_settings 使用说明

这个目录里放了 7 份可直接起步的 `settings.json` 模板：

- `settings_single_uav_with_sensors.json`
- `settings_single_car_with_sensors.json`
- `settings_airground_3uav_3car_with_sensors.json`
- `settings_airground_2uav_1car_1boat_with_sensors.json`
- `settings_airground_2uav_1car_1boat_1satellite_with_sensors.json`
- `settings_scene_map_1uav_1car_1boat.json`
- `settings_satellite_map_gps_start.json`

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
- `Vehicles`：具体实例定义
- `SubWindows`：UE 右下角 3 个小窗口显示哪个实例的哪个相机

## 4. SceneMap 图片地图怎么写

`SceneMap` 是仿真环境级功能，不属于某一辆车、某一架无人机或某一艘船。启动时由 `settings.json` 决定是否加载，运行时也可以通过 Python / ROS API 切换。

最小写法：

```json
"SceneMap": {
  "Enabled": true,
  "ImagePath": "C:/Users/32749/Documents/AirSim/maps/demo_map.png",
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
