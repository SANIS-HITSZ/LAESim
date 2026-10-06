# Wireless City Factory

Wireless City Factory 是一个本地运行的程序化城市与无线仿真配置平台。主要操作都在网页界面中完成：配置城市、部署基站、设置无人机任务、生成三维场景，并可选计算 Sionna RT 信道地图或接入 LAESim/Unreal Engine。

## 1. 首次安装

需要 Windows 和 Python 3.10 或更高版本。解压后，在工程根目录打开 PowerShell，执行：

```powershell
py -3.10 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
& ".\.venv\Scripts\python.exe" -m pytest
```

测试通过后即可启动基础仿真平台。

## 2. 启动仿真平台

双击：

```text
scripts\StartVisualizer.bat
```

程序会自动打开浏览器。默认地址为：

```text
http://127.0.0.1:8765/
```

若该端口被占用，终端会显示实际使用的新地址。不要关闭启动程序的终端窗口；使用结束后在窗口中按 `Ctrl+C` 停止服务。

## 3. 在网页中使用

推荐按页面左侧标签从左到右操作。

### 城市

选择城市预设、道路形态和随机种子，也可以修改尺寸、道路、建筑密度及高度等参数。相同参数和随机种子可以复现相同场景。

### 基站

选择低频广域、Sub-6 GHz、4.9 GHz 通感或毫米波等预设，也可以自定义频率、带宽、发射功率、站点密度、天线高度、下倾角和扇区数量。

### 无线与无人机

按需开启 Sionna RT，选择计算质量和 RSS/SINR 热力图。未安装 Sionna RT 时保持关闭，城市和基站三维可视化仍可正常使用。

### 任务

设置起点、终点、飞行高度和通信约束。可以自动选择可复现任务点，也可以在地图点选或直接输入坐标。运行前检查会提示任务是否满足边界、碰撞和无线连通条件。

### LAESim

安装并配置 LAESim、UE 4.27 和 AirSim 后，可以把当前生成结果导入 UE，在 LAESim 中执行无人机任务。基础验收不要求开启这一功能。

完成配置后，点击左下角的生成按钮。若启用了 Sionna RT，按钮会显示为“生成城市并计算无线”。生成成功后，可以在右侧旋转、缩放、点选对象、开关图层和查看无线结果，也可以使用页面顶部按钮导出配置、场景、基站清单和 OBJ 模型。

生成结果默认保存在：

```text
%LOCALAPPDATA%\WirelessCityFactory\outputs
```

## 4. 其他运行方式

PowerShell 也可以直接启动：

```powershell
$env:PYTHONPATH = "$PWD\src"
& ".\.venv\Scripts\python.exe" -m wireless_city_factory.web_app
```

Sionna RT 需要另外安装兼容的 NVIDIA 驱动、Sionna RT 2.x 和 Mitsuba CUDA 环境。LAESim 闭环需要 LAESim V1.5、Unreal Engine 4.27、Visual Studio C++ 工具链和 AirSim 插件。这些功能的安装、导入和任务执行步骤见完整中文说明：

- [可视化平台完整使用说明](docs/visualizer.md)
- [通信约束航迹规划与 LAESim 接入](docs/connectivity_aware_planning.md)
- [论文 use case 说明](docs/paper_use_case.md)

命令行生成城市、批量计算无线地图和 UE 导入脚本主要用于开发、复现实验与调试，普通使用者优先在网页仿真平台中完成配置。

## 5. 当前范围

当前版本支持平地、静态建筑、典型基站预设、离线信道地图和定高无人机任务。Sionna RT 在线阶段查询预先计算的静态无线地图，不会在每个飞行时刻重新执行射线追踪。地形、动态障碍、实时动态信道和训练算法不属于本版本范围。

工程源码采用 MIT License。第三方 LAESim、AirSim、Unreal Engine、Sionna RT 和相关资产遵循各自许可证。
