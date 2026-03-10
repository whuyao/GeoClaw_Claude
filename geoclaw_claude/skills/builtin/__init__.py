# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
内置 Skill 注册表。

分类：
  vector  — 矢量分析 (vec_*)
  network — 网络分析 (net_*)
  raster  — 栅格分析 (rst_*)
  urban   — 城市应用
"""
from pathlib import Path

BUILTIN_SKILLS = [
    # 矢量分析
    "vec_buffer", "vec_overlay", "vec_spatial_join", "vec_kde", "vec_zonal_stats",
    # 网络分析
    "net_shortest_path", "net_isochrone", "net_stats",
    # 栅格分析
    "rst_terrain", "rst_reclassify", "rst_zonal_clip",
    # 城市应用
    "hospital_coverage", "retail_site_ai", "retail_site_algo",
]

BUILTIN_DIR = Path(__file__).parent
