"""
tests/test_agentskills_compat.py
=================================
测试 OpenClaw / AgentSkills 兼容导出功能。

覆盖范围：
  A01-A05  agentskills_compat 字段声明完整性
  E01-E08  export_openclaw() 单个 Skill 导出
  B01-B04  export_openclaw_all() 批量导出
  C01-C02  CLI skill export 命令（smoke test）
"""
import importlib.util
import json
import pathlib
import re
import tempfile

import pytest

# ── 工具 ─────────────────────────────────────────────────────────────────────

BUILTIN_DIR = pathlib.Path(__file__).parent.parent / "geoclaw_claude" / "skills" / "builtin"


def _load_skill(name: str):
    """从 builtin 目录加载 Skill 模块（不依赖 SkillManager）。"""
    f = BUILTIN_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _all_skill_names():
    return [f.stem for f in sorted(BUILTIN_DIR.glob("*.py")) if not f.stem.startswith("_")]


# ── A 组：agentskills_compat 字段声明 ─────────────────────────────────────────

class TestAgentSkillsCompatDeclaration:

    @pytest.mark.parametrize("name", _all_skill_names())
    def test_A01_compat_field_exists(self, name):
        """A01 每个内置 Skill 都应有 agentskills_compat 字段。"""
        m = _load_skill(name)
        assert "agentskills_compat" in m.SKILL_META, \
            f"{name}: SKILL_META 缺少 agentskills_compat"

    @pytest.mark.parametrize("name", _all_skill_names())
    def test_A02_compat_enabled_true(self, name):
        """A02 agentskills_compat.enabled 必须为 True。"""
        m = _load_skill(name)
        compat = m.SKILL_META["agentskills_compat"]
        assert compat.get("enabled") is True, f"{name}: enabled 不为 True"

    @pytest.mark.parametrize("name", _all_skill_names())
    def test_A03_compat_requires_bins(self, name):
        """A03 requires_bins 必须是非空列表，且包含 geoclaw-claude。"""
        m = _load_skill(name)
        compat = m.SKILL_META["agentskills_compat"]
        bins = compat.get("requires_bins", [])
        assert isinstance(bins, list) and len(bins) > 0, \
            f"{name}: requires_bins 为空"
        assert "geoclaw-claude" in bins, \
            f"{name}: requires_bins 应包含 'geoclaw-claude'"

    @pytest.mark.parametrize("name", _all_skill_names())
    def test_A04_compat_requires_env_is_list(self, name):
        """A04 requires_env 必须是列表（可以为空）。"""
        m = _load_skill(name)
        compat = m.SKILL_META["agentskills_compat"]
        env = compat.get("requires_env", [])
        assert isinstance(env, list), f"{name}: requires_env 不是列表"

    def test_A05_retail_site_ai_declares_api_key_env(self):
        """A05 retail_site_ai 需声明 ANTHROPIC_API_KEY 环境变量依赖。"""
        m = _load_skill("retail_site_ai")
        env = m.SKILL_META["agentskills_compat"].get("requires_env", [])
        assert "ANTHROPIC_API_KEY" in env, \
            "retail_site_ai.agentskills_compat.requires_env 应包含 ANTHROPIC_API_KEY"


# ── E 组：export_openclaw() 单个导出 ─────────────────────────────────────────

class TestExportOpenclaw:

    def test_E01_export_creates_directory(self, tmp_path):
        """E01 导出后目标目录应存在。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        assert pathlib.Path(dest).is_dir()

    def test_E02_skill_md_exists(self, tmp_path):
        """E02 导出后 SKILL.md 文件应存在。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        assert (pathlib.Path(dest) / "SKILL.md").is_file()

    def test_E03_compat_json_exists(self, tmp_path):
        """E03 导出后 .geoclaw_compat.json 应存在并含 geoclaw_skill 字段。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        cj = pathlib.Path(dest) / ".geoclaw_compat.json"
        assert cj.is_file()
        data = json.loads(cj.read_text())
        assert data["geoclaw_skill"] == "vec_buffer"
        assert "exported_at" in data
        assert data["agentskills_version"] == "1.0"

    def test_E04_skill_md_has_valid_frontmatter(self, tmp_path):
        """E04 SKILL.md 应以 --- 开头，包含 name / description / metadata 单行字段。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        md = (pathlib.Path(dest) / "SKILL.md").read_text()

        assert md.startswith("---"), "SKILL.md 应以 --- 开头"
        assert re.search(r"^name: ", md, re.MULTILINE), "缺少 name 字段"
        assert re.search(r"^description: ", md, re.MULTILINE), "缺少 description 字段"
        assert re.search(r"^metadata: \{", md, re.MULTILINE), "metadata 应是单行 JSON"

    def test_E05_metadata_json_valid(self, tmp_path):
        """E05 frontmatter 中的 metadata 行应是合法单行 JSON，含 openclaw.requires.bins。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        md = (pathlib.Path(dest) / "SKILL.md").read_text()

        meta_line = next(l for l in md.splitlines() if l.startswith("metadata:"))
        json_str = meta_line[len("metadata:"):].strip()
        data = json.loads(json_str)          # 必须合法 JSON
        assert "openclaw" in data
        assert "bins" in data["openclaw"]["requires"]
        assert "geoclaw-claude" in data["openclaw"]["requires"]["bins"]

    def test_E06_skill_md_has_cli_invocation(self, tmp_path):
        """E06 SKILL.md 指令段落应包含 geoclaw-claude skill run 调用示例。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        md = (pathlib.Path(dest) / "SKILL.md").read_text()
        assert "geoclaw-claude skill run vec_buffer" in md

    def test_E07_export_with_env_requirement(self, tmp_path):
        """E07 retail_site_ai 导出的 metadata 应声明 ANTHROPIC_API_KEY env。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        dest = sm.export_openclaw("retail_site_ai", output_dir=str(tmp_path))
        md = (pathlib.Path(dest) / "SKILL.md").read_text()
        assert "ANTHROPIC_API_KEY" in md

    def test_E08_overwrite_false_raises(self, tmp_path):
        """E08 目标目录已存在且 overwrite=False 时应抛出 FileExistsError。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        with pytest.raises(FileExistsError):
            sm.export_openclaw("vec_buffer", output_dir=str(tmp_path), overwrite=False)

    def test_E09_overwrite_true_succeeds(self, tmp_path):
        """E09 overwrite=True 时应成功覆盖。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        sm.export_openclaw("vec_buffer", output_dir=str(tmp_path))
        dest = sm.export_openclaw("vec_buffer", output_dir=str(tmp_path), overwrite=True)
        assert pathlib.Path(dest).is_dir()

    def test_E10_nonexistent_skill_raises_key_error(self, tmp_path):
        """E10 导出不存在的 Skill 应抛出 KeyError。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        with pytest.raises(KeyError):
            sm.export_openclaw("no_such_skill_xyz", output_dir=str(tmp_path))


# ── B 组：export_openclaw_all() 批量导出 ──────────────────────────────────────

class TestExportOpencalwAll:

    def test_B01_exports_all_15_skills(self, tmp_path):
        """B01 批量导出应产生 15 个目录（与内置 Skill 数量一致）。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        exported = sm.export_openclaw_all(output_dir=str(tmp_path))
        assert len(exported) == 15, f"期望 15 个，实际 {len(exported)}"

    def test_B02_all_have_skill_md(self, tmp_path):
        """B02 每个导出目录都应包含 SKILL.md。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        exported = sm.export_openclaw_all(output_dir=str(tmp_path))
        for dest in exported:
            assert (pathlib.Path(dest) / "SKILL.md").is_file(), \
                f"{dest} 缺少 SKILL.md"

    def test_B03_only_compat_subset(self, tmp_path):
        """B03 only_compat=True 时仅导出声明了 agentskills_compat 的 Skill（应为全部 15 个）。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        exported_all    = sm.export_openclaw_all(output_dir=str(tmp_path / "all"))
        exported_compat = sm.export_openclaw_all(
            output_dir=str(tmp_path / "compat"),
            only_compat=True,
        )
        # 因为所有 Skill 都声明了 compat，两次结果应相同
        assert len(exported_all) == len(exported_compat)

    def test_B04_names_match_skill_registry(self, tmp_path):
        """B04 导出目录名应与 SkillManager 注册的 Skill 名一致。"""
        from geoclaw_claude.skill_manager import SkillManager
        sm = SkillManager()
        registered = {s["name"] for s in sm.list_skills()}
        exported = sm.export_openclaw_all(output_dir=str(tmp_path))
        exported_names = {pathlib.Path(d).name for d in exported}
        assert exported_names == registered


# ── C 组：CLI smoke test ──────────────────────────────────────────────────────

class TestCLISkillExport:

    def test_C01_cli_export_single(self, tmp_path):
        """C01 CLI skill export <name> 应正常退出（returncode=0）。"""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "geoclaw_claude.cli",
             "skill", "export", "vec_buffer",
             "--output", str(tmp_path), "--overwrite"],
            capture_output=True, text=True,
            cwd=str(pathlib.Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"CLI 失败:\n{result.stdout}\n{result.stderr}"
        assert (tmp_path / "vec_buffer" / "SKILL.md").is_file()

    def test_C02_cli_export_all(self, tmp_path):
        """C02 CLI skill export --all 应导出所有 Skill 并正常退出。"""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "geoclaw_claude.cli",
             "skill", "export", "--all",
             "--output", str(tmp_path), "--overwrite"],
            capture_output=True, text=True,
            cwd=str(pathlib.Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"CLI 失败:\n{result.stdout}\n{result.stderr}"
        exported_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(exported_dirs) == 15, f"期望 15 个目录，实际 {len(exported_dirs)}"
