## v3.1.1 (2026-03-09) — 安全、交互与可靠性修复

### 关键修复
- **[危险] render_map / render_interactive 缺失** → 导入即崩溃，地图操作全部失败（ImportError）
- **[危险] plt.show() 在无 GUI 终端挂死** → 强制 Agg 后端，static map 直接写文件，彻底消除终端冻结
- **[重要] output_dir 在 chat 模式下未初始化** → 文件写入位置未知；现在 NLExecutor 始终从 config/环境变量读取并创建目录
- **[重要] 自然语言理解退化为关键词匹配** → 新增 `chat` action，LLM 直接处理闲聊/问候；`unknown` action 在 AI 模式下也走 LLM 自由回复

### 新功能
- **onboard key 输入明文可见** → 用户可看到自己粘贴的长 key；再次配置时显示脱敏摘要（前4...后4）
- **README 安全声明** → 顶部醒目提示建议在沙盒/虚拟机运行

### 测试
- 新增 `test_v311_fixes.py`（34 用例），覆盖：key 脱敏 K01-K08、render 函数 R01-R05、output_dir O01-O05、chat action C01-C08、soul/user 个性化 S01-S08
- 全量测试：500/500 ✅

## v3.1.0 (2026-03-08) — Ollama 本地大模型支持 + 对话驱动 Profile 更新

### 新增功能

#### Ollama 本地大模型支持（nl/llm_provider.py）
- **PROVIDER_OLLAMA**：新增 `ollama` Provider，无需 API Key，支持全离线部署
- **OLLAMA_DEFAULT_BASE_URL**：默认地址 `http://localhost:11434/v1`，兼容局域网部署（自定义 `ollama_base_url`）
- **OLLAMA_MODELS**：内置常用模型列表（llama3 / qwen2.5 / deepseek-r1 / mistral / gemma3 / phi4 等 12 款）
- **_call_ollama()**：基于 OpenAI 兼容接口调用，不依赖额外 SDK（复用 openai 库）
- **Provider 优先级更新**：anthropic → gemini → openai → qwen → **ollama（本地离线兜底）**
- **ProviderConfig 扩展**：ollama 模式下 `api_key` 自动设为 dummy "ollama"，`is_valid` 只需 `base_url + model`

#### Config 新增字段（config.py）
- `ollama_base_url`：Ollama 服务地址（默认 `http://localhost:11434/v1`）
- `ollama_model`：默认使用模型（默认 `llama3`）
- `llm_provider` 新增可选值：`ollama`

#### 对话驱动 Profile 更新（nl/profile_manager.py）
- **ProfileUpdater**：新增核心类，在对话中根据用户输入动态更新 `soul.md` / `user.md`
  - `maybe_update(user_input)`：自动检测偏好更新意图并执行写入
  - `update_user_field(field, value)`：直接精准更新 user.md 中任意字段
  - `summarize_and_update(turns, llm_provider)`：会话结束时批量提取偏好更新（支持 AI 驱动 + 规则降级）
  - AI 驱动：请 LLM 从对话历史提取 preferred_lang / comm_style / role / tool_prefs / output_format
  - 规则驱动：统计中英文用量自动推断语言偏好，无需 LLM
- **安全锁定机制**：以下 soul.md 字段不允许通过对话修改
  - `Safety Boundaries` / `Execution Hierarchy` / `Core Principles` / `Data Handling Rules`
  - 触碰安全字段时返回 `UpdateResult(blocked=True)`，并提示手动编辑路径
- **UpdateResult**：新增结果数据类（file / fields / message / changed / blocked）
- **GeoAgent 集成**：
  - `__init__`：自动初始化 `_profile_updater`
  - `chat()`：每次对话优先检测 profile 更新意图（安全锁拦截 > 偏好更新 > GIS 操作）
  - `end(auto_update_profile=True)`：会话结束时自动调用 `summarize_and_update()`

### 测试
- **test_v310_new.py**：30 项新特性专项测试（O01-O10 Ollama / P01-P15 ProfileUpdater / I01-I05 集成）
- 累计测试：**374/374 全绿**（344 + 30）

### 版本
- `__version__ = "3.1.0"`
- SRE 引擎版本：sre-0.3-phase3（不变）

---

## v3.0.0-alpha (2026-03-08) — Spatial Reasoning Engine Phase 2

### 新增功能
- **template_library.py**：方法模板库加载与匹配引擎，支持 5 类分析场景（邻近/可达性/选址/变化检测/轨迹）
- **templates/*.yaml**：5 个完整方法模板文件（proximity / accessibility / site_selection / change_detection / trajectory），共包含 24 个分析方法
- **primitive_resolver.py**：地理原语解析器，三层解析（关键词 + 数据集类型推断 + 属性字段推断），支持 10 种实体 + 9 种关系 + 12 种指标
- **llm_reasoner.py（完整 Phase 2 实现）**：LLM Geo Reasoner，包含 Task Interpreter / Geo Method Reasoner / Geo Explanation Generator
  - 结构化 Prompt 构建（含规则层约束 + 模板局限说明注入）
  - 多策略 JSON 响应解析（直接解析 / 代码块提取 / {...} 块提取）
  - LLM 调用失败自动降级 rule-only 模式
- **reason_with_llm() 新入口**：SRE 完整模式（rule + template + primitive + LLM），LLM 失败自动降级
- **reason() 增强**：Phase 2 调用链（primitive_resolver + template_library 参与推理，无 LLM 也有更丰富的方法候选）
- **workflow_synthesizer Phase 2 扩展**：LLM primary_method 注入 candidates 首位，secondary_methods 自动加入 optional_steps
- **validator Phase 2 扩展**：Reasoning Consistency（6.3）+ Uncertainty Caveat（6.4）校验
- **test_sre_phase2.py**：76 项 Phase 2 专项测试

### 版本
- SRE 引擎版本：sre-0.2-phase2
- 测试总数：272/272 (196 + 76)


---

# GeoClaw-claude 版本历史

**UrbanComp Lab** (https://urbancomp.net)

---

## v2.4.1 (2025-03)

### 新增功能

**soul.md / user.md 个性化配置层**（`geoclaw_claude/nl/profile_manager.py`）
- `soul.md`：系统自我定义与行为边界层。定义 GeoClaw 的系统身份、使命、核心原则、空间推理规范、执行层级偏好、数据安全规则和输出标准；全局生效，优先级高于用户偏好
- `user.md`：用户画像与长期偏好层。持久化存储用户角色、语言偏好、通讯风格、技术水平、工具偏好、输出格式期望等；会话初始化时加载，作为软个性化层影响规划、回复和工具选择
- `ProfileManager`：统一管理两个配置文件的加载、解析、热更新，自动创建默认文件
- 两套配置首次使用时自动写入 `~/.geoclaw_claude/` 目录

**GeoAgent 深度集成**（`geoclaw_claude/nl/agent.py`）
- `__init__` 新增 `soul_path` / `user_path` 参数，支持自定义路径
- 欢迎语由 `ProfileManager.build_welcome_message()` 生成，融合用户角色/语言偏好
- `_build_context()` 自动注入 soul system prompt（行为边界）和 user 偏好提示
- `status()` 新增 `soul_loaded` / `user_loaded` / `user_role` / `user_lang` 字段

**NLProcessor 系统提示词融合**（`geoclaw_claude/nl/processor.py`）
- `_parse_with_ai()` 自动将 soul.md 内容合并进 LLM system prompt，user.md 偏好注入 context
- soul system prompt 作为最高优先级前缀注入（行为边界不被用户配置覆盖）

**`geoclaw-claude profile` CLI 命令组**（`geoclaw_claude/cli.py`）
- `profile status`：查看当前 soul/user 配置摘要
- `profile show [soul|user|all]`：显示配置文件原始内容
- `profile edit [soul|user]`：用系统编辑器打开配置文件
- `profile reset [soul|user|all]`：重置为内置默认内容
- `profile prompt`：预览生成的 LLM system prompt 和 context hint

### 测试
- `tests/test_profile.py`：23 项覆盖 soul/user 解析、ProfileManager 加载、系统提示词生成、GeoAgent 集成、CLI 命令

### 文档
- 用户手册 / 技术参考手册 / SKILL_WRITING_GUIDE 均更新至 v2.4.1

---

## v2.4.0 (2025-03)

### 新增功能

**Skill 体系全面升级**
- `retail_site_ai`：商场选址 AI 驱动版 Skill（内置）。以 LLM 为核心分析引擎，Python 计算空间指标后交 LLM 综合评判，输出评分图层与中文分析报告
- `retail_site_algo`：商场选址 MCDA 算法版 Skill（内置）。多准则决策分析（人口密度 / 竞争回避 / 空间分散 / 交通可达），完全离线可复现，支持权重自定义
- `SKILL_WRITING_GUIDE.docx / .pdf`：Skill 编写规范与安全指南（8章，含完整代码模板）

**SkillAuditor 安全审计模块**（`geoclaw_claude/skill_auditor.py`）
- 基于 AST + 正则表达式的静态代码分析，不执行代码
- 5 级风险分类：CRITICAL / HIGH / MEDIUM / LOW / INFO
- 综合风险分值（0~100），彩色进度条可视化
- 内置 25+ 条规则，覆盖：命令执行、代码注入、数据外泄、权限提升、危险文件操作、反序列化、代码混淆、危险模块导入等

**SkillManager 安全集成**
- `install()` 新增 `skip_audit` / `auto_approve` 参数
- CRITICAL/HIGH 风险强制用户输入 "yes" 确认；默认拒绝高危 Skill
- 新增 `audit()` 方法，支持仅审计不安装

**CLI 扩展**
- `skill audit <path>`：独立安全审计命令，退出码反映风险等级（CI/CD 友好）
- `skill install --no-audit`：跳过审计选项（不推荐第三方使用）

### 安全测试
- `tests/malicious_skills/evil_exfil.py`：模拟命令执行+数据外泄（CRITICAL）
- `tests/malicious_skills/evil_inject.py`：模拟代码注入+混淆（CRITICAL）
- `tests/malicious_skills/evil_file_ops.py`：模拟危险文件操作（HIGH/CRITICAL）
- `tests/test_skills_and_security.py`：40 个测试，全部通过（S01~S15, A01~A25）

---

## v2.3.1 — 输出路径配置 & 文档全面更新

### 新增

#### 输出路径动态配置（用户可在运行时指定输出目录）
- **CLI `ask` / `chat` 命令**新增 `--output-dir <路径>` / `-O <路径>` 选项
  - 目录不存在时自动创建
  - 仅当次命令/会话生效，不修改配置文件
  - 支持绝对路径和相对路径
- **环境变量 `GEOCLAW_OUTPUT_DIR`** 支持全 Shell 会话级覆盖
  - `ask` / `chat` 命令均绑定此环境变量
- **`GeoAgent(output_dir=...)`** Python API 参数支持
- **`NLExecutor(output_dir=...)`** 底层执行器参数支持
- 优先级：`--output-dir` > `GEOCLAW_OUTPUT_DIR` > `config.output_dir`
- `NLExecutor` 在 `output_dir` 非空时创建独立 `SecurityGuard` 实例（不影响全局单例）
- 新增 `NLExecutor._get_safe_output_path()` 内部方法（统一路径解析入口）

### 文档

- 重写 `docs/GeoClaw-claude_User_Guide_v2.3.0.pdf`（含输出路径专章、FAQ）
- 重写 `docs/GeoClaw-claude_Technical_Reference_v2.3.0.pdf`（含 SecurityGuard API、架构图）
- 删除 v2.2.1 旧版 docx / pdf 文档
- README 已在 v2.3.0 中完整更新

---

## v2.3.0 (2025-03-07)

### 新增功能

#### 1. 上下文压缩机制 (`geoclaw_claude/nl/context_compress.py`)

当多轮对话历史过长时自动压缩，避免超出 LLM token 限制。

**三级压缩策略（按严重程度递进）:**
- **Level 1 — 摘要旧轮次**: 保留最近 N 条消息原文，将更早的轮次用本地算法摘要为一条 `system` 消息（无需 API 调用）
- **Level 2 — 语义去重**: 删除连续相似消息（相似度 >80%）
- **Level 3 — 强制截断**: 仅保留最近 K 条消息 + 截断提示（最后手段）

**核心配置（`config.py` 新增字段）:**
```
ctx_max_tokens      = 6000   # 触发压缩的 token 阈值
ctx_target_tokens   = 4000   # 压缩目标
ctx_keep_recent     = 6      # 保留最近 N 条不压缩
```

**使用方式:**
```python
from geoclaw_claude.nl.context_compress import compress_if_needed
messages, report = compress_if_needed(messages, system_prompt)
print(report)  # [压缩] Level 1 | 8200 → 3900 tokens | 20 → 8 条消息
```
`GeoAgent` 在每轮 `_build_context()` 时自动触发；`NLProcessor._parse_with_ai()` 在调用 LLM 前也会自动压缩。

---

#### 2. 多 LLM Provider 支持 (`geoclaw_claude/nl/llm_provider.py`)

统一封装 Anthropic Claude / OpenAI / Qwen（通义千问）API，上层代码无需感知具体 Provider。

**支持的 Provider:**
| Provider | 默认模型 | 接口方式 |
|----------|----------|----------|
| `anthropic` | `claude-sonnet-4-20250514` | anthropic SDK |
| `openai` | `gpt-4o-mini` | openai SDK（支持自定义 base_url）|
| `qwen` | `qwen-plus` | OpenAI 兼容（DashScope base_url）|

**自动选择优先级:** anthropic → openai → qwen → 降级规则模式

**config.py 新增字段:**
```
openai_api_key   / openai_model   / openai_base_url
qwen_api_key     / qwen_model
llm_provider     # 强制指定 provider（空=自动）
```

**使用方式:**
```bash
geoclaw-claude config set qwen_api_key sk-xxx
geoclaw-claude config set qwen_model qwen-max
geoclaw-claude config set llm_provider qwen
geoclaw-claude ask "对医院做1公里缓冲区"
```

```python
# 指定 Provider
proc = NLProcessor(api_key="sk-xxx", provider="qwen")
# 或通过 Config 自动选择
proc = NLProcessor()  # 读取配置，按优先级自动选
```

---

#### 3. 安全机制 (`geoclaw_claude/security.py`)

保护输入文件不被意外覆盖/删除，所有输出写入固定目录。

**保护规则:**
1. **输出目录固定** — 所有写操作必须在 `output_dir` 下（严格模式）
2. **输入文件保护** — `data_dir` 及上传目录下的文件禁止被覆盖或删除
3. **系统目录保护** — 禁止写入 `/etc`、`/usr`、`/bin` 等系统路径
4. **路径穿越防护** — 拒绝包含 `..` 的路径（路径遍历攻击防护）
5. **软链接保护** — 禁止通过软链接绕过路径检查

**自动集成:** `NLExecutor._do_save()` 和 `_do_render()` 已集成安全检查，输出路径自动重定向到 `output_dir`。

**config.py 新增字段:**
```
security_enabled        = True   # 是否启用安全保护
security_strict_output  = True   # 严格模式：所有输出必须在 output_dir 下
security_verbose        = False  # 安全审计日志
```

**使用方式:**
```python
from geoclaw_claude.security import get_guard, safe_output_path, SecurityError

guard = get_guard()
try:
    safe = guard.check_write("/data/input/file.geojson")   # 抛出 SecurityError
except SecurityError as e:
    print(e.rule)   # input_file_protection

path = safe_output_path("result.geojson")  # → output_dir/result.geojson
```

---

### 测试矩阵 (v2.3.0)

| 测试文件 | 通过 | 覆盖内容 |
|---------|------|---------|
| test_memory.py | 37/37 ✅ | Memory 系统 |
| test_updater.py | 20/20 ✅ | 版本检测 & 自更新 |
| test_nl.py | 20/20 ✅ | 自然语言操作系统 |
| test_mobility.py | 20/20 ✅ | 移动性分析（trackintel）|
| **test_v230_features.py** | **33/33** ✅ | 上下文压缩 / 多 Provider / 安全机制 |
| **合计** | **130/130** ✅ | |

---

## v2.3.0 (2025-03-07)

### 新功能

#### 1. Google Gemini API 支持
- `nl/llm_provider.py`：新增 `PROVIDER_GEMINI` 适配，调用 `google-genai` SDK
- 支持模型：`gemini-2.0-flash` / `gemini-2.0-flash-lite` / `gemini-1.5-flash` / `gemini-1.5-pro` / `gemini-2.5-pro-preview-03-25`
- Provider 选择优先级：anthropic > **gemini** > openai > qwen
- `config.py`：新增 `gemini_api_key` / `gemini_model` 字段
- `Config.summary()`：新增 Gemini 配置显示行

#### 2. 记忆存档系统（MemoryArchive）
- 新文件：`memory/archive.py`
- 功能：会话快照持久化（JSON）、标题/标签/摘要索引、关键词搜索
- 按年月分目录存储：`~/.geoclaw_claude/archives/YYYY-MM/arc_<id>.json`
- 全量导出/导入（跨机器迁移）
- CLI 新命令：
  - `geoclaw-claude memory archive list`
  - `geoclaw-claude memory archive search <query>`
  - `geoclaw-claude memory archive save -t <title>`
  - `geoclaw-claude memory archive export / import`
  - `geoclaw-claude memory archive stats`

#### 3. 向量语义检索（VectorSearch）
- 新文件：`memory/vector_search.py`
- 零依赖 TF-IDF 近似向量，中英文混合分词
- 稀疏向量余弦相似度检索，重要度加权
- 可选增强：检测到 `sentence-transformers` 自动升级为神经网络嵌入
- 持久化索引：`~/.geoclaw_claude/vector_index/`
- CLI 命令：`geoclaw-claude memory vsearch <query> [--rebuild]`

#### 4. Onboard 向导重构（6 步全模型配置）
- `cli.py`：`_run_onboard()` 重写为 6 步向导（原 5 步）
- 第 1 步：完整多模型配置（Anthropic / Gemini / OpenAI / Qwen + 优先级）
- 第 2 步：上下文压缩参数配置（阈值/目标/保留条数/日志）
- 可选：向导结束后立即验证 LLM API 连接

#### 5. 上下文压缩集成增强
- `agent.py`：上下文压缩已完整集成于 `_build_context()`
- 自动按 `config.ctx_max_tokens/target_tokens/keep_recent` 触发三级压缩
- 压缩日志可通过 `ctx_compress_verbose=True` 开启

### 测试
- 新增测试文件 `tests/test_v230_new.py`（31 项：G01-G10 / A01-A10 / V01-V10 / X01）
- 全量测试矩阵：128/128 ✅

---

## v2.2.1 (2025-03-07)

### README 全面重组 + NL 关键词修复

#### README 重组亮点

- 新增**人类移动性分析**专节（原内容散落在功能表和版本历史中）
  - 数据层级模型图（positionfixes → staypoints → triplegs → trips → locations）
  - **自然语言调用方式**完整说明（CLI 逐步调用 + 一句话流水线）
  - Python API 完整示例（读入 → 层级生成 → 指标 → 家工作地识别 → 可视化）
  - Demo 数据集说明与图表输出列表
  - 可用指标函数速查表
- 自然语言操作章节增强：支持操作分类表新增移动性相关操作示例
- 版本历史改为简洁表格形式，便于快速浏览

#### NL 关键词映射修复

修复以下自然语言指令的误判问题：

| 输入 | 修复前 | 修复后 |
|------|--------|--------|
| `"出行方式构成图"` | `mobility_triplegs` | `mobility_modal` ✓ |
| `"预测出行方式"` | `unknown` | `mobility_transport` ✓ |
| `"出行方式预测"` | `unknown` | `mobility_transport` ✓ |

修复原因：`mobility_triplegs` 关键词列表包含"出行方式"导致优先级抢占，现已拆分为精确词组。

---

## v2.2.0 (2025-03-07)

### 新增：武汉城市移动性 Demo 数据集 + 完整案例演示

#### 测试数据（`data/mobility/`）

新增武汉城市 GPS 轨迹测试数据集，作为移动性分析模块的标准 Demo 数据：

| 文件 | 说明 |
|------|------|
| `wuhan_gps_tracks.csv` | 武汉城市 GPS 轨迹主数据（37,549 个轨迹点） |
| `users_meta.csv` | 5 位用户元数据（职业/居住地/工作地/通勤方式） |
| `generate_data.py` | 数据生成脚本（可重新生成） |
| `README.md` | 数据格式与使用说明 |

**数据规模**

- 用户数：5 位武汉居民（金融/互联网/商贸/学术/医疗各一位）
- 时间：10 天（2024-01-15 ~ 2024-01-25）
- 轨迹点：共 37,549 个（每用户约 7,500 个）
- 地理范围：武汉三镇（汉口/武昌/汉阳），WGS84 坐标系
- 出行方式：地铁/公交/步行/骑行，典型城市居民作息模式

**处理结果参考值**（默认参数）

| 层级 | 数量 |
|------|------|
| 停留点 staypoints | ~1,781 |
| 出行段 triplegs | ~1,240 |
| 出行 trips | ~1,240 |
| 重要地点 locations | ~20 |

#### Demo 案例（`examples/wuhan_mobility_demo.py`）

完整的 7 步移动性分析演示脚本，展示从原始 GPS 到可视化报告的全流程：

```
Step 1  读入 GPS 数据（read_positionfixes）
Step 2  生成停留点（generate_staypoints）
Step 3  生成出行段 + 预测出行方式（generate_triplegs + predict_transport_mode）
Step 4  生成出行与重要地点（generate_trips + generate_locations）
Step 5  计算移动性指标（radius_of_gyration + jump_lengths + mobility_summary）
Step 6  识别家/工作地（identify_home_work，OSNA 方法）
Step 7  可视化（5 张图表）
```

生成可视化图表（输出至 `output/mobility_demo/`）：

| 图表 | 内容 |
|------|------|
| `01_mobility_layers_map.png` | 分层移动性地图（停留点+出行段+重要地点叠加） |
| `02_modal_split.png` | 出行方式构成图（饼图+条形图） |
| `03_activity_heatmap_all.png` | 全体用户活动时间热力图（星期×小时矩阵） |
| `03b_activity_heatmap_u0.png` | 单用户（金融从业者）活动时间热力图 |
| `04_mobility_metrics_dashboard.png` | 移动性指标综合仪表盘 |
| `05_user1_trajectory.png` | 单用户（光谷互联网工程师）个人轨迹地图 |

运行方式：

```bash
python examples/wuhan_mobility_demo.py
```

#### 算法来源声明（trackintel）

移动性分析模块中的核心轨迹数据处理算法来自 **trackintel** 开源框架：

> **trackintel**: https://github.com/mie-lab/trackintel
>
> 开发团队：ETH Zurich · Mobility Information Engineering Lab
>
> 引用论文：
> Martin, H., Hong, Y., Wiedemann, N., Bucher, D., & Raubal, M. (2023).
> Trackintel: An open-source Python library for human mobility analysis.
> *Computers, Environment and Urban Systems*, 101, 101938.
> DOI: 10.1016/j.compenvurbsys.2023.101938

GeoClaw-claude 在 trackintel 基础上提供：
- 与 GeoClaw-claude 生态一致的 API 封装（`geoclaw_claude.analysis.mobility`）
- 与 GeoLayer/GeoClawProject 的无缝集成
- 自然语言操作接口（通过 NL 模块）
- UrbanComp Lab 风格的可视化主题

#### 其他修复

- `read_positionfixes()` 修复：时间戳格式解析兼容 `format="mixed"`（支持 ISO8601 含微秒格式）
- `radius_of_gyration()` 修复：trackintel 实际输出列名为 `radius_gyration`（而非 `radius_of_gyration`）
- `mobility_summary()` 修复：自动识别 trackintel 版本间的列名差异

---

## v2.1.0 (2025-03-07)

### 新增：复杂网络与人类移动性分析（trackintel 集成）

新增 `geoclaw_claude/analysis/mobility/` 模块，整合 [trackintel](https://github.com/mie-lab/trackintel) 框架，
提供完整的人类移动性数据分析能力。

#### 数据层级模型

```
positionfixes（GPS 原始轨迹点）
    ↓ generate_staypoints()    停留检测（滑动窗口，空间+时间双阈值）
staypoints（停留点）
    ↓ generate_triplegs()      出行段提取（停留点间的连续移动）
triplegs（出行段）
    ↓ generate_trips()         出行聚合（活动停留点间的完整出行）
trips（出行）
    ↓ generate_locations()     地点聚类（DBSCAN，识别家/工作地等）
locations（重要地点）
```

#### 核心功能（`mobility/core.py`）

| 函数 | 功能 |
|------|------|
| `read_positionfixes()` | 读入 GPS 数据（CSV/GeoDataFrame/DataFrame，自动规范化） |
| `generate_staypoints()` | 停留点检测（dist_threshold / time_threshold） |
| `generate_triplegs()` | 出行段提取 |
| `generate_trips()` | 完整出行生成 |
| `generate_locations()` | 重要地点聚类（DBSCAN） |
| `generate_full_hierarchy()` | **一键生成完整层级**（positionfixes → locations） |
| `predict_transport_mode()` | 出行方式识别（步行/骑行/驾车/火车） |
| `label_activity_staypoints()` | 停留点活动语义标注 |

#### 移动性指标（`mobility/metrics.py`）

| 函数 | 指标说明 |
|------|---------|
| `radius_of_gyration()` | 回转半径（活动范围大小，按次数或时长加权） |
| `jump_lengths()` | 跳跃距离分布（单次出行距离统计） |
| `modal_split()` | 出行方式构成（次数/时长/距离口径） |
| `tracking_quality()` | 轨迹时间覆盖率（数据完整性评估） |
| `mobility_summary()` | 综合摘要（用户数、各层数量、核心指标汇总） |
| `identify_home_work()` | 家/工作地识别（OSNA 作息模式法 / 频率法） |

#### 可视化（`mobility/visualization.py`）

- `plot_mobility_layers()` — 分层地图（GPS点/停留点/出行段/重要地点叠加，支持按交通方式着色）
- `plot_modal_split()` — 出行方式构成图（饼图 + 条形图）
- `plot_activity_heatmap()` — 活动时间热力图（星期 × 小时矩阵）
- `plot_mobility_metrics()` — 移动性指标仪表盘（回转半径/跳跃距离/覆盖率/出行方式）

#### 自然语言操作（NL 模块扩展）

新增 10 类移动性关键词识别：

```bash
geoclaw-claude ask "读入 gps_tracks.csv"
geoclaw-claude ask "生成停留点（距离阈值100米，时间阈值5分钟）"
geoclaw-claude ask "一键完成移动性分析"
geoclaw-claude ask "预测出行方式"
geoclaw-claude ask "识别家和工作地"
geoclaw-claude ask "计算移动性指标摘要"
geoclaw-claude ask "生成轨迹地图"
geoclaw-claude ask "时间热力图"
geoclaw-claude ask "读入gps数据然后生成停留点"   # 多步流水线
```

#### Python API 示例

```python
from geoclaw_claude.analysis.mobility import (
    read_positionfixes, generate_full_hierarchy,
    mobility_summary, plot_mobility_layers, plot_activity_heatmap
)

# 读入 GPS 数据
pfs = read_positionfixes("gps_tracks.csv")

# 一键生成完整层级
h = generate_full_hierarchy(pfs, dist_threshold=100, time_threshold=5)
# → positionfixes / staypoints / triplegs / trips / locations

# 指标摘要
summary = mobility_summary(h)
# → {n_users, n_staypoints, radius_of_gyration_m, jump_length_m, modal_split, ...}

# 可视化
plot_mobility_layers(h, save_path="mobility_map.png")
plot_activity_heatmap(h["staypoints"], save_path="activity_heatmap.png")
```

#### 测试
- 移动性模块测试 **20/20 全部通过**（M01-M20）
- 覆盖：数据读入、层级生成、指标计算、可视化、NL 解析

---

## v2.0.0 (2025-03-07)

### 重大版本升级 — 自然语言 GIS 操作系统全面成熟

v2.0.0 标志着 GeoClaw-claude 从传统 Python GIS 工具集正式迈入**自然语言驱动的智能 GIS 平台**。
核心自然语言操作系统经过完整测试验证，文档与代码完全同步，所有版本标记统一至 v2.0.0。

#### 核心系统完整性

| 模块 | 状态 | 测试 |
|------|------|------|
| `nl/processor.py` NLProcessor 双模式解析 | ✅ 稳定 | 20/20 |
| `nl/executor.py`  NLExecutor GIS 执行引擎 | ✅ 稳定 | 20/20 |
| `nl/agent.py`     GeoAgent 多轮对话代理 | ✅ 稳定 | 20/20 |
| `memory/`         三层记忆系统 | ✅ 稳定 | 37/37 |
| `updater.py`      自我检测与自动更新 | ✅ 稳定 | 20/20 |
| CLI               全命令组（ask/chat/memory/check/update） | ✅ 稳定 | — |

#### 变更内容

- **版本统一**：将所有文档、README、CHANGELOG、`__init__.py` 版本号统一标记为 v2.0.0
- **文档完善**：README 版本历史完整展开，CHANGELOG 各版本条目精确对应代码功能
- **无破坏性变更**：所有 v1.x API 完全兼容，可无缝升级

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
