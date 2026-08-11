# 安装与构建 LAESim

本页包含完整安装流程：先在 Windows 中构建 LAESim/UE 4.27 核心仿真器，再按需在 WSL2 中安装 ROS Noetic 和 ns-3。只使用 Windows Python API 时完成前半部分即可；需要 ROS 或自组织网络仿真时继续完成后半部分。

Visual Studio 工作负载、Unreal 基础环境和 AirSim 通用依赖可先参考 [AirSim 官方 Windows 构建文档](https://microsoft.github.io/AirSim/build_windows/)。

## 环境要求

- Windows 10/11
- Unreal Engine 4.27
- Visual Studio 2019 或 2022
- 使用 C++ 的桌面开发工作负载
- Windows 10 SDK，推荐 `10.0.19041.0`
- Git 和 PowerShell

需要 ROS 或 ns-3 时，再准备 WSL2；它们不是 Windows 插件编译的前置条件。

## 获取源码

```powershell
$LaesimRoot = Join-Path $HOME "source\LAESim"
git clone --branch V1.5 https://github.com/SANIS-HITSZ/LAESim.git $LaesimRoot
Set-Location $LaesimRoot
```

若 PowerShell 禁止运行本地脚本，可仅为当前用户启用签名策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 可选：导出可移植源码

需要把一份不含本机编译缓存的源码交付给其他开发者时，可以使用仓库提供的导出脚本：

```powershell
$PortableRoot = Read-Host "请输入可移植源码输出目录"
powershell -ExecutionPolicy Bypass -File .\PreparePortableSource.ps1 `
  -DestinationRoot $PortableRoot
```

该流程用于制作干净源码副本，不替代 Git 分支、发布标签或正式构建验证。

## 编译 LAESim 插件

推荐入口：

```powershell
.\BuildAirSimRelease.bat
```

该脚本会查找 Visual Studio 开发环境，然后调用：

```cmd
build.cmd --Release
```

也可以打开 Visual Studio 2019/2022 的 `x64 Native Tools Command Prompt`，在仓库根目录手动执行：

```cmd
build.cmd --Release
```

两种入口生成相同的 Release 产物；`BuildAirSimRelease.bat` 额外负责定位 Visual Studio 并初始化 x64 编译环境。

构建结束后，LAESim 插件位于：

```text
<LAESim 源码目录>\Unreal\Plugins\AirSim
```

### UE 安装在非标准目录

自动探测失败时指定 UE 根目录：

```powershell
$env:UNREAL_ENGINE_ROOT = Read-Host "请输入 UE 4.27 安装目录"
.\BuildAirSimRelease.bat
```

## Boat 模型资源

Boat 的源码资产位于：

```text
Unreal\Assets\Boat\Models\Boat
```

构建脚本会将其复制到：

```text
Unreal\Plugins\AirSim\Content\Models\Boat
```

默认 Pawn 会加载 `/AirSim/Models/Boat/Type_052B_Destroyer_Combined`，因此普通使用者不需要在 `settings.json` 中配置模型路径。若资源没有复制成功，Boat 会回退到代码生成的简化外形。

## Satellite 模型资源

Satellite 源码资产位于 `Unreal\Assets\Satellite\Models\Satellite`。构建脚本会将其复制到 `Unreal\Plugins\AirSim\Content\Models\Satellite`，默认 Pawn 加载 `/AirSim/Models/Satellite/10477_Satellite_v1_L3`；资源缺失时会回退到代码生成的简化卫星外形。

## 接入自己的 UE 工程

1. 创建或打开一个 UE 4.27 C++ 项目。
2. 将 `Unreal\Plugins\AirSim` 整体复制到目标项目的 `Plugins\AirSim`。
3. 重新生成并编译目标项目的 `Development Editor`。
4. 在关卡中配置 `PlayerStart` 和 `AirSimGameMode`。
5. 将 LAESim 配置放到 `%USERPROFILE%\Documents\AirSim\settings.json`。
6. 打开关卡并点击 Play。

只验证仓库自带 Blocks 场景时，可以额外运行：

```powershell
.\Unreal\Environments\Blocks\BuildBlocksEditor.bat
```

该脚本只构建 Blocks 示例，不替代 LAESim 插件构建。

## 构建验证

至少确认以下结果：

- `Unreal\Plugins\AirSim\Binaries` 已生成插件二进制
- UE 能加载 AirSim/LAESim 插件并进入 Play
- `settings.json` 使用 `AirGround` 时能同时生成无人机、汽车、船和卫星
- 本机端口 `41451`、`41461`、`41471`、`41481`、`41491` 按配置监听

## 常见 Windows 构建问题

### 找不到 `Eigen/Dense`

出现以下错误通常表示 Eigen 下载或解压中断，虽然 `AirLib\deps\eigen3` 目录存在，但实际头文件不完整：

```text
error C1083: 无法打开包括文件: "Eigen/Dense"
```

先检查真正的头文件：

```powershell
Test-Path .\AirLib\deps\eigen3\Eigen\Dense
```

返回 `False` 时清理残缺目录并重新构建：

```powershell
Remove-Item -LiteralPath .\AirLib\deps\eigen3 -Recurse -Force
.\BuildAirSimRelease.bat
```

### 依赖压缩包下载中断

`Invoke-WebRequest` 报意外 EOF、连接关闭或解压时报“找不到中央目录结尾记录”，通常表示代理或网络导致 zip 不完整。清理临时文件后重试：

```powershell
Remove-Item -LiteralPath .\eigen3.zip -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\suv_download_tmp -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\AirLib\deps\eigen3 -Recurse -Force -ErrorAction SilentlyContinue
.\BuildAirSimRelease.bat
```

`car_assets.zip` 失败时通常会回退到默认车辆模型；Eigen 下载失败会阻止 AirLib 编译，应先解决网络或代理问题。

完成 Windows/UE 构建后，可以先阅读[使用 LAESim](laesim_use.md)。需要 ROS 或 ns-3 时继续阅读独立维护的 [WSL2、ROS 与 ns-3](laesim_wsl_ros_ns3.md) 文档；该页面同时记录 ns-3 runner、网络桥接器、星地链路和回归测试流程。
