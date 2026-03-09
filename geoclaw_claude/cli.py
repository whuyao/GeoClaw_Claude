"""
geoclaw_claude/cli.py
=====================
GeoClaw-claude 命令行工具入口。

命令列表:
  geoclaw-claude onboard          — 交互式初始化配置向导
  geoclaw-claude config get <key> — 查看配置项
  geoclaw-claude config set <key> <val> — 修改配置项
  geoclaw-claude config show      — 显示全部配置
  geoclaw-claude skill list       — 列出已安装 skill
  geoclaw-claude skill run <name> [args] — 运行 skill
  geoclaw-claude skill install <path>   — 安装本地 skill
  geoclaw-claude download osm <place>   — 下载 OSM 数据
  geoclaw-claude test             — 运行环境测试

────────────────────────────────────────────────────────
TODO:
  - [ ] geoclaw-claude serve  — 启动本地 Web UI
  - [ ] geoclaw-claude update — 更新 geoclaw-claude 本身
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_click():
    """检查 click 是否安装，给出友好提示。"""
    try:
        import click
        return click
    except ImportError:
        print("❌ 缺少依赖: click\n   请运行: pip install click")
        sys.exit(1)


# ── 彩色输出工具 ──────────────────────────────────────────────────────────────

def _mask_key(key: str, show: int = 4) -> str:
    """显示 key 开头和结尾各 show 个字符，中间用 *** 替换。"""
    if not key:
        return "(未设置)"
    key = key.strip()
    if len(key) <= show * 2:
        return key[:2] + "***"
    return f"{key[:show]}...{key[-show:]}"


def _prompt_key(label: str, existing: str = "") -> str:
    """
    明文输入 API Key（需要看到输入内容便于粘贴长 key）。
    输入前显示已有 key 的脱敏摘要。
    """
    if existing:
        print(f"    当前: {_mask_key(existing)}")
        print(f"    直接回车保留现有 key，输入新 key 则覆盖")
    else:
        print(f"    （请粘贴 API Key，输入过程中可见，回车确认）")
    val = input(f"  {label}\n  > ").strip()
    return val or existing


def _ok(msg):   print(f"  \033[32m✓\033[0m {msg}")
def _warn(msg): print(f"  \033[33m⚠\033[0m {msg}")
def _err(msg):  print(f"  \033[31m✗\033[0m {msg}")
def _info(msg): print(f"  {msg}")


# ── onboard 向导 ──────────────────────────────────────────────────────────────

def _run_onboard():
    """交互式配置向导 — 极简版：只问必要的两件事。"""
    from geoclaw_claude.config import Config, CONFIG_FILE
    click = _ensure_click()

    print("\n" + "─" * 56)
    print("  🌍  GeoClaw-claude  初始化向导  v3.1.1")
    print("─" * 56)

    cfg = Config.load()

    # ── 【1/2】选 Provider ──────────────────────────────────────────────
    print()
    print("【1/2】选择 AI 模型来源")
    print()
    print("  1  Anthropic Claude   (推荐，效果最佳，需 API Key)")
    print("  2  通义千问 Qwen       (中文强，需 DashScope API Key)")
    print("  3  Google Gemini      (免费额度可用，需 API Key)")
    print("  4  OpenAI GPT         (全球通用，需 API Key)")
    print("  5  Ollama 本地模型     (完全免费离线，需本地安装 Ollama)")
    print("  0  先跳过（之后可随时运行 geoclaw-claude onboard 再配置）")
    print()

    choice = click.prompt("  请输入序号", default="0").strip()

    if choice == "1":
        key = _prompt_key("Anthropic API Key（sk-ant-...）", cfg.anthropic_api_key or "")
        if key:
            cfg.anthropic_api_key = key
            cfg.llm_provider = "anthropic"

    elif choice == "2":
        key = _prompt_key("Qwen API Key（DashScope，sk-...）", cfg.qwen_api_key or "")
        if key:
            cfg.qwen_api_key = key
            cfg.llm_provider = "qwen"

    elif choice == "3":
        key = _prompt_key("Gemini API Key（AIza...）", cfg.gemini_api_key or "")
        if key:
            cfg.gemini_api_key = key
            cfg.llm_provider = "gemini"

    elif choice == "4":
        key = _prompt_key("OpenAI API Key（sk-...）", cfg.openai_api_key or "")
        if key:
            cfg.openai_api_key = key
            cfg.llm_provider = "openai"

    elif choice == "5":
        print()
        print("  Ollama 无需 API Key，请确保已安装并运行 Ollama。")
        print("  安装：https://ollama.com/download")
        print("  推荐模型：ollama pull qwen3:8b  （6 GB 内存）")
        print()
        url = click.prompt(
            "  Ollama 服务地址",
            default=cfg.ollama_base_url or "http://localhost:11434/v1",
        ).strip()
        cfg.ollama_base_url = url
        model = click.prompt(
            "  模型名称",
            default=cfg.ollama_model or "qwen3:8b",
        ).strip()
        cfg.ollama_model = model
        cfg.llm_provider = "ollama"

    # ── 【2/2】输出目录 ─────────────────────────────────────────────────
    print()
    print("【2/2】分析结果保存目录")
    out = click.prompt(
        "  输出目录",
        default=cfg.output_dir or "~/geoclaw_output",
    ).strip()
    if out:
        cfg.output_dir = out

    # ── 保存 ─────────────────────────────────────────────────────────────
    print()
    if click.confirm("  保存配置？", default=True):
        cfg.save()
        cfg.ensure_dirs()
        _ok(f"配置已保存: {CONFIG_FILE}")

        if choice not in ("0", "") and click.confirm("  立即验证 LLM 连接？", default=True):
            _verify_llm(cfg)

    print()
    print("  ✅  完成！运行 geoclaw-claude ask '你好' 开始使用。")
    print("  📖  详细配置：geoclaw-claude config  |  帮助：geoclaw-claude -h")
    print()

def _verify_llm(cfg) -> None:
    """验证 LLM API 连接。"""
    print()
    try:
        from geoclaw_claude.nl.llm_provider import LLMProvider
        llm = LLMProvider.from_config(
            provider=cfg.llm_provider or None,
            verbose=True,
        )
        if llm is None:
            _warn("  未找到有效的 API Key，NL 系统将使用规则模式（离线）。")
            return
        print(f"  正在测试 {llm.provider_name}/{llm.model_name}...")
        resp = llm.chat(
            messages=[{"role": "user", "content": "reply with: ok"}],
            system="Reply with exactly: ok",
            max_tokens=10,
        )
        if resp and resp.content.strip().lower() in ("ok", "ok."):
            _ok(f"  LLM 连接成功！Provider: {llm.provider_name} / {llm.model_name}")
        elif resp:
            _ok(f"  LLM 已响应（{llm.provider_name}/{llm.model_name}）: {resp.content[:50]}")
        else:
            _warn("  LLM 未返回有效响应，请检查 API Key 和模型名称。")
    except Exception as e:
        _warn(f"  LLM 连接测试失败: {e}")


# ── CLI 命令定义 ──────────────────────────────────────────────────────────────

def main():
    """CLI 主入口，解析命令并分发。"""
    click = _ensure_click()

    @click.group(
        help="🌍 GeoClaw-claude — Python GIS 工具集命令行界面",
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    @click.version_option(
        package_name="geoclaw-claude",
        prog_name="geoclaw-claude",
    )
    def cli():
        pass

    # ── onboard ───────────────────────────────────────────────────────────────
    @cli.command()
    def onboard():
        """🚀 两步完成初始化：选 AI 模型 + 设置输出目录。"""
        _run_onboard()

    # ── config ────────────────────────────────────────────────────────────────
    @cli.group()
    def config():
        """⚙️  查看和修改配置项。"""
        pass

    @config.command("show")
    def config_show():
        """显示所有配置（敏感信息脱敏）。"""
        from geoclaw_claude.config import Config
        cfg = Config.load()
        print(cfg.summary())

    @config.command("get")
    @click.argument("key")
    def config_get(key):
        """查看单个配置项的值。"""
        from geoclaw_claude.config import Config
        from dataclasses import asdict
        cfg = Config.load()
        d = asdict(cfg)
        if key not in d:
            _err(f"未知配置项: {key}")
            _info(f"可用项: {', '.join(d.keys())}")
            sys.exit(1)
        print(f"{key} = {d[key]}")

    @config.command("set")
    @click.argument("key")
    @click.argument("value")
    def config_set(key, value):
        """修改单个配置项并保存。\n\n示例: geoclaw-claude config set anthropic_api_key sk-ant-xxx"""
        from geoclaw_claude.config import Config
        cfg = Config.load()
        try:
            cfg.set(key, value)
            cfg.save()
            _ok(f"{key} = {value}")
        except KeyError as e:
            _err(str(e))
            sys.exit(1)

    # ── skill ─────────────────────────────────────────────────────────────────
    @cli.group()
    def skill():
        """🧩 Skill 管理：列出、安装、运行用户自定义分析脚本。"""
        pass

    @skill.command("list")
    def skill_list():
        """列出所有已安装的 skill。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        skills = sm.list_skills()
        if not skills:
            _warn("暂无已安装的 skill。")
            _info("使用 `geoclaw-claude skill install <路径>` 安装 skill。")
            return
        print(f"\n  已安装 {len(skills)} 个 skill:\n")
        for s in skills:
            builtin_tag = " \033[36m[内置]\033[0m" if s.get("builtin") else ""
            print(f"  • \033[1m{s['name']}\033[0m{builtin_tag}")
            print(f"    {s.get('description', '(无描述)')}")
            print(f"    版本: {s.get('version', '?')}  作者: {s.get('author', '?')}")
            print()

    @skill.command("run")
    @click.argument("name")
    @click.argument("args", nargs=-1)
    @click.option("--data", "-d", default="", help="输入数据文件路径")
    @click.option("--output", "-o", default="", help="输出路径")
    @click.option("--ai/--no-ai", default=False, help="是否启用 AI 分析")
    def skill_run(name, args, data, output, ai):
        """运行指定 skill。\n\n示例: geoclaw-claude skill run hospital_coverage --data hospitals.geojson"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        try:
            result = sm.run(name, data=data, output=output, use_ai=ai, extra_args=list(args))
            _ok(f"Skill '{name}' 执行完成")
            if result:
                _info(str(result))
        except Exception as e:
            _err(f"执行失败: {e}")
            sys.exit(1)

    @skill.command("install")
    @click.argument("path")
    @click.option("--no-audit", is_flag=True, default=False,
                  help="跳过安全审计（不推荐，仅用于可信的内置 skill）")
    def skill_install(path, no_audit):
        """安装本地 skill 文件（默认启用安全审计）。

        \b
        示例:
          geoclaw-claude skill install ./my_skill.py
          geoclaw-claude skill install ./my_skill.py --no-audit
        """
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        try:
            name = sm.install(path, skip_audit=no_audit)
            _ok(f"Skill '{name}' 安装成功")
        except PermissionError as e:
            _warn(f"安装已取消: {e}")
            sys.exit(2)
        except ValueError as e:
            _err(f"Skill 不合规: {e}")
            sys.exit(1)
        except Exception as e:
            _err(f"安装失败: {e}")
            sys.exit(1)

    @skill.command("audit")
    @click.argument("path")
    @click.option("--verbose/--no-verbose", "-v", default=True,
                  help="显示代码片段和修复建议")
    def skill_audit(path, verbose):
        """对 Skill 文件执行安全审计（不安装）。

        \b
        示例:
          geoclaw-claude skill audit ./suspicious_skill.py
          geoclaw-claude skill audit ./my_skill.py --no-verbose
        """
        from geoclaw_claude.skill_manager import SkillManager
        from geoclaw_claude.skill_auditor import SkillAuditor, RiskLevel
        sm      = SkillManager()
        auditor = SkillAuditor()
        try:
            result = auditor.audit(path)
            print(auditor.format_report(result, verbose=verbose))
            # 退出码反映最高风险等级（便于 CI/CD 集成）
            lvl = result.max_level
            if lvl == RiskLevel.CRITICAL:
                sys.exit(4)
            elif lvl == RiskLevel.HIGH:
                sys.exit(3)
            elif lvl == RiskLevel.MEDIUM:
                sys.exit(2)
        except Exception as e:
            _err(f"审计失败: {e}")
            sys.exit(1)

    @skill.command("new")
    @click.argument("name")
    def skill_new(name):
        """创建新 skill 模板。\n\n示例: geoclaw-claude skill new my_analysis"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        path = sm.create_template(name)
        _ok(f"Skill 模板已创建: {path}")
        _info("编辑该文件，实现 run() 函数，然后用 skill install 安装。")

    # ── download ──────────────────────────────────────────────────────────────
    @cli.group()
    def download():
        """📥 数据下载：从 OSM、远程 URL 等下载地理数据。"""
        pass

    @download.command("osm")
    @click.argument("place")
    @click.option("--type", "-t", "poi_type", default="hospital",
                  help="POI类型: hospital/park/metro/university/road 等")
    @click.option("--output", "-o", default="", help="输出文件路径 (.geojson)")
    @click.option("--max", "-n", "max_results", default=500, type=int, help="最大结果数")
    def download_osm(place, poi_type, output, max_results):
        """从 OpenStreetMap 下载 POI 数据。

        \b
        示例:
          geoclaw-claude download osm "武汉市" --type hospital
          geoclaw-claude download osm "Beijing, China" --type park -n 200
        """
        import geopandas as gpd
        from geoclaw_claude.io.osm import download_pois, download_boundary
        from geoclaw_claude.config import Config

        cfg = Config.load()
        print(f"\n  下载: {place} / {poi_type}")

        # 先获取边界bbox
        boundary = download_boundary(place)
        if boundary is None:
            _err(f"无法解析地名: {place}")
            sys.exit(1)

        bbox = boundary.bounds
        layer = download_pois(bbox, poi_type=poi_type, max_results=max_results)
        if layer is None:
            _err("未找到数据")
            sys.exit(1)

        out = output or f"{place}_{poi_type}.geojson".replace(" ", "_").replace(",", "")
        layer.data.to_file(out, driver="GeoJSON")
        _ok(f"已保存 {len(layer)} 个要素 → {out}")

    @download.command("url")
    @click.argument("url")
    @click.option("--output", "-o", default="", help="输出文件路径")
    def download_url(url, output):
        """从 URL 下载地理数据文件。\n\n示例: geoclaw-claude download url https://example.com/data.geojson"""
        from geoclaw_claude.io.remote import download_file
        try:
            path = download_file(url, output or None)
            _ok(f"已下载 → {path}")
        except Exception as e:
            _err(f"下载失败: {e}")
            sys.exit(1)

    # ── test ──────────────────────────────────────────────────────────────────
    @cli.command()
    def test():
        """🧪 运行环境测试，验证依赖是否正常安装。"""
        print("\n  运行环境测试...\n")
        test_file = Path(__file__).parent.parent / "tests" / "test_environment.py"
        if test_file.exists():
            import subprocess
            subprocess.run([sys.executable, str(test_file)])
        else:
            _warn("测试文件不存在，跳过。")

    # ── memory ─────────────────────────────────────────────────────────────────
    @cli.group()
    def memory():
        """🧠 记忆系统管理（短期/长期记忆）。"""
        pass

    @memory.command("status")
    def memory_status():
        """查看记忆系统状态。"""
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        mem.print_status()

    @memory.command("list")
    @click.option("--category", "-c", default=None,
                  help="类别过滤 (knowledge/session/dataset/preference/error)")
    @click.option("--top", "-n", default=10, help="显示条数")
    def memory_list(category, top):
        """列出长期记忆条目。"""
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        entries = mem.ltm.get_recent(n=top, category=category)
        if not entries:
            _warn("长期记忆为空")
            return
        print(f"\n  最近 {len(entries)} 条长期记忆:\n")
        for e in entries:
            import time
            date = time.strftime("%m-%d %H:%M", time.localtime(e.updated_at))
            print(f"  [{e.id}] [{e.category:10s}] {date}  ⭐{e.importance:.1f}  {e.title}")
            if e.tags:
                print(f"           标签: {', '.join(e.tags)}")
        print()

    @memory.command("search")
    @click.argument("query")
    @click.option("--top", "-n", default=5, help="显示条数")
    def memory_search(query, top):
        """搜索长期记忆。\n\n示例: geoclaw-claude memory search "武汉 医院"
        """
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        results = mem.recall(query, top_k=top)
        if not results:
            _warn(f"未找到与 '{query}' 相关的记忆")
            return
        print(f"\n  搜索 '{query}' 共找到 {len(results)} 条:\n")
        for e in results:
            print(f"  [{e.id}] {e.title}  (重要性: {e.importance:.2f})")
            if isinstance(e.content, dict):
                for k, v in list(e.content.items())[:3]:
                    print(f"           {k}: {v}")
        print()

    @memory.command("learn")
    @click.argument("title")
    @click.argument("content")
    @click.option("--category", "-c", default="knowledge")
    @click.option("--tags",     "-t", default="", help="逗号分隔标签")
    @click.option("--importance", "-i", default=0.7, type=float)
    def memory_learn(title, content, category, tags, importance):
        """手动向长期记忆存入知识。

        \b
        示例:
          geoclaw-claude memory learn "武汉人口密度" "主城区约1万/km²" -t wuhan,population
        """
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        eid = mem.learn(title=title, content=content,
                        category=category, tags=tag_list, importance=importance)
        _ok(f"已存入长期记忆: [{eid}] {title}")

    @memory.command("forget")
    @click.argument("entry_id")
    def memory_forget(entry_id):
        """从长期记忆删除一条记忆。"""
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        if mem.forget(entry_id):
            _ok(f"已删除: {entry_id}")
        else:
            _warn(f"未找到: {entry_id}")

    @memory.command("compact")
    @click.option("--keep", default=200, help="保留条数上限")
    def memory_compact(keep):
        """压缩长期记忆，清理低重要性旧条目。"""
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        removed = mem.ltm.compact(keep_top_n=keep)
        _ok(f"已压缩，删除 {removed} 条低重要性旧记忆")

    @memory.command("export")
    @click.option("--output", "-o", default="memory_export.json")
    def memory_export(output):
        """将长期记忆导出为 JSON 文件。"""
        from geoclaw_claude.memory import get_memory
        mem = get_memory()
        json_str = mem.ltm.export_json()
        Path(output).write_text(json_str, encoding="utf-8")
        _ok(f"已导出 {len(mem.ltm)} 条记忆 → {output}")

    # ── memory archive 子命令组 ───────────────────────────────────────────────
    @memory.group("archive")
    def memory_archive():
        """📦 会话存档管理（保存/列出/搜索/导出历史会话快照）。"""
        pass

    @memory_archive.command("list")
    @click.option("--limit", "-n", default=15, help="显示条数")
    @click.option("--tag", default=None, help="按标签过滤")
    def archive_list(limit, tag):
        """列出所有存档。\n\n示例: geoclaw-claude memory archive list -n 20"""
        from geoclaw_claude.memory import get_archive
        arc = get_archive()
        entries = arc.list_archives(limit=limit, tag=tag)
        if not entries:
            _warn("暂无存档记录。")
            return
        print(f"\n  共 {len(arc)} 条存档（显示最近 {len(entries)} 条）\n")
        for e in entries:
            tags_str = f"  [{', '.join(e.tags)}]" if e.tags else ""
            print(f"  {e.date_str}  {e.archive_id[:8]}  {e.title}{tags_str}")
            if e.summary:
                print(f"            ↳ {e.summary[:80]}")
        print()

    @memory_archive.command("search")
    @click.argument("query")
    @click.option("--top", "-n", default=8, help="最多返回条数")
    def archive_search(query, top):
        """搜索存档。\n\n示例: geoclaw-claude memory archive search \"武汉医院\""""
        from geoclaw_claude.memory import get_archive
        arc = get_archive()
        results = arc.search(query, limit=top)
        if not results:
            _warn(f"未找到与 '{query}' 相关的存档。")
            return
        print(f"\n  搜索 '{query}' 找到 {len(results)} 条：\n")
        for e in results:
            print(f"  {e.date_str}  {e.archive_id[:8]}  {e.title}")
            if e.summary:
                print(f"            ↳ {e.summary[:80]}")
        print()

    @memory_archive.command("save")
    @click.option("--title", "-t", required=True, help="存档标题")
    @click.option("--summary", "-s", default="", help="摘要说明")
    @click.option("--tags", default="", help="逗号分隔标签")
    def archive_save(title, summary, tags):
        """手动保存当前会话为存档。\n\n示例: geoclaw-claude memory archive save -t \"武汉分析\" -s \"完成医院覆盖率分析\""""
        from geoclaw_claude.memory import get_archive, get_memory
        arc = get_archive()
        mem = get_memory()
        # 从短期记忆获取操作日志
        ops = [{"action": r.op, "detail": r.detail}
               for r in mem.stm.get_log()] if hasattr(mem, "stm") else []
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        entry = arc.save_session(
            title=title,
            ops_log=ops,
            summary=summary,
            tags=tag_list,
        )
        _ok(f"已存档：{entry.title} (ID: {entry.archive_id[:8]}) → {entry.date_str}")

    @memory_archive.command("export")
    @click.option("--output", "-o", default="archive_export.json")
    def archive_export(output):
        """导出所有存档到 JSON 文件。"""
        from geoclaw_claude.memory import get_archive
        arc = get_archive()
        arc.export(output)
        st = arc.stats()
        _ok(f"已导出 {st['total']} 条存档（{st['size_human']}）→ {output}")

    @memory_archive.command("import")
    @click.argument("filepath")
    @click.option("--overwrite", is_flag=True, default=False, help="ID 冲突时覆盖")
    def archive_import(filepath, overwrite):
        """从 JSON 文件导入存档。"""
        from geoclaw_claude.memory import get_archive
        arc = get_archive()
        n = arc.import_json(filepath, overwrite=overwrite)
        _ok(f"已导入 {n} 条存档。")

    @memory_archive.command("stats")
    def archive_stats():
        """显示存档统计信息。"""
        from geoclaw_claude.memory import get_archive
        arc = get_archive()
        st = arc.stats()
        print(f"\n  📦 存档统计")
        print(f"     总条数: {st['total']}")
        print(f"     总大小: {st['size_human']}")
        print(f"     来源分布: {st['sources']}\n")

    # ── memory vsearch 子命令 ─────────────────────────────────────────────────
    @memory.command("vsearch")
    @click.argument("query")
    @click.option("--top", "-n", default=8, help="最多返回条数")
    @click.option("--source", default=None, help="按来源过滤（memory/archive）")
    @click.option("--rebuild", is_flag=True, default=False, help="重建向量索引后再搜索")
    def memory_vsearch(query, top, source, rebuild):
        """🔍 向量语义搜索记忆（比关键词搜索更智能）。

        \b
        示例:
          geoclaw-claude memory vsearch "武汉医院空间分析"
          geoclaw-claude memory vsearch "人类移动性" --top 5
          geoclaw-claude memory vsearch "buffer" --source memory
          geoclaw-claude memory vsearch "all" --rebuild
        """
        from geoclaw_claude.memory import get_vector_search, get_memory

        vs = get_vector_search()

        if rebuild or len(vs) == 0:
            # 从长期记忆重建索引
            mem = get_memory()
            all_entries = mem.ltm.get_recent(n=500)
            added = 0
            for entry in all_entries:
                text = str(entry.content)[:400]
                vs.add(
                    doc_id=entry.id,
                    text=text,
                    title=entry.title,
                    tags=entry.tags,
                    source="memory",
                    importance=entry.importance,
                )
                added += 1
            # 从存档索引加入
            from geoclaw_claude.memory import get_archive
            arc = get_archive()
            for e in arc.list_archives(limit=200):
                vs.add(
                    doc_id=f"arc_{e.archive_id}",
                    text=e.summary,
                    title=e.title,
                    tags=e.tags,
                    source="archive",
                    importance=0.5,
                )
                added += 1
            vs.save()
            _ok(f"向量索引已重建（{added} 条文档，后端: {vs.backend}）")

        results = vs.search(query, top_k=top, source_filter=source)
        if not results:
            _warn(f"未找到与 '{query}' 相关的记忆。")
            print("  提示：运行 --rebuild 可重建向量索引。")
            return

        print(f"\n  🔍 向量搜索 '{query}' 找到 {len(results)} 条（后端: {vs.backend}）：\n")
        for i, r in enumerate(results, 1):
            src = r.meta.get("source", "")
            title = r.meta.get("title", r.doc_id)
            tags = r.meta.get("tags", [])
            tag_str = f"  [{', '.join(tags[:3])}]" if tags else ""
            print(f"  {i}. [{r.score:.3f}] ({src}) {title}{tag_str}")
            if r.snippet:
                print(f"       {r.snippet[:100]}")
        print()

    

    # ── tools ──────────────────────────────────────────────────────────────────
    @cli.group()
    def tools():
        """🔧 本地工具管理与执行。"""

    @tools.command("list")
    def tools_list():
        """列出所有可用本地工具。"""
        from geoclaw_claude.tools import LocalToolKit, ToolPermission
        kit = LocalToolKit()
        print("\n可用本地工具：\n")
        for spec in kit.specs:
            props = spec.parameters.get("properties", {})
            req   = spec.parameters.get("required", [])
            params = ", ".join(
                f"{k}{'*' if k in req else ''}" for k in props
            )
            print(f"  {spec.name:<20} {spec.description}")
            if params:
                print(f"  {'':20} 参数: {params}")
        print()

    @tools.command("permission")
    @click.argument("mode", type=click.Choice(["full", "sandbox", "whitelist"]))
    def tools_permission(mode):
        """设置工具执行权限（full/sandbox/whitelist）。

        \b
        full      : 完全授权，仅受硬性系统保护限制
        sandbox   : 拦截危险命令（默认）
        whitelist : 只允许预配置的命令/路径
        """
        from geoclaw_claude.config import Config
        cfg = Config.load()
        cfg.tool_permission = mode
        cfg.save()
        _ok(f"工具权限已设置为: {mode}")
        if mode == "full":
            _warn("完全授权模式：LLM 可执行任意命令（仍受硬性系统保护）。请确认这是你的意图。")

    @tools.command("run")
    @click.argument("tool_name")
    @click.argument("params", nargs=-1)
    def tools_run(tool_name, params):
        """直接执行指定工具。

        \b
        示例:
          geoclaw-claude tools run shell "ls ~/geoclaw_output"
          geoclaw-claude tools run file_list path=~/data
          geoclaw-claude tools run sys_info
          geoclaw-claude tools run http_get url=https://example.com
        """
        from geoclaw_claude.tools import LocalToolKit, ToolPermission
        from geoclaw_claude.config import Config

        cfg = Config.load()
        perm_map = {"full": ToolPermission.FULL,
                    "sandbox": ToolPermission.SANDBOX,
                    "whitelist": ToolPermission.WHITELIST}
        perm = perm_map.get(cfg.tool_permission, ToolPermission.SANDBOX)
        kit = LocalToolKit(permission=perm)

        kwargs = {}
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                kwargs[k] = v
            else:
                auto_key = {"shell": "cmd", "exec": "args",
                            "file_read": "path", "file_write": "path",
                            "file_find": "pattern", "file_list": "path",
                            "http_get": "url", "http_post": "url", "curl": "url",
                            "sys_processes": "filter_name"}.get(tool_name)
                if auto_key:
                    kwargs[auto_key] = p

        print(f"\n执行工具: {tool_name}  权限: {cfg.tool_permission}\n")
        result = kit.run(tool_name, **kwargs)

        if result.success:
            _ok(f"成功 ({result.duration:.2f}s)")
            print(result.output)
        else:
            _err(f"失败: {result.error}")
        print()

    @tools.command("react")
    @click.argument("task")
    @click.option("--max-steps", "-n", default=12, help="最大推理步数（默认 12）")
    @click.option("--verbose/--quiet", "-v/-q", default=True, help="显示每步进度")
    def tools_react(task, max_steps, verbose):
        """启动 ReAct 智能体执行复杂任务。

        \b
        示例:
          geoclaw-claude tools react "查找 ~/data 下最大的 geojson 文件"
          geoclaw-claude tools react "统计 output 目录下各文件类型的数量"
        """
        from geoclaw_claude.tools import LocalToolKit, ToolPermission, ReActAgent
        from geoclaw_claude.nl.llm_provider import LLMProvider
        from geoclaw_claude.config import Config
        from geoclaw_claude.tools.react_agent import ReActAgent as _RA

        cfg  = Config.load()
        perm = {"full": ToolPermission.FULL,
                "sandbox": ToolPermission.SANDBOX}.get(cfg.tool_permission, ToolPermission.SANDBOX)
        kit  = LocalToolKit(permission=perm)
        llm  = LLMProvider.from_config()

        if llm is None:
            _err("未配置 LLM Provider。请运行 geoclaw-claude onboard 配置 API Key。")
            return

        agent = _RA(toolkit=kit, llm=llm, max_steps=max_steps, verbose=verbose)

        print(f"\n任务: {task}")
        print(f"权限: {cfg.tool_permission}  最大步数: {max_steps}\n")
        print("─" * 60)

        result = agent.run(task)

        print("─" * 60)
        print(f"\n步骤: {len(result.steps)}  耗时: {result.total_duration:.2f}s")
        if result.max_steps_reached:
            _warn("已达最大步数限制")
        _ok("最终结论:") if result.success else _err("任务未完成:")
        print(result.final_answer)
        print()


# ── profile ─────────────────────────────────────────────────────────────────
    @cli.group()
    def profile():
        """👤 管理 soul.md / user.md 个性化配置层。

        \b
        soul.md：系统自我定义与行为边界（~/.geoclaw_claude/soul.md）
        user.md：用户画像与长期偏好（~/.geoclaw_claude/user.md）
        """

    @profile.command("status")
    def profile_status():
        """📋 查看当前 soul/user 配置摘要。"""
        from geoclaw_claude.nl.profile_manager import ProfileManager
        pm = ProfileManager().load()
        s = pm.summary()
        click.echo("\n  ── Profile 配置摘要 " + "─" * 36)
        click.echo(f"  soul.md  路径  : {s['soul_path']}")
        click.echo(f"  soul.md  加载  : {'✅' if s['soul_loaded'] else '❌'}")
        click.echo(f"  soul 身份摘要  : {s['soul_identity']}")
        click.echo(f"  soul 原则数量  : {s['soul_principles']} 条")
        click.echo(f"  user.md  路径  : {s['user_path']}")
        click.echo(f"  user.md  加载  : {'✅' if s['user_loaded'] else '❌'}")
        click.echo(f"  用户角色       : {s['user_role']}")
        click.echo(f"  语言偏好       : {s['user_lang']}")
        click.echo(f"  通讯风格       : {s['user_style']}")
        if s['user_tools']:
            click.echo(f"  偏好工具       : {', '.join(s['user_tools'])}")
        click.echo("  " + "─" * 52)

    @profile.command("show")
    @click.argument("target", type=click.Choice(["soul", "user", "all"]),
                    default="all")
    def profile_show(target):
        """📄 显示 soul.md 或 user.md 内容。

        \b
        示例:
          geoclaw-claude profile show soul
          geoclaw-claude profile show user
          geoclaw-claude profile show all
        """
        from geoclaw_claude.nl.profile_manager import (
            ProfileManager, DEFAULT_SOUL_PATH, DEFAULT_USER_PATH
        )
        pm = ProfileManager().load()
        if target in ("soul", "all"):
            click.echo(f"\n{'═'*60}")
            click.echo(f"  📄 soul.md  ({DEFAULT_SOUL_PATH})")
            click.echo(f"{'═'*60}")
            click.echo(pm._soul_raw)
        if target in ("user", "all"):
            click.echo(f"\n{'═'*60}")
            click.echo(f"  📄 user.md  ({DEFAULT_USER_PATH})")
            click.echo(f"{'═'*60}")
            click.echo(pm._user_raw)

    @profile.command("edit")
    @click.argument("target", type=click.Choice(["soul", "user"]))
    def profile_edit(target):
        """✏️  用系统默认编辑器打开 soul.md 或 user.md。

        \b
        示例:
          geoclaw-claude profile edit soul
          geoclaw-claude profile edit user
        """
        from geoclaw_claude.nl.profile_manager import (
            DEFAULT_SOUL_PATH, DEFAULT_USER_PATH, DEFAULT_SOUL_MD, DEFAULT_USER_MD
        )
        import subprocess, os
        path = DEFAULT_SOUL_PATH if target == "soul" else DEFAULT_USER_PATH
        default_content = DEFAULT_SOUL_MD if target == "soul" else DEFAULT_USER_MD
        # 确保文件存在
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_content, encoding="utf-8")
            click.echo(f"  ✅ 已创建默认 {target}.md: {path}")
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
        click.echo(f"  📝 打开编辑器: {editor} {path}")
        subprocess.call([editor, str(path)])

    @profile.command("reset")
    @click.argument("target", type=click.Choice(["soul", "user", "all"]))
    @click.confirmation_option(prompt="⚠️  确认重置为默认内容？已有修改将丢失")
    def profile_reset(target):
        """🔄 重置 soul.md / user.md 为内置默认内容。

        \b
        示例:
          geoclaw-claude profile reset soul
          geoclaw-claude profile reset user
          geoclaw-claude profile reset all
        """
        from geoclaw_claude.nl.profile_manager import (
            DEFAULT_SOUL_PATH, DEFAULT_USER_PATH,
            DEFAULT_SOUL_MD, DEFAULT_USER_MD
        )
        if target in ("soul", "all"):
            DEFAULT_SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_SOUL_PATH.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
            click.echo(f"  ✅ soul.md 已重置: {DEFAULT_SOUL_PATH}")
        if target in ("user", "all"):
            DEFAULT_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_USER_PATH.write_text(DEFAULT_USER_MD, encoding="utf-8")
            click.echo(f"  ✅ user.md 已重置: {DEFAULT_USER_PATH}")

    @profile.command("prompt")
    def profile_prompt():
        """🔍 预览当前 soul+user 配置生成的 LLM system prompt 片段。"""
        from geoclaw_claude.nl.profile_manager import ProfileManager
        pm = ProfileManager().load()
        click.echo("\n  ── Soul System Prompt " + "─" * 36)
        click.echo(pm.build_system_prompt())
        click.echo("\n  ── User Context Hint " + "─" * 37)
        click.echo(pm.build_context_hint())
        click.echo("\n  ── 欢迎语预览 " + "─" * 44)
        click.echo(pm.build_welcome_message(mode="AI"))
        click.echo()

    # ── check ──────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--json", "as_json", is_flag=True, default=False,
                  help="以 JSON 格式输出结果")
    def check(as_json):
        """🔍 检测是否有可用的新版本。

        \b
        示例:
          geoclaw-claude check
          geoclaw-claude check --json
        """
        from geoclaw_claude.updater import check as do_check
        result = do_check(verbose=not as_json)
        if as_json:
            import json
            click.echo(json.dumps({
                "local_version":  result.local_version,
                "remote_version": result.remote_version,
                "has_update":     result.has_update,
                "status":         result.status,
                "summary":        result.summary(),
                "latest_commit":  result.latest_commit,
                "latest_message": result.latest_message,
            }, ensure_ascii=False, indent=2))
        else:
            if result.has_update:
                _warn(result.summary())
            elif result.error:
                _err(result.summary())
            else:
                _ok(result.summary())

    # ── update ──────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--force", "-f", is_flag=True, default=False,
                  help="强制更新，即使已是最新版本")
    @click.option("--test", "run_tests", is_flag=True, default=False,
                  help="更新后运行测试套件验证")
    @click.option("--no-install", is_flag=True, default=False,
                  help="只 git pull，不执行 pip install（高级用法）")
    def update(force, run_tests, no_install):
        """⬆  拉取 GitHub 最新代码并自动安装。

        \b
        流程:
          1. 检测远程最新版本
          2. git pull origin main
          3. pip install -e .
          4. （可选）运行测试套件

        \b
        示例:
          geoclaw-claude update
          geoclaw-claude update --force
          geoclaw-claude update --test
        """
        from geoclaw_claude.updater import update as do_update
        print("\n  开始更新...\n")
        result = do_update(verbose=True, run_tests=run_tests, force=force)
        print()
        if result.success:
            if result.previous_version == result.current_version:
                _ok(result.summary())
            else:
                _ok(f"更新完成: v{result.previous_version} → v{result.current_version}")
                print(f"\n  建议重启 Python 环境以加载新版本。")
        else:
            _err(result.summary())
            sys.exit(1)

    # ── self-check ──────────────────────────────────────────────────────────────
    @cli.command("self-check")
    @click.option("--json", "as_json", is_flag=True, default=False,
                  help="以 JSON 格式输出报告")
    @click.option("--quick", is_flag=True, default=False,
                  help="快速模式：跳过远程版本检测")
    def self_check_cmd(as_json, quick):
        """🩺 全面自我检测：版本、模块完整性、依赖、更新状态。

        \b
        示例:
          geoclaw-claude self-check
          geoclaw-claude self-check --json
          geoclaw-claude self-check --quick
        """
        from geoclaw_claude.updater import self_check, print_self_check

        if quick:
            # 快速模式：只检测本地状态
            print("\n  快速检测（跳过远程版本检测）...")
            from geoclaw_claude import __version__, __author__
            import importlib
            modules = [
                "geoclaw_claude.core.layer",
                "geoclaw_claude.core.project",
                "geoclaw_claude.analysis.spatial_ops",
                "geoclaw_claude.memory",
                "geoclaw_claude.cli",
            ]
            ok = fail = 0
            for m in modules:
                try:
                    importlib.import_module(m)
                    ok += 1
                except Exception:
                    fail += 1
            _ok(f"v{__version__} — {ok} 模块正常{', ' + str(fail) + ' 失败' if fail else ''}")
            return

        report = self_check()

        if as_json:
            import json
            click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_self_check(report)

            # 给出建议
            if report["update"]["has_update"]:
                _warn("发现新版本，运行 `geoclaw-claude update` 升级")
            failed_mods = [k for k, v in report["modules"].items()
                           if k != "_summary" and v != "ok"]
            missing_deps = [k for k, v in report["dependencies"].items()
                            if k != "_summary" and v == "NOT INSTALLED"]
            if failed_mods or missing_deps:
                _warn(f"发现问题，建议重新安装: pip install -e .")
            elif not report["update"]["has_update"] and not failed_mods:
                _ok("系统运行正常，无需操作")

    # ── ask (单条自然语言指令) ─────────────────────────────────────────────────
    @cli.command()
    @click.argument("instruction", nargs=-1)
    @click.option("--ai",   "mode", flag_value="ai",   help="强制 AI 模式（需配置 API Key）")
    @click.option("--rule", "mode", flag_value="rule",  help="强制规则模式（离线）")
    @click.option("--dry-run", is_flag=True, default=False, help="只解析意图，不执行（输出 JSON）")
    @click.option("--output-dir", "-O", default="", envvar="GEOCLAW_OUTPUT_DIR",
                  help="本次输出目录（覆盖配置文件 output_dir，环境变量 GEOCLAW_OUTPUT_DIR 亦可）")
    def ask(instruction, mode, dry_run, output_dir):
        """🗣  自然语言单条 GIS 指令（解析 + 执行）。

        \b
        示例:
          geoclaw-claude ask 对医院做1公里缓冲区
          geoclaw-claude ask "下载武汉市医院数据"
          geoclaw-claude ask "加载 hospitals.geojson 然后做500米缓冲区"
          geoclaw-claude ask --dry-run "对医院做核密度分析"
          geoclaw-claude ask --rule "裁剪医院到边界范围内"
          geoclaw-claude ask --output-dir ./results "对医院做缓冲区"
        """
        if not instruction:
            _err("请提供自然语言指令，例如: geoclaw-claude ask 对医院做1公里缓冲区")
            sys.exit(1)

        text   = " ".join(instruction)
        use_ai = True if mode == "ai" else (False if mode == "rule" else None)
        out_dir = output_dir.strip() or None

        from geoclaw_claude.nl import NLProcessor, GeoAgent

        if dry_run:
            import json as _json
            proc   = NLProcessor(use_ai=False)   # dry-run 不消耗 API
            intent = proc.parse(text)
            click.echo(_json.dumps(intent.to_dict(), ensure_ascii=False, indent=2))
            return

        if out_dir:
            from pathlib import Path as _Path
            _Path(out_dir).mkdir(parents=True, exist_ok=True)
            _ok(f"输出目录: {out_dir}")

        agent = GeoAgent(use_ai=use_ai, verbose=False, output_dir=out_dir)
        reply = agent.chat(text)
        print(f"\n  {reply}\n")
        agent.end()

    # ── chat (交互式多轮对话) ──────────────────────────────────────────────────
    @cli.command()
    @click.option("--ai",   "mode", flag_value="ai",   help="强制 AI 模式")
    @click.option("--rule", "mode", flag_value="rule",  help="强制规则模式（离线）")
    @click.option("--output-dir", "-O", default="", envvar="GEOCLAW_OUTPUT_DIR",
                  help="本次会话输出目录（覆盖配置文件 output_dir，环境变量 GEOCLAW_OUTPUT_DIR 亦可）")
    def chat(mode, output_dir):
        """💬 进入交互式自然语言 GIS 对话模式（多轮）。

        \b
        在提示符下直接输入自然语言，输入 exit/退出 结束会话。
        特殊命令: history(历史) / layers(图层) / status(状态)

        \b
        示例:
          geoclaw-claude chat
          geoclaw-claude chat --ai
          geoclaw-claude chat --rule
          geoclaw-claude chat --output-dir ./project_results
        """
        from geoclaw_claude.nl import GeoAgent

        use_ai  = True if mode == "ai" else (False if mode == "rule" else None)
        out_dir = output_dir.strip() or None

        if out_dir:
            from pathlib import Path as _Path
            _Path(out_dir).mkdir(parents=True, exist_ok=True)
            _ok(f"输出目录: {out_dir}")

        agent  = GeoAgent(use_ai=use_ai, verbose=False, output_dir=out_dir)

        # 提示当前 AI 模式状态
        if not agent._proc._use_ai:
            _warn("当前为规则模式（未配置 AI）。自然语言理解有限，建议运行 geoclaw-claude onboard 配置 LLM。")
        else:
            provider = agent._proc._llm.provider_name if agent._proc._llm else "未知"
            _ok(f"AI 模式已启用（{provider}）")

        welcome = agent._history[-1].text if agent._history else ""
        print(f"\n{welcome}\n")
        print("  特殊命令: history(历史) / layers(图层) / status(状态) / exit(退出)\n")

        while True:
            try:
                user_input = input("  你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  [已退出]")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "退出", "q"}:
                agent.end(title="交互式NL对话会话")
                _ok("会话已结束，操作记录已保存到记忆")
                break
            if user_input.lower() in {"history", "历史"}:
                agent.print_history()
                continue
            if user_input.lower() in {"status", "状态"}:
                import json as _json
                print(_json.dumps(agent.status(), ensure_ascii=False, indent=2))
                continue
            if user_input.lower() in {"layers", "图层"}:
                layers = agent._exec.list_layers()
                print(f"  当前图层: {layers or '(空)'}")
                continue

            reply = agent.chat(user_input)
            print(f"\n  🤖 {reply}\n")

    cli()


if __name__ == "__main__":
    main()
