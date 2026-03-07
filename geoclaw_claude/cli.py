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

def _ok(msg):   print(f"  \033[32m✓\033[0m {msg}")
def _warn(msg): print(f"  \033[33m⚠\033[0m {msg}")
def _err(msg):  print(f"  \033[31m✗\033[0m {msg}")
def _info(msg): print(f"  {msg}")


# ── onboard 向导 ──────────────────────────────────────────────────────────────

def _run_onboard():
    """交互式配置向导，引导用户完成初始化。"""
    from geoclaw_claude.config import Config, CONFIG_FILE

    click = _ensure_click()

    print("\n" + "═" * 60)
    print("  🌍  GeoClaw-claude  初始化向导  v2.3.0")
    print("═" * 60)
    print("  按 Enter 保留当前值，输入新值后按 Enter 修改。\n")

    cfg = Config.load()

    # ── 【1/6】LLM Provider 选择 ──────────────────────────────────────────
    print("【1/6】AI 模型配置")
    print()
    print("  可用 Provider:  anthropic / gemini / openai / qwen")
    print("  （留空 = 自动按优先级选择：anthropic > gemini > openai > qwen）")
    provider = click.prompt(
        "  首选 LLM Provider",
        default=cfg.llm_provider or "",
    ).strip().lower()
    cfg.llm_provider = provider if provider in ("anthropic", "gemini", "openai", "qwen") else ""

    print()
    # ── Anthropic ──
    print("  ── Anthropic Claude ──")
    key = click.prompt(
        "  API Key",
        default=cfg.anthropic_api_key or "",
        hide_input=True,
        show_default=False,
        prompt_suffix="\n  > ",
    ).strip()
    if key:
        cfg.anthropic_api_key = key

    model = click.prompt(
        "  模型（如 claude-sonnet-4-20250514 / claude-opus-4-20250514）",
        default=cfg.anthropic_model,
    ).strip()
    if model:
        cfg.anthropic_model = model

    print()
    # ── Google Gemini ──
    print("  ── Google Gemini ──")
    print("  可用模型: gemini-2.0-flash / gemini-2.0-flash-lite / gemini-1.5-pro / gemini-2.5-pro-preview-03-25")
    gkey = click.prompt(
        "  Gemini API Key（AIza...，留空跳过）",
        default=cfg.gemini_api_key or "",
        hide_input=True,
        show_default=False,
        prompt_suffix="\n  > ",
    ).strip()
    if gkey:
        cfg.gemini_api_key = gkey

    gmodel = click.prompt(
        "  Gemini 模型",
        default=cfg.gemini_model,
    ).strip()
    if gmodel:
        cfg.gemini_model = gmodel

    print()
    # ── OpenAI ──
    print("  ── OpenAI（也可用于任意 OpenAI 兼容 API）──")
    okey = click.prompt(
        "  OpenAI API Key（留空跳过）",
        default=cfg.openai_api_key or "",
        hide_input=True,
        show_default=False,
        prompt_suffix="\n  > ",
    ).strip()
    if okey:
        cfg.openai_api_key = okey

    if cfg.openai_api_key:
        omodel = click.prompt("  OpenAI 模型", default=cfg.openai_model).strip()
        if omodel:
            cfg.openai_model = omodel
        obase = click.prompt(
            "  自定义 base_url（兼容 API 代理，留空=官方）",
            default=cfg.openai_base_url or "",
        ).strip()
        cfg.openai_base_url = obase

    print()
    # ── Qwen ──
    print("  ── 通义千问 Qwen ──")
    qkey = click.prompt(
        "  Qwen API Key（DashScope，留空跳过）",
        default=cfg.qwen_api_key or "",
        hide_input=True,
        show_default=False,
        prompt_suffix="\n  > ",
    ).strip()
    if qkey:
        cfg.qwen_api_key = qkey

    if cfg.qwen_api_key:
        qmodel = click.prompt(
            "  Qwen 模型（qwen-max / qwen-plus / qwen-turbo）",
            default=cfg.qwen_model,
        ).strip()
        if qmodel:
            cfg.qwen_model = qmodel

    # ── 【2/6】上下文压缩 ──────────────────────────────────────────────────
    print("\n【2/6】上下文压缩配置")
    print("  功能：对话历史超过阈值时自动压缩，避免超出 Token 限制。")
    ctx_max = click.prompt(
        "  触发压缩的 Token 阈值",
        default=cfg.ctx_max_tokens,
        type=int,
    )
    cfg.ctx_max_tokens = ctx_max

    ctx_target = click.prompt(
        "  压缩目标 Token 数",
        default=cfg.ctx_target_tokens,
        type=int,
    )
    cfg.ctx_target_tokens = ctx_target

    ctx_keep = click.prompt(
        "  保留最近 N 条消息不压缩",
        default=cfg.ctx_keep_recent,
        type=int,
    )
    cfg.ctx_keep_recent = ctx_keep

    ctx_verbose = click.confirm(
        "  显示压缩详情日志?",
        default=cfg.ctx_compress_verbose,
    )
    cfg.ctx_compress_verbose = ctx_verbose

    # ── 【3/6】数据目录 ───────────────────────────────────────────────────
    print("\n【3/6】数据目录配置")
    for attr, label in [
        ("data_dir",   "本地数据目录"),
        ("cache_dir",  "网络缓存目录"),
        ("output_dir", "分析输出目录"),
        ("skill_dir",  "用户 Skill 目录"),
    ]:
        val = click.prompt(f"  {label}", default=getattr(cfg, attr)).strip()
        if val:
            setattr(cfg, attr, val)

    # ── 【4/6】网络配置 ───────────────────────────────────────────────────
    print("\n【4/6】网络配置")
    proxy = click.prompt("  HTTP 代理 (留空=不使用)", default=cfg.proxy or "").strip()
    cfg.proxy = proxy

    overpass = click.prompt("  Overpass API URL", default=cfg.overpass_url).strip()
    if overpass:
        cfg.overpass_url = overpass

    cache = click.confirm("  启用网络请求缓存?", default=cfg.enable_cache)
    cfg.enable_cache = cache
    if cache:
        ttl = click.prompt("  缓存有效期 (小时)", default=cfg.cache_ttl_hours, type=int)
        cfg.cache_ttl_hours = ttl

    # ── 【5/6】制图配置 ───────────────────────────────────────────────────
    print("\n【5/6】制图配置")
    crs = click.prompt("  默认坐标系 (EPSG代码)", default=cfg.default_crs).strip()
    if crs:
        cfg.default_crs = crs

    dpi = click.prompt("  默认输出 DPI", default=cfg.default_dpi, type=int)
    cfg.default_dpi = dpi

    # ── 【6/6】日志配置 ───────────────────────────────────────────────────
    print("\n【6/6】日志配置")
    level = click.prompt(
        "  日志级别",
        default=cfg.log_level,
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    ).upper()
    cfg.log_level = level

    # ── 保存 ──────────────────────────────────────────────────────────────
    print()
    if click.confirm("  保存以上配置?", default=True):
        cfg.save()
        cfg.ensure_dirs()
        _ok(f"配置已保存到: {CONFIG_FILE}")
        print()
        print(cfg.summary())

        # 验证 LLM 配置
        print()
        if click.confirm("  立即验证 LLM 连接?", default=False):
            _verify_llm(cfg)
    else:
        _warn("已取消，配置未保存。")

    print("\n  运行 `geoclaw-claude test` 验证环境是否正常。\n")


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
        """🚀 交互式初始化向导：配置 API Key、数据目录、网络参数等。"""
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
    def skill_install(path):
        """安装本地 skill 文件或目录。\n\n示例: geoclaw-claude skill install ./my_skill.py"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        try:
            name = sm.install(path)
            _ok(f"Skill '{name}' 安装成功")
        except Exception as e:
            _err(f"安装失败: {e}")
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
    def ask(instruction, mode, dry_run):
        """🗣  自然语言单条 GIS 指令（解析 + 执行）。

        \b
        示例:
          geoclaw-claude ask 对医院做1公里缓冲区
          geoclaw-claude ask "下载武汉市医院数据"
          geoclaw-claude ask "加载 hospitals.geojson 然后做500米缓冲区"
          geoclaw-claude ask --dry-run "对医院做核密度分析"
          geoclaw-claude ask --rule "裁剪医院到边界范围内"
        """
        if not instruction:
            _err("请提供自然语言指令，例如: geoclaw-claude ask 对医院做1公里缓冲区")
            sys.exit(1)

        text   = " ".join(instruction)
        use_ai = True if mode == "ai" else (False if mode == "rule" else None)

        from geoclaw_claude.nl import NLProcessor, GeoAgent

        if dry_run:
            import json as _json
            proc   = NLProcessor(use_ai=False)   # dry-run 不消耗 API
            intent = proc.parse(text)
            click.echo(_json.dumps(intent.to_dict(), ensure_ascii=False, indent=2))
            return

        agent = GeoAgent(use_ai=use_ai, verbose=False)
        reply = agent.chat(text)
        print(f"\n  {reply}\n")
        agent.end()

    # ── chat (交互式多轮对话) ──────────────────────────────────────────────────
    @cli.command()
    @click.option("--ai",   "mode", flag_value="ai",   help="强制 AI 模式")
    @click.option("--rule", "mode", flag_value="rule",  help="强制规则模式（离线）")
    def chat(mode):
        """💬 进入交互式自然语言 GIS 对话模式（多轮）。

        \b
        在提示符下直接输入自然语言，输入 exit/退出 结束会话。
        特殊命令: history(历史) / layers(图层) / status(状态)

        \b
        示例:
          geoclaw-claude chat
          geoclaw-claude chat --ai
          geoclaw-claude chat --rule
        """
        from geoclaw_claude.nl import GeoAgent

        use_ai = True if mode == "ai" else (False if mode == "rule" else None)
        agent  = GeoAgent(use_ai=use_ai, verbose=False)

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
