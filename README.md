# LAESim 部署说明

`LAESim` 是在 [Microsoft AirSim](https://github.com/microsoft/AirSim) 基础上整理、适配和扩展的仿真工程，重点面向 UE 4.27、Windows API 示例、多车多机配置以及 WSL / ROS Noetic 联调场景。

感谢 AirSim 项目和原作者团队提供的高保真无人机/车辆仿真平台、Unreal 插件架构、RPC API、Python/C++ 客户端以及 ROS 相关能力。本项目保留并延续 AirSim 的开源基础，相关许可请参考仓库中的 [LICENSE](LICENSE)。如果在论文或项目中使用了 AirSim 相关能力，也建议引用 AirSim 原论文：

```bibtex
@inproceedings{airsim2017fsr,
  author = {Shital Shah and Debadeepta Dey and Chris Lovett and Ashish Kapoor},
  title = {AirSim: High-Fidelity Visual and Physical Simulation for Autonomous Vehicles},
  year = {2017},
  booktitle = {Field and Service Robotics},
  eprint = {arXiv:1705.05065},
  url = {https://arxiv.org/abs/1705.05065}
}
```

这份文档面向接手 `LAESim` 的使用者，重点说明源码仓库如何编译、如何接入 UE、如何继续使用 Windows API 和 ROS。当前这套工程已经不是只在单机环境里可运行的临时目录，而是一套可以继续编译、继续接入 UE 4.27、继续在 WSL / ROS Noetic 中联调的源码工程。

## 1. 交付

仓库根目录自带：

- `PreparePortableSource.ps1`
- `BuildAirSimRelease.bat`
- `build.cmd`
- `Unreal\Environments\Blocks\BuildBlocksEditor.bat`

推荐先导出一份干净源码：

```powershell
powershell -ExecutionPolicy Bypass -File .\PreparePortableSource.ps1 -DestinationRoot ..\LAESim_portable
```

然后把仓库同级目录下的 `LAESim_portable` 交给对方。

## 2. 电脑需要准备什么

推荐至少具备以下环境：

- Windows
- Unreal Engine 4.27
- Visual Studio 2019 或 2022（记得勾选 Windows SDK 10.0.19041.0）
- C++ 桌面开发工具链
- PowerShell
- 如果需要 ROS：WSL2 + Ubuntu 20.04 + ROS Noetic

补充说明：

- `VS2019`、`VS2022` 都可以使用。
- 如果机器已经装好 `VS2022`，不需要为了这套工程强制回退。
- 如果要在 `UE 4.27` 环境里尽量减少额外变量，仍然优先推荐 `VS2019`。

## 3. Windows 侧如何编译源码

有两种等价方式。

### 3.1 手动版

打开 `x64 Native Tools Command Prompt for VS 2019/2022`，进入仓库根目录后执行：

```cmd
build.cmd --Release
```

### 3.2 封装版

普通 `cmd`、`PowerShell` 或 `x64 Native Tools Command Prompt` 都可以，在仓库根目录执行：

```cmd
BuildAirSimRelease.bat
```

`BuildAirSimRelease.bat` 会自动查找 VS、自动调用 `VsDevCmd.bat`，然后再去运行 `build.cmd --Release`。它和手动版的构建结果没有本质区别，只是入口更省事。

如果是在普通 PowerShell 里遇到执行策略或 `profile.ps1` 相关提示，优先改用 `cmd` 或 `x64 Native Tools Command Prompt`，通常更省事。

## 4. 编完后如何接入 UE 项目

运行完 `build.cmd --Release` 或 `BuildAirSimRelease.bat` 后，可以把下面这个插件目录复制到 UE 项目里：

```text
<LAESim根目录>\Unreal\Plugins\AirSim
```

目标位置通常是：

```text
<你的UE项目>\Plugins\AirSim
```

推荐流程：

1. 先把 `LAESim` 本体编好。
2. 把 `Unreal\Plugins\AirSim` 整个目录复制到 UE 项目 `Plugins` 下。
3. UE 项目最好是 `C++` 项目，而不是纯蓝图项目。
4. 为该 UE 项目生成工程文件。
5. 编译该项目的 `Development Editor`。
6. 在 UE 里设置 `PlayerStart` 和 `AirSimGameMode`。
7. 准备 `C:\Users\<用户名>\Documents\AirSim\settings.json`。

如果只是想先验证官方自带 `Blocks` 示例环境，再额外运行：

```cmd
Unreal\Environments\Blocks\BuildBlocksEditor.bat
```

这里要特别说明：`BuildBlocksEditor.bat` 负责编 `Blocks` 示例工程，不是替代 `build.cmd`。

如果 UE 安装在非标准目录，例如：

```text
D:\Epic\UE\UE_4.27
```

当前版本的 `ResolveUnrealBuildToolPath.ps1` 已经兼容这类路径。
如果自动探测仍然失败，再手动设置：

```cmd
set UNREAL_ENGINE_ROOT=D:\Epic\UE\UE_4.27
```

## 5. 运行时最重要的配置文件

Windows 侧真正生效的是这份文件：

```text
C:\Users\<用户名>\Documents\AirSim\settings.json
```

如果需要现成模板，直接看：

- `how_to_use_settings\README_zh.md`
- `how_to_use_settings\settings_single_uav_with_sensors.json`
- `how_to_use_settings\settings_single_car_with_sensors.json`
- `how_to_use_settings\settings_airground_3uav_3car_with_sensors.json`

这些模板已经把常用相机、雷达、ROS 发布项写好，并且对车的 `magnetometer/barometer` 做了显式规避。

## 6. Windows API 示例代码在哪里

仓库中已经带了一套不依赖 ROS、直接通过 AirSim Python API 控制和采样的工具，目录是：

```text
Multi_use
```

详见：

- `Multi_use\README_zh.md`

里面包含：

- `keyboard_control.py`：无人机 `pygame` 控制
- `car_keyboard_control.py`：汽车 `pygame` 控制
- `sensor_probe.py`：按 `settings.json` 抓取相机和雷达数据

## 7. ROS 示例代码在哪里

ROS 示例在：

```text
ros\src\example
```

详见：

- `ros\src\example\README_zh.md`

里面已经拆成几类小工具：

- `connect_ue_ros.sh`：一键连接 Windows 上正在运行的 UE / AirSim
- `keyboard_uav_ros.py`：ROS + `pygame` 控无人机
- `keyboard_car_ros.py`：ROS + `pygame` 控汽车
- `vehicle_state_monitor_ros.py`：查看各实例状态
- `sensor_config_report_ros.py`：读取 `settings.json` 并核对 ROS 话题
- `camera_record_ros.py`：保存 ROS 相机数据
- `lidar_record_ros.py`：保存 ROS 雷达点云

## 8. WSL / ROS 部署要点

建议特别强调下面几件事：

1. 不要只拷 `ros` 子目录。
2. 要把整个 `LAESim` 放进 WSL 的 ext4 路径，比如 `/home/ag/LAESim`。
3. 在 WSL 中编译：

```bash
cd ~/LAESim/ros
catkin_make -DCMAKE_C_COMPILER=/usr/bin/gcc-8 -DCMAKE_CXX_COMPILER=/usr/bin/g++-8
source devel/setup.bash
```

4. 再连接 Windows 上的 UE：

```bash
bash src/example/connect_ue_ros.sh
```

如果是 `AirGround` 混合场景，端口约定是：

- `41451`：CV / 通用
- `41461`：Car
- `41471`：Multirotor

## 9. 当前已经验证过什么

到目前为止，已经验证过的链路包括：

- `LAESim` 本体 Windows 编译
- 插件接入 UE 4.27
- `AirGround` 多无人机 + 多汽车
- Windows 侧 API-only 控制
- 相机 / 雷达数据抓取
- WSL + ROS Noetic 连接 UE
- ROS 侧状态查看、键盘控制、相机 / 雷达录制

## 10. 建议先看哪些文档

如果第一次接触这套工程，建议按这个顺序阅读：

1. 先看本文件，完成编译和 UE 接入。
2. 再看 `how_to_use_settings\README_zh.md`，挑一份现成 `settings` 模板。
3. 如果只想先验证 Windows 侧，继续看 `Multi_use\README_zh.md`。
4. 如果需要 ROS，再看 `ros\src\example\README_zh.md`。

## 致谢与来源

本项目基于 AirSim 生态进行整理和扩展。感谢 Microsoft Research、AirSim 原作者团队以及社区贡献者提供的开源仿真平台和长期积累的工程基础。

- AirSim 官方仓库：[github.com/microsoft/AirSim](https://github.com/microsoft/AirSim)
- AirSim 官方文档：[microsoft.github.io/AirSim](https://microsoft.github.io/AirSim/)
- AirSim 论文：[AirSim: High-Fidelity Visual and Physical Simulation for Autonomous Vehicles](https://arxiv.org/abs/1705.05065)
- Project AirSim 相关仓库：[github.com/iamaisim/ProjectAirSim](https://github.com/iamaisim/ProjectAirSim)
