"""
tests/test_skills_and_security.py
===================================
Skill 功能测试 + 安全审计测试

覆盖：
  S01-S06  retail_site_algo Skill 算法逻辑
  S07-S10  retail_site_ai   Skill（无AI模式）
  S11-S15  SkillManager 注册与执行
  A01-A10  SkillAuditor 安全规则检测
  A11-A15  高危 Skill 全量审计（evil_exfil / evil_inject / evil_file_ops）
  A16-A20  SkillManager.install 安全集成
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

# ─────────────────────────────── 路径设置 ─────────────────────────────────────
REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from geoclaw_claude.core.layer import GeoLayer
from geoclaw_claude.skill_auditor import (
    SkillAuditor, RiskLevel, AuditResult, RiskFinding, interactive_audit
)
from geoclaw_claude.skill_manager import SkillManager, SkillContext

# ─────────────────────────────── 测试夹具 ─────────────────────────────────────

MALICIOUS_DIR = Path(__file__).parent / "malicious_skills"
BUILTIN_DIR   = REPO / "geoclaw_claude" / "skills" / "builtin"


def _make_layer(n: int = 6, name: str = "test") -> GeoLayer:
    """生成均匀分布在武汉附近的随机点图层。"""
    np.random.seed(42)
    lons = np.random.uniform(114.0, 114.5, n)
    lats = np.random.uniform(30.4, 30.8, n)
    names = [f"候选点_{i+1}" for i in range(n)]
    gdf = gpd.GeoDataFrame(
        {"name": names},
        geometry=[Point(lon, lat) for lon, lat in zip(lons, lats)],
        crs="EPSG:4326",
    )
    return GeoLayer(gdf, name=name)


def _make_skill_context(layer: GeoLayer, **params) -> SkillContext:
    """创建带有预设图层和参数的 SkillContext。"""
    ctx = SkillContext()
    ctx._layers["input"] = layer
    for k, v in params.items():
        ctx.set_param(k, v)
    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# S 系列：Skill 功能测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetailSiteAlgo:
    """retail_site_algo Skill 功能测试。"""

    def _run(self, n=6, **params):
        """辅助方法：运行 retail_site_algo。"""
        import importlib.util
        skill_path = BUILTIN_DIR / "retail_site_algo.py"
        spec = importlib.util.spec_from_file_location("retail_site_algo", skill_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        layer = _make_layer(n)
        ctx   = _make_skill_context(layer, **params)
        return mod.run(ctx)

    def test_S01_basic_run(self):
        """S01: 基本运行不报错，返回 scored 图层。"""
        result = self._run()
        assert "scored" in result
        assert isinstance(result["scored"], GeoLayer)

    def test_S02_score_columns(self):
        """S02: 评分图层包含所有分数列。"""
        result = self._run()
        gdf = result["scored"].data
        for col in ["score_total", "score_pop", "score_comp",
                    "score_disp", "score_road", "rank"]:
            assert col in gdf.columns, f"缺少列: {col}"

    def test_S03_score_range(self):
        """S03: 所有分值在 [0, 100] 内。"""
        result = self._run(n=8)
        gdf    = result["scored"].data
        for col in ["score_total", "score_pop", "score_comp",
                    "score_disp", "score_road"]:
            vals = gdf[col].values
            assert vals.min() >= 0.0, f"{col} 有负值"
            assert vals.max() <= 100.1, f"{col} 超出100"

    def test_S04_rank_unique(self):
        """S04: rank 列无重复（1..n 全覆盖）。"""
        n      = 5
        result = self._run(n=n)
        ranks  = sorted(result["scored"].data["rank"].tolist())
        assert ranks == list(range(1, n + 1)), f"排名异常: {ranks}"

    def test_S05_report_generated(self):
        """S05: 生成文字报告，包含关键词。"""
        result = self._run()
        report = result.get("report", "")
        assert "MCDA" in report or "评估报告" in report
        assert "TOP" in report

    def test_S06_weight_normalization(self):
        """S06: 权重不等于1时自动归一化，结果依然有效。"""
        # 权重加起来 = 2.0，不等于 1，应自动归一化
        result = self._run(w_pop=0.6, w_comp=0.5, w_disp=0.5, w_road=0.4)
        gdf    = result["scored"].data
        assert gdf["score_total"].notna().all()

    def test_S07_top_n_param(self):
        """S07: top_n 参数控制报告推荐数量。"""
        result = self._run(n=8, top_n=2)
        report = result.get("report", "")
        assert "TOP 2" in report

    def test_S08_single_candidate(self):
        """S08: 单候选点不崩溃（边界情况）。"""
        result = self._run(n=1)
        gdf    = result["scored"].data
        assert len(gdf) == 1
        assert gdf["rank"].iloc[0] == 1


class TestRetailSiteAI:
    """retail_site_ai Skill 测试（无AI模式）。"""

    def _run(self, **params):
        import importlib.util
        skill_path = BUILTIN_DIR / "retail_site_ai.py"
        spec = importlib.util.spec_from_file_location("retail_site_ai", skill_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        layer = _make_layer(5)
        ctx   = _make_skill_context(layer, **params)
        return mod.run(ctx)

    def test_S09_run_without_ai(self):
        """S09: 无 AI 模式运行不崩溃，返回候选图层。"""
        result = self._run()
        assert "candidates" in result
        assert isinstance(result["candidates"], GeoLayer)

    def test_S10_fallback_report(self):
        """S10: 无AI时生成基础报告（含提示信息）。"""
        result = self._run()
        report = result.get("report", "")
        assert len(report) > 50
        # 无AI时应有回退报告
        assert "商场选址" in report or "候选点" in report or "AI" in report


class TestSkillManager:
    """SkillManager 注册与执行测试。"""

    def test_S11_list_includes_builtins(self):
        """S11: list_skills 返回内置 skill。"""
        sm     = SkillManager()
        skills = sm.list_skills()
        names  = [s["name"] for s in skills]
        assert "hospital_coverage" in names
        assert "retail_site_algo"  in names
        assert "retail_site_ai"    in names

    def test_S12_get_returns_meta(self):
        """S12: get() 返回正确的 META 信息。"""
        sm    = SkillManager()
        entry = sm.get("retail_site_algo")
        assert entry is not None
        assert entry["version"] == "1.0.0"
        assert entry["builtin"] is True

    def test_S13_audit_method(self):
        """S13: SkillManager.audit() 能直接审计文件。"""
        sm     = SkillManager()
        result = sm.audit(str(MALICIOUS_DIR / "evil_exfil.py"))
        assert isinstance(result, AuditResult)
        assert result.critical_count > 0

    def test_S14_install_clean_skill(self, tmp_path):
        """S14: 安装干净 Skill 自动通过审计。"""
        skill_src = tmp_path / "clean_skill.py"
        skill_src.write_text(
            'SKILL_META = {"name":"clean_test","version":"1.0.0",'
            '"author":"test","description":"clean skill"}\n'
            'def run(ctx):\n    return {}\n',
            encoding="utf-8",
        )
        sm   = SkillManager()
        sm._skill_dir = tmp_path / "skills"
        name = sm.install(str(skill_src), skip_audit=False, auto_approve=True)
        assert name == "clean_test"

    def test_S15_install_critical_skill_rejected(self, tmp_path):
        """S15: CRITICAL 风险 Skill 在 auto_approve=True 时被自动拒绝。"""
        sm = SkillManager()
        sm._skill_dir = tmp_path / "skills"
        with pytest.raises(PermissionError):
            sm.install(
                str(MALICIOUS_DIR / "evil_exfil.py"),
                auto_approve=True,   # 非交互，默认拒绝高危
            )


# ═══════════════════════════════════════════════════════════════════════════════
# A 系列：SkillAuditor 安全规则测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditorRules:
    """SkillAuditor 规则触发测试。"""

    auditor = SkillAuditor()

    def _audit_snippet(self, code: str) -> AuditResult:
        """将代码片段写入临时文件后审计。"""
        meta = (
            'SKILL_META={"name":"t","version":"1","author":"t","description":"t"}\n'
            'def run(ctx): pass\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(meta + code)
            tmp = f.name
        return self.auditor.audit(tmp)

    def test_A01_os_system_critical(self):
        """A01: os.system() → CRITICAL [命令执行]。"""
        result = self._audit_snippet('import os\nos.system("ls")\n')
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A02_eval_critical(self):
        """A02: eval() → CRITICAL [代码注入]。"""
        result = self._audit_snippet('eval("1+1")\n')
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A03_exec_critical(self):
        """A03: exec() → CRITICAL [代码注入]。"""
        result = self._audit_snippet('exec("x=1")\n')
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A04_requests_post_critical(self):
        """A04: requests.post(data=...) → CRITICAL [数据外泄]。"""
        result = self._audit_snippet(
            'import requests\nrequests.post("http://x.com", data={"k":"v"})\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A05_subprocess_critical(self):
        """A05: subprocess.run() → CRITICAL [命令执行]。"""
        result = self._audit_snippet(
            'import subprocess\nsubprocess.run(["ls"])\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A06_os_remove_high(self):
        """A06: os.remove() → HIGH [危险文件操作]。"""
        result = self._audit_snippet('import os\nos.remove("/tmp/x")\n')
        levels = [f.level for f in result.findings]
        assert RiskLevel.HIGH in levels

    def test_A07_rmtree_high(self):
        """A07: shutil.rmtree() → HIGH [危险文件操作]。"""
        result = self._audit_snippet(
            'import shutil\nshutil.rmtree("/tmp/x")\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.HIGH in levels

    def test_A08_pickle_load_high(self):
        """A08: pickle.load() → HIGH [反序列化攻击]。"""
        result = self._audit_snippet(
            'import pickle\nwith open("f","rb") as f: pickle.load(f)\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.HIGH in levels

    def test_A09_requests_get_medium(self):
        """A09: requests.get() → MEDIUM [网络请求]。"""
        result = self._audit_snippet(
            'import requests\nrequests.get("http://example.com")\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.MEDIUM in levels

    def test_A10_os_environ_medium(self):
        """A10: os.environ → MEDIUM [环境变量]。"""
        result = self._audit_snippet(
            'import os\nkey = os.environ.get("SECRET")\n'
        )
        levels = [f.level for f in result.findings]
        assert RiskLevel.MEDIUM in levels

    def test_A11_base64_decode_critical(self):
        """A11: base64.b64decode → CRITICAL [代码混淆]。"""
        result = self._audit_snippet(
            'import base64\nx = base64.b64decode("aGVsbG8=")\n'
        )
        # base64 解码应触发 CRITICAL
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A12_dangerous_import_pty(self):
        """A12: import pty → CRITICAL [危险模块导入]。"""
        result = self._audit_snippet('import pty\n')
        levels = [f.level for f in result.findings]
        assert RiskLevel.CRITICAL in levels

    def test_A13_missing_meta_flagged(self):
        """A13: 缺少 SKILL_META → meta_valid=False。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('def run(ctx): pass\n')
            tmp = f.name
        result = self.auditor.audit(tmp)
        assert not result.meta_valid
        assert any("SKILL_META" in i for i in result.meta_issues)

    def test_A14_missing_run_flagged(self):
        """A14: 缺少 run() 函数 → meta_issues 记录。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'SKILL_META={"name":"t","version":"1","author":"t","description":"t"}\n'
            )
            tmp = f.name
        result = self.auditor.audit(tmp)
        assert not result.meta_valid
        assert any("run" in i for i in result.meta_issues)

    def test_A15_clean_skill_passes(self):
        """A15: 干净 Skill 审计通过，无高危发现。"""
        result = self._audit_snippet(
            'from geoclaw_claude.analysis.spatial_ops import buffer\n'
            'def run(ctx):\n'
            '    layer = ctx.get_layer("input")\n'
            '    return ctx.result(result=buffer(layer, 1000))\n'
        )
        assert result.passed
        assert result.critical_count == 0
        assert result.high_count == 0


class TestMaliciousSkillFullAudit:
    """高危 Skill 文件全量审计测试。"""

    auditor = SkillAuditor()

    def test_A16_evil_exfil_critical(self):
        """A16: evil_exfil.py 审计结果为 CRITICAL，passed=False。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_exfil.py"))
        assert not result.passed
        assert result.critical_count >= 2, (
            f"应有 ≥2 个 CRITICAL，实际 {result.critical_count}"
        )
        assert result.risk_score >= 60

    def test_A17_evil_inject_critical(self):
        """A17: evil_inject.py 审计结果为 CRITICAL（eval+exec+base64）。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_inject.py"))
        assert not result.passed
        # eval / exec / base64 / __import__ 各触发一个 CRITICAL
        assert result.critical_count >= 3

    def test_A18_evil_file_ops_high(self):
        """A18: evil_file_ops.py 含 HIGH 级别风险（文件删除+subprocess）。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_file_ops.py"))
        # subprocess 会触发 CRITICAL；os.remove/rmtree 触发 HIGH
        assert result.max_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
        assert result.risk_score >= 30

    def test_A19_report_formatting(self):
        """A19: 审计报告格式正确，包含必要章节。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_exfil.py"))
        report = self.auditor.format_report(result)
        assert "安全审计报告" in report
        assert "风险分值" in report
        assert "CRITICAL" in report

    def test_A20_score_bar_present(self):
        """A20: format_report 包含彩色进度条字符。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_inject.py"))
        report = self.auditor.format_report(result)
        # 进度条字符应在报告中
        assert "█" in report or "░" in report

    def test_A21_interactive_audit_auto_rejects_critical(self):
        """A21: interactive_audit(auto_approve=True) 自动拒绝 CRITICAL Skill。"""
        approved = interactive_audit(
            str(MALICIOUS_DIR / "evil_exfil.py"),
            auto_approve=True,
        )
        assert not approved, "CRITICAL Skill 应被自动拒绝"

    def test_A22_interactive_audit_approves_clean(self):
        """A22: 干净 Skill 在 interactive_audit 中自动通过。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'SKILL_META={"name":"c","version":"1","author":"a","description":"d"}\n'
                'def run(ctx): return {}\n'
            )
            tmp = f.name
        approved = interactive_audit(tmp, auto_approve=True)
        assert approved, "干净 Skill 应自动通过"

    def test_A23_risk_score_proportional(self):
        """A23: evil_inject 风险分值 > evil_file_ops 风险分值（危险度更高）。"""
        r_inject   = self.auditor.audit(str(MALICIOUS_DIR / "evil_inject.py"))
        r_file_ops = self.auditor.audit(str(MALICIOUS_DIR / "evil_file_ops.py"))
        assert r_inject.risk_score >= r_file_ops.risk_score, (
            f"evil_inject({r_inject.risk_score}) 应 ≥ evil_file_ops({r_file_ops.risk_score})"
        )

    def test_A24_finding_has_line_numbers(self):
        """A24: 风险发现条目含行号信息。"""
        result = self.auditor.audit(str(MALICIOUS_DIR / "evil_exfil.py"))
        findings_with_line = [f for f in result.findings if f.line_no > 0]
        assert len(findings_with_line) >= 1, "至少有一个发现含行号"

    def test_A25_audit_result_summary(self):
        """A25: AuditResult.summary() 返回单行摘要字符串。"""
        result  = self.auditor.audit(str(MALICIOUS_DIR / "evil_exfil.py"))
        summary = result.summary()
        assert isinstance(summary, str)
        assert "evil_exfil" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-q"])
