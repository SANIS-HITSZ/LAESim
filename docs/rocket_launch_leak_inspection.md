# 火箭发射平台漏气巡检

本工程的 FlyCo 风格发射塔巡检演示位于：

```text
<工作区>\rocket_launch_inspection
```

完整操作、坐标约定和命令见：

```text
<工作区>\rocket_launch_inspection\README.md
```

关键约定：

- UE 编辑器脚本根据选中发射塔 Actor 的包围盒生成漏气粒子和扫描配置。
- AirSim 控制与检测全部使用指定 vehicle 的 starting-point local NED 坐标。
- AirSim `simPlot*` 使用世界 NED，因此绘图前会加回 `vehicle_start_ned_m`。
- 飞行使用物理动力学速度指令，不使用 Pose 瞬移。
- 当前漏气检测是距离加视场角代理，粒子只负责视觉表现，并非真实气体传感器仿真。
