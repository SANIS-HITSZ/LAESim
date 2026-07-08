# 如何将工程简化上传 GitHub

本文记录这次从工作工程 `E:\AAA_project\CETC\AirSim_Multi` 生成 GitHub 上传版 `E:\AAA_project\CETC\AirSim_Multi_upload_gitclean_min` 的思路和操作。目标是得到一个干净、可维护、尽量接近旧仓库 `E:\AAA_project\CETC\AirSim_Multi-main` 风格的源码包，而不是把本机编译产物和 UE 项目部署产物一起上传。

## 1. 最终选择

本次最终采用：

```text
E:\AAA_project\CETC\AirSim_Multi_upload_gitclean_min
```

当前大小约为：

```text
218.34 MB
```

对比：

```text
旧 GitHub 基线 AirSim_Multi-main：193.61 MB
完整干净版 AirSim_Multi_upload_gitclean：284.71 MB
旧的偏臃肿版 AirSim_Multi_upload_clean：676.38 MB
```

`gitclean_min` 比旧基线大约多 24 MB，主要来自 052B Boat 默认模型源资产。这是为了让 GitHub 仓库中保留 Boat 默认模型，而不是只保留代码。

## 2. 为什么不用工作目录直接上传

`AirSim_Multi` 是工作目录，已经经历过编译、UE 插件部署、资源导入等操作，里面会混入大量不适合上传 GitHub 的内容，例如：

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

所以本次 `gitclean_min` 也采用旧仓库风格，不上传整包插件 Content。这样可以少约 66 MB。

需要注意：这是一种最小源码上传策略。它适合以下情况：

- 目标机器已有完整 AirSim 插件内容，或可以从原始 AirSim / 本地构建结果补齐。
- GitHub 仓库主要保存本工程的修改源码、Boat 支持代码、settings、Python 示例、ROS 接口和 Boat 模型源资产。
- 接收者知道需要先运行 `BuildAirSimRelease.bat`，再把生成后的插件复制到 UE 项目。

如果希望仓库从零 clone 后就尽量完整自包含，可以使用 `AirSim_Multi_upload_gitclean`，它保留了 `Unreal/Plugins/AirSim/Content` 中的默认蓝图、HUD、Weather、基础 Vehicle 资源，但体积约 284.71 MB。

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

## 5. 生成最小上传版的推荐流程

先以旧 GitHub 基线为底：

```powershell
$base = 'E:\AAA_project\CETC\AirSim_Multi-main'
$src  = 'E:\AAA_project\CETC\AirSim_Multi'
$out  = 'E:\AAA_project\CETC\AirSim_Multi_upload_gitclean_min'

robocopy $base $out /E `
  /XD .git .vs .vscode Build Binaries Intermediate Saved DerivedDataCache temp __pycache__ build devel obj `
  /XF *.sdf *.opensdf *.suo *.VC.db *.VC.VC.opendb *.ipch *.pdb *.ilk *.obj *.dll *.lib *.exp *.log *.tmp
```

然后从工作工程覆盖 Boat 相关源码、API、ROS、Python、settings 和文档。

核心应覆盖：

```text
build.cmd
BuildAirSimRelease.bat
AirSim_Multi部署说明_zh.md
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

最小版不要复制：

```text
Unreal/Plugins/AirSim/Content
```

如果已经复制过完整干净版，也可以从完整干净版同步出最小版：

```powershell
$src = 'E:\AAA_project\CETC\AirSim_Multi_upload_gitclean'
$out = 'E:\AAA_project\CETC\AirSim_Multi_upload_gitclean_min'

robocopy $src $out /MIR /MT:16 `
  /XD "$src\Unreal\Plugins\AirSim\Content"
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
Unreal\Plugins\AirSim\Content
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
PythonClient\airsim\client.py
PythonClient\airsim\types.py
Multi_use\boat_keyboard_control.py
ros\src\airsim_ros_pkgs\msg\BoatControls.msg
ros\src\airsim_ros_pkgs\msg\BoatState.msg
ros\src\example\keyboard_boat_ros.py
Unreal\Assets\Boat\Models\Boat\Type_052B_Destroyer_Combined.uasset
Unreal\Plugins\AirSim\Source\Vehicles\Boat\BoatPawn.cpp
Unreal\Plugins\AirSim\Source\Vehicles\AirGround\SimModeAirGround.cpp
how_to_use_settings\settings_airground_2uav_1car_1boat_with_sensors.json
```

可用下面命令快速检查大小：

```powershell
Get-ChildItem -LiteralPath 'E:\AAA_project\CETC\AirSim_Multi_upload_gitclean_min' -Recurse -File |
  Measure-Object Length -Sum |
  ForEach-Object { '{0:N2} MB' -f ($_.Sum / 1MB) }
```

## 7. 上传后的使用说明

别人 clone 这个最小版后，推荐流程是：

```cmd
cd /d <AirSim_Multi根目录>
BuildAirSimRelease.bat
```

编译完成后，把生成的插件复制到 UE 项目：

```text
<AirSim_Multi根目录>\Unreal\Plugins\AirSim
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

