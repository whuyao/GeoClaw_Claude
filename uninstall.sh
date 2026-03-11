#!/usr/bin/env bash
# ============================================================
# GeoClaw-claude 卸载脚本
# 用法:
#   bash uninstall.sh              # 卸载包，保留用户数据
#   bash uninstall.sh --purge      # 卸载包 + 删除全部用户数据
#   bash uninstall.sh --dry-run    # 预览将执行的操作，不实际删除
# ============================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.geoclaw_claude"

# ── 颜色输出 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()     { echo -e "${GREEN}  ✓${NC} $1"; }
warn()   { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()    { echo -e "${RED}  ✗${NC} $1"; exit 1; }
info()   { echo -e "  $1"; }
step()   { echo -e "${CYAN}  ▶${NC} $1"; }
dry()    { echo -e "${YELLOW}  [dry-run]${NC} 将执行: $1"; }

# ── 解析参数 ──────────────────────────────────────────────
PURGE=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --purge)   PURGE=true ;;
        --dry-run) DRY_RUN=true ;;
        --help)
            echo "用法: bash uninstall.sh [选项]"
            echo ""
            echo "选项:"
            echo "  (无参数)      卸载 pip 包和 CLI，保留 ~/.geoclaw_claude/ 用户数据"
            echo "  --purge       同上，并删除 ~/.geoclaw_claude/（配置、记忆、缓存全部清除）"
            echo "  --dry-run     仅预览操作，不实际删除任何内容"
            echo "  --help        显示此帮助"
            exit 0
            ;;
    esac
done

# ── 欢迎 ──────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   GeoClaw-claude 卸载程序                ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

if [ "$DRY_RUN" = true ]; then
    warn "dry-run 模式：仅预览，不实际执行任何删除操作"
    echo ""
fi

if [ "$PURGE" = true ]; then
    warn "--purge 模式：将删除包 + 全部用户数据（不可恢复）"
    echo ""
    if [ "$DRY_RUN" = false ]; then
        read -r -p "  确认删除用户数据？[y/N] " CONFIRM
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
            info "已取消。如只卸载包（保留数据），请不加 --purge 运行。"
            exit 0
        fi
    fi
fi

# ── 1. 卸载 pip 包 ─────────────────────────────────────────
echo ""
step "步骤 1/3：卸载 pip 包 geoclaw-claude"

PKG_FOUND=false
if python3 -m pip show geoclaw-claude &>/dev/null 2>&1; then
    PKG_FOUND=true
    PKG_LOCATION=$(python3 -m pip show geoclaw-claude 2>/dev/null | grep Location | awk '{print $2}')
    info "  安装位置: ${PKG_LOCATION}/geoclaw_claude"
    if [ "$DRY_RUN" = true ]; then
        dry "pip uninstall -y geoclaw-claude"
    else
        python3 -m pip uninstall -y geoclaw-claude
        ok "geoclaw-claude 包已卸载"
    fi
else
    # 检查开发模式安装（editable）
    if python3 -c "import sys; sys.path.insert(0,'${REPO_DIR}'); import geoclaw_claude" &>/dev/null 2>&1; then
        warn "检测到开发模式安装（-e），将移除 egg-link / dist-info"
        if [ "$DRY_RUN" = true ]; then
            dry "pip uninstall -y geoclaw-claude  # 或手动删除 .egg-link"
        else
            python3 -m pip uninstall -y geoclaw-claude 2>/dev/null || true
            # 手动清理 easy-install.pth 引用
            SITE_PKG=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || python3 -c "import site; print(site.getusersitepackages())")
            if [ -f "${SITE_PKG}/easy-install.pth" ]; then
                sed -i "\|${REPO_DIR}|d" "${SITE_PKG}/easy-install.pth" 2>/dev/null || true
            fi
            ok "开发模式安装已清理"
        fi
        PKG_FOUND=true
    else
        warn "未找到已安装的 geoclaw-claude 包（可能已卸载或从未安装）"
    fi
fi

# ── 2. 清理 CLI 命令 ───────────────────────────────────────
echo ""
step "步骤 2/3：检查 CLI 命令"

CLI_PATH=$(command -v geoclaw-claude 2>/dev/null || true)
if [ -n "$CLI_PATH" ]; then
    if [ "$DRY_RUN" = true ]; then
        dry "rm -f ${CLI_PATH}"
    else
        # pip uninstall 通常已处理，这里做兜底清理
        rm -f "$CLI_PATH" 2>/dev/null || true
        ok "CLI 命令 ${CLI_PATH} 已移除"
    fi
else
    ok "CLI 命令已不存在（无需处理）"
fi

# ── 3. 用户数据目录 ────────────────────────────────────────
echo ""
step "步骤 3/3：用户数据目录 ${CONFIG_DIR}"

if [ -d "$CONFIG_DIR" ]; then
    # 统计内容
    DATA_SIZE=$(du -sh "$CONFIG_DIR" 2>/dev/null | cut -f1)
    MEM_COUNT=$(find "$CONFIG_DIR/memory" -name "*.json*" 2>/dev/null | wc -l | tr -d ' ')
    info "  目录大小: ${DATA_SIZE}"
    info "  记忆条目: ${MEM_COUNT} 个文件"

    if [ "$PURGE" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            dry "rm -rf ${CONFIG_DIR}  # 删除配置、记忆、缓存全部数据"
        else
            rm -rf "$CONFIG_DIR"
            ok "用户数据目录已删除"
        fi
    else
        info "  已保留（重装后仍可使用历史记忆和配置）"
        info "  如需彻底清除，请运行: bash uninstall.sh --purge"
        info "  或手动删除: rm -rf ${CONFIG_DIR}"
    fi
else
    ok "用户数据目录不存在（无需处理）"
fi

# ── 完成 ────────────────────────────────────────────────────
echo ""
if [ "$DRY_RUN" = true ]; then
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║   🔍 dry-run 预览完成，未做任何更改     ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""
    echo "  确认无误后，去掉 --dry-run 重新运行即可执行实际卸载。"
else
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║   ✅ 卸载完成                            ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""
    if [ "$PURGE" = false ] && [ -d "$CONFIG_DIR" ]; then
        echo "  提示：用户数据（配置/记忆）已保留于 ${CONFIG_DIR}"
        echo "        重装后执行 geoclaw-claude onboard 可恢复使用。"
    fi
    echo "  如需重新安装: bash install.sh"
fi
echo ""
