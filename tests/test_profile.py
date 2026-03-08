# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
tests/test_profile.py
======================
soul.md / user.md 个性化配置层测试套件

测试分组：
  P01-P08  SoulConfig 解析测试
  U01-U08  UserConfig 解析测试
  M01-M07  ProfileManager 加载/热更新/system prompt 测试

Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""

import pytest
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock
from geoclaw_claude.nl.profile_manager import (
    SoulConfig, UserConfig, ProfileManager,
    parse_soul, parse_user,
    DEFAULT_SOUL_MD, DEFAULT_USER_MD,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

MINIMAL_SOUL = textwrap.dedent("""\
    # soul.md
    ## Identity
    GeoClaw Test Agent

    ## Mission
    Test mission statement here.

    ## Core Principles
    1. Principle one
    2. Principle two
    3. Principle three

    ## Spatial Reasoning Guidelines
    - Always check CRS
    - Consider MAUP effects

    ## Safety Boundaries
    - Never overwrite user data
    - No arbitrary shell commands
""")

MINIMAL_USER = textwrap.dedent("""\
    # user.md
    ## Identity
    Role: urban researcher
    Domain: urban computing

    ## Language Preference
    Preferred language: Chinese

    ## Communication Style
    Preferred style: concise

    ## Technical Level
    Assume the user understands advanced GIS concepts

    ## Tool Preferences
    Preferred tools:
    - QGIS
    - Python geospatial stack (GeoPandas)
    - PostGIS

    ## Output Preferences
    - maps
    - reproducible workflows
""")


# ═══════════════════════════════════════════════════════════════════════
# P01–P08  SoulConfig 解析
# ═══════════════════════════════════════════════════════════════════════

class TestSoulParsing:

    def test_P01_default_soul_parses_without_error(self):
        """P01: 默认 soul.md 内容可正常解析"""
        cfg = parse_soul(DEFAULT_SOUL_MD)
        assert isinstance(cfg, SoulConfig)
        assert cfg.identity
        assert cfg.mission

    def test_P02_identity_extracted(self):
        """P02: identity 字段正确提取"""
        cfg = parse_soul(MINIMAL_SOUL)
        assert "GeoClaw" in cfg.identity

    def test_P03_mission_extracted(self):
        """P03: mission 字段正确提取"""
        cfg = parse_soul(MINIMAL_SOUL)
        assert "Test mission" in cfg.mission

    def test_P04_principles_extracted_as_list(self):
        """P04: Core Principles 解析为列表"""
        cfg = parse_soul(MINIMAL_SOUL)
        assert len(cfg.principles) == 3
        assert "Principle one" in cfg.principles[0]

    def test_P05_spatial_rules_extracted(self):
        """P05: Spatial Reasoning Guidelines 解析为列表"""
        cfg = parse_soul(MINIMAL_SOUL)
        assert len(cfg.spatial_rules) >= 1
        assert any("CRS" in r for r in cfg.spatial_rules)

    def test_P06_safety_rules_extracted(self):
        """P06: Safety Boundaries 解析为列表"""
        cfg = parse_soul(MINIMAL_SOUL)
        assert len(cfg.safety_rules) >= 1

    def test_P07_to_system_prompt_returns_string(self):
        """P07: to_system_prompt() 返回非空字符串"""
        cfg = parse_soul(MINIMAL_SOUL)
        prompt = cfg.to_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_P08_system_prompt_contains_identity(self):
        """P08: system prompt 包含 identity 内容"""
        cfg = parse_soul(MINIMAL_SOUL)
        prompt = cfg.to_system_prompt()
        assert "GeoClaw" in prompt or cfg.identity[:20] in prompt


# ═══════════════════════════════════════════════════════════════════════
# U01–U08  UserConfig 解析
# ═══════════════════════════════════════════════════════════════════════

class TestUserParsing:

    def test_U01_default_user_parses_without_error(self):
        """U01: 默认 user.md 内容可正常解析"""
        cfg = parse_user(DEFAULT_USER_MD)
        assert isinstance(cfg, UserConfig)

    def test_U02_role_extracted(self):
        """U02: role 字段正确提取"""
        cfg = parse_user(MINIMAL_USER)
        assert cfg.role == "urban researcher"

    def test_U03_domain_extracted(self):
        """U03: domain 字段正确提取"""
        cfg = parse_user(MINIMAL_USER)
        assert "urban" in cfg.domain.lower()

    def test_U04_language_zh(self):
        """U04: 中文语言偏好正确解析"""
        cfg = parse_user(MINIMAL_USER)
        assert cfg.preferred_lang == "zh"

    def test_U05_language_auto_for_default(self):
        """U05: 默认 user.md 包含 Chinese 或 English，解析为 zh 或 auto"""
        cfg = parse_user(DEFAULT_USER_MD)
        # 默认值 "Chinese or English" 因含 Chinese 解析为 zh，也可为 auto，均可接受
        assert cfg.preferred_lang in ("zh", "auto", "en")

    def test_U06_comm_style_concise(self):
        """U06: concise 通讯风格正确解析"""
        cfg = parse_user(MINIMAL_USER)
        assert cfg.comm_style == "concise"

    def test_U07_tool_prefs_list(self):
        """U07: 工具偏好解析为列表"""
        cfg = parse_user(MINIMAL_USER)
        assert isinstance(cfg.tool_prefs, list)
        assert len(cfg.tool_prefs) >= 2
        assert any("QGIS" in t for t in cfg.tool_prefs)

    def test_U08_to_context_hint_non_empty(self):
        """U08: to_context_hint() 返回非空字符串"""
        cfg = parse_user(MINIMAL_USER)
        hint = cfg.to_context_hint()
        assert isinstance(hint, str)
        assert len(hint) > 10


# ═══════════════════════════════════════════════════════════════════════
# M01–M07  ProfileManager 功能
# ═══════════════════════════════════════════════════════════════════════

class TestProfileManager:

    def test_M01_loads_with_custom_content(self, tmp_path):
        """M01: ProfileManager 从自定义路径加载"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        pm = ProfileManager(soul_path=soul_f, user_path=user_f).load()
        assert pm._loaded
        assert "GeoClaw" in pm.soul.identity
        assert pm.user.role == "urban researcher"

    def test_M02_auto_creates_defaults(self, tmp_path):
        """M02: 文件不存在时自动创建默认内容"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"

        pm = ProfileManager(soul_path=soul_f, user_path=user_f, auto_create=True).load()
        assert soul_f.exists()
        assert user_f.exists()
        assert pm._loaded

    def test_M03_no_auto_create_uses_defaults(self, tmp_path):
        """M03: auto_create=False 时使用内置默认内容（不写文件）"""
        soul_f = tmp_path / "no_soul.md"
        user_f = tmp_path / "no_user.md"

        pm = ProfileManager(soul_path=soul_f, user_path=user_f, auto_create=False).load()
        assert pm._loaded
        assert pm.soul.identity  # 使用内置默认

    def test_M04_build_system_prompt(self, tmp_path):
        """M04: build_system_prompt() 返回 soul 内容片段"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        pm = ProfileManager(soul_path=soul_f, user_path=user_f).load()
        prompt = pm.build_system_prompt()
        assert isinstance(prompt, str)
        assert "GeoClaw" in prompt or "Test mission" in prompt

    def test_M05_build_context_hint(self, tmp_path):
        """M05: build_context_hint() 包含用户偏好信息"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        pm = ProfileManager(soul_path=soul_f, user_path=user_f).load()
        hint = pm.build_context_hint()
        assert "urban researcher" in hint or "urban" in hint.lower()

    def test_M06_welcome_message_personalized(self, tmp_path):
        """M06: 欢迎语融合用户偏好"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        pm = ProfileManager(soul_path=soul_f, user_path=user_f).load()
        msg = pm.build_welcome_message(mode="AI")
        assert isinstance(msg, str)
        assert len(msg) > 20
        # 中文用户应看到中文欢迎语
        assert "GeoClaw" in msg or "GIS" in msg

    def test_M07_reload_picks_up_changes(self, tmp_path):
        """M07: reload() 重新读取文件变更"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        pm = ProfileManager(soul_path=soul_f, user_path=user_f).load()
        old_identity = pm.soul.identity

        # 修改文件
        new_soul = MINIMAL_SOUL.replace("GeoClaw Test Agent", "GeoClaw Modified Agent")
        soul_f.write_text(new_soul, encoding="utf-8")

        pm.reload()
        assert "Modified" in pm.soul.identity or pm.soul.identity != old_identity


# ═══════════════════════════════════════════════════════════════════════
# A01–A08  GeoAgent 集成测试
# ═══════════════════════════════════════════════════════════════════════

class TestGeoAgentProfileIntegration:

    def test_A01_geoagent_has_profile(self, tmp_path):
        """A01: GeoAgent 初始化后拥有 profile 属性"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        from geoclaw_claude.nl.agent import GeoAgent
        agent = GeoAgent(
            use_ai=False,
            soul_path=str(soul_f),
            user_path=str(user_f),
        )
        assert hasattr(agent, "profile")
        assert agent.profile._loaded

    def test_A02_geoagent_welcome_uses_profile(self, tmp_path):
        """A02: GeoAgent 欢迎语由 ProfileManager 生成"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        from geoclaw_claude.nl.agent import GeoAgent
        agent = GeoAgent(
            use_ai=False,
            soul_path=str(soul_f),
            user_path=str(user_f),
        )
        # 欢迎语在 _history[0]
        welcome = agent._history[0].text
        assert "GeoClaw" in welcome or "GIS" in welcome

    def test_A03_build_context_includes_soul(self, tmp_path):
        """A03: _build_context() 包含 soul_system_prompt 键"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        from geoclaw_claude.nl.agent import GeoAgent
        agent = GeoAgent(
            use_ai=False,
            soul_path=str(soul_f),
            user_path=str(user_f),
        )
        ctx = agent._build_context()
        assert "soul_system_prompt" in ctx
        assert len(ctx["soul_system_prompt"]) > 10

    def test_A04_build_context_includes_user(self, tmp_path):
        """A04: _build_context() 包含 user_profile_hint 键"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        from geoclaw_claude.nl.agent import GeoAgent
        agent = GeoAgent(
            use_ai=False,
            soul_path=str(soul_f),
            user_path=str(user_f),
        )
        ctx = agent._build_context()
        assert "user_profile_hint" in ctx

    def test_A05_status_includes_profile_fields(self, tmp_path):
        """A05: status() 包含 soul_loaded / user_loaded / user_role"""
        soul_f = tmp_path / "soul.md"
        user_f = tmp_path / "user.md"
        soul_f.write_text(MINIMAL_SOUL, encoding="utf-8")
        user_f.write_text(MINIMAL_USER, encoding="utf-8")

        from geoclaw_claude.nl.agent import GeoAgent
        agent = GeoAgent(
            use_ai=False,
            soul_path=str(soul_f),
            user_path=str(user_f),
        )
        s = agent.status()
        assert "soul_loaded" in s
        assert "user_loaded" in s
        assert "user_role" in s
        assert s["soul_loaded"] is True
        assert s["user_loaded"] is True
