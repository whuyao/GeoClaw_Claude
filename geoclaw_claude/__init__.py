"""
GeoClaw-claude
==============
UrbanComp Lab (https://urbancomp.net) 开发的轻量级 Python 地理信息分析工具集。
参考 QGIS Processing Framework 设计，支持空间分析、路网分析、栅格处理与 AI Skill。

版本历史:
  v2.4.0 (2025-03)  Skill 体系全面升级：新增商场选址典型案例两种实现
                    （retail_site_ai LLM驱动版 / retail_site_algo MCDA算法版）；
                    新增 SkillAuditor 静态安全审计模块（AST+正则，5级风险分类）；
                    SkillManager.install 集成安全审计与交互确认流程；
                    CLI 新增 skill audit 子命令；CHANGELOG 与规范文档同步更新。
  v2.3.0 (2025-03)  Gemini API 支持，记忆存档（MemoryArchive），
                    向量语义检索（VectorSearch/TF-IDF），
                    onboard 多模型配置向导，上下文压缩自动集成增强。
  v2.2.1 (2025-03)  README 全面重组：人类移动性分析专节增强，
                    新增自然语言调用说明与 Demo 示例，NL 关键词
                    映射修复（出行方式构成图/预测出行方式优先级）。
  v2.2.0 (2025-03)  武汉城市移动性 Demo 数据集与完整案例。新增
                    data/mobility/ 测试数据（37,549 个 GPS 轨迹点，5 位武汉
                    居民 10 天数据）、examples/wuhan_mobility_demo.py 完整
                    演示脚本（7 步分析 + 5 张可视化图表）。明确标注算法来源
                    trackintel (mie-lab/trackintel)，更新 README 与 CHANGELOG。
  v2.1.0 (2025-03)  复杂网络与移动性分析（trackintel 集成）。新增
                    geoclaw_claude/analysis/mobility/ 模块：GPS 轨迹→停留点→
                    出行段→出行→重要地点完整层级生成；回转半径/跳跃距离/交通
                    方式识别/家工作地识别等指标；活动热力图/分层地图可视化。
                    NL 解析器新增 10 类移动性操作关键词。
  v2.0.0 (2025-03)  重大版本升级。自然语言操作系统全面成熟：NLProcessor 双模式
                    解析、NLExecutor GIS 执行引擎、GeoAgent 多轮对话代理；
                    CLI 新增 ask / chat 命令。README 与 CHANGELOG 全面同步。
  v1.3.0 (2025-03)  自然语言操作系统（NL模块）。新增 NLProcessor（AI/规则双模式
                    意图解析）、NLExecutor（意图→GIS函数执行）、GeoAgent（多轮对话
                    代理）。CLI 新增 ask（单条指令）和 chat（交互式对话）命令。
  v1.2.0 (2025-03)  自我检测与自动更新。新增 Updater 模块：check() 检测远程
                    最新版本，update() 拉取并安装，self_check() 全面健康检查。
                    CLI 新增 check / update / self-check 三个命令。
  v1.1.0 (2025-03)  Memory 系统。新增短期记忆（ShortTermMemory）、长期记忆
                    （LongTermMemory）、统一管理器（MemoryManager）。支持操作日志、
                    中间结果缓存、跨会话知识持久化、关键词检索与自动复盘摘要。
                    修复 nearest_neighbor 距离为0的BUG；新增 kde() 函数。
  v1.0.0 (2025-03)  首个正式版本。模块重构，加入 CLI、配置系统、Skill 框架、
                    路网分析（最短路径/等时圈）、栅格分析（DEM/坡度/重分类/分区统计）、
                    远程数据下载（HTTP/WFS/天地图）、坐标转换（WGS84/GCJ02/BD09）。
  v0.2.0 (2025-02)  增加 CLI 命令行工具、Skill 系统、远程数据下载、路网分析骨架。
  v0.1.0 (2025-01)  初始版本。核心图层类、OSM 下载、空间分析、制图模块。

版权:
  Copyright (c) 2025 UrbanComp Lab, https://urbancomp.net
  MIT License
"""

__version__     = "2.4.1"
__author__      = "UrbanComp Lab"
__author_url__  = "https://urbancomp.net"
__license__     = "MIT"
__description__ = "Python GIS Toolkit by UrbanComp Lab"

# 快速导入常用类
from geoclaw_claude.core.layer   import GeoLayer
from geoclaw_claude.core.project import GeoClawProject
from geoclaw_claude.memory       import get_memory, MemoryManager
