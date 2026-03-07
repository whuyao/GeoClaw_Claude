"""
GeoClaw-claude
==============
UrbanComp Lab (https://urbancomp.net) 开发的轻量级 Python 地理信息分析工具集。
参考 QGIS Processing Framework 设计，支持空间分析、路网分析、栅格处理与 AI Skill。

版本历史:
  v1.0.0 (2025-03)  首个正式版本。模块重构，加入 CLI、配置系统、Skill 框架、
                    路网分析（最短路径/等时圈）、栅格分析（DEM/坡度/重分类/分区统计）、
                    远程数据下载（HTTP/WFS/天地图）、坐标转换（WGS84/GCJ02/BD09）。
  v0.2.0 (2025-02)  增加 CLI 命令行工具、Skill 系统、远程数据下载、路网分析骨架。
  v0.1.0 (2025-01)  初始版本。核心图层类、OSM 下载、空间分析、制图模块。

版权:
  Copyright (c) 2025 UrbanComp Lab, https://urbancomp.net
  MIT License
"""

__version__     = "1.0.0"
__author__      = "UrbanComp Lab"
__author_url__  = "https://urbancomp.net"
__license__     = "MIT"
__description__ = "Python GIS Toolkit by UrbanComp Lab"

# 快速导入常用类
from geoclaw_claude.core.layer   import GeoLayer
from geoclaw_claude.core.project import GeoClawProject
