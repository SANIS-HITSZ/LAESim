# GeoTIFF 覆盖飞行与稳定下视数据采集

这个案例把一张带地理标签的 GeoTIFF 转为 LAESim `SceneMap`，规划平行航带，驱动无人机覆盖飞行，并按固定频率采集稳定正下方图像、GPS、物理真值和状态估计。它适合视觉定位、地图匹配、正射巡检和图像/轨迹数据集生成。

仓库不包含地图和输出数据。请准备自己的 GeoTIFF，并将其命名为本目录下的 `input_map.tif`，或在命令中显式传入 `--tif`。

## 1. 环境与输入

- Windows、UE 4.27 和已编译的 LAESim V1.5 插件。
- Python 3.10 或 3.11。
- 一个包含像素比例尺、TiePoint 和受支持坐标系标签的 GeoTIFF；当前读取器支持 EPSG:3857。

在仓库根目录安装依赖：

```powershell
py -3 -m pip install -r .\Examples\quickstart\nadir_geotiff_collection\requirements.txt
```

本案例优先使用仓库中的 `PythonClient/airsim`，不会误用系统里安装的旧 AirSim 客户端。

## 2. 生成 SceneMap 与 settings

```powershell
py -3 .\Examples\quickstart\nadir_geotiff_collection\prepare_scenemap.py `
  --tif C:\data\area.tif
```

脚本会生成：

- `scene_map.png`：UE 能直接加载的北向地图图片。
- `settings.generated.json`：已经写入绝对图片路径、当地真实米/像素、GeoTIFF 中心 GPS、`GeoReference` 和稳定下视相机。

备份活动配置并启用案例：

```powershell
$AirSimDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AirSim'
New-Item -ItemType Directory -Force $AirSimDir | Out-Null
$Settings = Join-Path $AirSimDir 'settings.json'
if (Test-Path $Settings) { Copy-Item $Settings "$Settings.backup" -Force }
Copy-Item .\Examples\quickstart\nadir_geotiff_collection\settings.generated.json $Settings -Force
```

`settings.example.json` 只用于展示结构；其中经纬度、比例尺和图片路径是占位值，不应直接运行。

!!! warning
    `ImagePath` 必须是 Windows UE 进程能读取的绝对路径。UE 4.27 的部分图片加载链路不能可靠处理中文路径，建议让仓库、地图和输出目录都只使用 ASCII 路径。

## 3. 先检查规划结果

无需启动 UE：

```powershell
py -3 .\Examples\quickstart\nadir_geotiff_collection\collect_geotiff_dataset.py `
  --tif C:\data\area.tif `
  --plan-only --overwrite
```

默认任务为 1000 m、4.6 m/s、35 m 相对高度、218 s、10 Hz、5 条航带和 90 度水平视场角。可用 `--distance-m`、`--speed-mps`、`--altitude-m`、`--duration-s`、`--rate-hz`、`--lanes` 和 `--fov-deg` 修改。

输出中的 `route_preview.jpg` 用于检查航线是否越界，`planned_trajectory.csv` 是理想参考轨迹。去掉 `--plan-only` 可直接从 GeoTIFF 裁取离线理想图像数据集。

## 4. 在 LAESim 中实时采集

1. 完全重启 UE，打开接入 LAESim 的场景并进入 **Play**。
2. 确认屏幕显示 SceneMap 已成功加载。
3. 在仓库根目录运行：

```powershell
py -3 .\Examples\quickstart\nadir_geotiff_collection\collect_airsim_nadir.py `
  --tif C:\data\area.tif `
  --output .\Examples\quickstart\nadir_geotiff_collection\output\run01 `
  --no-land-after
```

当 SceneMap 关闭碰撞时使用 `--no-land-after`，任务后停止 Play 或调用 `reset()`。有可靠碰撞地面的三维关卡可以不加该参数。

实时输出包括：

| 文件 | 含义 |
| --- | --- |
| `images/` | UE `nadir` 相机图像 |
| `metadata.csv` | 图像路径、时间戳、GPS、真值、估计值和碰撞状态关联表 |
| `groundtruth.csv` | `simGetGroundTruthKinematics()` 物理真值及其 WGS84 经纬度 |
| `estimated_trajectory.csv` | 飞控状态估计 |
| `planned_trajectory.csv` | 理想覆盖航线，不等于实际飞行轨迹 |
| `trajectory_error.csv` | 估计相对真值、真值相对计划的逐帧误差 |
| `runtime_summary.json` | 实际采样率、跳帧、距离和误差统计 |

Ground truth 的坐标链为：AirSim 载具局部 NED -> SceneMap 局部 NED -> GeoTIFF 中心局部投影 -> WGS84。图像和状态来自连续 RPC，并非原子采样；严格时序分析应使用 `image_timestamp_ns` 和 `state_timestamp_ns`。

## 5. 稳定下视云台

相机的 `Pitch=-90` 只是相对机体向下；无人机横滚和俯仰时，普通下视相机仍会随之倾斜。本案例额外使用：

```json
"Gimbal": {
  "Stabilization": 1.0,
  "Pitch": -90.0,
  "Roll": 0.0,
  "Yaw": 0.0
}
```

这会把目标姿态固定在世界坐标系，适合正射采集和地图匹配。若任务希望相机航向随载具变化，只稳定俯仰和横滚，则省略 `Gimbal.Yaw`；省略的轴不会被稳定。

## 6. 验证

无需地图和第三方包的结构检查：

```powershell
py -3 .\Examples\quickstart\nadir_geotiff_collection\validate_example.py
```

有真实 GeoTIFF 并安装依赖后，先运行 `collect_geotiff_dataset.py --plan-only`。实时采集后重点检查 `runtime_summary.json` 中：

- `captured_frame_count` 是否符合 `duration_s * rate_hz + 1`。
- `skipped_schedule_frame_count` 是否为 0。
- `achieved_capture_rate_hz` 是否接近目标频率。
- `groundtruth_vs_planned_tracking_error_m` 是否符合所用飞控和航速预期。

该案例生成的是平面地图上的仿真数据。即使高度和视场角按真实米制设置，SceneMap 仍不包含建筑侧面、三维遮挡和真实地形起伏。
