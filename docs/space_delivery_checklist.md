# LAESim 天基任务模块交付与验收清单

本文用于把 LAESim 天基任务模块部署到另一台电脑，并验证复制、编译、ROS、ns-3、UE 和任务链路是否完整。这里的验收脚本均为只读检查或独立测试，不修改活动 `settings.json`，也不改变无人机、车辆、船舶、SceneMap 和原有 AirSim API 的行为。

## 1. 交付边界

应交付完整的 LAESim 工程目录，不要只复制 `Multi_use` 或几个 Python 文件。卫星载具涉及 AirLib、PythonClient、UE 插件、ROS 消息和 NetworkSim 多个层次，漏掉任意一层都可能出现“模型存在但接口缺失”的问题。

标准交付能力包括：

- `SimpleSatellite` 载具、RPC、PythonClient 和 ROS 接口。
- TLE/SGP4 实时传播，多星、多目标、选星、切换、空窗和重访统计。
- 星地真实链路预算、ns-3 消息投递、丢包诊断、星间链路和显式多跳。
- UE 星下点、覆盖圈、UP/DOWN 链路显示。
- 确定性验收、配置校验、环境自检和运行报告。

Orekit、Basilisk 和 GMAT 是可选专业后端，不是标准实时演示的必需依赖。没有它们时，TLE/SGP4、ROS、UE 和 ns-3 闭环仍应通过。

## 2. 不应跨电脑复制的生成目录

不要把旧机器路径绑定的构建缓存当成交付产物使用：

```text
ros/build
ros/devel
ros/install
.runtime
AirLib/temp
Unreal/Environments/*/Binaries
Unreal/Environments/*/Intermediate
```

复制到新机器后，应在新路径重新执行 UE 插件构建、`catkin_make` 和 ns-3 runner 构建。尤其不能直接复用另一条路径生成的 `ros/build/CMakeCache.txt`。

## 3. 源文件完整性检查

在 Windows 工程根目录执行：

```powershell
python NetworkSim\scripts\verify_space_delivery_files.py `
  --output .runtime\delivery_acceptance\source_manifest.json
```

输出必须是 `Verification: PASS`。报告包含关键文件和目录的 SHA-256，可随交付包一起保存；接收电脑再次运行后，可用于发现漏文件或复制损坏。机器可读清单位于 `NetworkSim/config/space-delivery-manifest.json`。

## 4. 新电脑部署顺序

1. 将完整 LAESim 工程复制到 Windows，例如 `E:\LAESim`。
2. 按 `docs/laesim_build.md` 重新构建 AirLib 和 UE 插件，并让目标 UE 4.27 工程加载新的 AirSim 插件。
3. 从 `how_to_use_settings/settings_space_dynamic_targets.json` 复制所需配置到用户的 `Documents/AirSim/settings.json`，再按关卡修改出生位置。不要让安装脚本覆盖用户已有配置。
4. 把源码复制到 WSL Linux 文件系统，例如 `${HOME}/LAESim`。建议排除上一节的生成目录。
5. 在 `${HOME}/LAESim/ros` 删除旧 `build/devel/install` 后运行 `catkin_make`。
6. 构建并验证 ns-3 runner。

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/build_and_verify_ns3_runner.sh
```

## 5. 配置校验

Windows 或 WSL 都可以只读校验 settings 和离线任务文件：

```bash
python3 NetworkSim/python/space_delivery_validation.py \
  --settings /path/to/settings.json \
  --mission Multi_use/space_mission.example.json \
  --expect-satellite Satellite \
  --expect-satellite Satellite2 \
  --expect-satellite Satellite3 \
  --expect-target UAV --expect-target UAV2 \
  --expect-target Car --expect-target Boat \
  --require-ns3
```

`errors=0` 才允许进入运行验收。默认不会修改配置；加 `--strict` 后警告也会导致非零退出码，适合自动化交付流水线。

## 6. 不依赖 UE 的确定性验收

该验收使用独立 ROS master 和固定接入状态，不使用当前 TLE，也不连接正在运行的 UE：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/tests/ros_space_delivery_acceptance.sh
```

必须固定得到以下事件序列：

```text
DOWN -> UP:Satellite -> HANDOVER:Satellite2 -> DOWN
```

两个 `DOWN` 阶段必须由 `drop_stage=space_access_policy` 阻断；两个可见阶段必须通过 `link_type=satellite` 投递并返回非零 `latency_ns`。报告写到：

```text
.runtime/delivery_acceptance/acceptance_report.json
```

## 7. 真实 UE 联调验收

先启动 UE 并进入 Play，再在 WSL 启动 AirSim ROS wrapper。随后执行：

```bash
cd "${HOME}/LAESim"
bash NetworkSim/scripts/check_space_demo_environment.sh \
  --settings /mnt/c/Users/<Windows用户名>/Documents/AirSim/settings.json \
  --require-ros --require-ns3 --live \
  --output .runtime/delivery_acceptance/environment_report.json
```

标准交付要求所有必需项为 `PASS`。Orekit/Basilisk 显示 `WARN` 可以接受。

启动并检查演示：

```bash
bash NetworkSim/scripts/start_space_demo.sh
bash NetworkSim/scripts/space_demo_status.sh
```

至少确认：

- `/airsim_node/Satellite/odom_local_ned` 时间戳持续推进。
- 三个 `/space/Satellite*/state` 话题存在。
- `/space/selection/Car` 能输出最佳星或正常空窗。
- `/space/visualization/status` 的 `frame_count` 持续增加且 `last_error` 为空。
- UE 中三颗卫星位置不同，UP/DOWN 标签会随场景时间变化。

一键脚本默认让任务状态保持 2 Hz，而 UE 位姿和标记只刷新 0.5 Hz。不要为了画面更快而随意提高 `POSE_RATE_HZ` 或 `VISUAL_RATE_HZ`；可视化器会在上游中断或连续 RPC 失败时自动退出，这是防止无效调用持续压迫 UE 的保护行为。

正常停止并导出报告：

```bash
bash NetworkSim/scripts/stop_space_demo.sh
python3 NetworkSim/python/export_space_demo_report.py \
  --runtime-dir .runtime/constellation_demo
```

摘要 `sample_count` 应与 JSONL 有效行数一致。若不一致，说明进程曾被强制终止，应重新执行并正常停止。

## 8. 原功能回归

天基模块验收完成后，至少抽查一个无人机、车辆和船舶接口：

```bash
rostopic hz /airsim_node/UAV/odom_local_ned
rostopic hz /airsim_node/Car/odom_local_ned
rostopic hz /airsim_node/Boat/odom_local_ned
```

这些话题应继续更新。天基脚本只驱动 `SimpleSatellite`，NetworkSim 只处理显式发布到 `/network_sim/tx` 的消息，不会自动拦截原有 ROS topic、TCP/UDP 或其他载具控制命令。

## 9. 验收结论

以下全部满足时，可以把当前版本标记为“LAESim 天基任务分析与通信仿真模块第一版交付完成”：

- 关键文件完整性 `PASS`。
- 配置校验 `errors=0`。
- 确定性四阶段验收 `passed=true`。
- 环境自检必需项全部 `PASS`。
- UE 真实三星状态、可视化帧和 ROS 时间戳持续推进。
- 报告正常闭合且样本数一致。
- 无人机、车辆、船舶和 SceneMap 原有配置保持可选，未被天基模块强制启用或覆盖。

当前开发机已经完成上述验收：Windows/WSL 各 33 个纯 Python 测试通过，文件清单 41/41，通过独立四阶段 ns-3 验收、两跳中继验收和真实 UE 低负载/熔断复验。接收电脑仍应按本清单重新执行，不能直接沿用开发机结论。
