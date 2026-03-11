#!/usr/bin/env bash
# ============================================================
# GeoClaw-claude 安装脚本
# 用法:
#   bash install.sh          # 标准安装
#   bash install.sh --dev    # 开发模式（可编辑安装）
#   bash install.sh --mini   # 最小安装（跳过大型依赖）
# ============================================================

set -e

VERSION="3.2.0"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 颜色输出 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()  { echo -e "${RED}  ✗${NC} $1"; exit 1; }
info() { echo -e "  $1"; }

# ── 解析参数 ──────────────────────────────────────────────
DEV_MODE=false
MINI_MODE=false
for arg in "$@"; do
    case $arg in
        --dev)  DEV_MODE=true ;;
        --mini) MINI_MODE=true ;;
        --help) echo "用法: bash install.sh [--dev|--mini]"; exit 0 ;;
    esac
done

# ── 欢迎 ──────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   GeoClaw-claude v${VERSION} 安装向导        ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── 检查 Python ────────────────────────────────────────────
info "检查 Python 环境..."
if ! command -v python3 &>/dev/null; then
    err "未找到 python3，请先安装 Python 3.9+"
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo $PY_VER | cut -d. -f1)
PY_MINOR=$(echo $PY_VER | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    err "需要 Python 3.9+，当前版本: $PY_VER"
fi
ok "Python $PY_VER"

# ── 检查 pip ───────────────────────────────────────────────
if ! python3 -m pip --version &>/dev/null; then
    err "未找到 pip，请安装: python3 -m ensurepip"
fi
ok "pip 已就绪"

# ── 虚拟环境（可选）────────────────────────────────────────
if [ -n "$VIRTUAL_ENV" ]; then
    ok "已在虚拟环境: $VIRTUAL_ENV"
elif [ -n "$CONDA_DEFAULT_ENV" ]; then
    ok "已在 conda 环境: $CONDA_DEFAULT_ENV"
else
    warn "建议在虚拟环境中安装（conda/venv）"
    info "  创建虚拟环境: python3 -m venv .venv && source .venv/bin/activate"
fi

echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "安装核心依赖..."
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 升级 pip ──────────────────────────────────────────────
python3 -m pip install --upgrade pip --quiet
ok "pip 已升级"

# ── 安装核心依赖 ────────────────────────────────────────────
CORE_DEPS=(
    "geopandas>=0.14"
    "shapely>=2.0"
    "pyproj>=3.5"
    "numpy>=1.24"
    "pandas>=2.0"
    "matplotlib>=3.7"
    "click>=8.0"
    "requests>=2.28"
)

for dep in "${CORE_DEPS[@]}"; do
    pkg_name=$(echo "$dep" | sed 's/[>=<].*//')
    if python3 -c "import ${pkg_name//-/_}" &>/dev/null 2>&1; then
        ok "$pkg_name（已安装）"
    else
        info "安装 $dep..."
        python3 -m pip install "$dep" --quiet || warn "安装 $dep 失败，跳过"
        ok "$pkg_name"
    fi
done

# ── 安装可选依赖 ────────────────────────────────────────────
if [ "$MINI_MODE" = false ]; then
    echo ""
    info "安装扩展依赖（--mini 跳过）..."

    OPT_DEPS=(
        "folium>=0.14"
        "contextily>=1.3"
        "mapclassify>=2.6"
        "rasterio>=1.3"
        "scipy>=1.10"
    )

    for dep in "${OPT_DEPS[@]}"; do
        pkg_name=$(echo "$dep" | sed 's/[>=<].*//')
        info "  安装 $dep..."
        python3 -m pip install "$dep" --quiet && ok "$pkg_name" || warn "$pkg_name 安装失败（可选，跳过）"
    done

    # osmnx（较大）
    info "  安装 osmnx（路网分析，较大）..."
    python3 -m pip install "osmnx>=1.7" --quiet && ok "osmnx" || warn "osmnx 安装失败（路网功能不可用）"

    # anthropic（AI功能）
    info "  安装 anthropic（AI分析接口）..."
    python3 -m pip install "anthropic>=0.25" --quiet && ok "anthropic" || warn "anthropic 安装失败（AI功能不可用）"
fi

# ── 安装 geoclaw-claude 本身 ────────────────────────────────
echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "安装 geoclaw-claude..."
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$DEV_MODE" = true ]; then
    info "开发模式（可编辑安装）..."
    python3 -m pip install -e "$REPO_DIR" --quiet
    ok "geoclaw-claude（开发模式，代码修改即时生效）"
else
    python3 -m pip install "$REPO_DIR" --quiet
    ok "geoclaw-claude v${VERSION}"
fi

# ── 验证安装 ────────────────────────────────────────────────
echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "验证安装..."
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if python3 -c "import geoclaw_claude; print(geoclaw_claude.__version__)" &>/dev/null; then
    VER=$(python3 -c "import geoclaw_claude; print(geoclaw_claude.__version__)")
    ok "geoclaw_claude 模块可导入 (v${VER})"
else
    err "geoclaw_claude 导入失败，请检查安装日志"
fi

if command -v geoclaw-claude &>/dev/null; then
    ok "geoclaw-claude 命令可用"
else
    warn "geoclaw-claude 命令未找到，可能需要将 pip bin 目录加入 PATH"
    info "  $(python3 -m pip show -f geoclaw-claude 2>/dev/null | grep 'Location' | awk '{print $2}')/bin"
fi

# ── 完成 ────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║        ✅ 安装完成！                     ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  下一步:"
echo "    1. 运行初始化向导: geoclaw-claude onboard"
echo "    2. 验证环境:        geoclaw-claude test"
echo "    3. 查看帮助:        geoclaw-claude --help"
echo ""
