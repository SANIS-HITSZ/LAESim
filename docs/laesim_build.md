# 构建 LAESim

本页只说明 LAESim 的 Windows/UE 4.27 构建流程。Visual Studio 工作负载、Unreal 基础环境和 AirSim 通用依赖可先参考 [AirSim 官方 Windows 构建文档](https://microsoft.github.io/AirSim/build_windows/)。

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
git clone https://github.com/SANIS-HITSZ/LAESim.git $LaesimRoot
Set-Location $LaesimRoot
```

若 PowerShell 禁止运行本地脚本，可仅为当前用户启用签名策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 编译 LAESim 插件

推荐入口：

```powershell
.\BuildAirSimRelease.bat
```

该脚本会查找 Visual Studio 开发环境，然后调用：

```cmd
build.cmd --Release
```

构建结束后，LAESim 插件位于：

```text
<LAESim 源码目录>\Unreal\Plugins\AirSim
```

### UE 安装在非标准目录

自动探测失败时指定 UE 根目录：

```cmd
set UNREAL_ENGINE_ROOT=E:\epgame\UE_4.27
BuildAirSimRelease.bat
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

构建完成后继续阅读[使用 LAESim](laesim_use.md)。
