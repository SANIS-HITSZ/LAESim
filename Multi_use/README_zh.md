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

## 3. sensor_probe.py

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

## 4. 建议的使用顺序

如果第一次拿到工程，建议按这个顺序试：

1. 先用 `sensor_probe.py --list-only` 检查配置。
2. 再用 `sensor_probe.py` 抓一帧图像和点云。
3. 然后用 `keyboard_control.py` 验证无人机。
4. 最后用 `car_keyboard_control.py` 验证汽车。
