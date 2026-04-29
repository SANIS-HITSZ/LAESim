# how_to_use_settings 使用说明

这个目录里放了 3 份可直接起步的 `settings.json` 模板：

- `settings_single_uav_with_sensors.json`
- `settings_single_car_with_sensors.json`
- `settings_airground_3uav_3car_with_sensors.json`

推荐使用方法：

1. 选一份最接近需求的模板。
2. 复制到：

```text
C:\Users\<用户名>\Documents\AirSim\settings.json
```

3. 重开 UE 或至少重新 `Play`。

## 1. 三份模板分别适合什么场景

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

## 2. 车的传感器 bug 要怎么规避

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

原因是过去 `AirGround` 场景里，车被错误注入过更偏无人机的默认传感器包，而磁力计 / 气压计正好触发过运行时问题。模板里已经把这件事做掉了。

## 3. 常用顶层字段怎么理解

- `SettingsVersion`：建议保持 `1.2`
- `SimMode`：决定 UE 这次启动的是 `Multirotor`、`Car` 还是 `AirGround`
- `ClockType`：一般用 `ScalableClock`
- `ApiServerPortCV`：通用 / CV 端口，通常 `41451`
- `ApiServerPortCar`：汽车 API 端口，通常 `41461`
- `ApiServerPortMultirotor`：无人机 API 端口，通常 `41471`
- `Vehicles`：具体实例定义
- `SubWindows`：UE 右下角 3 个小窗口显示哪个实例的哪个相机

## 4. 想新增一架无人机怎么加

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

## 5. 想新增一辆汽车怎么加

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

## 6. 想给实例加相机怎么加

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

## 7. 想加 lidar 怎么加

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

## 8. SensorType 速查表

- `1`：Barometer
- `2`：Imu
- `3`：Gps
- `4`：Magnetometer
- `5`：Distance
- `6`：Lidar

## 9. 改完 settings 后别忘了什么

每次改完 `settings.json`，都建议：

1. 停掉当前 `Play`
2. 重开 UE 或重新 `Play`
3. 先用 Windows 侧 `Multi_use/sensor_probe.py --list-only`
4. 再用 ROS 侧 `sensor_config_report_ros.py`

这样最容易第一时间看出名字、端口、相机或传感器是不是写错了。
