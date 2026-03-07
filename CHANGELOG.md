# GeoClaw-claude 版本历史

**UrbanComp Lab** (https://urbancomp.net)

---

## v1.3.0 (2025-03-07)

### 新增：自然语言操作系统（NL 模块）

**`geoclaw_claude/nl/` 模块**

- `NLProcessor` — 自然语言意图解析器，两种模式：
  - **AI 模式**：调用 Claude API 语义理解，精准识别意图/参数/链式操作
  - **规则模式**：关键词+正则离线解析，无需 API Key，随时可用
- `NLExecutor` — 意图执行器，将 `ParsedIntent` 转为实际 GIS 函数调用：
  - 图层上下文管理（命名图层字典、模糊匹配、Memory 集成）
  - 支持 15+ 操作：load / buffer / clip / nn / kde / isochrone / render / ...
  - 流水线自动顺序执行（`pipeline` 多步操作）
- `GeoAgent` — 多轮对话代理（Processor + Executor 一体）：
  - `agent.chat(text)` 完成 解析→确认→执行→反馈 全流程
  - 低置信度（<55%）自动请求用户确认
  - 跨轮上下文保持（可用图层、上一步结果、最近输入）
  - Memory 集成：操作自动记录到短期/长期记忆
- `ParsedIntent` — 结构化意图数据类，支持多步流水线、`to_dict()` 序列化

**CLI 新增 2 个命令**
```
geoclaw-claude ask "对医院做1公里缓冲区"     # 单条自然语言指令
geoclaw-claude ask --dry-run "核密度分析"    # 只解析，输出 JSON
geoclaw-claude ask --rule "裁剪到边界范围"   # 强制规则模式（离线）
geoclaw-claude chat                          # 交互式多轮对话
geoclaw-claude chat --ai                     # 强制 AI 模式
```

### 已支持的自然语言操作

| 操作 | 示例描述 |
|------|---------|
| 加载数据 | "加载 hospitals.geojson" |
| 缓冲区 | "对医院做1公里缓冲区" / "500米范围" |
| 裁剪 | "用边界裁剪医院数据" |
| 最近邻 | "计算医院到地铁站的最近邻距离" |
| 核密度 | "对医院做核密度分析" / "密度热力图" |
| 等时圈 | "以医院为中心做10分钟步行等时圈" |
| 坐标转换 | "把医院数据从 wgs84 转成 gcj02" |
| 下载OSM | "下载武汉市公园数据" |
| 制图 | "可视化当前结果" / "用交互地图显示" |
| 多步流水线 | "对医院做1公里缓冲区然后可视化" |

### 测试
- NL 模块测试 20/20 通过（N01-N20）
- Memory + Updater 回归测试 5/5 通过

---

## v1.2.0 (2025-03-07)

### 新增：自我检测与自动更新（Updater 模块）

**`geoclaw_claude/updater.py`**

- `check()` — 检测 GitHub 最新版本，与本地对比，返回 `CheckResult`（状态/版本/commit 信息）
- `update()` — 自动拉取最新代码并安装：
  1. 版本检测（已最新则跳过，`--force` 强制执行）
  2. `git pull origin main`
  3. `pip install -e .`
  4. 打印 CHANGELOG diff
  5. 可选 `--test`：更新后自动运行测试套件验证
- `self_check()` — 全面健康检查报告（版本 + 模块完整性 + 依赖状态 + Git 信息 + 更新状态）
- `changelog_diff()` — 从 GitHub Raw 获取指定版本之后的 CHANGELOG 内容
- `VersionInfo` — 语义版本解析与比较（`<` / `==` / `<=`）
- `CheckResult` / `UpdateResult` — 结果数据类，含 `.summary()` 友好输出

**CLI 新增 3 个命令**
```
geoclaw-claude check               # 检测是否有新版本
geoclaw-claude check --json        # JSON 输出（适合脚本化）
geoclaw-claude update              # 拉取最新代码并安装
geoclaw-claude update --force      # 强制更新（即使已是最新）
geoclaw-claude update --test       # 更新后运行测试套件
geoclaw-claude self-check          # 全面健康检测报告
geoclaw-claude self-check --quick  # 快速模式（跳过远程检测）
geoclaw-claude self-check --json   # JSON 输出
```

### 测试
- Updater 测试 20/20 通过（U01-U20）
- Memory 回归测试 9/9 通过
- 覆盖：VersionInfo 解析比较、网络请求、check/update/self_check 逻辑、CLI 命令注册

---

## v1.1.0 (2025-03-07)

### 新增：Memory 系统

**短期记忆 `ShortTermMemory`**
- 会话内操作日志（`log_operation`）：记录函数名、参数、耗时、成功/失败状态
- 中间结果缓存（`store` / `retrieve`）：支持任意值（GeoLayer/ndarray/dict 等）
- TTL 自动过期机制（可按条目独立设置生存时间）
- 会话上下文管理（`set_context` / `get_context`，永不过期）
- 按类别/标签查询，LRU 淘汰策略
- `summarize()` 生成会话摘要（操作序列、频率统计、错误汇总）

**长期记忆 `LongTermMemory`**
- JSON 持久化存储（`~/.geoclaw_claude/memory/`），跨会话保留
- 四大类别：`knowledge`（分析规律）/ `session`（任务复盘）/ `dataset`（数据档案）/ `preference`（用户偏好）
- 关键词全文检索（标题 + 标签 + content 三层搜索）
- 按标签、类别、时间、重要性多维检索
- 访问计数（`access_count`）+ upsert 更新
- `compact()` 压缩：自动清理低重要性旧条目

**统一管理器 `MemoryManager`**
- `start_session()` / `end_session()` 会话生命周期管理
- `end_session()` 自动将短期摘要 flush 入长期记忆
- 重要性自动评分（操作数多 + 无错误 → 评分高）
- `learn()` 手动存入领域知识
- `recall()` 关键词检索 / `recall_recent()` / `recall_important()`
- `get_memory()` 全局单例，支持 `reset_memory()` 重置
- `print_status()` 可视化状态面板

**CLI 新增 `memory` 命令组**
```
geoclaw-claude memory status          # 查看系统状态
geoclaw-claude memory list [-c cat]   # 列出长期记忆
geoclaw-claude memory search "关键词" # 搜索记忆
geoclaw-claude memory learn <title> <content>  # 手动存知识
geoclaw-claude memory forget <id>     # 删除记忆
geoclaw-claude memory compact         # 压缩旧记忆
geoclaw-claude memory export          # 导出 JSON
```

### 修复
- `nearest_neighbor()`：修复地理坐标系下 `nn_distance=0` 的 BUG（改用 Web Mercator→UTM 投影）
- `nearest_neighbor()`：兼容 GeoDataFrame / GeoLayer 双输入，消除 centroid UserWarning
- `spatial_ops`：新增 `kde()` 核密度估计函数

### 测试
- Memory 系统测试 37/37 全部通过（T01-T37）
- 覆盖：STM CRUD、TTL、操作日志、摘要生成、LTM 持久化、检索、flush、Manager 生命周期、全局单例、GIS 集成

---

## v1.0.0 (2025-03)

**首个正式发布版本。**

### 新增功能
- **CLI 命令行工具** (`geoclaw-claude`)
  - `onboard` — 交互式初始化向导，引导配置 API Key、数据目录、网络参数
  - `config show/get/set` — 配置项查看与修改
  - `skill list/run/install/new` — Skill 生命周期管理
  - `download osm/url` — 命令行数据下载
  - `test` — 环境验证
- **配置系统** (`config.py`)
  - 统一配置文件 `~/.geoclaw_claude/config.json`
  - 支持环境变量覆盖（`GEOCLAW_<KEY>=value`）
- **Skill 系统** (`skill_manager.py`)
  - 用户自定义分析脚本规范（`SKILL_META` + `run(ctx)`）
  - `SkillContext` 提供图层访问、参数读取、AI调用、结果保存接口
  - 内置 Skill：`hospital_coverage`（医院覆盖分析 + AI 解读）
- **远程数据下载** (`io/remote.py`)
  - HTTP/HTTPS 文件下载（含缓存机制）
  - WFS 标准接口支持
  - 天地图 POI API 接入
- **路网分析完善** (`analysis/network.py`)
  - `build_network()` — 从地名/bbox/GeoLayer 构建路网
  - `shortest_path()` — Dijkstra 最短路径（距离/时间权重）
  - `isochrone()` — N 分钟等时圈多边形
  - `service_areas()` — 批量设施服务区分析
  - `network_stats()` — 路网密度/连通性/迂回度统计
- **栅格空间分析** (`analysis/raster_ops.py`)
  - `RasterLayer` 栅格数据容器
  - `slope()` / `aspect()` / `hillshade()` — DEM 地形分析
  - `reclassify()` — 栅格重分类
  - `raster_calc()` — 栅格计算器（numpy 表达式）
  - `zonal_stats()` — 矢量分区统计
  - `clip_raster()` / `resample()` — 裁剪与重采样
- **坐标转换工具** (`utils/coord_transform.py`)
  - WGS84 ↔ GCJ-02 ↔ BD-09 三坐标系完整互转
  - `transform_layer()` 支持整个 GeoLayer 批量转换
- **安装支持**
  - `install.sh` 一键安装脚本（`--dev` / `--mini` 模式）
  - `setup.py` 支持 `pip install -e .`
  - 命令注册 `geoclaw-claude` 入口点

### 改进
- 全面重命名：`geoclaw` → `geoclaw_claude`，避免与实验室其他项目冲突
- 所有模块统一添加 UrbanComp Lab 版权声明
- `__init__.py` 加入完整版本历史追踪

---

## v0.2.0 (2025-02)

### 新增
- CLI 骨架（click）
- Skill 系统原型
- 远程数据下载基础框架
- 路网分析模块骨架（`network.py`）

### 改进
- 模块重命名为 `geoclaw_claude`

---

## v0.1.0 (2025-01)

**初始版本（内部使用）。**

### 功能
- `GeoLayer` 核心图层类
- `GeoClawProject` 项目管理
- OSM/Overpass 数据下载 (`io/osm.py`)
- 空间分析：缓冲区、叠加、最近邻、KDE (`analysis/spatial_ops.py`)
- 静态制图与交互地图 (`cartography/`)
- GeoJSON/Shapefile/CSV 读写 (`io/vector.py`)
- 武汉城市分析示例 (`examples/wuhan_analysis.py`)

---

*GeoClaw-claude 由 UrbanComp Lab (https://urbancomp.net) 开发维护，MIT 许可证开放使用。*
