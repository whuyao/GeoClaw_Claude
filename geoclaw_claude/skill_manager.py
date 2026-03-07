"""
geoclaw_claude/skill_manager.py
================================
Skill 系统核心 — 管理用户自定义地理分析脚本。

Skill 是一个 Python 文件，需符合以下规范:

    # my_skill.py
    SKILL_META = {
        "name":        "hospital_coverage",
        "version":     "1.0.0",
        "author":      "张三",
        "description": "分析医院服务覆盖范围",
        "inputs": [
            {"name": "hospitals", "type": "GeoLayer", "desc": "医院点图层"},
            {"name": "radius_km", "type": "float",    "desc": "覆盖半径(km)", "default": 3.0},
        ],
        "outputs": [
            {"name": "coverage", "type": "GeoLayer", "desc": "覆盖区域图层"},
        ],
    }

    def run(ctx):
        hospitals = ctx.get_layer("hospitals")
        radius    = ctx.param("radius_km")
        # ... 分析逻辑 ...
        return ctx.result(coverage=coverage_layer)

────────────────────────────────────────────────────────
TODO:
  - [ ] Skill 依赖声明与自动安装 (requirements in SKILL_META)
  - [ ] Skill 沙箱执行 (限制危险操作)
  - [ ] Skill 版本管理与升级
  - [ ] Skill Hub 在线市场 (geoclaw-claude skill search)
────────────────────────────────────────────────────────
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from geoclaw_claude.config import Config


# ── Skill 执行上下文 ──────────────────────────────────────────────────────────

class SkillContext:
    """
    Skill 执行时的上下文对象，注入到 run(ctx) 中。
    提供图层访问、参数读取、AI调用、结果输出等接口。
    """

    def __init__(
        self,
        data_path: str = "",
        output_path: str = "",
        use_ai: bool = False,
        extra_args: Optional[List[str]] = None,
    ):
        self._cfg        = Config.load()
        self._data_path  = data_path
        self._output_path = output_path or self._cfg.output_dir
        self._use_ai     = use_ai
        self._extra_args = extra_args or []
        self._layers: Dict[str, Any] = {}
        self._results: Dict[str, Any] = {}
        self._params: Dict[str, Any] = {}

        # 自动加载 data_path 图层
        if data_path and Path(data_path).exists():
            self._load_default_layer(data_path)

    def _load_default_layer(self, path: str) -> None:
        from geoclaw_claude.io.vector import load_vector
        try:
            layer = load_vector(path)
            self._layers["input"] = layer
            self._layers[Path(path).stem] = layer
        except Exception as e:
            print(f"  ⚠ 自动加载数据失败: {e}")

    # ── 图层访问 ──────────────────────────────────────────────────────────────

    def get_layer(self, name: str = "input") -> Any:
        """获取已加载的图层。"""
        if name not in self._layers:
            raise KeyError(f"图层 '{name}' 不存在。可用: {list(self._layers.keys())}")
        return self._layers[name]

    def load_layer(self, path: str, name: Optional[str] = None) -> Any:
        """从文件加载图层并注册。"""
        from geoclaw_claude.io.vector import load_vector
        layer = load_vector(path, name=name)
        reg_name = name or Path(path).stem
        self._layers[reg_name] = layer
        return layer

    def set_param(self, key: str, value: Any) -> None:
        """设置参数（供 skill 内部使用）。"""
        self._params[key] = value

    def param(self, key: str, default: Any = None) -> Any:
        """读取参数，支持从命令行 extra_args 解析。"""
        if key in self._params:
            return self._params[key]
        # 尝试从 extra_args 解析 --key=value 或 --key value
        for i, arg in enumerate(self._extra_args):
            if arg == f"--{key}" and i + 1 < len(self._extra_args):
                return self._extra_args[i + 1]
            if arg.startswith(f"--{key}="):
                return arg.split("=", 1)[1]
        return default

    # ── AI 分析接口 ───────────────────────────────────────────────────────────

    def ask_ai(self, prompt: str, context_data: Optional[str] = None) -> str:
        """
        调用 Claude API 进行数据分析。

        Args:
            prompt      : 分析指令
            context_data: 附加的数据描述（如图层摘要）

        Returns:
            AI 返回的文本结果

        TODO:
            - [ ] 支持流式输出
            - [ ] 支持图像（截图地图后分析）
            - [ ] 缓存相同 prompt 的结果
        """
        if not self._use_ai:
            return "(AI 分析未启用，使用 --ai 参数开启)"

        api_key = self._cfg.anthropic_api_key
        if not api_key:
            raise ValueError(
                "未配置 Anthropic API Key。\n"
                "请运行: geoclaw-claude config set anthropic_api_key sk-ant-xxx"
            )

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "缺少 anthropic 库。\n"
                "请运行: pip install anthropic"
            )

        full_prompt = prompt
        if context_data:
            full_prompt = f"{prompt}\n\n数据背景:\n{context_data}"

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=self._cfg.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": full_prompt}],
        )
        return msg.content[0].text

    # ── 结果输出 ──────────────────────────────────────────────────────────────

    def result(self, **kwargs) -> Dict[str, Any]:
        """注册分析结果并自动保存图层到输出目录。"""
        self._results.update(kwargs)

        Path(self._output_path).mkdir(parents=True, exist_ok=True)

        for name, val in kwargs.items():
            # 自动保存 GeoLayer
            if hasattr(val, "data") and hasattr(val, "name"):
                from geoclaw_claude.io.vector import save_vector
                out_path = str(Path(self._output_path) / f"{name}.geojson")
                try:
                    save_vector(val, out_path)
                    print(f"  ✓ 结果已保存: {out_path}")
                except Exception as e:
                    print(f"  ⚠ 保存失败 {name}: {e}")

        return self._results

    @property
    def output_dir(self) -> str:
        return self._output_path

    @property
    def config(self) -> Config:
        return self._cfg


# ── Skill 管理器 ──────────────────────────────────────────────────────────────

class SkillManager:
    """管理 skill 的安装、发现和执行。"""

    def __init__(self):
        self._cfg = Config.load()
        self._skill_dir   = Path(self._cfg.skill_dir)
        self._builtin_dir = Path(__file__).parent / "skills" / "builtin"
        self._registry: Dict[str, Dict] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._scan_skills()
            self._loaded = True

    def _scan_skills(self):
        """扫描内置和用户 skill 目录。"""
        # 内置 skill
        if self._builtin_dir.exists():
            for f in sorted(self._builtin_dir.glob("*.py")):
                if f.stem.startswith("_"):
                    continue
                self._register_file(f, builtin=True)

        # 用户 skill
        if self._skill_dir.exists():
            for f in sorted(self._skill_dir.glob("*.py")):
                if f.stem.startswith("_"):
                    continue
                self._register_file(f, builtin=False)

    def _register_file(self, path: Path, builtin: bool = False) -> Optional[str]:
        """加载并注册单个 skill 文件。"""
        try:
            spec = importlib.util.spec_from_file_location(f"_skill_{path.stem}", path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            meta = getattr(mod, "SKILL_META", {})
            name = meta.get("name", path.stem)

            self._registry[name] = {
                "name":        name,
                "version":     meta.get("version", "0.0.1"),
                "author":      meta.get("author", "unknown"),
                "description": meta.get("description", ""),
                "inputs":      meta.get("inputs", []),
                "outputs":     meta.get("outputs", []),
                "path":        str(path),
                "builtin":     builtin,
                "module":      mod,
            }
            return name
        except Exception as e:
            print(f"  ⚠ 加载 skill 失败: {path.name} — {e}")
            return None

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def list_skills(self) -> List[Dict]:
        """返回所有已注册 skill 的元数据列表。"""
        self._ensure_loaded()
        return [
            {k: v for k, v in s.items() if k != "module"}
            for s in self._registry.values()
        ]

    def get(self, name: str) -> Optional[Dict]:
        """按名称获取 skill 信息。"""
        self._ensure_loaded()
        return self._registry.get(name)

    def run(
        self,
        name: str,
        data:       str = "",
        output:     str = "",
        use_ai:     bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> Any:
        """
        执行指定 skill。

        Args:
            name      : skill 名称
            data      : 输入数据文件路径
            output    : 输出目录路径
            use_ai    : 是否启用 AI 分析
            extra_args: 额外参数列表 (如 ["--radius_km=5"])

        Returns:
            skill run() 的返回值
        """
        self._ensure_loaded()

        if name not in self._registry:
            available = list(self._registry.keys())
            raise KeyError(f"Skill '{name}' 不存在。可用: {available}")

        entry = self._registry[name]
        mod   = entry["module"]

        if not hasattr(mod, "run"):
            raise AttributeError(f"Skill '{name}' 缺少 run(ctx) 函数")

        ctx = SkillContext(
            data_path=data,
            output_path=output or self._cfg.output_dir,
            use_ai=use_ai,
            extra_args=extra_args,
        )

        print(f"\n  ▶ 执行 skill: {name} v{entry['version']}")
        print(f"    {entry['description']}\n")

        return mod.run(ctx)

    def install(self, path: str) -> str:
        """
        安装本地 skill 文件到 skill_dir。

        Args:
            path: .py 文件路径

        Returns:
            安装后的 skill 名称
        """
        src = Path(path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if src.suffix != ".py":
            raise ValueError("Skill 必须是 .py 文件")

        self._skill_dir.mkdir(parents=True, exist_ok=True)
        dst = self._skill_dir / src.name
        shutil.copy2(src, dst)

        name = self._register_file(dst, builtin=False)
        if name is None:
            raise RuntimeError("Skill 文件加载失败，请检查语法")
        return name

    def create_template(self, name: str) -> str:
        """生成 skill 模板文件。"""
        self._skill_dir.mkdir(parents=True, exist_ok=True)
        out = self._skill_dir / f"{name}.py"

        template = f'''"""
{name} — GeoClaw-claude Skill
"""

SKILL_META = {{
    "name":        "{name}",
    "version":     "1.0.0",
    "author":      "your_name",
    "description": "描述这个 skill 的功能",
    "inputs": [
        {{"name": "input",     "type": "GeoLayer", "desc": "输入图层"}},
        {{"name": "radius_km", "type": "float",    "desc": "分析半径(km)", "default": 5.0}},
    ],
    "outputs": [
        {{"name": "result", "type": "GeoLayer", "desc": "分析结果图层"}},
    ],
}}


def run(ctx):
    """
    Skill 主函数，接收 SkillContext 对象。

    ctx 提供:
        ctx.get_layer("input")      — 获取输入图层
        ctx.param("radius_km", 5.0) — 读取参数
        ctx.ask_ai("分析这些数据...") — 调用 AI 分析
        ctx.result(result=layer)    — 输出结果并保存
    """
    # 读取输入
    layer     = ctx.get_layer("input")
    radius_km = float(ctx.param("radius_km", 5.0))

    print(f"  处理图层: {{layer.name}} ({{len(layer)}} 个要素)")
    print(f"  分析半径: {{radius_km}} km")

    # ── 在此编写分析逻辑 ────────────────────────────────────
    from geoclaw_claude.analysis.spatial_ops import buffer
    result = buffer(layer, radius_km * 1000, unit="meters")

    # （可选）AI 分析
    ai_summary = ctx.ask_ai(
        f"请用中文分析这{{len(layer)}}个点位的分布特征，并给出空间优化建议。",
        context_data=layer.summary(),
    )
    if ai_summary:
        print(f"\\n  AI 分析结果:\\n  {{ai_summary}}")

    # 返回结果
    return ctx.result(result=result)
'''
        out.write_text(template, encoding="utf-8")
        return str(out)
