# LAESim 部署说明

这份文档面向接手 `LAESim` 的使用者，重点说明源码仓库如何编译、如何接入 UE、如何继续使用 Windows API 和 ROS。当前这套工程已经不是只在单机环境里可运行的临时目录，而是一套可以继续编译、继续接入 UE 4.27、继续在 WSL / ROS Noetic 中联调的源码工程。

## 当前版本要点

- 支持 `AirGround` 混合多载具仿真：多无人机、多车、多船可以同时在同一个 `settings.json` 中配置。
- 新增 `SimpleBoat` / `PhysXBoat` 船载具类型，默认 API 端口为 `41481`。
- 船具备 Python API、ROS topic、示例脚本、settings 模板和传感器配置链路。
- 默认船模型为 052B Boat，源码资产放在 `Unreal\Assets\Boat\Models\Boat`，构建时自动复制到 AirSim 插件 Content。
- 新增 `SceneMap` 图片地图功能：可在 `settings.json` 启动加载图片为可碰撞平面地图，支持任意长宽比卫星图、`GeoReference` GPS 配准和按 GPS / 像素 / 米制坐标出生，也可通过 Python / ROS 在运行时切换、查询和做坐标转换。
- GitHub 上传版保留 AirSim 插件基础 Content 和 StarterContent，排除编译产物、ROS build/devel、AirLib deps、UE Intermediate/Binaries、高模 SUV 和 Boat 构建产物。

更多细节：

- `如何加入新的载具类型.md`
- `如何加入图片场景地图功能.md`
- `如何将工程简化上传github.md`
- `how_to_use_settings\README_zh.md`

## 1. 交付

仓库根目录自带：

- `PreparePortableSource.ps1`
- `BuildAirSimRelease.bat`
- `build.cmd`
- `Unreal\Environments\Blocks\BuildBlocksEditor.bat`

推荐先导出一份干净源码：

```powershell
powershell -ExecutionPolicy Bypass -File .\PreparePortableSource.ps1 -DestinationRoot D:\LAESim_portable
```

然后把 `D:\LAESim_portable` 交给对方。

## 2. 电脑需要准备什么（去知乎看Airsim的安装教程的配置就好了，做好适配了）

推荐至少具备以下环境：

- Windows
- Unreal Engine 4.27
- Visual Studio 2019 或 2022（记得勾选windows SDK 10.019041.0）
- C++ 桌面开发工具链
- PowerShell
- 如果需要 ROS：WSL2 + Ubuntu 20.04 + ROS Noetic

补充说明：

- `VS2019`、`VS2022` 都可以使用
- 如果机器已经装好 `VS2022`，不需要为了这套工程强制回退
- 如果要在 `UE 4.27` 环境里尽量减少额外变量，仍然优先推荐 `VS2019`

## 3. Windows 侧如何编译源码

有两种等价方式。

注意：由于 AirSim 的构建脚本（build.cmd）在后台需要调用 PowerShell 执行下载和解压任务，如果遇到“禁止执行脚本”的错误，请以管理员身份打开 PowerShell 并运行以下命令：
#### 解锁 PowerShell 脚本执行权限
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine

说明：此操作允许运行本地编写的脚本和由受信任发行者签名的远程脚本，是编译 AirSim 插件的必要前提，要不然git下来的项目无法正常编译。

### 3.1 手动版

打开 `x64 Native Tools Command Prompt for VS 2019/2022`：

```cmd
cd /d D:\LAESim
build.cmd --Release
```

### 3.2 封装版

普通 `cmd`、`PowerShell` 或 `x64 Native Tools Command Prompt` 都可以：

```cmd
cd /d D:\LAESim
BuildAirSimRelease.bat
```

`BuildAirSimRelease.bat` 会自动查找 VS、自动调用 `VsDevCmd.bat`，然后再去运行 `build.cmd --Release`。它和手动版的构建结果没有本质区别，只是入口更省事。

如果是在普通 PowerShell 里遇到执行策略或 `profile.ps1` 相关提示，优先改用 `cmd` 或 `x64 Native Tools Command Prompt`，通常更省事。

编译结束碰到Unreal\Environments\Blocks的“文件未找到”之类的问题不用管，用不到的。

### 3.3 Boat 默认模型资源

Boat 的 052B 默认模型不需要在 `settings.json` 里指定。源码仓库里保留的是资产源目录：

```text
<LAESim根目录>\Unreal\Assets\Boat\Models\Boat
```

运行 `build.cmd --Release` 或 `BuildAirSimRelease.bat` 时，脚本会把它复制到插件内容目录：

```text
<LAESim根目录>\Unreal\Plugins\AirSim\Content\Models\Boat
```

`BoatPawn.cpp` 运行时加载的是 `/AirSim/Models/Boat/Type_052B_Destroyer_Combined`。所以 GitHub 源码版应保留 `Unreal\Assets\Boat`，不需要把构建后生成的 `Unreal\Plugins\AirSim\Content\Models\Boat` 当成源码目录单独上传。

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
2. 把 `Unreal\Plugins\AirSim` 整个目录复制到 UE 项目 `Plugins` 下。（没有就自己建一个）
3. UE 项目最好是 `C++` 项目，而不是纯蓝图项目。
4. 放好Plugins\AirSim之后，重新点击进入该UE项目，会弹窗显示需要新编译项目，点击编译即可，为该 UE 项目生成工程文件。
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
- `how_to_use_settings\settings_airground_2uav_1car_1boat_with_sensors.json`
- `how_to_use_settings\settings_scene_map_1uav_1car_1boat.json`
- `how_to_use_settings\settings_satellite_map_gps_start.json`

这些模板已经把常用相机、雷达、ROS 发布项写好，并且对车和船的 `magnetometer/barometer` 做了显式规避。

如果要做纯视觉 VIO + 2D 地图匹配定位仿真，可以使用 `SceneMap` 配置在启动时把一张干净卫星图变成 UE 里的可碰撞平面地图，并用 `StartOnSceneMap` 指定载具在地图像素坐标、地图局部米制坐标或 GPS 经纬度上的出生位置。卫星图可以通过 `GeoReference` 做 GPS 配准。详见：

- `如何加入图片场景地图功能.md`
- `how_to_use_settings\settings_scene_map_1uav_1car_1boat.json`
- `how_to_use_settings\settings_satellite_map_gps_start.json`

### 5.1 图片地图 SceneMap 快速导入

最小流程：

1. 准备一张 Windows 能访问的图片，例如 `C:/Users/32749/Documents/AirSim/maps/test1.png`。
2. 在 `settings.json` 顶层增加 `SceneMap`，填写 `ImagePath`、`MetersPerPixel`、`PixelCoordinateFrame`、`CollisionEnabled`。
3. 如果要按 GPS 出生，继续填写 `GeoReference`，把一个已知参考点的经纬度和图片像素坐标写进去。
4. 在每个载具里用 `StartOnSceneMap` 写出生位置；如果不写，仍然使用旧的 `X/Y/Z/Yaw`。

关键参数：

- `ImagePath`：图片绝对路径。UE 在 Windows 上运行，所以不要写 WSL 的 `/home/...`。
- `MetersPerPixel`：每个像素代表多少米，是 2D 地图匹配的比例尺。
- `PixelCoordinateFrame`：卫星图 / Google Earth 推荐 `NorthUp`；旧测试图可用 `NED`。
- `CollisionEnabled`：是否给地图平面碰撞。车、船要站在图上时保持 `true`。
- `ReferenceLatitude / ReferenceLongitude`：GPS 参考点经纬度，决定 GPS 如何配准到图片。
- `ReferenceU / ReferenceV`：参考点在图片中的像素坐标，左上角为 `(0, 0)`。
- `ReferenceAltitude`：参考点海拔；对二维平面定位不重要，不影响水平出生位置，可以写 Google Earth 海拔、场地平均海拔或 `0`。
- `Height`：载具离地图平面的高度，只影响垂直方向。无人机常写 `5` 或 `10`，车和船通常写 `0`。

出生方式：

- 旧方式 `X/Y/Z/Yaw`：直接写 AirSim NED 世界坐标，不依赖图片地图。
- 新方式 `StartOnSceneMap`：按地图出生，会覆盖同一载具里的旧 `X/Y/Z/Yaw`。
- `CoordinateType = Pixel`：用图片像素 `U/V` 出生。
- `CoordinateType = Meters`：用地图中心为原点的米制 `MapX/MapY` 出生。
- `CoordinateType = GPS`：用 `Latitude/Longitude/Altitude` 出生，需要 `GeoReference.Enabled = true`。

`NorthUp` 卫星图的 GPS 出生已按当前 UE 显示补偿修正：内部使用 `local_x=east, local_y=-north`。同经度时纬度减小会沿图面右方移动，对应像素 `U` 增大。

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
- `boat_keyboard_control.py`：船 / 水面载具 `pygame` 控制
- `scene_map_tools.py`：加载、查询和坐标转换图片地图
- `sensor_probe.py`：按 `settings.json` 抓取相机和雷达数据

船的运动模型是地面平面上的简化船舶三自由度模型：纵向速度 `u`、横向漂移速度 `v`、艏向角速度 `r`。它不要求 UE 关卡里有真实水面，也不模拟波浪、水流、浮力，只适合把蓝色地面区域当作水域来跑船舶运动和传感器链路。

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
- `keyboard_boat_ros.py`：ROS + `pygame` 控船
- `vehicle_state_monitor_ros.py`：查看各实例状态
- `sensor_config_report_ros.py`：读取 `settings.json` 并核对 ROS 话题
- `camera_record_ros.py`：保存 ROS 相机数据
- `lidar_record_ros.py`：保存 ROS 雷达点云

图片地图功能的 ROS 入口是：

- 话题：`/airsim_node/scene_map/info`
- 服务：`/airsim_node/scene_map/load`
- 服务：`/airsim_node/scene_map/unload`
- 服务：`/airsim_node/scene_map/get_info`
- 服务：`/airsim_node/scene_map/scene_map_to_world`
- 服务：`/airsim_node/scene_map/world_to_scene_map`

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

如果当前 WSL 没有 `/usr/bin/g++-8`，可以先直接用默认编译器：

```bash
catkin_make
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
- `41481`：Boat

## 9. 常见编译问题

### 9.1 找不到 Eigen/Dense

如果 Windows 编译时报：

```text
AirLib\include\common\VectorMath.hpp(14,10): error C1083: 无法打开包括文件: "Eigen/Dense": No such file or directory
```

说明 `AirLib\deps\eigen3` 目录存在但不完整，通常是上一次下载 / 解压 Eigen 中断后留下了空目录。旧版 `build.cmd` 只判断 `AirLib\deps\eigen3` 是否存在，会误以为依赖已经准备好。

当前版本已经修复为检查真正的头文件：

```text
AirLib\deps\eigen3\Eigen\Dense
```

如果遇到这个问题，可以先删除残缺目录，再重新运行编译：

```powershell
Remove-Item -LiteralPath .\AirLib\deps\eigen3 -Recurse -Force
.\BuildAirSimRelease.bat
```

也可以直接重新运行新版 `BuildAirSimRelease.bat`，脚本会在发现 `Eigen\Dense` 缺失时自动清理并重新下载 Eigen。

### 9.2 Invoke-WebRequest 下载中断或 zip 损坏

如果编译过程中出现：

```text
iwr : 从传输流收到意外的 EOF 或 0 个字节
New-Object : 找不到中央目录结尾记录
iwr : 基础连接已经关闭: 发送时发生错误
```

通常是网络或代理导致依赖 zip 没下载完整。`car_assets.zip` 下载失败时只会回退到默认车模型，一般不影响继续编译；`eigen-3.3.7.zip` 下载失败会导致 AirLib 编译失败。

处理办法：

```powershell
Remove-Item -LiteralPath .\eigen3.zip -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\suv_download_tmp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\AirLib\deps\eigen3 -Recurse -Force -ErrorAction SilentlyContinue
.\BuildAirSimRelease.bat
```

如果仍然失败，先确认代理端口可用，或者换一个网络后重新运行同一条编译命令。

## 10. 当前已经验证过什么

到目前为止，已经验证过的链路包括：

- `LAESim` 本体 Windows 编译
- 插件接入 UE 4.27
- 多无人机 + 多汽车 + 多船
- Windows 侧 API-only 控制
- 相机 / 雷达数据抓取
- WSL + ROS Noetic 连接 UE
- ROS 侧状态查看、键盘控制、相机 / 雷达录制

## 11. 建议先看哪些文档

如果第一次接触这套工程，建议按这个顺序阅读：

1. 先看本文件，完成编译和 UE 接入。
2. 再看 `how_to_use_settings\README_zh.md`，挑一份现成 `settings` 模板。
3. 如果只想先验证 Windows 侧，继续看 `Multi_use\README_zh.md`。
4. 如果需要 ROS，再看 `ros\src\example\README_zh.md`。
