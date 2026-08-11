# V1.5 基线同步说明

本文记录 LAESim V1.5 对公开 V1.4 工程的承接范围。同步基线为 `SANIS-HITSZ/LAESim` 的 V1.4 下载副本，核对日期为 2026-08-11。

## 1. 同步原则

- V1.4 是 V1.5 的完整工程基线，不只复制某一个功能目录。
- V1.4 独有的源码、文档、示例和发布元数据应进入 V1.5。
- V1.5 已扩展的文件按功能并集合并，不用 V1.4 旧实现覆盖。
- 编译缓存、ROS `build/devel/install`、UE `Binaries/Intermediate/Saved` 等生成目录不参与版本同步。
- 同步不修改用户当前生效的 `%USERPROFILE%\Documents\AirSim\settings.json`。

## 2. 核对结果

全量相对路径和关键文件哈希核对得到：

- C++ 载具、SceneMap、AirSim settings 解析、Python API 等核心实现已与 V1.4 对齐。
- V1.4 有 21 个本地原先缺少的有效文件，集中在软件引用、团队信息、文档站资源和 quickstart。
- 共有 33 个同名文件存在内容差异；其中 NetworkSim、ROS 消息和天基任务文档属于 V1.5 的扩展实现。
- 卫星 OBJ/MTL 的文本差异不包含语义变化，因此保留本地资产版本。

## 3. 从 V1.4 承接的内容

| 类别 | 承接内容 |
| --- | --- |
| 发布元数据 | `CITATION.cff`、`CONTRIBUTORS.md` |
| 文档站 | 发布版首页、文档概览、landing 模板与样式、展示图片和演示视频 |
| 快速入门 | `Examples/quickstart/heterogeneous_fleet` 与 `Examples/quickstart/ns3_network` |
| 通用文档 | V1.4 的安装页、案例页、通用化路径写法和可移植源码说明 |
| 工程配置 | V1.4 的 MkDocs 发布结构和确定性 Python API 文档配置 |

V1.4 文档中的版本链接已统一更新为 V1.5；机器相关绝对路径改为环境变量或 `<占位符>`。

## 4. V1.5 保留和新增的内容

V1.5 没有回退下列本地功能：

- TLE/SGP4、CSV、mock 与可选 Orekit 天基任务后端。
- 多星、多目标、覆盖窗口、重访时间、最佳卫星和切换统计。
- UE 卫星显示坐标与真实轨道/真实星地斜距解耦。
- 星地链路预算、星间链路、多跳路径和 access 门控。
- NetworkSim 结构化丢包诊断与 `/network_sim/drop`。
- ROS `/space/...` 状态、access、最佳星、切换和链路可视化接口。
- 统一仿真时钟、启动/停止/检查脚本和交付验收清单。

这些功能均为可选增量。不开启天基任务脚本、`SpaceAccessPolicy`、`SatelliteLinkModel` 或 `UnifiedClock` 时，原有 V1.4 的 UE、Python、ROS 和 `Backend=none` 流程不改变。

## 5. 同名文件合并决策

| 文件范围 | 决策 |
| --- | --- |
| `NetworkSim/**` | 保留 V1.5 增强实现；V1.4 quickstart 作为兼容性用例加入 |
| `ros/src/airsim_ros_pkgs/CMakeLists.txt` | 保留 V1.5 的 `SpaceSatelliteState` 和 `SpaceAccessState` 消息 |
| `docs/laesim_wsl_ros_ns3.md` | 保留 V1.5 完整操作手册，安装页链接到该单一事实来源 |
| `README.md`、`docs/index.md` | 使用 V1.4 发布版结构，合入 V1.5 能力和版本信息 |
| `docs/simulation_cases.md` | 保留 V1.4 两个 quickstart，新增天基任务与通信联动案例 |
| SceneMap 和载具开发说明 | 采用 V1.4 的通用路径写法，移除开发机绝对路径 |

## 6. 回归验证

交付前至少执行：

```powershell
python -m py_compile .\Examples\quickstart\heterogeneous_fleet\run_experiment.py
python -m json.tool .\Examples\quickstart\heterogeneous_fleet\settings.json > $null
python -m json.tool .\Examples\quickstart\ns3_network\settings.json > $null
python -m unittest discover -s .\NetworkSim\tests -p "test_*.py" -v
```

文档环境安装 MkDocs 及项目扩展后执行：

```powershell
python -m mkdocs build --strict
```

涉及 ROS/ns-3 运行时的完整验收按 [WSL2、ROS 与 ns-3](laesim_wsl_ros_ns3.md) 执行；涉及天基任务的完整验收按[交付检查清单](space_delivery_checklist.md)执行。

### 本次同步验证结果

2026-08-11 的实际检查结果：

- V1.4 相对路径文件缺失数：`0`。
- JSON 配置解析：`21/21` 通过。
- V1.4 新增 quickstart 与 V1.5 NetworkSim/天基任务关键脚本：`py_compile` 通过。
- 异构载具 quickstart `--check-only`：通过，识别 `UAV/Car/Boat` 和三个独立 RPC 端口。
- NetworkSim 单元测试：`33/33` 通过。
- MkDocs `build --strict`：通过。
- Windows 工程已无删除同步到 WSL `$HOME/LAESim`；保留 `ros/build`、`ros/devel`、`ros/install`、依赖和运行目录。
- WSL 关键文件哈希与 Windows 源一致，`ros/src/CMakeLists.txt` catkin 符号链接及 `ros/devel/setup.bash` 保持有效。
- WSL 副本再次完成 quickstart `--check-only`、关键脚本 `py_compile` 和 NetworkSim `33/33` 单元测试。

本次没有修改 C++ 核心文件，因此未因文档同步重复构建 UE 插件；后续若继续修改 `AirLib` 或 `Unreal/Plugins/AirSim/Source`，再执行完整 Release 和目标 UE 工程编译。
