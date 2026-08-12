# LAESim 可复现快速入门实验

本目录提供三个互相独立的最小实验：

1. [`heterogeneous_fleet`](heterogeneous_fleet/README.md)：在同一个 `AirGround` 场景中配置并控制无人机、汽车和船，熟悉 Python API、载具名称和独立 RPC 端口。
2. [`ns3_network`](ns3_network/README.md)：把 `settings.json` 中的载具自动映射为 ns-3 节点，验证通信范围内交付和范围外丢包。
3. [`nadir_geotiff_collection`](nadir_geotiff_collection/README.md)：导入 GeoTIFF，规划覆盖航线，并采集稳定下视图像、GPS 与物理真值。

每个实验都包含完整的 `settings.json`、运行脚本、预期结果和故障排查。第一次使用建议按顺序完成。
