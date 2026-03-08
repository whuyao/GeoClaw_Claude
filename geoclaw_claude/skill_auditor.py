"""
geoclaw_claude/skill_auditor.py
================================
Skill 安全审计模块

在 Skill 注册到系统前，对其源代码进行静态安全扫描，
识别潜在的恶意行为或高危操作，并输出结构化风险报告。

设计原则：
  - 零依赖：仅使用 Python 标准库（ast, re, tokenize）
  - 静态分析：不执行代码，避免引入执行风险
  - 分级报告：CRITICAL / HIGH / MEDIUM / LOW / INFO
  - 交互确认：CRITICAL/HIGH 级别强制要求用户手动确认

风险分类体系：
  ┌────────────┬─────────────────────────────────────────────────────────┐
  │ CRITICAL   │ 高概率恶意行为（系统命令执行、网络回传、代码注入）       │
  │ HIGH       │ 高风险但有合法用途（文件删除、进程操作、反射执行）       │
  │ MEDIUM     │ 需关注的敏感操作（网络请求、环境变量读取、动态导入）     │
  │ LOW        │ 低风险但值得注意（大量文件读写、临时文件操作）           │
  │ INFO       │ 提示信息（第三方库、资源密集型操作）                     │
  └────────────┴─────────────────────────────────────────────────────────┘
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


# ── 风险等级 ──────────────────────────────────────────────────────────────────

class RiskLevel(Enum):
    CRITICAL = 5   # 强制阻断 + 用户确认
    HIGH     = 4   # 警告 + 用户确认
    MEDIUM   = 3   # 警告，可通过
    LOW      = 2   # 提示
    INFO     = 1   # 信息

    @property
    def label(self) -> str:
        colors = {
            "CRITICAL": "\033[1;31m",   # 红色加粗
            "HIGH":     "\033[31m",     # 红色
            "MEDIUM":   "\033[33m",     # 黄色
            "LOW":      "\033[36m",     # 青色
            "INFO":     "\033[37m",     # 灰色
        }
        reset = "\033[0m"
        c = colors.get(self.name, "")
        return f"{c}[{self.name}]{reset}"

    @property
    def requires_confirmation(self) -> bool:
        return self in (RiskLevel.CRITICAL, RiskLevel.HIGH)


# ── 发现的风险条目 ─────────────────────────────────────────────────────────────

@dataclass
class RiskFinding:
    level:       RiskLevel
    category:    str           # 风险类别，如 "命令执行"
    description: str           # 具体描述
    line_no:     int           # 源码行号（0=未定位）
    code_snippet: str = ""     # 相关代码片段
    suggestion:  str = ""      # 修复建议


# ── 审计结果 ──────────────────────────────────────────────────────────────────

@dataclass
class AuditResult:
    skill_path:  str
    skill_name:  str
    passed:      bool                    # True = 无 CRITICAL
    risk_score:  int                     # 0~100，越高越危险
    findings:    List[RiskFinding] = field(default_factory=list)
    meta_valid:  bool = True
    meta_issues: List[str] = field(default_factory=list)

    @property
    def max_level(self) -> Optional[RiskLevel]:
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: f.level.value).level

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.level == RiskLevel.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.level == RiskLevel.HIGH)

    def summary(self) -> str:
        """返回一行摘要字符串。"""
        lvl = self.max_level
        level_str = lvl.label if lvl else "\033[32m[CLEAN]\033[0m"
        return (
            f"  Skill: {self.skill_name}  "
            f"风险分值: {self.risk_score}/100  "
            f"最高等级: {level_str}  "
            f"发现: {len(self.findings)} 项"
        )


# ── 规则定义 ──────────────────────────────────────────────────────────────────

# 格式：(正则表达式, 风险等级, 类别, 描述, 建议)
_PATTERN_RULES: List[Tuple[str, RiskLevel, str, str, str]] = [

    # ── CRITICAL：系统命令执行 ────────────────────────────────────────────────
    (r"\bos\.system\s*\(",          RiskLevel.CRITICAL, "命令执行",
     "os.system() 可直接执行任意系统命令",
     "移除或替换为受限的 subprocess 调用"),
    (r"\bsubprocess\.(run|call|Popen|check_output)\s*\(",
                                     RiskLevel.CRITICAL, "命令执行",
     "subprocess 模块可执行任意系统命令",
     "如确有需要，限制 shell=False 且使用白名单命令"),
    (r"\beval\s*\(",                 RiskLevel.CRITICAL, "代码注入",
     "eval() 可执行任意Python代码，是最常见的注入入口",
     "绝对禁止在 Skill 中使用 eval()"),
    (r"\bexec\s*\(",                 RiskLevel.CRITICAL, "代码注入",
     "exec() 可执行任意Python代码",
     "绝对禁止在 Skill 中使用 exec()"),
    (r"__import__\s*\(",            RiskLevel.CRITICAL, "代码注入",
     "__import__() 可动态加载任意模块，绕过导入检查",
     "使用标准 import 语句替代"),
    (r"\bcompile\s*\(.*exec",       RiskLevel.CRITICAL, "代码注入",
     "compile+exec 组合可绕过静态检测执行任意代码",
     "禁止使用此模式"),

    # ── CRITICAL：数据外泄 ────────────────────────────────────────────────────
    (r"requests\.(post|put|patch)\s*\([^)]*(?:data|json|files)\s*=",
                                     RiskLevel.CRITICAL, "数据外泄",
     "向外部服务器POST数据，可能泄露分析数据或系统信息",
     "Skill 不应主动上传数据至外部服务器"),
    (r"socket\.connect\s*\(",       RiskLevel.CRITICAL, "数据外泄",
     "建立原始 socket 连接，可能用于数据回传",
     "禁止在 Skill 中使用 raw socket"),
    (r"\bparamiko\b|\bftplib\b|\bsmtplib\b",
                                     RiskLevel.CRITICAL, "数据外泄",
     "使用 SSH/FTP/SMTP 协议，高度疑似数据外泄行为",
     "禁止在 Skill 中使用远程传输协议"),

    # ── CRITICAL：权限提升 ────────────────────────────────────────────────────
    (r"\bos\.chmod\s*\([^)]*0o[0-9]*7[0-9]*\)",
                                     RiskLevel.CRITICAL, "权限提升",
     "修改文件权限为可执行，可能为后续攻击准备",
     "禁止在 Skill 中修改文件执行权限"),
    (r"\bctypes\b",                  RiskLevel.CRITICAL, "权限提升",
     "ctypes 可调用底层 C 函数，绕过 Python 沙箱",
     "禁止在 Skill 中使用 ctypes"),

    # ── HIGH：危险文件操作 ────────────────────────────────────────────────────
    (r"\bos\.remove\s*\(|os\.unlink\s*\(|shutil\.rmtree\s*\(",
                                     RiskLevel.HIGH, "危险文件操作",
     "删除文件或目录，可能造成不可逆数据损失",
     "如需清理，只操作 ctx.output_dir 内的临时文件"),
    (r"open\s*\([^)]*,\s*['\"]w['\"]",
                                     RiskLevel.HIGH, "危险文件操作",
     "以写入模式打开文件，可能覆盖系统文件",
     "使用 ctx.output_dir 限制写入范围"),
    (r"\bos\.makedirs\s*\([^)]*(?:\/etc|\/usr|\/bin|\/sys|C:\\\\Windows)",
                                     RiskLevel.HIGH, "危险文件操作",
     "在系统目录创建文件夹",
     "禁止操作系统保护目录"),
    (r"\bpickle\.load\s*\(",        RiskLevel.HIGH, "反序列化攻击",
     "pickle.load() 反序列化不可信数据可执行任意代码",
     "使用 json.load() 或 geojson 替代"),

    # ── HIGH：进程与系统操作 ──────────────────────────────────────────────────
    (r"\bos\.fork\s*\(\|os\.spawn",  RiskLevel.HIGH, "进程操作",
     "创建子进程，可能用于后台恶意执行",
     "禁止在 Skill 中创建进程"),
    (r"\bos\.kill\s*\(",             RiskLevel.HIGH, "进程操作",
     "发送信号给进程，可能终止系统服务",
     "禁止在 Skill 中使用 os.kill()"),
    (r"\bsignal\b",                  RiskLevel.HIGH, "进程操作",
     "操作系统信号，可能干扰父进程运行",
     "禁止在 Skill 中使用 signal 模块"),

    # ── MEDIUM：网络请求 ──────────────────────────────────────────────────────
    (r"\brequests\.get\s*\(",        RiskLevel.MEDIUM, "网络请求",
     "发起 HTTP GET 请求，注意目标 URL 是否可信",
     "确认请求目标为已知数据源"),
    (r"\burllib\.request\b",         RiskLevel.MEDIUM, "网络请求",
     "urllib 网络请求",
     "确认请求目标为已知数据源"),
    (r"\bhttpx\b|\baiohttp\b",       RiskLevel.MEDIUM, "网络请求",
     "第三方 HTTP 库发起网络请求",
     "确认请求目标为已知数据源"),

    # ── MEDIUM：环境与系统信息 ────────────────────────────────────────────────
    (r"\bos\.environ\b",             RiskLevel.MEDIUM, "环境变量",
     "读取环境变量，可能获取 API Key、密码等敏感信息",
     "避免读取与分析无关的环境变量"),
    (r"\bos\.getenv\s*\(",           RiskLevel.MEDIUM, "环境变量",
     "读取环境变量",
     "明确说明读取的变量名称及用途"),
    (r"\bplatform\b|\bsysconfig\b",  RiskLevel.MEDIUM, "系统信息",
     "读取系统平台信息",
     "若非必要，避免采集系统指纹"),

    # ── MEDIUM：动态代码 ──────────────────────────────────────────────────────
    (r"\bimportlib\.import_module\s*\(",
                                     RiskLevel.MEDIUM, "动态导入",
     "动态导入模块，导入目标在运行时确定，难以静态审查",
     "在 SKILL_META 的 dependencies 中声明所有依赖"),
    (r"\bgetattr\s*\([^)]*,\s*[^)]*\)",
                                     RiskLevel.MEDIUM, "反射调用",
     "getattr 动态调用，可能用于绕过静态检测",
     "尽量使用直接属性访问"),

    # ── LOW：大量文件操作 ─────────────────────────────────────────────────────
    (r"glob\.glob\s*\(",             RiskLevel.LOW, "文件遍历",
     "遍历文件系统，注意路径范围",
     "限制 glob 路径在 ctx.output_dir 内"),
    (r"\bos\.walk\s*\(",             RiskLevel.LOW, "文件遍历",
     "递归遍历目录树",
     "限制遍历范围，避免扫描系统目录"),
    (r"\btempfile\b",                RiskLevel.LOW, "临时文件",
     "使用临时文件，注意清理",
     "确保临时文件在 Skill 执行完毕后被清除"),

    # ── INFO：第三方库 ────────────────────────────────────────────────────────
    (r"\bimport\s+torch\b|\bimport\s+tensorflow\b",
                                     RiskLevel.INFO, "重型依赖",
     "深度学习框架体积庞大（>1GB），首次运行需下载",
     "在 SKILL_META.dependencies 中声明并提示用户"),
    (r"\bimport\s+cv2\b|\bimport\s+PIL\b",
                                     RiskLevel.INFO, "图像处理库",
     "图像处理库，请确认在 dependencies 中声明",
     "在 SKILL_META 中声明 opencv-python 或 Pillow"),
]

# 高危导入模块（仅 import 语句本身即为风险）
_DANGEROUS_IMPORTS = {
    "pty":       (RiskLevel.CRITICAL, "伪终端操作，常用于提权"),
    "pdb":       (RiskLevel.HIGH,     "调试器，可在生产环境暂停执行"),
    "code":      (RiskLevel.HIGH,     "交互式解释器，可获取任意变量"),
    "codeop":    (RiskLevel.HIGH,     "动态代码编译"),
    "marshal":   (RiskLevel.HIGH,     "底层序列化，可绕过安全检查"),
    "cffi":      (RiskLevel.HIGH,     "C外部函数接口，可绕过 Python 沙箱"),
    "winreg":    (RiskLevel.HIGH,     "读写 Windows 注册表"),
    "msvcrt":    (RiskLevel.MEDIUM,   "Windows C 运行时访问"),
}


# ── 主审计器 ──────────────────────────────────────────────────────────────────

class SkillAuditor:
    """
    对 Skill .py 文件执行静态安全审计。

    用法：
        auditor = SkillAuditor()
        result  = auditor.audit("/path/to/my_skill.py")
        print(auditor.format_report(result))
        if result.max_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            confirmed = input("是否仍要安装？(yes/no) ")
    """

    def audit(self, path: str) -> AuditResult:
        """
        对指定 Skill 文件执行完整审计。

        Args:
            path: Skill .py 文件路径

        Returns:
            AuditResult 对象，包含所有发现的风险项
        """
        src_path   = Path(path)
        skill_name = src_path.stem
        findings:  List[RiskFinding] = []
        meta_valid  = True
        meta_issues: List[str] = []

        # 读取源码
        try:
            source = src_path.read_text(encoding="utf-8")
        except Exception as e:
            return AuditResult(
                skill_path=str(path),
                skill_name=skill_name,
                passed=False,
                risk_score=100,
                findings=[RiskFinding(
                    RiskLevel.CRITICAL, "读取失败",
                    f"无法读取 Skill 文件: {e}", 0,
                )],
            )

        lines = source.splitlines()

        # 1. 正则模式扫描（逐行）
        findings.extend(self._scan_patterns(lines))

        # 2. AST 深层分析
        try:
            tree = ast.parse(source)
            findings.extend(self._scan_ast(tree, lines))
            # 3. META 字段验证
            meta_valid, meta_issues = self._validate_meta(tree)
        except SyntaxError as e:
            findings.append(RiskFinding(
                RiskLevel.HIGH, "语法错误",
                f"Skill 源码存在语法错误: {e}", e.lineno or 0,
                suggestion="修复语法错误后重新审计",
            ))

        # 4. 计算综合风险分值
        risk_score = self._calc_score(findings)
        passed     = all(f.level != RiskLevel.CRITICAL for f in findings)

        return AuditResult(
            skill_path=str(path),
            skill_name=skill_name,
            passed=passed,
            risk_score=risk_score,
            findings=sorted(findings, key=lambda f: -f.level.value),
            meta_valid=meta_valid,
            meta_issues=meta_issues,
        )

    # ── 正则扫描 ───────────────────────────────────────────────────────────────

    def _scan_patterns(self, lines: List[str]) -> List[RiskFinding]:
        findings = []
        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            for pattern, level, category, desc, suggestion in _PATTERN_RULES:
                if re.search(pattern, line):
                    findings.append(RiskFinding(
                        level=level,
                        category=category,
                        description=desc,
                        line_no=line_no,
                        code_snippet=stripped[:120],
                        suggestion=suggestion,
                    ))
        return findings

    # ── AST 深层分析 ───────────────────────────────────────────────────────────

    def _scan_ast(self, tree: ast.AST, lines: List[str]) -> List[RiskFinding]:
        findings = []
        visitor  = _ASTVisitor(lines)
        visitor.visit(tree)
        findings.extend(visitor.findings)

        # 危险模块导入检测
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [alias.name.split(".")[0] for alias in node.names]
                else:
                    mods = [node.module.split(".")[0]] if node.module else []
                for mod in mods:
                    if mod in _DANGEROUS_IMPORTS:
                        lvl, desc = _DANGEROUS_IMPORTS[mod]
                        ln = getattr(node, "lineno", 0)
                        snippet = lines[ln - 1].strip() if ln > 0 else ""
                        findings.append(RiskFinding(
                            level=lvl,
                            category="危险模块导入",
                            description=f"导入高风险模块 '{mod}'：{desc}",
                            line_no=ln,
                            code_snippet=snippet,
                            suggestion=f"移除 import {mod}，使用更安全的替代方案",
                        ))
        return findings

    # ── META 验证 ──────────────────────────────────────────────────────────────

    def _validate_meta(self, tree: ast.AST) -> Tuple[bool, List[str]]:
        """验证 SKILL_META 字典是否包含必填字段。"""
        issues = []
        required_keys = {"name", "version", "author", "description"}

        # 找到 SKILL_META 赋值节点
        meta_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SKILL_META":
                        meta_node = node
                        break

        if meta_node is None:
            return False, ["缺少 SKILL_META 字典（必填）"]

        # 提取字典键
        if not isinstance(meta_node.value, ast.Dict):
            return False, ["SKILL_META 必须是字典字面量"]

        found_keys = set()
        for key in meta_node.value.keys:
            if isinstance(key, ast.Constant):
                found_keys.add(key.value)

        missing = required_keys - found_keys
        if missing:
            issues.append(f"SKILL_META 缺少必填字段: {', '.join(sorted(missing))}")

        # 检查 run() 函数
        has_run = any(
            isinstance(node, ast.FunctionDef) and node.name == "run"
            for node in ast.walk(tree)
        )
        if not has_run:
            issues.append("缺少 run(ctx) 入口函数（必填）")

        return len(issues) == 0, issues

    # ── 风险分值计算 ───────────────────────────────────────────────────────────

    def _calc_score(self, findings: List[RiskFinding]) -> int:
        """
        将所有发现映射为 0~100 分（越高越危险）。

        权重：CRITICAL=30, HIGH=15, MEDIUM=5, LOW=2, INFO=0
        上限：100 分
        """
        weights = {
            RiskLevel.CRITICAL: 30,
            RiskLevel.HIGH:     15,
            RiskLevel.MEDIUM:    5,
            RiskLevel.LOW:       2,
            RiskLevel.INFO:      0,
        }
        score = sum(weights.get(f.level, 0) for f in findings)
        return min(score, 100)

    # ── 报告格式化 ─────────────────────────────────────────────────────────────

    def format_report(self, result: AuditResult, verbose: bool = True) -> str:
        """生成人类可读的审计报告。"""
        sep  = "═" * 64
        sep2 = "─" * 64
        lines = [
            "",
            sep,
            "  🔍 GeoClaw-claude  Skill 安全审计报告",
            sep,
            f"  Skill 文件 : {result.skill_path}",
            f"  Skill 名称 : {result.skill_name}",
            f"  风险分值   : {result.risk_score}/100  "
            + self._score_bar(result.risk_score),
            f"  审计结论   : " + (
                "\033[32m✅ 通过（可安装）\033[0m" if result.passed
                else "\033[1;31m❌ 未通过（含 CRITICAL 风险）\033[0m"
            ),
        ]

        # META 验证
        if not result.meta_valid:
            lines.append(f"\n  ⚠ META 验证问题:")
            for issue in result.meta_issues:
                lines.append(f"    · {issue}")

        # 风险详情
        if not result.findings:
            lines += [sep2, "  ✅ 未发现任何风险项", sep2]
        else:
            lines += [
                "",
                sep2,
                f"  发现 {len(result.findings)} 项风险  "
                f"(CRITICAL:{result.critical_count}  HIGH:{result.high_count}  "
                f"其他:{len(result.findings)-result.critical_count-result.high_count})",
                sep2,
            ]

            # 按等级分组输出
            for level in (RiskLevel.CRITICAL, RiskLevel.HIGH,
                          RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.INFO):
                level_findings = [f for f in result.findings if f.level == level]
                if not level_findings:
                    continue
                lines.append(f"\n  {level.label} ({len(level_findings)} 项)")
                for f in level_findings:
                    loc = f"行 {f.line_no}" if f.line_no else "未定位"
                    lines.append(f"  ┌ [{loc}] {f.category}")
                    lines.append(f"  │ {f.description}")
                    if verbose and f.code_snippet:
                        lines.append(f"  │ 代码: {f.code_snippet}")
                    if verbose and f.suggestion:
                        lines.append(f"  │ 建议: {f.suggestion}")
                    lines.append(f"  └")

        lines += ["", sep, ""]
        return "\n".join(lines)

    def _score_bar(self, score: int) -> str:
        """返回彩色进度条。"""
        filled = score // 5
        bar    = "█" * filled + "░" * (20 - filled)
        if score >= 60:
            color = "\033[1;31m"   # 红
        elif score >= 30:
            color = "\033[33m"     # 黄
        else:
            color = "\033[32m"     # 绿
        return f"{color}[{bar}]\033[0m"


# ── AST 访问者（深层模式检测）─────────────────────────────────────────────────

class _ASTVisitor(ast.NodeVisitor):
    """使用 AST 检测难以用正则捕获的危险模式。"""

    def __init__(self, lines: List[str]):
        self.lines    = lines
        self.findings: List[RiskFinding] = []

    def _snippet(self, lineno: int) -> str:
        if lineno and 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()[:120]
        return ""

    def visit_Call(self, node: ast.Call):
        """检测函数调用。"""
        ln = getattr(node, "lineno", 0)

        # open() + 写模式（AST 级别）
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            for arg in node.args[1:]:
                if isinstance(arg, ast.Constant) and "w" in str(arg.value):
                    self.findings.append(RiskFinding(
                        RiskLevel.HIGH, "文件写入",
                        "以写入模式 open() 打开文件",
                        ln, self._snippet(ln),
                        "确保写入路径限制在 ctx.output_dir 内",
                    ))
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    if "w" in str(kw.value.value):
                        self.findings.append(RiskFinding(
                            RiskLevel.HIGH, "文件写入",
                            "以写入模式 open(..., mode='w') 打开文件",
                            ln, self._snippet(ln),
                        ))

        # base64 + exec/eval 组合（混淆执行）
        func_str = ast.unparse(node.func) if hasattr(ast, "unparse") else ""
        if "b64decode" in func_str or "base64" in func_str:
            self.findings.append(RiskFinding(
                RiskLevel.CRITICAL, "代码混淆",
                "使用 base64 解码，可能用于隐藏恶意 payload",
                ln, self._snippet(ln),
                "禁止在 Skill 中使用 base64 动态解码执行",
            ))

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """检测属性链调用。"""
        ln = getattr(node, "lineno", 0)

        # os.popen / os.system（属性访问方式）
        dangerous_attrs = {
            "popen": (RiskLevel.CRITICAL, "命令执行", "os.popen() 执行系统命令"),
            "system": (RiskLevel.CRITICAL, "命令执行", "调用系统命令"),
        }
        if node.attr in dangerous_attrs:
            lvl, cat, desc = dangerous_attrs[node.attr]
            self.findings.append(RiskFinding(
                lvl, cat, desc, ln, self._snippet(ln),
            ))

        self.generic_visit(node)


# ── 交互式确认流程 ────────────────────────────────────────────────────────────

def interactive_audit(path: str, auto_approve: bool = False) -> bool:
    """
    执行审计并根据风险等级进行交互式确认。

    Args:
        path:         Skill 文件路径
        auto_approve: True = 跳过交互（用于测试）

    Returns:
        True 表示用户确认安装，False 表示取消
    """
    auditor = SkillAuditor()
    result  = auditor.audit(path)

    print(auditor.format_report(result))

    # META 不合规 → 直接拒绝
    if not result.meta_valid:
        print("\033[1;31m  ✗ Skill META 不合规，安装已取消。\033[0m\n")
        return False

    # 无风险 → 直接通过
    if not result.findings:
        print("\033[32m  ✓ 安全扫描通过，将自动安装。\033[0m\n")
        return True

    # 仅 LOW/INFO → 提示后通过
    if result.max_level in (RiskLevel.LOW, RiskLevel.INFO):
        print("\033[36m  ℹ 存在低等级提示，Skill 可以安装。\033[0m\n")
        return True

    # MEDIUM → 提示 + 默认通过
    if result.max_level == RiskLevel.MEDIUM:
        if auto_approve:
            return True
        resp = input(
            "\033[33m  ⚠ 存在中等风险项，是否仍要安装？"
            "[y/N]: \033[0m"
        ).strip().lower()
        return resp in ("y", "yes", "是")

    # HIGH / CRITICAL → 强制用户输入 "yes" 确认
    max_lv = result.max_level
    color  = "\033[1;31m" if max_lv == RiskLevel.CRITICAL else "\033[31m"
    print(f"{color}  {'⛔' if max_lv==RiskLevel.CRITICAL else '⚠'} "
          f"检测到 {max_lv.name} 级风险！\033[0m")
    print(f"  发现 {result.critical_count} 个 CRITICAL，{result.high_count} 个 HIGH 风险项。")
    print("  安装此 Skill 可能带来以下危害：")
    for f in result.findings:
        if f.level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            print(f"    · [{f.category}] {f.description}")

    if auto_approve:
        print("\033[33m  (auto_approve=True，已跳过交互)\033[0m")
        return False   # 默认拒绝高危

    print(f"\n  如果你确认已审阅以上风险并信任该 Skill 的来源，")
    resp = input(
        f"  请输入 \033[1myes\033[0m 以继续安装（其他任意输入取消）: "
    ).strip().lower()

    if resp == "yes":
        print("\033[33m  ⚠ 用户已确认，执行安装（风险自负）。\033[0m\n")
        return True
    else:
        print("\033[32m  ✓ 已取消安装，系统保持安全。\033[0m\n")
        return False
