# 如何将工程简化上传 GitHub

本文记录这次从工作工程 `<LAESim 源码目录>` 生成 GitHub 上传版 `<输出目录>\LAESim_upload_gitclean` 的思路和操作。目标是得到一个干净、可维护、尽量接近旧仓库 `<旧基线工程目录>` 风格的源码包，而不是把本机编译产物和 UE 项目部署产物一起上传。

## 1. 最终选择

V1.5 本次采用：

```text
<输出目录>\LAESim_upload_V1.5
```

V1.5 的实际大小应以导出后的检查结果为准。与旧版相比，V1.5 增加了天基任务、NetworkSim 增强、quickstart 和文档展示资源；导出脚本仍会排除重复插件与构建资源。

```text
约 340 MB（随文档和展示资源调整会有变化）
```

对比：

```text
旧 GitHub 基线 AirSim_Multi-main：193.61 MB
完整干净版 AirSim_Multi_upload_gitclean：284.71 MB
旧的偏臃肿版 AirSim_Multi_upload_clean：676.38 MB
```

`gitclean_min` 早期曾尝试做到约 218 MB，但实践证明从 GitHub 新 clone 后进入 UE 会因为缺少 AirSim 插件基础 Content 而崩溃。之后又发现排除 `StarterContent` 虽然不影响运行，但会触发 CDO 默认属性警告。现在修正版保留必要的插件基础 Content 和 StarterContent，并继续排除高模 SUV、Boat / Satellite 构建产物、`Blocks/Plugins/AirSim` 重复插件和编译产物。

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
$base = '<旧基线工程目录>'
$src  = '<LAESim 源码目录>'
$out  = '<输出目录>\LAESim_upload_gitclean'

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
$src = '<LAESim 源码目录>'
$out = '<输出目录>\LAESim_upload_gitclean'

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
Get-ChildItem -LiteralPath '<输出目录>\LAESim_upload_V1.5' -Recurse -File |
  Measure-Object Length -Sum |
  ForEach-Object { '{0:N2} MB' -f ($_.Sum / 1MB) }
```

## 7. 创建并上传 V1.5 分支

当前工作目录不一定带有 `.git`，因此不要直接在工作工程里执行 `git init`。推荐从远端 V1.4 建立一个干净 Git 工作副本，再覆盖 V1.5 的可移植源码。

### 7.1 导出 V1.5 可移植源码

```powershell
$src = '<LAESim 源码目录>'
$stage = '<输出目录>\LAESim_portable_V1.5'

Set-Location $src
powershell -ExecutionPolicy Bypass -File .\PreparePortableSource.ps1 `
  -DestinationRoot $stage
```

`DestinationRoot` 必须不存在或为空目录。脚本会排除 `.git`、依赖下载目录、UE/ROS/C++ 编译产物、运行目录、日志和缓存，同时保留 `Unreal\Assets` 中 Boat/Satellite 使用的 OBJ 源模型，以及仓库跟踪的 `tools/HttpGet.exe`、`tools/unzip.exe` 等构建辅助程序。它还会排除 `Blocks/Plugins/AirSim` 的重复插件，以及构建时从源码资产生成的 Boat/Satellite/SUV 插件资源。

### 7.2 从 V1.4 创建 V1.5

```powershell
$repo = '<输出目录>\LAESim_upload_V1.5'
git clone --branch V1.4 https://github.com/SANIS-HITSZ/LAESim.git $repo
Set-Location $repo
git switch -c V1.5
```

将可移植源码覆盖到 Git 工作副本并保留 clone 得到的 `.git`。`ros/src/CMakeLists.txt` 不属于 Git 源码，它会由 WSL 中的 `catkin_make` 生成：

```powershell
robocopy $stage $repo /E /COPY:DAT /DCOPY:T /R:2 /W:1 `
  /XD "$repo\.git" `
  /XF "$stage\ros\src\CMakeLists.txt"

# robocopy 返回 0-7 都表示复制成功
if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $LASTEXITCODE" }
```

### 7.3 提交前验证

```powershell
Set-Location $repo

# 检查变更内容
git status --short
git diff --check

# 禁止出现单个接近 GitHub 100 MB 上限的文件
$largeFiles = Get-ChildItem -Recurse -File |
  Where-Object { $_.FullName -notlike "$repo\.git\*" -and $_.Length -ge 95MB }
if ($largeFiles) { $largeFiles; throw '存在大于等于 95 MB 的文件' }

# 确认生成目录没有进入上传版
$forbidden = @(
  'AirLib\deps', 'AirLib\lib', 'external\rpclib',
  'ros\build', 'ros\devel', 'ros\install',
  'Unreal\Plugins\AirSim\Binaries',
  'Unreal\Plugins\AirSim\Intermediate',
  'Unreal\Plugins\AirSim\Source\AirLib'
)
$found = $forbidden | Where-Object { Test-Path -LiteralPath (Join-Path $repo $_) }
if ($found) { $found; throw '上传版仍包含生成目录' }
```

继续运行 JSON、Python 和 NetworkSim 回归：

```powershell
python -m py_compile .\Examples\quickstart\heterogeneous_fleet\run_experiment.py `
  .\Examples\quickstart\ns3_network\run_experiment.py
python -m json.tool .\Examples\quickstart\heterogeneous_fleet\settings.json > $null
python -m json.tool .\Examples\quickstart\ns3_network\settings.json > $null
python -m unittest discover -s .\NetworkSim\tests -p "test_*.py" -v
```

### 7.4 提交并推送

确认 Git 用户名和邮箱属于实际提交者：

```powershell
git config user.name
git config user.email
```

未配置时只在当前仓库设置，不要写入不属于自己的姓名或邮箱：

```powershell
git config user.name '<提交者姓名>'
git config user.email '<提交者邮箱>'
```

提交并推送：

```powershell
git add -A
git commit -m "release: prepare LAESim V1.5"
git push -u origin V1.5
```

推送完成后通过下面命令确认远端分支和提交：

```powershell
git ls-remote --heads origin V1.5
git log -1 --oneline --decorate
```

### 7.5 V1.5 本次实际验证结果

本次整理以远程 `V1.4` 的提交
`f2fc0741c19322c0313fe6feed00e2d30ec34c36` 为基线。使用
`PreparePortableSource.ps1` 导出后的 V1.5 可移植源码包共有 1735 个文件，
约 325.54 MB。

上传前已确认：

- 没有大于或等于 95 MB 的单个文件。
- 没有包含 `external/rpclib`、编译产物、catkin 工作空间产物或重复的 UE 插件资源。
- 保留 `tools/HttpGet.exe`、`tools/unzip.exe` 和
  `Examples/DataCollection/exe/DataCollectorSGM.exe` 这 3 个源码工程所需工具。
- 20 个 JSON 配置文件通过解析。
- quickstart 异构载具配置检查通过。
- `NetworkSim/tests` 的 33 个单元测试全部通过。
- MkDocs 严格模式构建通过。

这些数据用于快速判断后续导出是否异常；随着源码和文档继续更新，
文件数和体积可以小幅变化。

## 8. 上传后的使用说明

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

## 9. 这次已留档的问题

这次从工作工程整理 GitHub 干净版时，实际遇到并已经记录的问题包括：

- 新 clone 缺少 `Unreal/Plugins/AirSim/Content` 基础资源时，UE 会在 `ACarPawn` 构造阶段因为加载默认资源失败而崩溃。解决方式是 GitHub 版保留插件基础 Content。
- 去掉 `StarterContent` 时，UE 会弹 `P_Explosion`、`M_Tech_Hex_Tile_Pulse` 等默认属性警告。解决方式是保留 `Unreal/Plugins/AirSim/Content/StarterContent`。
- `AirLib\deps\eigen3` 目录残缺但存在时，旧脚本会跳过 Eigen 下载并报 `Eigen/Dense` 找不到。解决方式是让 `build.cmd` 检查 `AirLib\deps\eigen3\Eigen\Dense`。
- 网络或代理不稳定时，`Invoke-WebRequest` 可能报 EOF / 基础连接关闭，`Expand-Archive` 可能报找不到中央目录结尾记录。解决方式是删除残缺 zip 或临时目录后重跑 `BuildAirSimRelease.bat`；如果是 `car_assets.zip` 失败，会回退默认车模型，如果是 Eigen 失败，需要等网络恢复后重新下载。
