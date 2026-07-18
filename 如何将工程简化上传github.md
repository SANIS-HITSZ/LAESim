# 如何将工程简化上传 GitHub

本文记录这次从工作工程 `E:\AAA_project\CETC\LAESim` 生成 GitHub 上传版 `E:\AAA_project\CETC\LAESim_upload_gitclean` 的思路和操作。目标是得到一个干净、可维护、尽量接近旧仓库 `E:\AAA_project\CETC\AirSim_Multi-main` 风格的源码包，而不是把本机编译产物和 UE 项目部署产物一起上传。

## 1. 最终选择

本次最终采用：

```text
E:\AAA_project\CETC\LAESim_upload_gitclean
```

当前修正版大小约为：

```text
284.71 MB
```

对比：

```text
旧 GitHub 基线 AirSim_Multi-main：193.61 MB
完整干净版 AirSim_Multi_upload_gitclean：284.71 MB
旧的偏臃肿版 AirSim_Multi_upload_clean：676.38 MB
```

`gitclean_min` 早期曾尝试做到约 218 MB，但实践证明从 GitHub 新 clone 后进入 UE 会因为缺少 AirSim 插件基础 Content 而崩溃。之后又发现排除 `StarterContent` 虽然不影响运行，但会触发 CDO 默认属性警告。现在修正版保留必要的插件基础 Content 和 StarterContent，并继续排除高模 SUV、Boat / Satellite 构建产物和编译产物。

## 2. 为什么不用工作目录直接上传

`LAESim` 是工作目录，已经经历过编译、UE 插件部署、资源导入等操作，里面会混入大量不适合上传 GitHub 的内容，例如：

- `AirLib/deps`
- `AirLib/lib`
- `AirLib/temp`
- `MavLinkCom/lib`
- `external/rpclib`
- `ros/build`
- `ros/devel`
- `Unreal/Plugins/AirSim/Source/AirLib`
- `Binaries`
- `Intermediate`
- `Saved`
- `DerivedDataCache`
- UE 项目生成的 `.sln`、缓存、日志

这些目录可以由 `build.cmd`、`BuildAirSimRelease.bat`、UE 编译或 ROS 编译重新生成，不应该作为源码上传。

## 3. 模型和插件内容的取舍

AirSim 默认无人机和车使用插件内容路径：

```text
/AirSim/Blueprints/BP_FlyingPawn
/AirSim/VehicleAdv/Vehicle/VehicleAdvPawn
/AirSim/VehicleAdv/SUV/SuvCarPawn
```

但是旧的 `AirSim_Multi-main` 并没有上传完整的：

```text
Unreal\Plugins\AirSim\Content
```

早期 `gitclean_min` 曾采用旧仓库风格，不上传整包插件 Content。这样虽然可以少约 66 MB，但从 GitHub 新下载后会缺少默认无人机 / 车 / 相机 / HUD / 物理材质等资源。

实际验证中，进入 UE 项目时出现过类似崩溃：

```text
UE4Editor_AirSim!UAirBlueprintLib::LoadObject()
UE4Editor_AirSim!ACarPawn::ACarPawn()
```

原因是 `CarPawn` 会加载这些资源：

```text
/AirSim/Blueprints/BP_PIPCamera
/AirSim/VehicleAdv/PhysicsMaterials/Slippery
/AirSim/VehicleAdv/PhysicsMaterials/NonSlippery
/AirSim/VehicleAdv/Sound/Engine_Loop_Cue
```

因此 GitHub 版必须保留 `Unreal/Plugins/AirSim/Content` 中的基础资源。当前保留：

```text
Unreal/Plugins/AirSim/Content/Blueprints
Unreal/Plugins/AirSim/Content/HUDAssets
Unreal/Plugins/AirSim/Content/Models
Unreal/Plugins/AirSim/Content/StarterContent
Unreal/Plugins/AirSim/Content/VehicleAdv
Unreal/Plugins/AirSim/Content/Weather
```

其中 `StarterContent` 也需要保留。否则虽然插件能运行，但 UE 会在进入工程时弹默认属性警告，例如：

```text
CDO Constructor (SimModeBase): Failed to find ParticleSystem'/AirSim/StarterContent/Particles/P_Explosion.P_Explosion'
加载失败 /AirSim/StarterContent/Materials/M_Tech_Hex_Tile_Pulse...
```

原因是 `SimModeBase.cpp` 和相关 UE 资产依赖了 StarterContent 里的爆炸粒子、材质和贴图。为避免每次启动 UE 都报默认属性警告，GitHub 版应保留整个 `Unreal/Plugins/AirSim/Content/StarterContent`。

同时继续排除：

```text
Unreal/Plugins/AirSim/Content/VehicleAdv/SUV
Unreal/Plugins/AirSim/Content/Models/Boat
Unreal/Plugins/AirSim/Content/Models/Satellite
```

其中 `VehicleAdv/SUV` 由 `build.cmd` 下载，`Models/Boat` 由 `Unreal/Assets/Boat` 构建时复制，`Models/Satellite` 由 `Unreal/Assets/Satellite` 构建时复制。插件 Content 里的 `Models/Boat` 和 `Models/Satellite` 是部署结果，不是源码入口。

## 4. Boat 模型如何保留

不要把构建后生成的 Boat 插件目录当作源码上传：

```text
Unreal\Plugins\AirSim\Content\Models\Boat
```

本工程采用源码资产目录：

```text
Unreal\Assets\Boat\Models\Boat
```

该目录中包含 052B Boat 的 `.uasset`、材质和贴图资源。`build.cmd` 中已经加入同步逻辑：

```cmd
IF EXIST Unreal\Assets\Boat\Models\Boat (
    IF NOT EXIST Unreal\Plugins\AirSim\Content\Models mkdir Unreal\Plugins\AirSim\Content\Models
    robocopy /MIR Unreal\Assets\Boat\Models\Boat Unreal\Plugins\AirSim\Content\Models\Boat /njh /njs /ndl /np
    IF ERRORLEVEL 8 goto :buildfailed
)
```

也就是说：

- GitHub 上传：保留 `Unreal/Assets/Boat/Models/Boat`
- 编译/部署后运行：由脚本复制到 `Unreal/Plugins/AirSim/Content/Models/Boat`
- 运行时加载：`BoatPawn.cpp` 固定加载 `/AirSim/Models/Boat/Type_052B_Destroyer_Combined`

## 4.1 Satellite 模型如何保留

Satellite 和 Boat 使用同样的资源保留方式。不要把构建后生成的 Satellite 插件目录当作源码上传：

```text
Unreal\Plugins\AirSim\Content\Models\Satellite
```

本工程采用源码资产目录：

```text
Unreal\Assets\Satellite\Models\Satellite
```

该目录中包含卫星 OBJ、贴图、材质和已经导入 UE 后得到的 `.uasset`。`build.cmd` 中已经加入同步逻辑：

```cmd
IF EXIST Unreal\Assets\Satellite\Models\Satellite (
    IF NOT EXIST Unreal\Plugins\AirSim\Content\Models mkdir Unreal\Plugins\AirSim\Content\Models
    robocopy /MIR Unreal\Assets\Satellite\Models\Satellite Unreal\Plugins\AirSim\Content\Models\Satellite /njh /njs /ndl /np
    IF ERRORLEVEL 8 goto :buildfailed
)
```

也就是说：

- GitHub 上传：保留 `Unreal/Assets/Satellite/Models/Satellite`
- 编译/部署后运行：由脚本复制到 `Unreal/Plugins/AirSim/Content/Models/Satellite`
- 运行时加载：`SatellitePawn.cpp` 固定加载 `/AirSim/Models/Satellite/10477_Satellite_v1_L3`
- `PreparePortableSource.ps1` 会保留 `Unreal/Assets` 下的模型 `.obj`，但仍排除其他位置的 C++ 编译 `.obj`

`settings.json` 中只需要写：

```json
"VehicleType": "SimpleSatellite"
```

不需要写 Satellite 模型路径。

## 5. 生成最小上传版的推荐流程

先以旧 GitHub 基线为底：

```powershell
$base = 'E:\AAA_project\CETC\AirSim_Multi-main'
$src  = 'E:\AAA_project\CETC\LAESim'
$out  = 'E:\AAA_project\CETC\LAESim_upload_gitclean'

robocopy $base $out /E `
  /XD .git .vs .vscode Build Binaries Intermediate Saved DerivedDataCache temp __pycache__ build devel obj `
  /XF *.sdf *.opensdf *.suo *.VC.db *.VC.VC.opendb *.ipch *.pdb *.ilk *.obj *.dll *.lib *.exp *.log *.tmp
```

注意：上面这个手工 `robocopy` 基线命令会排除所有 `.obj`，这对 C++ 编译产物是对的，但 Satellite 的源模型也有 `.obj` 文件。后续覆盖 `Unreal/Assets/Satellite` 时要从工作工程重新复制，或者直接使用 `PreparePortableSource.ps1`，该脚本已经 special-case 保留 `Unreal/Assets` 下的模型 `.obj`。

然后从工作工程覆盖 Boat / Satellite 相关源码、API、ROS、Python、settings 和文档。

核心应覆盖：

```text
build.cmd
BuildAirSimRelease.bat
LAESim部署说明_zh.md
如何加入新的载具类型.md
如何将工程简化上传github.md
AirLib/include
AirLib/src
AirLib/AirLib.vcxproj
AirLib/AirLib.vcxproj.filters
cmake/AirLib
PythonClient
Multi_use
how_to_use_settings
ros
Unreal/Assets/Boat
Unreal/Assets/Satellite
Unreal/Plugins/AirSim/AirSim.uplugin
Unreal/Plugins/AirSim/Source
```

覆盖 `Unreal/Plugins/AirSim/Source` 时要排除构建复制出的 AirLib 副本：

```powershell
robocopy "$src\Unreal\Plugins\AirSim\Source" "$out\Unreal\Plugins\AirSim\Source" /E /MT:16 `
  /XD "$src\Unreal\Plugins\AirSim\Source\AirLib" `
      "$src\Unreal\Plugins\AirSim\Source\Binaries" `
      "$src\Unreal\Plugins\AirSim\Source\Intermediate" `
      "$src\Unreal\Plugins\AirSim\Source\Saved"
```

修正版需要复制插件基础 Content 和 StarterContent，但排除高模 SUV 与 Boat / Satellite 构建产物：

```powershell
robocopy "$src\Unreal\Plugins\AirSim\Content" "$out\Unreal\Plugins\AirSim\Content" /E /MT:16 `
  /XD "$src\Unreal\Plugins\AirSim\Content\Models\Boat" `
      "$src\Unreal\Plugins\AirSim\Content\Models\Satellite" `
      "$src\Unreal\Plugins\AirSim\Content\VehicleAdv\SUV"
```

如果已经复制过一个缺少 Content 的最小版，可以从工作工程补回：

```powershell
$src = 'E:\AAA_project\CETC\LAESim'
$out = 'E:\AAA_project\CETC\LAESim_upload_gitclean'

robocopy "$src\Unreal\Plugins\AirSim\Content" "$out\Unreal\Plugins\AirSim\Content" /E /MT:16 `
  /XD "$src\Unreal\Plugins\AirSim\Content\Models\Boat" `
      "$src\Unreal\Plugins\AirSim\Content\Models\Satellite" `
      "$src\Unreal\Plugins\AirSim\Content\VehicleAdv\SUV"
```

## 6. 上传前检查清单

上传前确认这些目录不存在：

```text
AirLib\deps
AirLib\lib
AirLib\temp
MavLinkCom\lib
external\rpclib
ros\build
ros\devel
Unreal\Plugins\AirSim\Source\AirLib
Unreal\Environments\Blocks\Plugins\AirSim
Binaries
Intermediate
Saved
DerivedDataCache
```

确认这些关键文件存在：

```text
build.cmd
BuildAirSimRelease.bat
AirLib\include\vehicles\boat
AirLib\src\vehicles\boat
AirLib\include\vehicles\satellite
AirLib\src\vehicles\satellite
PythonClient\airsim\client.py
PythonClient\airsim\types.py
Multi_use\boat_keyboard_control.py
Multi_use\satellite_keyboard_control.py
ros\src\airsim_ros_pkgs\msg\BoatControls.msg
ros\src\airsim_ros_pkgs\msg\BoatState.msg
ros\src\airsim_ros_pkgs\msg\SatelliteControls.msg
ros\src\airsim_ros_pkgs\msg\SatelliteState.msg
ros\src\example\keyboard_boat_ros.py
ros\src\example\keyboard_satellite_ros.py
Unreal\Assets\Boat\Models\Boat\Type_052B_Destroyer_Combined.uasset
Unreal\Assets\Satellite\Models\Satellite\10477_Satellite_v1_L3.uasset
Unreal\Plugins\AirSim\Content\Blueprints\BP_PIPCamera.uasset
Unreal\Plugins\AirSim\Content\VehicleAdv\PhysicsMaterials\Slippery.uasset
Unreal\Plugins\AirSim\Content\VehicleAdv\PhysicsMaterials\NonSlippery.uasset
Unreal\Plugins\AirSim\Content\VehicleAdv\Sound\Engine_Loop_Cue.uasset
Unreal\Plugins\AirSim\Content\StarterContent\Particles\P_Explosion.uasset
Unreal\Plugins\AirSim\Content\StarterContent\Materials\M_Tech_Hex_Tile_Pulse.uasset
Unreal\Plugins\AirSim\Source\Vehicles\Boat\BoatPawn.cpp
Unreal\Plugins\AirSim\Source\Vehicles\Satellite\SatellitePawn.cpp
Unreal\Plugins\AirSim\Source\Vehicles\AirGround\SimModeAirGround.cpp
how_to_use_settings\settings_airground_2uav_1car_1boat_with_sensors.json
how_to_use_settings\settings_airground_2uav_1car_1boat_1satellite_with_sensors.json
```

可用下面命令快速检查大小：

```powershell
Get-ChildItem -LiteralPath 'E:\AAA_project\CETC\LAESim_upload_gitclean' -Recurse -File |
  Measure-Object Length -Sum |
  ForEach-Object { '{0:N2} MB' -f ($_.Sum / 1MB) }
```

## 7. 上传后的使用说明

别人 clone 这个最小版后，推荐流程是：

```cmd
cd /d <LAESim根目录>
BuildAirSimRelease.bat
```

编译完成后，把生成的插件复制到 UE 项目：

```text
<LAESim根目录>\Unreal\Plugins\AirSim
```

目标位置：

```text
<UE项目>\Plugins\AirSim
```

Boat 默认模型会在 `BuildAirSimRelease.bat` 调用的 `build.cmd` 中从 `Unreal\Assets\Boat\Models\Boat` 自动复制到插件 Content。`settings.json` 中只需要写：

```json
"VehicleType": "SimpleBoat"
```

不需要写 Boat 模型路径。

Satellite 默认模型同理，会从：

```text
Unreal\Assets\Satellite\Models\Satellite
```

自动复制到：

```text
Unreal\Plugins\AirSim\Content\Models\Satellite
```

`settings.json` 中只需要写：

```json
"VehicleType": "SimpleSatellite"
```

不需要写 Satellite 模型路径。

## 8. 这次已留档的问题

这次从工作工程整理 GitHub 干净版时，实际遇到并已经记录的问题包括：

- 新 clone 缺少 `Unreal/Plugins/AirSim/Content` 基础资源时，UE 会在 `ACarPawn` 构造阶段因为加载默认资源失败而崩溃。解决方式是 GitHub 版保留插件基础 Content。
- 去掉 `StarterContent` 时，UE 会弹 `P_Explosion`、`M_Tech_Hex_Tile_Pulse` 等默认属性警告。解决方式是保留 `Unreal/Plugins/AirSim/Content/StarterContent`。
- `AirLib\deps\eigen3` 目录残缺但存在时，旧脚本会跳过 Eigen 下载并报 `Eigen/Dense` 找不到。解决方式是让 `build.cmd` 检查 `AirLib\deps\eigen3\Eigen\Dense`。
- 网络或代理不稳定时，`Invoke-WebRequest` 可能报 EOF / 基础连接关闭，`Expand-Archive` 可能报找不到中央目录结尾记录。解决方式是删除残缺 zip 或临时目录后重跑 `BuildAirSimRelease.bat`；如果是 `car_assets.zip` 失败，会回退默认车模型，如果是 Eigen 失败，需要等网络恢复后重新下载。
