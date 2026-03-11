#!/usr/bin/env bash
# ============================================================
# GeoClaw-claude 重装脚本
# 用法:
#   bash reinstall.sh              # 重装，保留用户数据
#   bash reinstall.sh --clean      # 清理用户数据后重装（全新开始）
#   bash reinstall.sh --dev        # 以开发模式重装
#   bash reinstall.sh --mini       # 最小依赖重装
# ============================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.geoclaw_claude"

# ── 颜色输出 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()  { echo -e "${RED}  ✗${NC} $1"; exit 1; }
info() { echo -e "  $1"; }
step() { echo -e "${CYAN}  ▶${NC} $1"; }

# ── 解析参数 ──────────────────────────────────────────────
CLEAN=false
DEV_MODE=false
MINI_MODE=false

for arg in "$@"; do
    case $arg in
        --clean) CLEAN=true ;;
        --dev)   DEV_MODE=true ;;
        --mini)  MINI_MODE=true ;;
        --help)
            echo "用法: bash reinstall.sh [选项]"
            echo ""
            echo "选项:"
            echo "  (无参数)      卸载旧版本并重新安装，保留 ~/.geoclaw_claude/ 用户数据"
            echo "  --clean       同上，并清空用户数据目录（配置、记忆重置为全新状态）"
            echo "  --dev         以开发模式重装（代码修改即时生效，适合开发调试）"
            echo "  --mini        最小依赖重装（跳过 osmnx、rasterio 等大型依赖）"
            echo "  --help        显示此帮助"
            echo ""
            echo "组合示例:"
            echo "  bash reinstall.sh --clean --dev    # 清数据 + 开发模式"
            echo "  bash reinstall.sh --mini           # 快速重装最小版"
            exit 0
            ;;
    esac
done

# ── 欢迎 ──────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   GeoClaw-claude 重装程序                ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# 打印当前模式
MODES=""
[ "$CLEAN" = true ]    && MODES="${MODES} --clean"
[ "$DEV_MODE" = true ] && MODES="${MODES} --dev"
[ "$MINI_MODE" = true ] && MODES="${MODES} --mini"
[ -n "$MODES" ] && info "模式:${MODES}" || info "模式: 标准重装（保留用户数据）"
echo ""

# ── 确认 --clean ──────────────────────────────────────────
if [ "$CLEAN" = true ] && [ -d "$CONFIG_DIR" ]; then
    DATA_SIZE=$(du -sh "$CONFIG_DIR" 2>/dev/null | cut -f1)
    MEM_COUNT=$(find "$CONFIG_DIR/memory" -name "*.json*" 2>/dev/null | wc -l | tr -d ' ')
    warn "--clean 将删除用户数据目录 ${CONFIG_DIR}"
    info "  目录大小: ${DATA_SIZE}，记忆条目: ${MEM_COUNT} 个文件"
    read -r -p "  确认清空用户数据？[y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        info "已取消。如只重装不清数据，请不加 --clean 运行。"
        exit 0
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 阶段一：卸载旧版本
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
step "阶段 1/3：卸载旧版本"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 记录旧版本号
OLD_VER=""
if python3 -m pip show geoclaw-claude &>/dev/null 2>&1; then
    OLD_VER=$(python3 -m pip show geoclaw-claude 2>/dev/null | grep Version | awk '{print $2}')
    info "当前已安装版本: v${OLD_VER}"
    python3 -m pip uninstall -y geoclaw-claude 2>/dev/null
    ok "旧版本 v${OLD_VER} 已卸载"
else
    # 检查是否以开发模式安装
    if python3 -c "import sys; sys.path.insert(0,'${REPO_DIR}'); import geoclaw_claude" &>/dev/null 2>&1; then
        python3 -m pip uninstall -y geoclaw-claude 2>/dev/null || true
        SITE_PKG=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || python3 -c "import site; print(site.getusersitepackages())")
        [ -f "${SITE_PKG}/easy-install.pth" ] && sed -i "\|${REPO_DIR}|d" "${SITE_PKG}/easy-install.pth" 2>/dev/null || true
        ok "开发模式旧安装已清理"
    else
        info "未检测到已安装的旧版本，直接安装"
    fi
fi

# ── 清理用户数据（--clean）────────────────────────────────
if [ "$CLEAN" = true ] && [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
    ok "用户数据目录已清空"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 阶段二：安装依赖
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
step "阶段 2/3：安装依赖"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 -m pip install --upgrade pip --quiet
ok "pip 已升级"

# 核心依赖
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

info "安装核心依赖..."
for dep in "${CORE_DEPS[@]}"; do
    pkg_name=$(echo "$dep" | sed 's/[>=<].*//')
    python3 -m pip install "$dep" --quiet || warn "$pkg_name 安装失败"
done
ok "核心依赖已就绪"

# 扩展依赖
if [ "$MINI_MODE" = false ]; then
    info "安装扩展依赖..."
    OPT_DEPS=(
        "folium>=0.14"
        "contextily>=1.3"
        "mapclassify>=2.6"
        "rasterio>=1.3"
        "scipy>=1.10"
        "osmnx>=1.7"
        "anthropic>=0.25"
    )
    for dep in "${OPT_DEPS[@]}"; do
        pkg_name=$(echo "$dep" | sed 's/[>=<].*//')
        python3 -m pip install "$dep" --quiet && ok "$pkg_name" || warn "$pkg_name 安装失败（可选，跳过）"
    done
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 阶段三：安装 geoclaw-claude
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
step "阶段 3/3：安装 geoclaw-claude"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$DEV_MODE" = true ]; then
    python3 -m pip install -e "$REPO_DIR" --quiet
    ok "geoclaw-claude（开发模式）已安装"
else
    python3 -m pip install "$REPO_DIR" --quiet
    ok "geoclaw-claude 已安装"
fi

# ── 验证 ─────────────────────────────────────────────────
NEW_VER=$(python3 -m pip show geoclaw-claude 2>/dev/null | grep Version | awk '{print $2}' || echo "?")
ok "版本验证: v${NEW_VER}"

if command -v geoclaw-claude &>/dev/null; then
    ok "CLI 命令 geoclaw-claude 可用"
else
    warn "geoclaw-claude 命令未在 PATH 中找到"
    info "  请将 pip bin 目录加入 PATH 后重试"
fi

# ── 完成 ────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   ✅ 重装完成！                          ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

if [ -n "$OLD_VER" ] && [ "$OLD_VER" != "$NEW_VER" ]; then
    info "  版本更新: v${OLD_VER} → v${NEW_VER}"
fi

if [ "$CLEAN" = true ]; then
    echo "  用户数据已重置，请重新初始化:"
    echo "    geoclaw-claude onboard"
elif [ -d "$CONFIG_DIR" ]; then
    echo "  用户数据已保留（配置/记忆不受影响）"
    echo "  直接使用: geoclaw-claude chat"
else
    echo "  首次使用请运行初始化向导:"
    echo "    geoclaw-claude onboard"
fi
echo ""
