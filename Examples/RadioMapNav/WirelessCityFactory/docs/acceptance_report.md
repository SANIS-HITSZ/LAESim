# LAESim 城市通信功能更新验收记录

> 历史 v3 记录：本文中的无线地图和数值结论早于 v4 Sionna 扇区方向修正。城市生成、UE 导入和 AirSim 联调证据仍有效，但无线结果必须重新生成并重新验收后才能作为物理结果使用。

记录日期：2026-09-12

本记录对应 `simulator_construction_plan.md` 的 A-E 最小交付顺序。它区分已经在本机实际执行的结果、自动测试结果和仍需项目负责人冻结的实验参数。

## A. LAESim 安装与交互验证

- LAESim：V1.5，commit `fd53f1885275f2b92be8b671b7a9a35eb4bbb7e7`。
- Unreal Engine：4.27.2；AirSim plugin：1.8.1；控制模式：SimpleFlight，不依赖 PX4。
- 已实际验证 UAV 生成、位姿读取、确定性速度动作、碰撞状态、仿真时间戳和 RPC 连接。
- 启动与导入命令使用仓库相对路径及调用时传入的根目录，不将个人绝对路径写入配置。

结论：当前机器上的最小启动与动作闭环通过，可以通过终端控制无人机运动。

## B. 程序化随机城市

- 支持 `manhattan`、`bsp_tjunction`、`voronoi`、`radial_organic` 四种候选形态。
- 已生成 4 种形态乘 3 个随机种子的 12 个 1 km x 1 km 候选场景。
- `scene.json` 记录连续三维建筑几何、材料、边界、任务和统计；同配置与种子字节级一致。
- 自动检查建筑重叠、边界、自由空间连通性、任务可达性和最短路径；无效场景拒绝发布成功 manifest。
- 输出闭合、外向法线的 LOD1 OBJ，并保留清单中的解析 AABB。

结论：城市集已冻结为 `dense_highrise_grid`、`irregular_midrise`、`sparse_suburban`，每类固定使用 `20260821`、`20260822`、`20260823` 三个种子，共 9 个可复现城市。`compact_radial_lowrise` 保留为后续扩展场景。

## C. 基站生成与注册

- 同一 1 km 城市已生成 5、10、30 sites/km2 三组配置，分别对应 15、30、90 个扇区。
- `base_station_manifest.json` 记录物理站点、屋顶宿主、位置、天线高度、部署种子/偏移、逐扇区方位、下倾和功率。
- Sionna、UE importer、SVG 预览和运行时查询共同读取或校验该清单及其 fingerprint。
- UE commandlet 导入和保存后验证已通过，站点 marker 坐标来自同一清单。

结论：天线类型为sector3-tr38901-8x8-dualpol

### 典型化更新

- 新增 UMa 校准参考：5 sites/km2、25 m 绝对离地高度、500 m 参考站间距、3 扇区、49 dBm/sector、8 x 8 双极化阵列代理。
- 新增 UMi street-canyon 校准参考：30 sites/km2、10 m 绝对离地高度、200 m 参考站间距、3 扇区、44 dBm/sector、8 x 8 双极化阵列代理。
- 10 sites/km2 被明确标记为项目中间敏感性档，不再表述为 3GPP 标准场景。
- 配置和清单区分 `absolute_agl` 与 `mast_above_rooftop`，避免把绝对天线高度错误解释为屋顶以上杆高。
- 参考来源定位到 3GPP TR 38.901 v18.0.0 的 Table 7.2-1 与校准表；有限 1 km 窗口会同时记录参考站间距和实际生成坐标。

## D. Sionna RT 离线信道地图

- 本机实际版本：Python 3.10.11、Sionna RT 2.1.0、Mitsuba 3.9.1、Dr.Jit 1.5.0；运行于 Windows CUDA/OptiX。
- v3 契约冒烟结果：`examples/outputs/city_radio_contract_smoke-ba3f4f99945e`。
- 早期已验证示例中的 4.9 GHz、100 MHz、53 dBm/sector、三扇区、10 deg 下倾、8 x 4 空间位置、`cross` +/-45 deg 双极化和 64 线性端口；该组合现仅保留为历史回归代理，不再表述为典型基站。
- `radio_volume.npz` 按 `[transmitter,z,y,x]` 保存 `path_gain_linear`、`rsrp_dbm`、`sinr_linear` 和 `sinr_db`；本次四个数组尺寸均为 `[3,2,3,3]` 且全部为有限值。
- `radio_manifest.json` 保存实际软件版本、传播开关、坐标轴顺序、样本语义、数组尺寸、文件 SHA-256、场景 fingerprint 和基站 fingerprint。

结论：Sionna 接口、参数契约和真实计算通过。计划文本写的是 Sionna RT 2.0.1，本机实际验证为 2.1.0。

实际运行了 UMa reference contract smoke：25 m AGL、3 扇区、49 dBm/sector、8 x 8 `cross` 双极化、128 线性端口，输出尺寸 `[3,2,3,3]`，最终 v6 结果目录为 `examples/outputs/city_radio_uma_contract_smoke-428ca90c5b77`。

首版场景矩阵冻结后又实际运行了 UMi street-canyon contract smoke：10 m AGL、3 扇区、44 dBm/sector、8 x 8 `cross` 双极化、128 线性端口；`path_gain_linear`、`rsrp_dbm`、`sinr_linear`、`sinr_db` 均为 `[3,2,3,3]` 且计算完成。结果目录为 `examples/outputs/city_radio_umi_contract_smoke-333ce57c4a06`。

正式 `production_v1` 数据已生成：3 类城市乘 3 个种子，共 9 个 `1 km x 1 km` 场景；接收网格为 `2 m`，高度为 `35/65/95/115 m`，每逻辑扇区 `16,777,216` samples。高层 UMi 的数组尺寸为 `[90,4,500,500]`，不规则/郊区 UMa 为 `[15,4,500,500]`。九个结果的四组无线数组均为有限值，总压缩体积约 `4.66 GiB`；统一清单为 `examples/outputs/production_radio_set_v1.json`，重复运行时 9 项全部复用。

## E. UE/LAESim 在线无线观测

- 9 个冻结城市均已通过 UE 4.27 commandlet 实际导入，并保存为 9 个独立地图：`/Game/WirelessCity/Maps/WCF_<Profile>_<Seed>`。
- 每图均完成保存后独立验证：地图加载、建筑碰撞、几何边界、坐标变换、站点/任务 marker、AirSimGameMode、天空和日光配置全部通过。
- 每图导入 30 个 UMi 物理站点或 5 个 UMa 物理站点；每站的 3 个逻辑扇区保留在共享基站清单和离线信道数组中。
- 批量导入总报告：`examples/outputs/production_ue_bundles_v1/production_ue_import_set_v1.json`，状态 `complete`、`import_count=9`，9 个地图路径唯一。
- AirSim NED 与 canonical scene 的坐标变换经过导入验证和在线位姿查询验证。
- 外部 RF 查询接口按 UAV 当前位姿对离线线性 path gain 做三线性插值，返回检测小区、逐小区 RSRP、服务小区、SINR 和 outage。
- 最新实跑日志：`runtime_observation_v4.jsonl`。UAV 场景 x 坐标约从 68.63 m 移到 70.57 m，RSRP 约从 -31.88 dBm 变到 -32.13 dBm；查询耗时约 0.17-0.48 ms，并记录 `valid_mask=true`、动作、位姿、速度、碰撞和两个时间戳。
- 越出场景或高度范围时抛出明确错误，不静默返回值；加载时校验 radio 文件 SHA-256、场景 fingerprint 和基站 fingerprint。

结论：任务 E 的 9 城市 UE 导入和外部交互接口闭环完成。它不是 UE C++ 内置自定义传感器，但符合计划允许的外部查询接口边界；UE 不执行实时射线追踪，也不访问未来位置。

## 自动检查

- `41 passed`。
- Ruff 静态检查通过。
- `src`、`scripts`、`tests` Python 语法编译通过。
- Sionna v3 UMa 和 UMi reference 三扇区 128 端口真实计算均通过；此前 64 端口历史代理的计算和运行时查询也通过。

## 尚未完成的事项

- 已冻结首版城市形态、基站组合、`35/65/95/115 m` 测量高度及 `16,777,216 samples/sector` 的 `production_v1` 采样预算。
- 9 个冻结城市已逐一导入并保存为 UE 地图；当前在线 UAV/RF 动态闭环已在代表性示例城市实跑，其他 8 个地图完成静态导入与保存后验证，未逐图重复飞行演示。
- 未实现导航策略、训练算法或未来 RF 真值访问；这些明确不属于本工程。
- 未把外部 RF 查询封装成 UE C++ 自定义传感器，因为当前计划允许使用外部服务/进程接口。

## 2026-10-01 至 2026-10-03 增量动态验收

本节是当前代码与交互式可视化器的新增验收，不改写上面的历史 v3/v4 记录。

- 运行编号：`interactive_city-0c6fbad83430`；城市 profile 为 `sparse_suburban`，道路形态为 `bsp_tjunction`，无线演示网格为 40 m，测量高度为 65 m。
- 任务硬门限：最低 SINR `-4 dB`、最低服务小区 RSS `-105 dBm`、最大中断比例 `0`。
- 真实 LAESim/AirSim 任务日志：`laesim_connectivity_sparse.jsonl`，包含 1 行 mission、647 行 sample 和 1 行 complete。
- 通信约束路线长 `963.78 m`，实际执行约 `199 s`；最终误差 `0.50 m`，小于 `3 m` 到达容差。
- 实际最低/平均 SINR 为 `-3.86/2.61 dB`，实际最低/平均服务小区 RSS 为 `-53.81/-39.64 dBm`；无线中断采样为 0，服务小区切换 17 次。
- 647 个采样点均无碰撞，最终状态为 complete，说明当前代表性场景的 UE 运动、AirSim 位姿、外部 RF 查询和通信约束任务闭环通过。
- 实时状态增加 30 秒过期判断，已停止的旧任务不会再被网页误报为当前场景不一致。
- 实时无线观测现在使用任务自身的 SINR/RSS 门限判定 outage，并在逐点 JSONL 中记录当前高层动作。
- LAESim 已作为独立页签接入网页；“执行任务”只在当前运行未修改、无线地图完整、预检查通过且最近一次 UE 导入一致时可用，并自动启用实时同步。同一网页同时只允许启动一个任务进程。
- “停止任务”采用受控停止：先请求无人机悬停、写入 `type=stopped`、释放 AirSim 控制权；超过 5 秒仍未退出时才强制终止。网页启动的 JSONL 和控制台日志统一保存在 `runtime/missions`。
- 在 `1280 x 720` 浏览器视口完成 LAESim 页实际检查：执行/停止按钮可见，未导入场景时均正确禁用，任务进程显示“未启动”，页面无横向溢出，控制台无 warning/error。
- 当前自动测试为 `95 passed`，Ruff 对 `src`、`tests` 和 `scripts` 的检查全部通过，前端 `app.js` 通过 Node.js 语法检查。
- 重新核对正式产物：9/9 无线运行目录、complete manifest 和 `radio_volume.npz` 均存在，数组尺寸为 `[15,4,500,500]` 或 `[90,4,500,500]`；9/9 UE 地图的导入、保存后验证及全部检查项均为 complete。
