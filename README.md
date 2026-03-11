# GeoClaw-Claude

> [!WARNING]
> **安全声明 / Security Notice**
>
> GeoClaw 是一个具备文件系统访问、代码执行和网络请求能力的 AI 智能体框架。
> **强烈建议在沙盒环境（虚拟机、Docker 容器或独立测试机）中运行，不要直接在主力工作机上部署。**
>
> GeoClaw is an AI agent framework with file system access, code execution, and network request capabilities.
> **It is strongly recommended to run it in a sandboxed environment (VM, Docker container, or a dedicated test machine). Do not deploy directly on your primary workstation.**

> **UrbanComp Lab** 出品的自然语言驱动城市地理信息分析平台
> https://urbancomp.net

[![Version](https://img.shields.io/badge/version-3.1.4-blue)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-577%2F577-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.9+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![LLM](https://img.shields.io/badge/LLM-Claude%20%7C%20Gemini%20%7C%20GPT%20%7C%20Qwen%20%7C%20Ollama-blueviolet)](#多-llm-provider)
[![Skills](https://img.shields.io/badge/builtin%20skills-15-success)](#内置-skill-列表)
[![SRE](https://img.shields.io/badge/SRE-Phase%203-7B2D8B)](#spatial-reasoning-engine-sre)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-compat%20export-lightgrey)](#openclaw--agentskills-兼容导出)

参考 QGIS Processing Framework 设计，专注于城市地理空间数据分析。核心理念是用**自然语言**直接驱动 GIS 操作——一句话完成从数据加载、空间分析到制图输出的完整流水线。

---

## 目录

- [快速开始](#快速开始)
- [v3.1.4 新特性：活人感对话记忆系统](#v314-新特性活人感对话记忆系统)
- [v3.1.3 新特性：OpenClaw 兼容导出](#openclaw--agentskills-兼容导出)
- [v3.1.2 新特性：15 个内置 Skill + Profile 增强](#v312-新特性)
- [v3.1.1 新特性：可靠性修复](#v311-新特性)
- [v3.1.0 新特性：Ollama 本地大模型](#ollama-本地大模型支持)
- [Spatial Reasoning Engine (SRE)](#spatial-reasoning-engine-sre)
- [Skill 系统](#skill-系统)
- [自然语言操作系统](#自然语言操作系统)
- [Memory 记忆系统](#memory-记忆系统)
- [人类移动性分析](#人类移动性分析)
- [多 LLM Provider](#多-llm-provider)
- [安装与依赖](#安装与依赖)
- [更新](#更新)
- [卸载与重装](#卸载与重装)
- [项目结构](#项目结构)
- [测试矩阵](#测试矩阵)
- [版本历史](#版本历史)
- [算法来源声明](#算法来源声明trackintel)

---

## 快速开始

```bash
# 1. 克隆并安装
git clone https://github.com/whuyao/GeoClaw_Claude.git
cd GeoClaw_Claude && bash install.sh

# 2. 初始化（选 AI 模型 + 设置输出目录）
geoclaw-claude onboard

# 3. 开始分析
geoclaw-claude ask "下载武汉市医院数据，做 1 公里缓冲区，用交互地图显示"
```

如需卸载或重装，参见 [卸载与重装](#卸载与重装) 章节。

更多用法：

```bash
# 多轮对话模式（含活人感记忆）
geoclaw-claude chat

# 检查是否有新版本
geoclaw-claude check

# 一键更新到最新版本（git pull + pip install）
geoclaw-claude update

# 运行内置 Skill（无需 API Key）
geoclaw-claude skill run retail_site_algo --data candidates.geojson --top_n=3

# 导出 Skill 为 OpenClaw 格式
geoclaw-claude skill export vec_buffer
geoclaw-claude skill export --all --output ./openclaw_skills/

# 搜索历史记忆
geoclaw-claude memory vsearch "武汉医院空间分析"
```

---

## v3.1.4 新特性：活人感对话记忆系统

v3.1.4 是一次**对话体验**的系统性升级，让 GeoClaw 从「工具」进化为「有记忆的分析伙伴」。

### 三项核心改造

#### ① 跨轮记忆注入（Alive System Prompt）

每次对话调用前，`GeoAgent` 自动构建包含完整上下文的 system prompt：

```
soul.md 身份边界（GeoClaw 是什么）
    +
user.md 用户偏好（角色、语言、工具偏好）
    +
本次会话操作摘要（今日做了什么）
    +
长期记忆片段（历史分析复盘、用户习惯）
    ↓
_build_alive_system_prompt() → 注入 LLM
```

效果：GeoClaw 记得你是谁、你今天做了什么、你之前的研究习惯——对话有连贯性，不需要每次重新介绍自己。

#### ② AI 优先模式（AI-First）

- **无 API Key 时**：打印清晰的五行引导提示，明确告知当前为离线规则模式，提供配置命令示例
- **欢迎语**：规则模式下显示 `⚠ 建议配置 API Key 启用 AI 模式`，不再静默降级
- **默认模型**：`config` 默认模型更新为 `gpt-5.1-chat-latest`

```bash
# 配置 API Key（五种 Provider 均支持）
export OPENAI_API_KEY=sk-...        # OpenAI (gpt-5.1-chat-latest 默认)
export ANTHROPIC_API_KEY=sk-...     # Claude
export GEMINI_API_KEY=...           # Gemini
export QWEN_API_KEY=...             # 通义千问
# 或本地 Ollama（无需 Key）
```

#### ③ GPT-5.x / o-series API 兼容

修复了 `gpt-5.1-chat-latest`、`o1`、`o3`、`o4` 系列使用 `max_completion_tokens`（而非旧版 `max_tokens`）的 API 兼容性问题。GeoClaw 自动检测模型系列，透明切换参数。

### 30 轮对话测试效果

以虚拟用户「姚静涵」（城市规划博士生）连续 30 轮纯聊天验证，`gpt-5.1-chat-latest` 驱动：

| 验证维度 | 测试轮次 | 结果 |
|---------|---------|------|
| 记忆连贯性 | Q16 / Q17 / Q27 | 准确回引前轮研究背景、样本量、研究者画像 |
| 学术深度 | Q5 / Q10 / Q18 | Tobler 定律局限、MAUP、混合方法有实质分析 |
| 活人感 | Q2 / Q24 / Q30 | 对「有性格吗」「会无聊吗」有自然、有温度的回应 |
| 主动参与 | Q4 / Q6 | 主动提出延伸问题，展现对话连续性 |
| 语言适配 | 全程 | 中英文自然切换，与用户风格对齐 |

---

## OpenClaw / AgentSkills 兼容导出

GeoClaw v3.1.3 新增**单向兼容导出**功能，将 GeoClaw Skill 导出为 [OpenClaw](https://openclaw.ai) / AgentSkills 兼容格式（`SKILL.md` + 元数据文件）。

### 导出方向

```
GeoClaw Skill (.py)  →  export_openclaw()  →  SKILL.md + .geoclaw_compat.json
                                                    ↓
                                           可直接安装到 OpenClaw
```

> **注意**：导出方向为单向（GeoClaw → OpenClaw）。两者执行哲学不同，不支持双向运行时兼容。

### 使用方法

```bash
geoclaw-claude skill export vec_buffer            # 导出单个 Skill
geoclaw-claude skill export --all                 # 导出所有内置 Skill
geoclaw-claude skill export --all --only-compat   # 仅导出声明兼容的 Skill
geoclaw-claude skill export --all --output ./my_openclaw_skills/
```

Python API：

```python
from geoclaw_claude.skill_manager import SkillManager
sm = SkillManager()
sm.export_openclaw("vec_buffer", output_dir="./openclaw_skills/")
sm.export_openclaw_all(output_dir="./openclaw_skills/", only_compat=True)
```

### agentskills_compat 字段

在 `SKILL_META` 中新增可选字段（所有 15 个内置 Skill 均已声明）：

```python
"agentskills_compat": {
    "enabled": True,
    "export_description": "Run vector buffer analysis on GeoJSON files.",
    "requires_bins": ["python3", "geoclaw-claude"],
    "requires_env": [],
    "homepage": "https://github.com/whuyao/GeoClaw_Claude"
}
```

---

## v3.1.2 新特性

### 内置 Skill 列表（15 个）

| 分类 | Skill 名称 | 功能描述 |
|------|-----------|---------| 
| 矢量 | `vec_buffer` | 点/线/面缓冲区分析，支持合并与面积统计 |
| 矢量 | `vec_kde` | 核密度估计（KDE），热点分析，生成密度栅格 |
| 矢量 | `vec_overlay` | clip / intersect / union 叠加分析 |
| 矢量 | `vec_spatial_join` | 空间连接与最近邻，属性关联 |
| 矢量 | `vec_zonal_stats` | 按多边形区域聚合统计 |
| 栅格 | `rst_terrain` | DEM 坡度/坡向/山体阴影分析 |
| 栅格 | `rst_reclassify` | 栅格重分类，NDVI 等多波段表达式 |
| 栅格 | `rst_zonal_clip` | 分区统计 / 矢量掩膜裁剪 / 空间重采样 |
| 路网 | `net_isochrone` | 等时圈分析，设施可达服务区 |
| 路网 | `net_shortest_path` | 路网最短路径，含距离/时间统计 |
| 路网 | `net_stats` | 路网拓扑指标（节点/边/度/连通性）|
| 选址 | `retail_site_algo` | 商场选址（MCDA 多准则决策，纯算法）|
| 选址 | `retail_site_ai` | 商场选址（空间指标 + LLM 综合评判）|
| 环境 | `env_heat_island` | 城市热岛效应（不透水面/绿化/水体 → UHI 指数）|
| 医疗 | `hospital_coverage` | 医院服务覆盖分析，含 AI 解读 |

### 对话驱动 user.md 自动更新

`agent.end()` 时自动从对话中提取用户偏好，写入 `user.md`：城市偏好、研究领域推断、会话摘要、语言偏好/沟通风格。

---

## v3.1.1 新特性

关键可靠性修复：

- 修复 `render_map` / `render_interactive` 在无 GUI 终端导致的 ImportError
- 修复 `plt.show()` 在无 GUI 终端挂死（强制 Agg 后端）
- 修复 `chat` 模式下 `output_dir` 未初始化
- 新增 `chat` action：LLM 直接处理闲聊，不再退化为关键词匹配
- onboard 配置时 API Key 明文可见 + 脱敏摘要显示

---

## Ollama 本地大模型支持

GeoClaw v3.1.0 新增 **Ollama** Provider，支持完全离线、无需 API Key 的本地大模型推理。

### 快速配置

```bash
# 安装 Ollama（https://ollama.com/download）并启动
ollama serve

# 拉取模型（推荐 qwen3:8b）
ollama pull qwen3:8b

# 配置 GeoClaw 使用 Ollama
geoclaw-claude onboard
```

### 推荐模型（截至 2026-03）

| 模型 | 拉取命令 | VRAM | 特点 |
|------|---------|------|------|
| **qwen3:8b** ★ | `ollama pull qwen3:8b` | 6 GB | 默认推荐，中文最强 |
| **qwen3.5:9b** ★ | `ollama pull qwen3.5:9b` | 8 GB | Qwen3.5 轻量推荐 |
| qwen3.5:35b-a3b | `ollama pull qwen3.5:35b-a3b` | 8 GB | 服务器推荐，MoE 架构 |
| deepseek-r1:7b | `ollama pull deepseek-r1:7b` | 6 GB | SRE 分析优选 |
| llama4:scout | `ollama pull llama4:scout` | 16 GB | 原生多模态 MoE |
| gemma3:9b | `ollama pull gemma3:9b` | 6 GB | Google 出品，128K 上下文 |

**Provider 优先级（自动模式）：** `anthropic → gemini → openai → qwen → ollama`

---

## Spatial Reasoning Engine (SRE)

SRE 是 GeoClaw v3.0 的核心创新，在执行 GIS 分析前自动进行**专业地理推理**，输出结构化工作流方案。

### Phase 3 四项能力

| 能力 | 字段 | 说明 |
|------|------|------|
| 五维不确定性量化 | `uncertainty_score` | 0-1 评分，数据质量/方法/时间/空间/假设 |
| 分析模式识别 | `analysis_mode` | exploratory / confirmatory / causal / descriptive |
| 参数敏感性说明 | `parameter_sensitivity` | 8 类关键参数的敏感性与建议范围 |
| MAUP 风险评估 | `maup_risk` | 可变面积单元问题风险（high/medium/low）|

```python
from geoclaw_claude.reasoning import reason

result = reason("分析武汉地铁站周边商业活跃度",
                datasets=[{"id": "metro", "type": "vector", "crs": "EPSG:4326"}])
print(result.summary_text(lang="zh"))
# [SRE] 任务类型: comparison | 分析模式: exploratory
#       不确定性: medium (0.38) | MAUP 风险: low | 步骤: 4
```

> SRE 所有逻辑均为纯规则实现，离线可用，不依赖 LLM。

---

## Skill 系统

```bash
geoclaw-claude skill list                          # 列出所有 Skill
geoclaw-claude skill run vec_buffer --distance=500 # 运行 Skill
geoclaw-claude skill install ./my_skill.py         # 安装自定义 Skill
geoclaw-claude skill audit my_skill                # 安全审计（25+ 规则）
geoclaw-claude skill export vec_buffer             # 导出为 OpenClaw 格式
```

**最小 Skill 模板：**

```python
SKILL_META = {
    "name": "my_skill",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "自定义分析 Skill",
    "agentskills_compat": {           # 可选：OpenClaw 兼容声明
        "enabled": True,
        "export_description": "English description.",
        "requires_bins": ["python3", "geoclaw-claude"],
        "requires_env": [],
    }
}

def run(ctx):
    layer = ctx.get_layer("input")
    radius_km = float(ctx.param("radius_km", default=1.0))
    from geoclaw_claude.analysis.spatial_ops import buffer
    result_layer = buffer(layer, radius_km * 1000, unit="meters")
    ai_comment = ctx.ask_ai("简述空间覆盖分布规律。")
    return ctx.result(output=result_layer, commentary=ai_comment)
```

---

## 自然语言操作系统

支持 17 类操作（数据加载、缓冲区、裁剪、叠加、KDE、等时圈、最短路径、坐标转换、制图、记忆检索等）。

**双模解析：**
- **AI 模式**：LLM 语义理解（置信度 ≥ 0.60），`gpt-5.1-chat-latest` 为默认模型
- **规则模式**：关键词 + 正则，离线可用，无需 API Key（降级时有明确引导提示）

---

## Memory 记忆系统

| 层级 | 范围 | 核心能力 |
|------|------|---------| 
| ShortTermMemory | 单次会话 | 层缓存、操作日志、会话上下文 |
| LongTermMemory | 跨会话持久化 | 关键词检索、向量语义检索、重要度加权、自动复盘 |

v3.1.4 新增：**对话时自动从 LongTermMemory 检索历史复盘和用户偏好，注入 system prompt**，让每次会话都能「记住」上一次的分析经验。

```bash
geoclaw-claude memory add "武汉市人口重心在汉口" --tag 武汉 --importance 0.8
geoclaw-claude memory vsearch "城市人口分布"
geoclaw-claude memory recent --limit 5
```

---

## 人类移动性分析

基于 trackintel 封装，支持停留点生成、出行段提取、回转半径、活动熵等指标计算，以及 NL 操作（`"分析用户移动性指标"`、`"绘制轨迹热力图"`）。

---

## 多 LLM Provider

| Provider | 关键词 | 特点 |
|---------|--------|------|
| OpenAI GPT | `openai` | 默认，支持 gpt-5.1-chat-latest / gpt-4.1 等最新模型 |
| Anthropic Claude | `anthropic` | 自然语言理解最强 |
| Google Gemini | `gemini` | 高速，中文支持优秀 |
| Qwen（通义千问） | `qwen` | 中文优化 |
| Ollama（本地） | `ollama` | 完全离线，隐私保护 |

---

## 安装与依赖

```bash
bash install.sh                   # 标准安装
bash install.sh --dev             # 开发模式
pip install openai                # OpenAI（默认，推荐）
pip install anthropic             # Claude
pip install google-genai          # Gemini
pip install sentence-transformers # 可选：向量语义检索增强
```

| 包 | 用途 | 类型 |
|----|------|------|
| `geopandas` · `shapely` | 核心矢量处理 | 必须 |
| `pyproj` · `rasterio` | 投影与栅格分析 | 必须 |
| `networkx` · `osmnx` | 路网与等时圈分析 | 必须 |
| `trackintel ≥ 1.4.2` | 人类移动性分析 | 必须 |
| `scipy` · `matplotlib` · `folium` | 统计 / 制图 | 必须 |
| `click` | CLI 框架 | 必须 |

---

## 更新

GeoClaw 支持一键原地更新，无需重新克隆仓库。要求安装时使用 `git clone`（非 zip 下载）。

```bash
# 检查是否有新版本（不下载任何内容）
geoclaw-claude check

# 一键更新：git pull + pip install，保留所有用户数据
geoclaw-claude update

# 强制重装当前版本（用于修复依赖问题）
geoclaw-claude update --force

# 更新后立即运行测试套件验证
geoclaw-claude update --test

# 只拉取代码，不重装包（高级用法）
geoclaw-claude update --no-install
```

| 选项 | 效果 |
|------|------|
| *(无参数)* | 检测远程版本 → `git pull` → `pip install` |
| `--force` | 跳过版本比较，强制执行完整更新流程 |
| `--test` | 更新完成后运行内置测试套件，验证新版本正常 |
| `--no-install` | 只执行 `git pull`，不重装 pip 包 |

更新流程会自动打印 CHANGELOG 差异，并在完成后提示重启 Python 环境以加载新模块。用户数据（`~/.geoclaw_claude/`）**完全不受影响**。

> **注意**：如果通过 zip 下载安装（非 `git clone`），`update` 命令会提示无法自动更新，并给出手动操作指引。此时可改用 `reinstall.sh` 重装。

---

## 卸载与重装

### 卸载

```bash
# 卸载包，保留 ~/.geoclaw_claude/（配置、记忆、缓存）
bash uninstall.sh

# 卸载包 + 彻底删除用户数据（不可恢复）
bash uninstall.sh --purge

# 预览将执行的操作，不实际删除任何内容
bash uninstall.sh --dry-run
```

| 选项 | 效果 |
|------|------|
| *(无参数)* | 卸载 pip 包和 CLI，**保留** `~/.geoclaw_claude/` 用户数据 |
| `--purge` | 同上，并**删除** `~/.geoclaw_claude/`（配置/记忆/缓存全部清除）|
| `--dry-run` | 仅预览操作，不实际删除任何内容 |

> `~/.geoclaw_claude/` 目录包含你的配置文件、长期记忆和会话缓存。默认卸载时**不会**删除，重装后仍可恢复使用。

### 重装

```bash
# 标准重装：卸载旧版本重新安装，保留用户数据
bash reinstall.sh

# 清数据重装：用户数据重置为全新状态
bash reinstall.sh --clean

# 开发模式重装：代码修改即时生效（适合二次开发）
bash reinstall.sh --dev

# 最小重装：跳过 osmnx / rasterio 等大型依赖
bash reinstall.sh --mini

# 组合示例：清数据 + 开发模式
bash reinstall.sh --clean --dev
```

| 选项 | 效果 |
|------|------|
| *(无参数)* | 卸载旧版 → 重装，**保留**用户数据 |
| `--clean` | 卸载旧版 → 清空 `~/.geoclaw_claude/` → 重装（全新开始）|
| `--dev` | 可编辑安装（`pip install -e .`），适合开发调试 |
| `--mini` | 跳过 `osmnx`、`rasterio`、`anthropic` 等大型依赖 |

---

## 项目结构

```
GeoClaw_Claude/
├── geoclaw_claude/
│   ├── cli.py                  # CLI 入口（ask/chat/memory/skill/profile）
│   ├── skill_manager.py        # Skill 注册/执行/导出/安全
│   ├── skill_auditor.py        # SkillAuditor：25+ 规则静态安全审计
│   ├── nl/                     # 自然语言系统
│   │   ├── processor.py        # NLProcessor：意图解析（AI 优先，无 Key 时引导）
│   │   ├── executor.py         # NLExecutor：GIS 执行
│   │   ├── agent.py            # GeoAgent：多轮对话 + 活人感记忆注入
│   │   ├── profile_manager.py  # ProfileManager：soul.md / user.md
│   │   └── llm_provider.py     # LLMProvider：多 Provider + gpt-5.x 兼容
│   ├── analysis/
│   │   ├── spatial_ops.py
│   │   ├── network.py
│   │   ├── raster_ops.py
│   │   └── mobility/           # trackintel 封装
│   ├── memory/                 # 短期 + 长期 + 向量检索 + 存档
│   ├── reasoning/              # SRE 空间推理引擎
│   └── skills/builtin/         # 15 个内置 Skill
├── data/                       # 武汉 GIS 数据 + GPS 轨迹数据
├── examples/                   # 案例脚本（武汉/景德镇商场选址）
├── tests/                      # 577 项测试，全部通过
└── docs/                       # 技术文档（docx + pdf）
```

---

## 测试矩阵

| 测试文件 | 项目数 | 覆盖范围 |
|---------|--------|---------| 
| `test_sre_phase3.py` | 72 | SRE Phase 3：uncertainty / analysis_mode / sensitivity / MAUP |
| `test_sre_phase2.py` | 76 | SRE Phase 2：template_library / primitive_resolver / llm_reasoner |
| `test_sre_phase1.py` | 59 | SRE Phase 1：schemas / task_typer / rule_engine / validator |
| `test_agentskills_compat.py` | 21 | AgentSkills 兼容导出（字段/导出/批量/CLI）|
| `test_v311_fixes.py` | 34 | key 脱敏 / render 函数 / output_dir / chat action |
| `test_v310_new.py` | 30 | Ollama provider / ProfileUpdater / v3.1.0 集成 |
| `test_skills_and_security.py` | 40 | Skill 系统 + SkillAuditor 安全审计 |
| `test_v230_features.py` | 33 | 上下文压缩 / 多 Provider / SecurityGuard |
| `test_v230_new.py` | 31 | Gemini · MemoryArchive · VectorSearch |
| `test_memory.py` | 37 | ShortTermMemory / LongTermMemory / 向量检索 |
| `test_profile.py` | 28 | soul.md / user.md / ProfileManager |
| `test_nl.py` | 20 | NLProcessor / NLExecutor / GeoAgent |
| `test_mobility.py` | 20 | GPS 层级生成 / 移动性指标 / 可视化 |
| `test_updater.py` | 20 | VersionInfo / check / update / self_check |
| **合计** | **577** | **全部 ✅** |

---

## 版本历史

| 版本 | 时间 | 亮点 |
|------|------|------|
| **v3.1.4** 🆕 | 2026-03 | 活人感记忆对话系统；AI 优先引导；gpt-5.x/o-series 兼容；577 测试 ✅ |
| **v3.1.3** | 2026-03 | OpenClaw / AgentSkills 兼容导出；`agentskills_compat` 字段；`skill export` CLI |
| **v3.1.2** | 2026-03 | 15 个内置 Skill 全就绪；对话驱动 user.md 更新；500 测试 ✅ |
| **v3.1.1** | 2026-03 | render 函数修复；chat action；无 GUI 兼容 |
| **v3.1.0** | 2026-03 | Ollama 离线大模型；ProfileUpdater；Provider 自动切换 |
| **v3.0.0** | 2026-03 | SRE Phase 3：五维不确定性、AnalysisMode、敏感性、MAUP；466 测试 ✅ |
| v2.5.0-alpha | 2026-02 | SRE Phase 1+2：rule_engine / template_library / llm_reasoner |
| v2.4.1 | 2026-02 | soul.md / user.md 个性化（ProfileManager） |
| v2.4.0 | 2026-02 | 商场选址 Skill 双模式；SkillAuditor 安全审计 |
| v2.3.0 | 2025-12 | Google Gemini；MemoryArchive；VectorSearch；onboard 向导 |
| v2.0.0 | 2025-10 | 自然语言 GIS 平台；多 Provider；安全机制 |
| v1.0.0 | 2025-06 | 首个正式版本：CLI、Skill 系统、路网/栅格分析 |

完整变更记录详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 文档

| 文档 | 说明 |
|------|------|
| [Technical Reference v3.1.4](docs/GeoClaw-claude_Technical_Reference_v3.1.4.pdf) | 完整技术架构参考 |
| [User Guide v3.1.4](docs/GeoClaw-claude_User_Guide_v3.1.4.pdf) | 用户使用手册 |
| [Beginner Guide v3.1.4](docs/GeoClaw-claude_Beginner_Guide_v3.1.4.pdf) | 新手入门 |
| [Skill Writing Guide](docs/SKILL_WRITING_GUIDE.pdf) | Skill 编写规范（含 agentskills_compat 说明）|

---

## 算法来源声明：trackintel

`geoclaw_claude/analysis/mobility/` 中的核心算法来自 [trackintel](https://github.com/mie-lab/trackintel)（ETH Zurich，trackintel >= 1.4.2）。

> Martin, H., et al. (2023). Trackintel: An open-source Python library for human mobility analysis. *Computers, Environment and Urban Systems*, 101, 101938.

---

## 关于

**GeoClaw-claude** 由 [UrbanComp Lab](https://urbancomp.net) 开发，服务于城市计算与地理信息科学研究。

MIT License © 2025 UrbanComp Lab
