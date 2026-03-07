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

    print("\n" + "═" * 58)
    print("  🌍  GeoClaw-claude  初始化向导")
    print("═" * 58)
    print("  按 Enter 保留当前值，输入新值后按 Enter 修改。\n")

    cfg = Config.load()

    # ── AI API Key ────────────────────────────────────────────
    print("【1/5】AI 接口配置")
    key = click.prompt(
        "  Anthropic API Key",
        default=cfg.anthropic_api_key or "",
        hide_input=True,
        show_default=False,
        prompt_suffix="\n  > ",
    ).strip()
    if key:
        cfg.anthropic_api_key = key

    model = click.prompt(
        "  默认模型",
        default=cfg.anthropic_model,
    ).strip()
    if model:
        cfg.anthropic_model = model

    # ── 目录配置 ──────────────────────────────────────────────
    print("\n【2/5】数据目录配置")
    for attr, label in [
        ("data_dir",   "本地数据目录"),
        ("cache_dir",  "网络缓存目录"),
        ("output_dir", "分析输出目录"),
        ("skill_dir",  "用户 Skill 目录"),
    ]:
        val = click.prompt(f"  {label}", default=getattr(cfg, attr)).strip()
        if val:
            setattr(cfg, attr, val)

    # ── 网络配置 ──────────────────────────────────────────────
    print("\n【3/5】网络配置")
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

    # ── 制图配置 ──────────────────────────────────────────────
    print("\n【4/5】制图配置")
    crs = click.prompt("  默认坐标系 (EPSG代码)", default=cfg.default_crs).strip()
    if crs:
        cfg.default_crs = crs

    dpi = click.prompt("  默认输出 DPI", default=cfg.default_dpi, type=int)
    cfg.default_dpi = dpi

    # ── 日志配置 ──────────────────────────────────────────────
    print("\n【5/5】日志配置")
    level = click.prompt(
        "  日志级别",
        default=cfg.log_level,
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    ).upper()
    cfg.log_level = level

    # ── 保存 ──────────────────────────────────────────────────
    print()
    if click.confirm("  保存以上配置?", default=True):
        cfg.save()
        cfg.ensure_dirs()
        _ok(f"配置已保存到: {CONFIG_FILE}")
        print()
        print(cfg.summary())
    else:
        _warn("已取消，配置未保存。")

    print("\n  运行 `geoclaw-claude test` 验证环境是否正常。\n")


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

    cli()


if __name__ == "__main__":
    main()
