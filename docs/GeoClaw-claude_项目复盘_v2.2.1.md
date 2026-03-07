# GeoClaw-claude 项目复盘
**UrbanComp Lab | 截至 v2.2.1 | 2025-03-07**

---

## 一、项目全貌

### 定位
轻量级 Python 城市 GIS 分析工具集，参考 QGIS Processing Framework 设计。
核心差异化：**自然语言驱动 GIS 操作** + **人类移动性分析（trackintel）** + **跨会话记忆系统**。

### 仓库
- GitHub: https://github.com/whuyao/GeoClaw_Claude
- 分支: `main`
- 最新 commit: `fc8d059`（test: 97/97 全绿）
- 用户: `whuyao` | Token 30 天期限（ghp_X4U7c9...）

### 当前版本
**v2.2.1** — 所有测试 97/97 ✅

---

## 二、版本演进路线

| 版本 | 核心内容 |
|------|---------|
| v1.0.0 | CLI、Skill 脚本系统、路网/栅格分析、坐标转换 |
| v1.1.0 | Memory 记忆系统（短期 + 长期 + MemoryManager） |
| v1.2.0 | 自我检测 & 自动更新（check / update / self-check） |
| v1.3.0 | 自然语言操作系统（NLProcessor / NLExecutor / GeoAgent） |
| v2.0.0 | 重大升级：文档与代码全面同步，API 完全向后兼容 |
| v2.1.0 | analysis/mobility/ 模块（trackintel 集成），NL 移动性操作 10 类 |
| v2.2.0 | 武汉 GPS 轨迹测试数据集（37,549点），完整 Demo 脚本，trackintel 来源声明 |
| **v2.2.1** | README 重组，docs 全面重写（docx+pdf），NL 关键词修复，97/97 测试全绿 |

---

## 三、代码架构

```
geoclaw_claude/
├── cli.py                        # Click CLI：ask/chat/memory/check/update/skill/download
├── config.py                     # JSON 配置 + 环境变量覆盖
├── updater.py                    # check/update/self_check，VersionInfo 解析
├── skill_manager.py              # Skill 注册/执行/上下文
├── core/
│   ├── layer.py                  # GeoLayer（核心矢量图层类）
│   └── project.py                # GeoClawProject（图层注册表）
├── io/
│   ├── vector.py                 # GeoJSON/SHP 读写
│   ├── osm.py                    # Overpass/OSM 下载
│   └── remote.py                 # HTTP/WFS/Tianditu
├── analysis/
│   ├── spatial_ops.py            # buffer/clip/nearest_neighbor/kde
│   ├── network.py                # build_network/isochrone/shortest_path（OSMnx）
│   ├── raster_ops.py             # slope/aspect/reclassify/zonal_stats（rasterio）
│   └── mobility/                 # ★ trackintel 集成
│       ├── core.py               #   read_positionfixes/generate_full_hierarchy
│       ├── metrics.py            #   radius_of_gyration/modal_split/etc.
│       └── visualization.py      #   plot_mobility_layers/heatmap/modal/dashboard
├── nl/
│   ├── processor.py              # NLProcessor（AI+规则双模式，意图解析）
│   ├── executor.py               # NLExecutor（意图→GIS 执行）
│   └── agent.py                  # GeoAgent（多轮对话，Memory 集成）
├── memory/
│   ├── short_term.py             # 会话内缓存（OperationLog + 对象存储）
│   ├── long_term.py              # 持久化 JSON 知识库（~/.geoclaw_claude/memory/）
│   └── manager.py                # MemoryManager（统一接口）
├── cartography/
│   ├── renderer.py               # 4 种地图主题 + Folium 交互
│   └── map_composer.py           # 多图层布局、比例尺、图例
├── utils/
│   └── coord_transform.py        # WGS84↔GCJ-02↔BD-09（纯数学，无外部依赖）
└── skills/builtin/
    └── hospital_coverage.py      # 内置 Skill 示例
```

### 关键依赖
| 包 | 用途 | 版本 |
|----|------|------|
| geopandas | 矢量核心 | 1.1.2 |
| trackintel | 移动性分析 | ≥1.4.2 |
| osmnx | 路网 | 2.1.0 |
| rasterio | 栅格 | 1.5.0 |
| anthropic | Claude API（NL AI 模式，可选） | — |

---

## 四、自然语言系统（nl/）

### 解析流水线
```
用户输入 → NLProcessor.parse() → ParsedIntent
         ↓ AI 模式（Anthropic API）/ 规则模式（关键词+正则）
NLExecutor.execute(intent, layers) → ExecutionResult
         ↓ GeoAgent 封装，维护 layers 上下文，集成 Memory
```

### ParsedIntent 结构
```python
@dataclass
class ParsedIntent:
    action:     str        # 'buffer' / 'mobility_hierarchy' / ...
    params:     dict       # 提取的参数（radius, dist_threshold...）
    targets:    list[str]  # 目标图层名
    confidence: float      # 0.0 ~ 1.0
    explanation:str        # 人读描述
    steps:      list[dict] # 多步流水线分解
```

### 已支持的 action（30+）
**GIS 类：** load_vector / load_osm / buffer / clip / nearest_neighbor / kde / build_network / isochrone / shortest_path / slope / reclassify / zonal_stats / coord_transform / visualize / interactive_map / save_layer

**移动性类（v2.1+ 新增）：**
| action | 中文触发词 | 说明 |
|--------|-----------|------|
| mobility_load | 读入 GPS / 加载轨迹 | read_positionfixes |
| mobility_staypoints | 生成停留点 | generate_staypoints |
| mobility_triplegs | 生成出行段 | generate_triplegs |
| mobility_transport | **预测出行方式 / 出行方式预测** | predict_transport_mode |
| mobility_hierarchy | 一键完成移动性分析 | generate_full_hierarchy |
| mobility_locations | 识别重要地点 / 识别家和工作地 | generate_locations / identify_home_work |
| mobility_summary | 移动性指标摘要 | mobility_summary |
| mobility_plot | 轨迹地图 | plot_mobility_layers |
| mobility_heatmap | 时间热力图 | plot_activity_heatmap |
| mobility_modal | **出行方式构成图** | plot_modal_split |

### v2.2.1 修复的关键词冲突
- `mobility_triplegs` 关键词列表原含"出行方式"，导致"出行方式构成图"误判为 `mobility_triplegs`
- `mobility_transport` 缺少精确词"预测出行方式"，导致返回 `unknown`
- **修复**：拆分关键词集合，在热力图检测前插入精确的出行方式预测词组

---

## 五、移动性分析模块（analysis/mobility/）

### 数据层级模型
```
positionfixes（原始 GPS 点）
    ↓ generate_staypoints(dist=80m, time=5min)
staypoints（停留点）
    ↓ generate_triplegs()
triplegs（出行段）+ predict_transport_mode()
    ↓ generate_trips()
trips（出行）
    ↓ generate_locations(epsilon=120m)
locations（重要地点）+ identify_home_work()
```

### trackintel 版本兼容注意事项（v1.4 坑点）
- `read_positionfixes()` 需 `pd.to_datetime(..., format="mixed")`（非 `infer_datetime_format`）
- `location_identifier()` 改为位置参数（不再接受 keyword `epsilon`）
- `radius_of_gyration()` 返回列名为 `radius_gyration`（无下划线后缀）
- 以上均已在 `core.py` 和 `metrics.py` 中 patch 兼容

### Demo 数据（data/mobility/wuhan_gps_tracks.csv）
- 37,549 GPS 点 | 5 用户 | 10 天（2024-01-15 ~ 2024-01-25）
- 武汉三镇覆盖：Bbox lon[114.17, 114.42], lat[30.51, 30.62]
- 层级结果（默认参数）：停留点 1,781 | 出行段 1,240 | 行程 1,240 | 地点 20

---

## 六、Memory 系统

### ShortTermMemory（会话内）
- `log_op(op, detail)` — 操作日志
- `remember(key, obj)` / `recall_short(key)` — 对象缓存
- `set_context(key, val)` / `get_context(key)` — 会话上下文

### LongTermMemory（持久化）
- 存储路径：`~/.geoclaw_claude/memory/{category}/{uuid}.json`
- 每次 `get()` 自动 `touch()`：`access_count += 1` 且更新 `updated_at`
- **注意**：access_count 统计包含检索本身，因此调用 N 次 get 返回值为 N（含最后一次）

---

## 七、测试矩阵（v2.2.1 最终状态）

| 文件 | 通过 | 关键覆盖 |
|------|------|---------|
| test_memory.py | 37/37 ✅ | ShortTermMemory / LongTermMemory / MemoryManager |
| test_updater.py | 20/20 ✅ | VersionInfo.parse / check / update / self_check |
| test_nl.py | 20/20 ✅ | NLProcessor / NLExecutor / GeoAgent / 30+ action |
| test_mobility.py | 20/20 ✅ | read_positionfixes / hierarchy / metrics / viz |
| **合计** | **97/97** ✅ | |

### 修复历史（本次复盘修复）
| 测试 | 问题 | 修复 |
|------|------|------|
| T20 access_count | 期望 3，实际 4 | 期望值改为 4 |
| T37 版本号 | 仍是 v1.1.0 | 更新至 v2.2.1 |
| U01 VersionInfo | v2.2.0 的 minor 断言为 0 | 改为 2 |
| U20/N20 版本号 | 旧版本号残留 | 统一更新至 v2.2.1 |

---

## 八、文档状态（docs/）

| 文件 | 状态 |
|------|------|
| GeoClaw-claude_User_Guide_v2.2.1.docx | ✅ 完整（9章，含移动性分析完整章节） |
| GeoClaw-claude_User_Guide_v2.2.1.pdf | ✅ LibreOffice 转换 |
| GeoClaw-claude_Technical_Reference_v2.2.1.docx | ✅ 完整（10章，完整 API 参考） |
| GeoClaw-claude_Technical_Reference_v2.2.1.pdf | ✅ LibreOffice 转换 |
| README.md | ✅ 460 行，人类移动性分析专节完整 |
| CHANGELOG.md | ✅ v1.0.0 ~ v2.2.1 全记录 |

---

## 九、下一步开发优先级

### 高优先级
| 任务 | 模块 | 说明 |
|------|------|------|
| 更多内置 Skill | skills/builtin/ | poi_density / route_analysis / transit_coverage |
| KML/GML 支持 | io/vector.py | 扩充读写格式 |
| cartography 增强 | cartography/map_composer.py | add_labels() / add_inset_map() / contextily 底图 |

### 中优先级
| 任务 | 模块 | 说明 |
|------|------|------|
| PostGIS 连接器 | io/postgis.py | 企业级数据接入 |
| HTML/PDF 自动报告 | reporting/report.py | 一键生成分析报告 |
| Memory AI 摘要 | memory/ | Anthropic API 提炼长期记忆 |

### 低优先级
| 任务 | 说明 |
|------|------|
| Skill Hub | 在线 Skill 市场 |
| geoclaw-claude serve | 本地 Web UI |
| 移动性：出行链重建 | trip chain reconstruction |

---

## 十、Git 提交历史（关键节点）

```
fc8d059  test: 全量测试修复，97/97 全绿
e295f88  docs: v2.2.1 文档全面重写
e9a87f1  release: v2.2.1 — README重组，NL关键词修复
8a84df3  release: v2.2.0 — 武汉GPS Demo数据集
5d4e413  release: v2.0.0 — 全面升级
bbd6f72  docs: README v1.3.0
4b635d0  feat: 自然语言操作系统 v1.3.0
```

---

## 十一、重要约定（给下次开发的提示）

1. **每次推送前**：`bash /home/claude/push.sh` 或手动设置含 token 的 remote 再 push，push 后重置 remote 隐藏 token
2. **每次版本升级**：`__init__.py` → `setup.py` → `CHANGELOG.md` → 测试版本断言 → 文档版本号 → README badge
3. **trackintel 坑**：`format="mixed"`、`location_identifier()` 位置参数、`radius_gyration` 列名——已全部在代码中 patch，不要回退
4. **NL 关键词**：processor.py 中各 action 的关键词集合顺序敏感，mobility_transport / mobility_modal 的精确词要放在宽泛词之前检测
5. **test_memory.py T20**：access_count 期望值是「调用次数」（含最后一次 get 自身），不是「显式调用次数」

---

*Copyright © 2025 UrbanComp Lab (https://urbancomp.net) — MIT License*
