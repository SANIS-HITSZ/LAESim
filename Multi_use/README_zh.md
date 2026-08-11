# Multi_use 代码使用说明

这个目录放的是 Windows 侧 API 工具脚本。它们直接基于 AirSim Python API，不依赖 ROS，适合先把 UE、端口、控制和传感器链路单独跑通。它们默认会优先从仓库相对路径 `..\PythonClient` 读取 AirSim Python 包，所以把整个 `Multi_use` 随仓库一起带走时，不需要强依赖固定盘符。

默认使用前提：

- UE 工程已经打开并 `Play`
- `settings.json` 已经放在 `C:\Users\<用户名>\Documents\AirSim\settings.json`
- Python 环境里已安装 `airsim` 依赖和 `pygame`

## 1. keyboard_control.py

这个脚本可以：

- 用 `pygame` 控制多旋翼无人机
- 支持 `physics` 和 `kinematic` 两种模式
- 支持 `body` 和 `ros-like` 两种速度接口风格
- 可以在启动时自动起飞，也可以退出时自动降落

默认连接：

- 端口：`41471`
- 默认实例名：`UAV`

最常用命令：

```powershell
python .\Multi_use\keyboard_control.py
```

常见变体：

```powershell
python .\Multi_use\keyboard_control.py --vehicle UAV2
python .\Multi_use\keyboard_control.py --mode kinematic
python .\Multi_use\keyboard_control.py --gain-profile soft
python .\Multi_use\keyboard_control.py --official-ros-values
```

按键：

- `Up/Down`：前进 / 后退
- `Left/Right`：左 / 右平移
- `W/S`：上升 / 下降
- `A/D`：左 / 右偏航
- `Space`：加速
- `ESC`：退出

两种模式的区别：

- `physics`：真正调用 AirSim 的运动 API，适合验证物理控制、接口连通性、机体响应。
- `kinematic`：直接改位姿，适合做可视化、场景走位、快速调相机，不等于真实飞控物理。

重要参数：

- `--mode {physics,kinematic}`：选择控制模式
- `--velocity-api {ros-like,body}`：`ros-like` 会把机体系输入转换成世界系速度，尽量贴近 AG ROS 控制链；`body` 直接走 `moveByVelocityBodyFrameAsync`
- `--gain-profile {none,soft,very-soft}`：对 `SimpleFlight` 的横向 PID 做运行时软化
- `--takeoff-altitude`：起飞到目标高度
- `--land-on-exit`：退出时自动降落
- `--official-ros-values`：直接套 AG 旧 `keyboard_ctrl.py` 的速度参数

适合做什么：

- 验证无人机是不是能被 API 控住
- 对比 `physics` / `kinematic` 差异
- 观察姿态、位置、偏航是否正常
- 快速看相机跟着无人机运动是否合理

## 2. car_keyboard_control.py

这个脚本可以：

- 用 `pygame` 控制汽车
- 支持前进、倒车、转向、手刹
- 显示当前速度、档位、转向和位姿

默认连接：

- 端口：`41461`
- 默认实例名：`Car`

最常用命令：

```powershell
python .\Multi_use\car_keyboard_control.py
```

常见变体：

```powershell
python .\Multi_use\car_keyboard_control.py --vehicle Car2
python .\Multi_use\car_keyboard_control.py --throttle 0.5 --steering 0.3
```

按键：

- `W`：前进
- `S`：倒车
- `A/D`：左 / 右打轮
- `Space`：手刹
- `ESC`：退出并停车

补充说明：

- 脚本已经显式处理倒挡，`S` 不会再因为只给负油门而“看起来还在往前拱”
- 适合先排查车体 API、转向、速度和档位是否正常

## 3. boat_keyboard_control.py

这个脚本可以：

- 用 `pygame` 控制船 / 水面载具
- 支持前进、倒退、转向、抛锚减速
- 显示当前速度、纵向速度 `u`、横向漂移速度 `v`、艏向角速度 `r` 和位姿

船会在地面平面上运动，不要求 UE 场景里有真实水体。运动模型是简化船舶平面三自由度模型，保留转向惯性和横向漂移，不做波浪、水流、浮力等水相互作用。

默认连接：

- 端口：`41481`
- 默认实例名：`Boat`

最常用命令：

```powershell
python .\Multi_use\boat_keyboard_control.py
```

常见变体：

```powershell
python .\Multi_use\boat_keyboard_control.py --vehicle Boat2
python .\Multi_use\boat_keyboard_control.py --throttle 0.5 --steering 0.3
```

按键：

- `W`：前进
- `S`：倒退
- `A/D`：左 / 右转向
- `Space`：抛锚 / 减速
- `ESC`：退出并停船

## 4. satellite_keyboard_control.py

这个脚本可以：

- 用 `pygame` 控制 `SimpleSatellite`
- 直接发送三维 NED 速度 `vx / vy / vz`
- 发送 `yaw_rate` 控制偏航角速度
- 松开按键时发送零速度，使卫星静止悬停

默认连接：

- 端口：`41491`
- 默认实例名：`Satellite`

最常用命令：

```powershell
python .\Multi_use\satellite_keyboard_control.py
```

常见变体：

```powershell
python .\Multi_use\satellite_keyboard_control.py --vehicle Satellite2
python .\Multi_use\satellite_keyboard_control.py --speed 50 --yaw-rate 1.0
```

按键：

- `W/S`：NED X 正 / 负方向
- `A/D`：NED Y 负 / 正方向
- `R/F`：上升 / 下降，其中 `vz` 为 NED 速度，正数表示向下
- `Q/E`：左 / 右偏航
- `ESC`：退出并发送零速度

## 5. space_mission_bridge.py

这个脚本把 TLE/SGP4、CSV 或 mock 数据源里的卫星状态同步到 LAESim 的 `SimpleSatellite` 模型。脚本负责卫星位置、局部 NED 和目标可见性计算，UE 只负责演示性显示。

默认连接：

- 端口：`41491`
- 默认实例名：`Satellite`

CSV 冒烟测试：

```powershell
conda activate <AirSim Python环境名>
python .\Multi_use\space_mission_bridge.py --provider csv --csv .\Multi_use\space_mission_sample.csv --vehicle Satellite --rate 1
```

TLE/SGP4 传播：

```powershell
conda activate <AirSim Python环境名>
pip install sgp4
python .\Multi_use\space_mission_bridge.py --provider tle --tle .\Multi_use\space_mission_sample.tle --vehicle Satellite --rate 2
```

常用显示模式：

- `scaled-ned`：把真实 NED 按比例缩放到 UE，默认水平和高度都乘以 `0.001`
- `fixed-overhead`：卫星固定在场景上方，只表现“天上有卫星”
- `subpoint-only`：显示星下点水平运动，高度固定
- `global-track`：把全球地面轨迹正交压缩到有限圆盘内，适合真实 TLE 的 UE 演示

注意：UE 中卫星模型的位置是演示坐标，不代表真实星地距离。真实距离、覆盖和可见性应使用桥接脚本输出。

刷新并校验当前 TLE：

```powershell
python .\Multi_use\update_tle.py --catalog-number 25544 --output .\.runtime\current_iss.tle
```

该工具会校验 TLE 行格式和校验和，原子更新输出文件，并在同目录写入包含来源 URL、下载时间和 TLE 历元的 JSON 元数据。实时脚本可用 `--max-tle-age-days` 检查历元偏差，用 `--require-fresh-tle` 在 TLE 过期时直接退出。

任务目标与可见性演示：

```powershell
conda activate <AirSim Python环境名>
python .\Multi_use\space_mission_bridge.py --provider mock --vehicle Satellite --target Island:22.591164:113.975317:0 --rate 2 --print-every 1
```

输出 JSONL 报告：

```powershell
python .\Multi_use\space_mission_bridge.py --provider mock --vehicle Satellite --target Island:22.591164:113.975317:0 --mission-report-jsonl .\space_report.jsonl
```

离线任务分析：

```powershell
python .\Multi_use\space_mission_analyzer.py --mission .\Multi_use\space_mission.example.json --out .\Multi_use\space_mission_report --print-summary
```

该命令会生成区域网格覆盖、覆盖窗口、重访时间、逐时间步样本、GeoJSON 可视化文件，以及供 ns-3 联动使用的链路启停 JSON。

Orekit 精确事件窗口验证：

```powershell
conda activate laesim_space
$env:PYTHONNOUSERSITE="1"
python .\Multi_use\space_mission_analyzer.py --mission .\Multi_use\space_mission_orekit.example.json --out .\Multi_use\space_mission_orekit_report --print-summary
```

该示例使用 Orekit 的仰角事件检测生成升起/落下窗口。检查 `windows.csv` 的 `method=orekit-events`，可确认窗口不是由固定 `step_s` 采样边界近似得到。

专业后端检查：

```powershell
python .\Multi_use\space_backend_probe.py
```

GMAT 离线任务设计交接包：

```powershell
python .\Multi_use\space_mission_export_gmat.py --mission .\Multi_use\space_mission.example.json --out .\Multi_use\space_mission_gmat.script
```

Basilisk 或自定义姿态 CSV 接入：

```powershell
python .\Multi_use\space_mission_bridge.py --provider csv --csv .\Multi_use\space_mission_sample.csv --attitude-csv .\Multi_use\space_mission_attitude_sample.csv --vehicle Satellite
```

## 6. sensor_probe.py

这个脚本可以：

- 读取 `settings.json`
- 枚举指定实例上的相机和雷达配置
- 抓取一帧相机图像
- 抓取一帧雷达点云
- 保存报告、图片、深度图和点云

默认行为：

- 默认读取 `C:\Users\<用户名>\Documents\AirSim\settings.json`
- 默认把输出保存到当前目录下的 `sensor_probe_outputs`

最常用命令：

```powershell
python .\Multi_use\sensor_probe.py
```

只检查配置，不抓数据：

```powershell
python .\Multi_use\sensor_probe.py --list-only
```

只看指定实例：

```powershell
python .\Multi_use\sensor_probe.py --vehicle UAV --vehicle Car
```

输出内容：

- `sensor_probe_report.json`
- `png` 图片
- `pfm` 深度图
- `xyz` 点云

适合做什么：

- 快速检查 `settings.json` 是否和场景实际生成结果一致
- 确认相机名字、雷达名字、图像类型是否能正确读取
- 在不引入 ROS 的前提下验证传感器链路

## 7. scene_map_tools.py

这个脚本用于测试“图片地图平面”功能，不依赖 ROS，走 `41451` 这个 CV / 世界级 RPC 端口。它可以加载地图、卸载地图、查询地图尺寸与位姿，也可以做像素坐标和 AirSim 世界坐标的转换。

加载一张图片作为带碰撞的平面地图：

```powershell
python .\Multi_use\scene_map_tools.py load "$env:USERPROFILE\Documents\AirSim\maps\demo_map.png" --meters-per-pixel 0.05 --center-x 0 --center-y 0 --z 0 --yaw 0
```

查询当前地图：

```powershell
python .\Multi_use\scene_map_tools.py info
```

像素坐标转世界坐标：

```powershell
python .\Multi_use\scene_map_tools.py to-world --u 800 --v 600 --z 0
```

世界坐标转像素坐标：

```powershell
python .\Multi_use\scene_map_tools.py to-pixel --x 10 --y 0
```

卸载当前地图：

```powershell
python .\Multi_use\scene_map_tools.py unload
```

## 8. 建议的使用顺序

如果第一次拿到工程，建议按这个顺序试：

1. 先用 `sensor_probe.py --list-only` 检查配置。
2. 再用 `sensor_probe.py` 抓一帧图像和点云。
3. 然后用 `keyboard_control.py` 验证无人机。
4. 再用 `car_keyboard_control.py` 验证汽车。
5. 再用 `boat_keyboard_control.py` 验证船。
6. 再用 `satellite_keyboard_control.py` 验证卫星。
7. 如果要测试 2D 地图场景，用 `scene_map_tools.py info` 或 `scene_map_tools.py load ...` 验证 SceneMap。
