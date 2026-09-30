#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Easel 一键安装
# 用法: git clone <repo> && cd Easel && bash setup.sh
#
# 环境隔离：所有 OpenClaw 配置存在 ~/.openclaw-easel/
# 不影响用户本机已有的 OpenClaw 配置
# ============================================================

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROFILE="easel"
OC="openclaw --profile $PROFILE"

# macOS ships Bash 3.2; keep the installer portable to that baseline.
if [ -z "${BASH_VERSION:-}" ]; then
    echo "请使用 Bash 运行 setup.sh（bash setup.sh）" >&2
    exit 1
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
DIM='\033[2m'
NC='\033[0m'

info()  { echo -e "${CYAN}[easel]${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
ask()   { if [ -t 0 ]; then printf "${CYAN}  ?${NC} %s " "$1" >&2; read -r REPLY; printf '%s' "$REPLY"; else printf ''; fi; }
ask_secret() { if [ -t 0 ]; then printf "${CYAN}  ?${NC} %s " "$1" >&2; read -r -s REPLY; printf '\n' >&2; printf '%s' "$REPLY"; else printf ''; fi; }
step()  { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${MAGENTA}  [$1]${NC} ${CYAN}$2${NC}"; echo -e "${DIM}  $3${NC}"; }

run_with_progress() {
    local label log_file pid started elapsed frame
    label="$1"
    shift
    log_file="$(mktemp "${TMPDIR:-/tmp}/easel-install.XXXXXX")"
    "$@" >"$log_file" 2>&1 &
    pid=$!
    started=$(date +%s)
    frame=0
    while kill -0 "$pid" 2>/dev/null; do
        elapsed=$(( $(date +%s) - started ))
        case $((frame % 4)) in
            0) progress='[>   ]' ;;
            1) progress='[=>  ]' ;;
            2) progress='[==> ]' ;;
            *) progress='[===>]' ;;
        esac
        printf '\r  %s 进行中 %s 已运行 %ss' "$progress" "$label" "$elapsed" >&2
        frame=$((frame + 1))
        sleep 1
    done
    if wait "$pid"; then
        printf '\r  [====] %s 完成                         \n' "$label" >&2
        rm -f "$log_file"
        return 0
    fi
    printf '\r  [FAIL] %s 失败                         \n' "$label" >&2
    tail -40 "$log_file" >&2 || true
    rm -f "$log_file"
    return 1
}

clear 2>/dev/null || true
echo -e "\n${CYAN}╭────────────────────────────────────────────────────╮${NC}"
echo -e "${CYAN}│${NC}  ${MAGENTA}Easel${NC} · 社媒内容工作台安装向导                 ${CYAN}│${NC}"
echo -e "${CYAN}│${NC}  ${DIM}OpenClaw-powered · Linux / macOS${NC}                 ${CYAN}│${NC}"
echo -e "${CYAN}╰────────────────────────────────────────────────────╯${NC}"
echo -e "\n${DIM}  Easel 会使用独立 profile ~/.openclaw-${PROFILE}/，不会覆盖已有 OpenClaw。${NC}\n"

# ---- 1. Node.js >= 24.16 ----
# 跟随 openclaw@latest 的引擎要求：当前 2026.9.x 需要 Node >=24.16.0 <25 || >=26.1.0
# （注意 25.x 与 26.0 被排除）。setup 默认安装 openclaw@latest，故 Node 下限对齐到 24.16。
step "1/8" "检查系统环境" "Python · Node.js · Git · FFmpeg"
info "检查 Node.js..."
node_version_ok() {  # $1=major $2=minor
    { [ "$1" -eq 24 ] && [ "$2" -ge 16 ]; } \
        || { [ "$1" -eq 26 ] && [ "$2" -ge 1 ]; } \
        || [ "$1" -ge 27 ]
}
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VER=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    NODE_MINOR=$(echo "$NODE_VER" | cut -d. -f2)
    if node_version_ok "$NODE_MAJOR" "$NODE_MINOR"; then
        NODE_OK=true
    fi
fi

if $NODE_OK; then
    ok "Node.js $NODE_VER"
else
    if [ -n "${NODE_VER:-}" ]; then
        info "Node.js $NODE_VER 过旧（openclaw@latest 需要 24.16+），安装 Node.js 24..."
    else
        info "安装 Node.js 24..."
    fi
    if [ "$(uname -s)" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            brew install node@24
            export PATH="$(brew --prefix node@24)/bin:$PATH"
        else
            echo "macOS 未找到 Homebrew。请先安装 Node.js 24.16+（Homebrew: brew install node@24），再重新运行 setup.sh。" >&2
            exit 1
        fi
    else
        NODE_TARGET="v24.21.0"
        curl -fL --max-time 120 "https://nodejs.org/dist/${NODE_TARGET}/node-${NODE_TARGET}-linux-x64.tar.xz" -o /tmp/node24.tar.xz
        cd /tmp && tar xf node24.tar.xz
        cp -rf node-${NODE_TARGET}-linux-x64/bin/* /usr/local/bin/
        cp -rf node-${NODE_TARGET}-linux-x64/lib/* /usr/local/lib/
        rm -rf /tmp/node-${NODE_TARGET}-linux-x64 /tmp/node24.tar.xz
        cd "$PROJECT_ROOT"
    fi
    ok "Node.js $(node -v)"
fi
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    PYTHON_OK=$(python3 -c 'import sys; print(int(sys.version_info >= (3, 10)))')
    if [ "$PYTHON_OK" -eq 1 ]; then
        ok "Python $(python3 --version 2>&1 | awk '{print $2}')"
    else
        echo "Python 版本过低：检测到 ${PYTHON_VER}，需要 Python 3.10+。" >&2
        exit 1
    fi
else
    echo "未找到 python3；Easel 需要 Python 3.10+。" >&2
    exit 1
fi
if [ -t 0 ]; then
    USE_VENV="$(ask '使用项目虚拟环境 .venv 安装 Python 依赖？[Y/n]')"
    case "${USE_VENV:-Y}" in
        n|N) warn "将使用当前 Python 环境" ;;
        *)
            if [ ! -x "$PROJECT_ROOT/.venv/bin/python" ]; then
                if ! python3 -c 'import venv' >/dev/null 2>&1; then
                    echo "当前 Python 缺少 venv 模块，无法创建虚拟环境。" >&2
                    echo "Debian/Ubuntu 请运行：sudo apt install python3-venv" >&2
                    echo "RHEL/CentOS 请安装对应的 python3 virtualenv/venv 包后重试。" >&2
                    exit 1
                fi
                info "创建虚拟环境 .venv..."
                python3 -m venv "$PROJECT_ROOT/.venv"
            fi
            # shellcheck disable=SC1091
            source "$PROJECT_ROOT/.venv/bin/activate"
            if ! python3 -m pip --version >/dev/null 2>&1; then
                echo "虚拟环境已创建但缺少 pip，请检查系统 Python 的 ensurepip/venv 包后重试。" >&2
                exit 1
            fi
            ok "已使用虚拟环境：$PROJECT_ROOT/.venv"
            ;;
    esac
elif [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    # Non-interactive runs reuse an existing project environment when available.
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
    info "检测到 .venv，非交互模式自动使用项目虚拟环境"
else
    warn "当前为非交互模式且未找到 .venv，将使用系统 Python；建议先创建 Python 3.10+ 虚拟环境"
fi
command -v git >/dev/null 2>&1 && ok "Git $(git --version | awk '{print $3}')" || warn "未找到 git"
if command -v ffmpeg >/dev/null 2>&1; then
    ok "FFmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
else
    info "安装 FFmpeg（媒体功能必需）..."
    if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        brew install ffmpeg
    elif command -v apt-get >/dev/null 2>&1; then
        if [ "$(id -u)" -eq 0 ]; then apt-get update && apt-get install -y ffmpeg
        elif command -v sudo >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y ffmpeg
        fi
    elif command -v dnf >/dev/null 2>&1; then
        if [ "$(id -u)" -eq 0 ]; then dnf install -y ffmpeg
        elif command -v sudo >/dev/null 2>&1; then sudo dnf install -y ffmpeg
        fi
    elif command -v yum >/dev/null 2>&1; then
        if [ "$(id -u)" -eq 0 ]; then yum install -y ffmpeg
        elif command -v sudo >/dev/null 2>&1; then sudo yum install -y ffmpeg
        fi
    fi
    if command -v ffmpeg >/dev/null 2>&1; then
        ok "FFmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
    else
        echo "FFmpeg 安装失败；请手动安装 FFmpeg 后重新运行 bash setup.sh。" >&2
        exit 1
    fi
fi

# ---- 2. npm 源 ----
step "2/8" "准备 Node.js 工具链" "设置 npm registry"
npm config set registry https://registry.npmjs.org 2>/dev/null
ok "npm registry: npmjs.org"

# ---- 3. 检测/安装 OpenClaw（复用用户已有安装，不覆盖全局配置） ----
step "3/8" "检测 OpenClaw" "已有安装将直接复用"
info "检查 OpenClaw..."
if command -v openclaw >/dev/null 2>&1; then
    OPENCLAW_BIN="$(command -v openclaw)"
    ok "检测到 OpenClaw：$($OPENCLAW_BIN --version 2>&1 | head -1)"
else
    info "安装 OpenClaw..."
    npm install -g openclaw@latest --loglevel warn 2>&1 | tail -1
    # npm 全局 bin 目录未必在当前 shell 的 PATH 上：macOS Homebrew 的 Node 会把全局包装到
    # $(npm prefix -g)/bin（如 /opt/homebrew/Cellar/node/<ver>/bin），而 /opt/homebrew/bin 里
    # 并没有 openclaw 链接。此时 command -v 拿到空值，后面 $OPENCLAW_BIN --version 会直接崩。
    # 先把 npm 全局 bin 补进 PATH 再检测。
    if ! command -v openclaw >/dev/null 2>&1; then
        NPM_GLOBAL_BIN="$(npm prefix -g 2>/dev/null)/bin"
        if [ -x "$NPM_GLOBAL_BIN/openclaw" ]; then
            export PATH="$NPM_GLOBAL_BIN:$PATH"
        fi
    fi
    OPENCLAW_BIN="$(command -v openclaw)"
    if [ -z "$OPENCLAW_BIN" ]; then
        echo "OpenClaw 安装后仍未在 PATH 中找到。请把 npm 全局 bin 目录（$(npm prefix -g 2>/dev/null)/bin）加入 PATH 后重新运行 setup.sh（幂等，会跳过已装部分）。" >&2
        exit 1
    fi
    ok "OpenClaw 已安装：$($OPENCLAW_BIN --version 2>&1 | head -1)"
fi
OC="$OPENCLAW_BIN --profile $PROFILE"

# ---- 4. 初始化 Easel 专属 OpenClaw profile ----
step "4/8" "初始化 Easel profile" "独立配置、独立 workspace、独立 Gateway"
info "初始化 Easel profile (--profile $PROFILE)..."
if [ -f "$HOME/.openclaw-${PROFILE}/openclaw.json" ]; then
    ok "Profile 已存在"
else
    ONBOARD_HELP="$($OPENCLAW_BIN onboard --help 2>/dev/null || true)"
    if [ -n "$ONBOARD_HELP" ]; then
        ONBOARD_ARGS=(onboard --non-interactive --mode local --accept-risk)
        for optional_arg in --skip-health --skip-channels --skip-skills \
            --skip-ui --skip-hooks --skip-search; do
            if printf '%s\n' "$ONBOARD_HELP" | grep -q -- "$optional_arg"; then
                ONBOARD_ARGS+=("$optional_arg")
            fi
        done
        if printf '%s\n' "$ONBOARD_HELP" | grep -q -- '--skip-daemon'; then
            ONBOARD_ARGS+=(--skip-daemon)
        elif printf '%s\n' "$ONBOARD_HELP" | grep -q -- '--no-install-daemon'; then
            ONBOARD_ARGS+=(--no-install-daemon)
        fi
        $OPENCLAW_BIN --profile "$PROFILE" "${ONBOARD_ARGS[@]}" 2>&1 | tail -2
    elif $OPENCLAW_BIN setup --help >/dev/null 2>&1; then
        $OC setup --non-interactive --mode local --accept-risk 2>&1 | tail -2
    else
        echo "当前 OpenClaw 不支持可用的非交互初始化命令，请升级 OpenClaw 后重试。" >&2
        exit 1
    fi
    ok "Profile 初始化完成 → ~/.openclaw-${PROFILE}/"
fi

# ---- 5. 安装 easel CLI ----
step "5/8" "安装 Easel 运行依赖" "Web · 媒体 · 浏览器发布"
info "[1/2] 安装 Python 依赖与 easel CLI..."
PIP_ARGS=(install -e "$PROJECT_ROOT" --progress-bar on)
if [ "$(id -u)" -eq 0 ]; then
    PIP_ARGS+=(--root-user-action=ignore)
    warn "当前以 root 安装；生产服务器建议使用虚拟环境"
fi
run_with_progress "Python 依赖安装" python3 -m pip "${PIP_ARGS[@]}"
if ! command -v easel >/dev/null 2>&1; then
    echo "easel 命令未找到；请检查 Python 环境和 PATH。" >&2
    exit 1
fi
ok "[2/2] easel 命令可用"

# ---- 6. 构建 Web 前端（Node 已装 → easel web 直接出真 UI，无需手动构建） ----
step "6/8" "构建 Web 工作台" "React production bundle"
info "构建 Web 前端..."
if [ -d "$PROJECT_ROOT/web/frontend" ]; then
    if ! (
        cd "$PROJECT_ROOT/web/frontend"
        if [ -f package-lock.json ]; then npm ci --no-audit --no-fund || npm install --no-audit --no-fund; else npm install --no-audit --no-fund; fi
        npm run build
    ); then
        echo "前端依赖安装或构建失败；请检查 Node.js/npm 网络后重新运行 bash setup.sh。" >&2
        exit 1
    fi
    ok "前端已构建 → web/frontend/dist/"
else
    echo "未找到 web/frontend，无法完成 Web 工作台安装。" >&2
    exit 1
fi

# ---- 7. 认证配置 ----
step "7/8" "配置模型服务" "Agent API：Anthropic · OpenAI · 兼容接口 · 本机 Claude CLI"
info "配置认证..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    ok ".env 已存在"
else
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    warn "已创建 .env，请编辑并填入 API key："
    warn "  vim .env"
fi

# ---- 8. 同步 skills + workspace ----
info "同步 Easel skills..."
# 不要把 stderr 并进管道：sync.sh 解析不出 workspace 时那条警告只走 stderr，且不含 ✓/→，
# 一并 grep 就被整条吃掉 —— 装完什么都没说，技能却同步到了 agent 不读的目录（issue #19
# 的失败模式在这一层原样重建）。stdout 照旧过滤噪音，stderr 直通用户。
bash "$PROJECT_ROOT/openclaw/sync.sh" | grep -E '✓|→'

# ---- 9. 认证信息写入 Easel 专属 OpenClaw config ----
info "同步认证到 OpenClaw profile..."
source "$PROJECT_ROOT/.env" 2>/dev/null || true

# 部分 OpenClaw 版本执行 config unset 后会把字段留成 null 而非真正删除该键，
# 一旦落盘就再也无法通过 config set/doctor --fix 修复（每次校验都先失败）。
# 这里在写入任何配置前，先把 models.providers.* 下残留的 null 叶子节点原地清空。
OPENCLAW_JSON="$HOME/.openclaw-${PROFILE}/openclaw.json"
if [ -f "$OPENCLAW_JSON" ]; then
    python3 - "$OPENCLAW_JSON" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path) as f:
    config = json.load(f)


def strip_nulls(node):
    if isinstance(node, dict):
        changed = False
        for key in list(node.keys()):
            value = node[key]
            if value is None:
                del node[key]
                changed = True
            elif strip_nulls(value):
                changed = True
        return changed
    return False


providers = config.get("models", {}).get("providers", {})
if strip_nulls(providers):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
PY
fi

# 原子写入 anthropic provider。部分 OpenClaw 版本（如 2026.3.x）的 schema 要求 provider 一次性带齐
# baseUrl + models，逐字段 config set 会因中间态缺字段而整体校验失败（baseUrl/models: received undefined）。
# 这里用一次 --json 原子写入建好完整 provider；整块替换也会顺带清掉旧的 Cookie/X-Adapter-* 等残留 header。
# 用法：oc_write_anthropic <baseUrl> <apiKey> [apiKeyHeader] [anthropicVersion]
oc_write_anthropic() {
    local seed
    seed="$(A_BASE_URL="$1" A_API_KEY="$2" A_HDR="${3:-}" A_VER="${4:-}" python3 -c '
import json, os
p = {"baseUrl": os.environ["A_BASE_URL"], "apiKey": os.environ["A_API_KEY"], "models": []}
hdr = os.environ.get("A_HDR"); ver = os.environ.get("A_VER")
if hdr or ver:
    h = {}
    if hdr: h[hdr] = os.environ["A_API_KEY"]
    if ver: h["anthropic-version"] = ver
    p["headers"] = h
print(json.dumps(p))')"
    $OC config set models.providers.anthropic "$seed" --json 2>&1 | sed '/^No change$/d'
}

# 若用户已有默认 OpenClaw 配置，复用其模型名称；密钥不会从别的 profile 复制。
# Claude CLI 路线不问：它只认 anthropic/<模型>，复用来的多半是别家 provider，下面只会被打回默认。
if [ -z "${CLAUDE_MODEL:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -t 0 ] \
   && [ "${EASEL_AGENT_RUNTIME:-}" != "claude-cli" ]; then
    EXISTING_MODEL="$($OPENCLAW_BIN config get agents.defaults.model.primary 2>/dev/null || true)"
    if [ -n "$EXISTING_MODEL" ] && [ "$EXISTING_MODEL" != "null" ]; then
        echo "  检测到已有 OpenClaw 默认模型：$EXISTING_MODEL"
        USE_EXISTING="$(ask '复用这个模型到 Easel？[Y/n]')"
        case "${USE_EXISTING:-Y}" in
            n|N) ;;
            *) printf '\nCLAUDE_MODEL=%s\n' "$EXISTING_MODEL" >> "$PROJECT_ROOT/.env"; CLAUDE_MODEL="$EXISTING_MODEL"; ok "已复用模型配置" ;;
        esac
    fi
fi

# .env.example 里的 key 带的是占位符，所以「变量有值」≠「这个 key 能用」。
# 认证判定一律走这里，别再各写各的 -n/-z：之前下面那段用 `-z ANTHROPIC_API_KEY`
# 判「没配 Anthropic」，占位符行一留就永远不成立，整条 OpenAI 分支被跳过，
# 最后只写了个指向不存在 provider 的 primary，对话直接报
# "No route-compatible authentication source is configured for openai"。
# 语义与 setup.ps1 的 Is-UsableKey 保持一致。
usable_key() {
    [ -n "${1:-}" ] || return 1
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        *replace_me*|*your-api-key*|*your_api_key*|*"your api key"*) return 1 ;;
    esac
    return 0
}

MODEL_CONFIGURED=false
if [ "${EASEL_AGENT_RUNTIME:-}" = "claude-cli" ]; then
    # 显式选了本机 Claude Code 登录，不需要任何 key（登录态在下面写配置时检查）
    MODEL_CONFIGURED=true
elif usable_key "${ANTHROPIC_API_KEY:-}"; then
    MODEL_CONFIGURED=true
elif usable_key "${EASEL_LLM_API_KEY:-}" && [ -n "${EASEL_LLM_BASE_URL:-}" ]; then
    MODEL_CONFIGURED=true
elif usable_key "${OPENAI_API_KEY:-}"; then
    MODEL_CONFIGURED=true
elif usable_key "${ANTHROPIC_AUTH_TOKEN:-}" && [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
    MODEL_CONFIGURED=true
elif usable_key "${OPENAI_MAAS_API_KEY:-}" && [ -n "${OPENAI_MAAS_ENDPOINT:-}" ]; then
    MODEL_CONFIGURED=true
fi

# 首次安装时提供模型向导；占位值不算已配置，非交互运行则明确提示后继续。
if [ "$MODEL_CONFIGURED" = false ] && [ -t 0 ]; then
    echo ""
    echo "  Easel 需要一个可用的 Agent 模型服务才能对话。"
    echo "    1) Anthropic API"
    echo "    2) OpenAI / OpenAI-compatible API"
    echo "    3) 其他 Anthropic-compatible API"
    echo "    4) 本机 Claude Code 登录（Claude CLI，无需 API Key）"
    echo "    0) 稍后配置"
    PROVIDER_CHOICE="$(ask '请选择模型服务 [1]：')"
    case "${PROVIDER_CHOICE:-1}" in
        1)
            MODEL_KEY="$(ask_secret 'Anthropic API Key（不会回显）：')"
            if [ -n "$MODEL_KEY" ]; then
                MODEL_NAME="$(ask '模型名 [anthropic/claude-sonnet-4-6]：')"
                printf '\nANTHROPIC_API_KEY=%s\nCLAUDE_MODEL=%s\n' \
                    "$MODEL_KEY" "${MODEL_NAME:-anthropic/claude-sonnet-4-6}" >> "$PROJECT_ROOT/.env"
                ok "Anthropic Agent 配置已写入 .env"
            fi
            ;;
        2)
            MODEL_KEY="$(ask_secret 'OpenAI API Key（不会回显）：')"
            if [ -n "$MODEL_KEY" ]; then
                MODEL_URL="$(ask 'Base URL [https://api.openai.com/v1]：')"
                MODEL_NAME="$(ask '模型名 [gpt-4o]：')"
                printf '\nOPENAI_API_KEY=%s\nOPENAI_BASE_URL=%s\nOPENAI_MODEL=%s\n' \
                    "$MODEL_KEY" "${MODEL_URL:-https://api.openai.com/v1}" \
                    "${MODEL_NAME:-gpt-4o}" >> "$PROJECT_ROOT/.env"
                ok "OpenAI Agent 配置已写入 .env"
            fi
            ;;
        3)
            MODEL_KEY="$(ask_secret 'API Key（不会回显）：')"
            MODEL_URL="$(ask 'Base URL：')"
            MODEL_NAME="$(ask '模型名：')"
            if [ -n "$MODEL_KEY" ] && [ -n "$MODEL_URL" ] && [ -n "$MODEL_NAME" ]; then
                printf '\nEASEL_LLM_API_KEY=%s\nEASEL_LLM_BASE_URL=%s\nCLAUDE_MODEL=%s\n' \
                    "$MODEL_KEY" "$MODEL_URL" "$MODEL_NAME" >> "$PROJECT_ROOT/.env"
                ok "兼容 API 的 Agent 配置已写入 .env"
            fi
            ;;
        4)
            # gateway 是直接从 PATH 拉起 claude 的，这里找不到它，写了配置也跑不起来
            if ! command -v claude >/dev/null 2>&1; then
                warn "PATH 上找不到 claude：先安装 Claude Code（https://claude.com/claude-code），再重新运行 bash setup.sh"
            else
                MODEL_NAME="$(ask '模型名 [anthropic/claude-opus-5]：')"
                printf '\nEASEL_AGENT_RUNTIME=claude-cli\nCLAUDE_MODEL=%s\n' \
                    "${MODEL_NAME:-anthropic/claude-opus-5}" >> "$PROJECT_ROOT/.env"
                ok "Claude CLI 路线已写入 .env（登录态在下一步检查）"
            fi
            ;;
        0) ;;
        *) warn "无法识别的选择，稍后可编辑 .env 后重新运行 bash setup.sh" ;;
    esac
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
elif [ "$MODEL_CONFIGURED" = false ]; then
    warn "未检测到 Agent API 配置；请编辑 .env 后重新运行 bash setup.sh"
fi

DEFAULT_PRIMARY_MODEL="anthropic/claude-sonnet-4-6"
# 本机 Claude Code 登录路线（EASEL_AGENT_RUNTIME=claude-cli）。setup.ps1 尚未同步这条路线。
CLAUDE_CLI_ROUTE=false
# 改了 env.vars.CLAUDE_CONFIG_DIR 就得 restart：见文末启动 gateway 那一步。
GATEWAY_RESTART_NEEDED=false

# agents.defaults.models[<provider/model>].agentRuntime：claude-cli 分支挂上，API 分支摘掉残留。
# 读写都只走 $OC —— 它按 OPENCLAW_STATE_DIR / OPENCLAW_CONFIG_PATH / $include 解析出的才是真配置，
# 自己去读 $OPENCLAW_JSON 会和它对不上。实测 OpenClaw 2026.9.6：
# - set --merge 递归合并，其他模型、该条目的其他键（alias/params…）原样保留；值没变时回 "No change"；
# - get 对字符串值原样输出一行，路径不存在时退出码 1；带 "/" 的模型名用 ["..."] 寻址。
# 补丁 JSON 交给 python 生成：模型名来自 .env，不拼进 shell 字符串；json.dumps 保持默认的
# ensure_ascii（纯 ASCII 输出，任何 locale 下都不会编码失败或被 Node 误读）。
# 用法：oc_model_runtime set|strip <provider/model>；set 写失败时返回非 0，strip 绝不中断安装。
oc_model_runtime() {
    local runtime_path="agents.defaults.models[\"$2\"].agentRuntime" current patch
    current="$($OC config get "$runtime_path.id" 2>/dev/null || true)"
    if [ "$1" = set ]; then
        [ "$current" = "claude-cli" ] && return 0      # 已经是了就不写
        patch="$(MR_MODEL="$2" python3 -c 'import json, os; print(json.dumps({os.environ["MR_MODEL"]: {"agentRuntime": {"id": "claude-cli"}}}))')"
        $OC config set agents.defaults.models "$patch" --strict-json --merge 2>&1 | sed '/^No change$/d'
    elif [ "$current" = "claude-cli" ]; then
        $OC config unset "$runtime_path" 2>&1 | sed '/^No change$/d' \
            || warn "没能摘掉 ${runtime_path}（不影响本次安装；残留时 agent 仍会走 Claude CLI）"
    fi
}

# Claude CLI 是否**明确**未登录（参数：配置目录，空 = 个人 ~/.claude）。判据与 easel doctor 一致：
# 只有解析出 loggedIn=false 才算；超时、起不来、老版本不认 --json、输出为空之类的都算拿不准，放行。
# 交给 python 跑是为了 20s 超时（macOS 没有 timeout(1)）。探测环境对齐 gateway：OpenClaw 拉起
# claude 前会删掉这几个认证变量（完整清单见 doctor.py 的 CLAUDE_CLI_CLEAR_ENV），shell 里导出的
# key 不能让这里误判成已登录。
claude_cli_logged_out() {
    CLI_PROBE_DIR="${1:-}" python3 -c '
import json, os, subprocess
drop = {"CLI_PROBE_DIR", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN"}
env = {k: v for k, v in os.environ.items() if k not in drop}
if os.environ.get("CLI_PROBE_DIR"):
    env["CLAUDE_CONFIG_DIR"] = os.environ["CLI_PROBE_DIR"]
try:
    proc = subprocess.run(["claude", "auth", "status", "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=20, env=env)
    status = json.loads(proc.stdout)
except (OSError, subprocess.SubprocessError, ValueError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(status, dict) and status.get("loggedIn") is False else 1)'
}

# 只认 claude-cli 一个值；拼错（如 claude）会悄悄落回下面的 API 路线，得说一声。
if [ -n "${EASEL_AGENT_RUNTIME:-}" ] && [ "${EASEL_AGENT_RUNTIME}" != "claude-cli" ]; then
    warn "EASEL_AGENT_RUNTIME=${EASEL_AGENT_RUNTIME} 不认识（目前只支持 claude-cli），按 .env 里的 API key 配置"
fi

STANDARD_LLM_CONFIGURED=false
# 仅当真正写了 anthropic provider 时，才补设它的 provider 级超时（见下方 timeoutSeconds）；
# 否则会给 OpenAI/MAAS 用户凭空造出一个只有 timeoutSeconds、缺 baseUrl/models 的残缺 anthropic provider。
ANTHROPIC_PROVIDER_SYNCED=false
# 下面 if 链里只要有一支写成了 provider 就算配好；仅 else（谁都没匹配上）会翻成 false。
AUTH_CONFIGURED=true
if usable_key "${ANTHROPIC_API_KEY:-}"; then
    STANDARD_LLM_CONFIGURED=true
elif usable_key "${EASEL_LLM_API_KEY:-}" && [ -n "${EASEL_LLM_BASE_URL:-}" ]; then
    STANDARD_LLM_CONFIGURED=true
elif usable_key "${OPENAI_API_KEY:-}"; then
    STANDARD_LLM_CONFIGURED=true
fi

# 「只配了 OpenAI」才走这支（Anthropic/EASEL_LLM 优先级更高）。判据必须是 usable_key
# 而非 -z，否则 .env.example 留下的占位符会一直把这支挡掉。
# EASEL_LLM 要连 BASE_URL 一起判：只填了 key 没填 URL 时它哪条分支都用不上，
# 不能让这种半拉配置把可用的 OPENAI 也一并挡死、最后落到「认证未配置」。
if [ "${EASEL_AGENT_RUNTIME:-}" = "claude-cli" ]; then
    # 显式选择，排第一：.env 里同时留着 API key 也以它为准；这条路线失败也不悄悄退回 API。
    # agent 跑在 OpenClaw 自带的 claude-cli runtime 上，复用本机 Claude Code 的登录，不写任何 provider。
    # 注意：变量后面紧跟中文时一律写 ${VAR}。bash 3.2（macOS 自带）在 UTF-8 locale 下会把全角字符的
    # 字节吞进变量名，set -u 当场报 unbound variable、整个安装中断（tests 里有静态检查）。
    CLAUDE_CLI_DEFAULT_MODEL="anthropic/claude-opus-5"   # = OpenClaw 2026.9.6 的 CLAUDE_CLI_DEFAULT_MODEL_REF
    CLI_MODEL="${CLAUDE_MODEL:-}"
    case "$CLI_MODEL" in
        "") CLI_MODEL="$CLAUDE_CLI_DEFAULT_MODEL" ;;
        anthropic/?*) ;;
        claude-cli/?*) CLI_MODEL="anthropic/${CLI_MODEL#claude-cli/}" ;;   # 老写法，OpenClaw 已改用 anthropic/ + agentRuntime
        */*|claude-) CLI_MODEL="" ;;                                       # 别家 provider：下面打回默认
        claude-?*) CLI_MODEL="anthropic/${CLI_MODEL}" ;;                   # 裸模型名，补上 provider
        *) CLI_MODEL="" ;;
    esac
    if [ -z "$CLI_MODEL" ]; then
        warn "CLAUDE_MODEL=${CLAUDE_MODEL:-} 不是 anthropic/<模型>，Claude CLI 路线改用默认 ${CLAUDE_CLI_DEFAULT_MODEL}"
        CLI_MODEL="$CLAUDE_CLI_DEFAULT_MODEL"
    fi
    # 默认给 agent 一份独立的 Claude Code 配置目录：共用个人 ~/.claude 时，里面的插件、hooks、
    # CLAUDE.md 会原样带进 agent（实际出过事：个人 hook 的输出混进了 agent 的回复）。
    # OpenClaw 把 env.vars 原样交给 claude、两边都不展开 ~ / $VAR，所以这里自己展开并要求绝对路径。
    CLI_DIR="${EASEL_CLAUDE_CONFIG_DIR:-}"
    CLI_DIR_OK=true
    case "$CLI_DIR" in
        "") CLI_DIR="$HOME/.claude-easel" ;;
        shared) CLI_DIR="" ;;                       # 不隔离：直接用个人 ~/.claude 的登录
        "~/"?*) CLI_DIR="$HOME/${CLI_DIR:2}" ;;
        /*) ;;
        *) CLI_DIR_OK=false ;;                      # 相对路径、~user/、单独一个 ~ 都不行
    esac
    while [ "${#CLI_DIR}" -gt 1 ] && [ "${CLI_DIR%/}" != "$CLI_DIR" ]; do
        CLI_DIR="${CLI_DIR%/}"                      # 末尾的 / 不算改目录，免得白白重启 gateway
    done
    # 整个家目录当 Claude Code 配置目录，会把 .claude.json 之类直接铺进 ~ 下
    if [ -n "$CLI_DIR" ] && [ "$CLI_DIR" = "${HOME%/}" ]; then
        CLI_DIR_OK=false
    fi
    if ! command -v claude >/dev/null 2>&1; then
        AUTH_CONFIGURED=false
        warn "EASEL_AGENT_RUNTIME=claude-cli，但 PATH 上找不到 claude（gateway 也是从 PATH 找它）"
        warn "  先安装 Claude Code（https://claude.com/claude-code），再重新运行 bash setup.sh"
    elif [ "$CLI_DIR_OK" = false ]; then
        AUTH_CONFIGURED=false
        warn "EASEL_CLAUDE_CONFIG_DIR=${EASEL_CLAUDE_CONFIG_DIR:-} 不能用：要绝对路径（或 ~/ 开头）且不能是家目录本身"
        warn "  相对路径会被当成 gateway 工作目录下的目录；改好（或填 shared）后重新运行 bash setup.sh"
    elif ! oc_model_runtime set "$CLI_MODEL"; then
        AUTH_CONFIGURED=false
        warn "没能把 ${CLI_MODEL} 设为 Claude CLI runtime（见上方 openclaw 报错；需要支持 config set --merge 与 agentRuntime 的 OpenClaw，已验证 2026.9.6）"
    else
        CLAUDE_CLI_ROUTE=true
        PREV_CLI_DIR="$($OC config get env.vars.CLAUDE_CONFIG_DIR 2>/dev/null || true)"
        while [ "${#PREV_CLI_DIR}" -gt 1 ] && [ "${PREV_CLI_DIR%/}" != "$PREV_CLI_DIR" ]; do
            PREV_CLI_DIR="${PREV_CLI_DIR%/}"
        done
        if [ "$CLI_DIR" != "$PREV_CLI_DIR" ]; then
            if [ -n "$CLI_DIR" ]; then
                $OC config set env.vars.CLAUDE_CONFIG_DIR "$CLI_DIR" 2>&1 | sed '/^No change$/d'
            else
                # 上面 get 读到了值才会走到这里；万一路径已经不在，unset 退出码非 0 也不能掐断安装
                $OC config unset env.vars.CLAUDE_CONFIG_DIR 2>&1 | sed '/^No change$/d' || true
            fi
            # env.vars 只在 gateway 进程启动时注入（openclaw 自己也提示 "Restart the gateway to apply"）；
            # 已有会话还绑着旧目录下的 Claude 会话，续聊会报 "Claude Code process exited with code 1"，
            # 直到 /reset（本机实测）。
            GATEWAY_RESTART_NEEDED=true
            warn "Claude Code 配置目录改为 ${CLI_DIR:-个人 ~/.claude}，gateway 会重启以生效"
            warn "  若之前已在用 Claude CLI 路线：旧对话绑定的是原目录的会话，请在对话里 /reset 或新开会话"
        fi
        # OpenClaw 让内联的 env.CLAUDE_CONFIG_DIR 盖过 env.vars（同名时后处理）
        INLINE_CLI_DIR="$($OC config get env.CLAUDE_CONFIG_DIR 2>/dev/null || true)"
        if [ -n "$INLINE_CLI_DIR" ] && [ "$INLINE_CLI_DIR" != "$CLI_DIR" ]; then
            warn "openclaw.json 里还有内联的 env.CLAUDE_CONFIG_DIR=${INLINE_CLI_DIR}，它优先于上面的设置"
            warn "  删掉它：openclaw --profile ${PROFILE:-easel} config unset env.CLAUDE_CONFIG_DIR"
        fi
        # OpenClaw 只在 gateway 进程环境**没有**这个变量时才用 env.vars 补上；只有导出的才会被继承
        SHELL_CLI_DIR="$(printenv CLAUDE_CONFIG_DIR || true)"
        if [ -n "$SHELL_CLI_DIR" ] && [ "$SHELL_CLI_DIR" != "$CLI_DIR" ]; then
            warn "当前 shell 导出了 CLAUDE_CONFIG_DIR=${SHELL_CLI_DIR}：从这里起的 gateway 会用它、盖过上面的配置"
        fi
        CLI_LOGIN_CMD="claude auth login"
        if [ -n "$CLI_DIR" ]; then
            CLI_LOGIN_CMD="CLAUDE_CONFIG_DIR=$(printf '%q' "$CLI_DIR") claude auth login"
        fi
        if claude_cli_logged_out "$CLI_DIR"; then
            if [ -t 0 ]; then
                info "Claude CLI 尚未登录（${CLI_DIR:-个人 ~/.claude}），开始登录..."
                env -u CLAUDE_CONFIG_DIR ${CLI_DIR:+"CLAUDE_CONFIG_DIR=$CLI_DIR"} claude auth login || true
            fi
            # 没登录不回滚配置：配置本身是对的，登录补上即可；easel doctor 也会继续标出来
            if claude_cli_logged_out "$CLI_DIR"; then
                warn "Claude CLI 未登录，agent 暂时用不了：运行 ${CLI_LOGIN_CMD}"
            fi
        fi
        # OpenClaw 续聊前到 ~/.claude/projects/<工作区> 找上一轮的会话文件、不看 CLAUDE_CONFIG_DIR：
        # 隔离目录下不软链过去，隔一会儿再追问就会丢上下文（见 easel/claude_cli_link.py）
        if [ -n "$CLI_DIR" ]; then
            if LINK_MSG="$(PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m easel.claude_cli_link --config-dir "$CLI_DIR" 2>&1)"; then
                info "${LINK_MSG}"
            else
                warn "续聊软链没建成：${LINK_MSG}"
                warn "  处理后运行 python -m easel.claude_cli_link；不处理的话，隔一会儿再追问会丢上下文"
            fi
        fi
        DEFAULT_PRIMARY_MODEL="$CLI_MODEL"
        CLAUDE_MODEL="$CLI_MODEL"
        ok "Claude CLI 路线已配置：${CLI_MODEL}（Claude Code 配置目录：${CLI_DIR:-个人 ~/.claude}）"
    fi
elif usable_key "${OPENAI_API_KEY:-}" && ! usable_key "${ANTHROPIC_API_KEY:-}" \
   && ! { usable_key "${EASEL_LLM_API_KEY:-}" && [ -n "${EASEL_LLM_BASE_URL:-}" ]; }; then
    OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o}"
    $OC config set models.providers.openai.api "openai-completions" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers.openai.apiKey "$OPENAI_API_KEY" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers.openai.baseUrl "${OPENAI_BASE_URL:-https://api.openai.com/v1}" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers.openai.models \
        "[{\"id\":\"$OPENAI_MODEL\",\"name\":\"OpenAI model\",\"reasoning\":true,\"input\":[\"text\",\"image\"]}]" \
        --strict-json 2>&1 | sed '/^No change$/d'
    DEFAULT_PRIMARY_MODEL="openai/$OPENAI_MODEL"
    CLAUDE_MODEL="$DEFAULT_PRIMARY_MODEL"
    ok "OpenAI 服务认证已同步"
elif [ "$STANDARD_LLM_CONFIGURED" = false ] && usable_key "${OPENAI_MAAS_API_KEY:-}"; then
    OPENAI_PROVIDER="rednote-openai"
    OPENAI_MODEL="${OPENAI_MAAS_MODEL:-gpt-5.5}"
    OPENAI_PORT="${OPENAI_MAAS_ADAPTER_PORT:-18791}"
    OPENAI_ENDPOINT="${OPENAI_MAAS_ENDPOINT:?OPENAI_MAAS_ENDPOINT is required}"
    # A new custom provider must be written atomically or OpenClaw rejects the incomplete intermediate state.
    OPENAI_PROVIDER_CONFIG=$(python3 - "$PROJECT_ROOT" "$OPENAI_PORT" "$OPENAI_MODEL" \
        "$OPENAI_ENDPOINT" "$OPENAI_MAAS_API_KEY" "${OPENAI_MAAS_API_KEY_HEADER:-Authorization}" <<'PY'
import json
import sys

root, port, model, endpoint, api_key, api_key_header = sys.argv[1:]
print(json.dumps({
    "baseUrl": f"http://127.0.0.1:{port}/v1",
    "api": "openai-completions",
    "apiKey": "local-adapter",
    "timeoutSeconds": 600,
    "request": {"allowPrivateNetwork": True},
    "models": [{
        "id": model,
        "name": "OpenAI-compatible model",
        "reasoning": True,
        "input": ["text"],
    }],
    "localService": {
        "command": "/usr/bin/python3",
        "args": [f"{root}/scripts/openai_maas_adapter.py", "--port", port],
        "cwd": root,
        "healthUrl": f"http://127.0.0.1:{port}/health",
        "idleStopMs": 0,
        "env": {
            "OPENAI_MAAS_API_KEY": api_key,
            "OPENAI_MAAS_ENDPOINT": endpoint,
            "OPENAI_MAAS_MODEL": model,
            "OPENAI_MAAS_API_KEY_HEADER": api_key_header,
        },
    },
}))
PY
)
    $OC config set models.providers."$OPENAI_PROVIDER" "$OPENAI_PROVIDER_CONFIG" \
        --strict-json 2>&1 | sed '/^No change$/d'
    DEFAULT_PRIMARY_MODEL="$OPENAI_PROVIDER/$OPENAI_MODEL"
    CLAUDE_MODEL="$DEFAULT_PRIMARY_MODEL"
    ok "OpenAI-compatible 服务已通过本地适配器同步"
elif [ "$STANDARD_LLM_CONFIGURED" = false ] && usable_key "${GEMINI_MAAS_API_KEY:-}"; then
    GEMINI_PROVIDER="rednote-gemini"
    GEMINI_MODEL="${GEMINI_MAAS_MODEL:-gemini-3.1-pro-preview}"
    $OC config set models.providers."$GEMINI_PROVIDER".baseUrl \
        "http://127.0.0.1:${GEMINI_ADAPTER_PORT:-18790}/v1" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".api "openai-completions" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".apiKey "local-adapter" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".models \
        "[{\"id\":\"$GEMINI_MODEL\",\"name\":\"Gemini-compatible model\",\"reasoning\":true,\"input\":[\"text\",\"image\"],\"contextWindow\":1048576,\"maxTokens\":65535}]" \
        --strict-json 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".timeoutSeconds 600 --strict-json 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".request.allowPrivateNetwork true --strict-json 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.command "/usr/bin/python3" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.args \
        "[\"$PROJECT_ROOT/scripts/gemini_maas_adapter.py\",\"--port\",\"${GEMINI_ADAPTER_PORT:-18790}\"]" \
        --strict-json 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.cwd "$PROJECT_ROOT" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.healthUrl \
        "http://127.0.0.1:${GEMINI_ADAPTER_PORT:-18790}/health" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.idleStopMs 0 --strict-json 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.env.GEMINI_MAAS_API_KEY \
        "$GEMINI_MAAS_API_KEY" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.env.GEMINI_MAAS_ENDPOINT \
        "${GEMINI_MAAS_ENDPOINT:?GEMINI_MAAS_ENDPOINT is required}" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.env.GEMINI_MAAS_MODEL \
        "$GEMINI_MODEL" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.env.GEMINI_THINKING_LEVEL \
        "${GEMINI_THINKING_LEVEL:-HIGH}" 2>&1 | sed '/^No change$/d'
    $OC config set models.providers."$GEMINI_PROVIDER".localService.env.GEMINI_INCLUDE_THOUGHTS \
        "${GEMINI_INCLUDE_THOUGHTS:-true}" 2>&1 | sed '/^No change$/d'
    DEFAULT_PRIMARY_MODEL="$GEMINI_PROVIDER/$GEMINI_MODEL"
    CLAUDE_MODEL="$DEFAULT_PRIMARY_MODEL"
    ok "Gemini-compatible 服务已通过本地适配器同步"
elif usable_key "${EASEL_LLM_API_KEY:-}" && [ -n "${EASEL_LLM_BASE_URL:-}" ]; then
    # 原子写入整块 provider（含 header 与 anthropic-version）；整块替换会顺带清掉旧的 CodeWiz 专用 header。
    oc_write_anthropic "$EASEL_LLM_BASE_URL" "$EASEL_LLM_API_KEY" \
        "${EASEL_LLM_API_KEY_HEADER:-api-key}" "${EASEL_LLM_ANTHROPIC_VERSION:-2023-06-01}"
    ANTHROPIC_PROVIDER_SYNCED=true
    ok "自定义 Anthropic 兼容 MaaS 认证已同步"
elif usable_key "${ANTHROPIC_AUTH_TOKEN:-}" && [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
    oc_write_anthropic "$ANTHROPIC_BASE_URL" "$ANTHROPIC_AUTH_TOKEN"
    ANTHROPIC_PROVIDER_SYNCED=true
    ok "Anthropic 兼容服务认证已同步"
elif usable_key "${ANTHROPIC_API_KEY:-}"; then
    # 官方 ANTHROPIC_API_KEY 可搭配 ANTHROPIC_BASE_URL 指向自定义代理/网关；未指定时显式指向官方端点，
    # 否则请求会发往默认的 api.anthropic.com，代理网络下会直接超时。provider 由 oc_write_anthropic 原子写入。
    oc_write_anthropic "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}" "$ANTHROPIC_API_KEY"
    ANTHROPIC_PROVIDER_SYNCED=true
    if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
        ok "API key + 自定义 Anthropic Base URL 已同步"
    else
        ok "API key 已同步"
    fi
else
    AUTH_CONFIGURED=false
    warn "认证未配置：.env 里没有可用的 API key（占位符 REPLACE_ME 不算）"
    warn "  编辑 $PROJECT_ROOT/.env 填入真实 key 后，重新运行 bash setup.sh"
fi

# ---- 10. OpenClaw agent 模型 + 超时 ----
# CLAUDE_MODEL 保留旧变量名以兼容现有环境，值必须是 OpenClaw 的 provider/model。
# 不要填内部 proxy 映射名（如 claude-4.6-opus-google），否则 OpenClaw 不认识。
if [ "$AUTH_CONFIGURED" = true ]; then
    PRIMARY_MODEL="${CLAUDE_MODEL:-$DEFAULT_PRIMARY_MODEL}"
    # 从 Claude CLI 换回 API 路线、模型名又没变时，残留的模型级 agentRuntime=claude-cli 会让 agent
    # 悄悄继续走 Claude CLI（它优先于 provider）。只摘 claude-cli 这一种、只动这一个模型。
    if [ "$CLAUDE_CLI_ROUTE" = false ]; then
        oc_model_runtime strip "$PRIMARY_MODEL"
    fi
    $OC config set agents.defaults.model.primary "$PRIMARY_MODEL" 2>&1 | sed '/^No change$/d'
else
    # 上面一个 provider 都没写。这时还去写 primary 只会把 agent 指向一个不存在的
    # provider（CLAUDE_MODEL 直接来自 .env），对话时报 "No route-compatible
    # authentication source is configured for <provider>" —— 比「没配置」更难查。
    # 保持不动：既不造假配置，也不覆盖用户上一次跑成功时留下的可用 primary。
    warn "未写入 agents.defaults.model.primary；openclaw 中已有的模型设置保持不变"
fi
# 整个 agent run 的总时长上限。制作层任务（OpenClaw 自执行短剧/长稿/多镜）很久 → 给足。
$OC config set agents.defaults.timeoutSeconds 7200 2>&1 | sed '/^No change$/d'
# Easel 使用 profiles/<当前画像>/memory.md；关闭 OpenClaw 全局记忆索引，避免旧索引跨画像召回。
# Easel 使用 profiles/<当前画像>/memory.md；向量记忆必须使用单独的 embedding API。
# 否则 OpenClaw 会默认请求 text-embedding-3-small，很多聊天 MaaS 并不提供该模型。
EMBEDDING_API_KEY="${EASEL_EMBEDDING_API_KEY:-${EASEL_EMBEDDINGS_API_KEY:-${OPENAI_EMBEDDING_API_KEY:-${EMBEDDING_API_KEY:-${EMBEDDINGS_API_KEY:-}}}}}"
EMBEDDING_BASE_URL="${EASEL_EMBEDDING_BASE_URL:-${EASEL_EMBEDDINGS_BASE_URL:-${OPENAI_EMBEDDING_BASE_URL:-${EMBEDDING_BASE_URL:-${EMBEDDINGS_BASE_URL:-}}}}}"
EMBEDDING_MODEL="${EASEL_EMBEDDING_MODEL:-${EASEL_EMBEDDINGS_MODEL:-${OPENAI_EMBEDDING_MODEL:-${EMBEDDING_MODEL:-${EMBEDDINGS_MODEL:-}}}}}"
# 记忆检索配置的 schema 位置随 OpenClaw 版本变化：2026.9.x 起挪到顶层 memory.search.*，
# 之前（<=2026.6.x）在 agents.defaults.memorySearch.*。两者互斥（各自把对方的 key 判为 Unrecognized）。
# 用「先试新 key、失败再退老 key」自适应：第一条写入既是真实配置也是版本探测（失败输出静默）。
if [ -n "$EMBEDDING_API_KEY" ] && [ -n "$EMBEDDING_BASE_URL" ] && [ -n "$EMBEDDING_MODEL" ]; then
    if $OC config set memory.search.provider openai-compatible >/dev/null 2>&1; then
        # 新 schema：顶层 memory.search（OpenClaw 2026.9.x+）
        $OC config set memory.search.enabled true --strict-json 2>&1 | sed '/^No change$/d'
        $OC config set memory.search.model "$EMBEDDING_MODEL" 2>&1 | sed '/^No change$/d'
        $OC config set memory.search.remote.baseUrl "$EMBEDDING_BASE_URL" 2>&1 | sed '/^No change$/d'
        $OC config set memory.search.remote.apiKey "$EMBEDDING_API_KEY" 2>&1 | sed '/^No change$/d'
        ok "独立向量模型已配置（memory.search）：$EMBEDDING_MODEL"
    else
        # 老 schema：agents.defaults.memorySearch（OpenClaw <=2026.6.x）
        $OC config set agents.defaults.memorySearch.provider openai-compatible 2>&1 | sed '/^No change$/d'
        $OC config set agents.defaults.memorySearch.model "$EMBEDDING_MODEL" 2>&1 | sed '/^No change$/d'
        $OC config set agents.defaults.memorySearch.remote.baseUrl "$EMBEDDING_BASE_URL" 2>&1 | sed '/^No change$/d'
        $OC config set agents.defaults.memorySearch.remote.apiKey "$EMBEDDING_API_KEY" 2>&1 | sed '/^No change$/d'
        ok "独立向量模型已配置（memorySearch）：$EMBEDDING_MODEL"
    fi
else
    # Deliberate FTS-only mode: never fall back to the chat endpoint for embeddings.
    # 新 schema 用 memory.search.enabled=false 关闭向量检索；老 schema 用 provider=none。
    if $OC config set memory.search.enabled false --strict-json >/dev/null 2>&1; then
        :
    else
        $OC config set agents.defaults.memorySearch.provider none 2>&1 | sed '/^No change$/d'
    fi
    if [ -n "$EMBEDDING_API_KEY$EMBEDDING_BASE_URL$EMBEDDING_MODEL" ]; then
        warn "向量 API 配置不完整，已关闭向量检索；需要同时设置 EASEL_EMBEDDING_API_KEY、EASEL_EMBEDDING_BASE_URL、EASEL_EMBEDDING_MODEL"
    else
        info "未配置独立向量 API，使用关键词记忆检索（不会请求 text-embedding-3-small）"
    fi
fi
# 单次 LLM 请求的「空闲超时」（等模型开始/继续产出 token 的最长时间）。内部网关对大上下文/带思考的
# 请求首 token 可能较慢，不设会用默认较短值 → 报「model did not produce a response before the model
# idle timeout」而中断整个 run。与 agents.defaults.timeoutSeconds 是两回事，provider 超时不能延长整个 run。
# 尽力而为：老版本 OpenClaw（如 2026.3.x）的 provider schema 不认识 timeoutSeconds，会报 Unrecognized key
# 并拒绝该次写入。这里吞掉这条噪音、绝不让它中断安装（|| true）；新版本 OpenClaw 才会真正把它调到 600s。
# 想彻底拿到更长的 provider 超时，请 npm i -g openclaw@latest 升级到支持该字段的版本。
if [ "$ANTHROPIC_PROVIDER_SYNCED" = true ]; then
    $OC config set models.providers.anthropic.timeoutSeconds 600 2>&1 \
        | sed -e '/^No change$/d' -e '/[Uu]nrecognized key/d' -e '/timeoutSeconds/d' || true
fi
$OC config set gateway.mode local 2>&1 | sed '/^No change$/d'
$OC config set gateway.bind loopback 2>&1 | sed '/^No change$/d'
$OC config set gateway.auth.mode none 2>&1 | sed '/^No change$/d'
# 对话直连常驻网关（web/app.py 的 http 传输层）要用 OpenAI 兼容端点，而 openclaw 默认
# 不挂这条路由（chatCompletions.enabled 默认 false），不开的话 POST /v1/chat/completions
# 一律 404、只能退回每轮 spawn 客户端的老路径。端点只绑 loopback + auth.mode=none 的本机
# 网关，不额外扩暴露面。旧版本没这个键时会报 Unrecognized key，吞掉即可（照常走 cli）。
$OC config set gateway.http.endpoints.chatCompletions.enabled true --strict-json 2>&1 \
    | sed -e '/^No change$/d' -e '/[Uu]nrecognized key/d' || true

# Refuse to start with a config rejected by the installed OpenClaw version.
# This catches schema changes early instead of producing opaque Gateway errors.
if ! $OC config validate; then
    echo "OpenClaw 配置校验失败：请检查上方报错，并确认使用受支持的 OpenClaw 版本。" >&2
    exit 1
fi
ok "OpenClaw 配置校验通过"

# ---- 11. 启动 gateway ----
step "8/8" "启动并验证" "配置校验 · Chromium · Gateway health"
info "启动 Easel gateway..."
# env.vars 只在 gateway 进程启动时注入，而 gateway.sh start 见到网关活着就直接退出 ——
# 上面改了 Claude Code 配置目录时不 restart，新目录就永远不生效。
if [ "$GATEWAY_RESTART_NEEDED" = true ]; then
    bash "$PROJECT_ROOT/scripts/gateway.sh" restart
else
    bash "$PROJECT_ROOT/scripts/gateway.sh" start
fi

# Playwright is a runtime dependency for browser login/publishing.
if python3 -c 'import playwright' >/dev/null 2>&1; then
    if ! python3 -m playwright install chromium; then
        echo "Chromium 安装失败；请手动运行 python3 -m playwright install chromium 后重试。" >&2
        exit 1
    fi
    if ! python3 -c 'from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); path=Path(p.chromium.executable_path); p.stop(); raise SystemExit(0 if path.is_file() else 1)'; then
        echo "未找到已安装的 Chromium；请检查 Playwright 安装后重试。" >&2
        exit 1
    fi
    ok "Playwright Chromium 已就绪"
else
    echo "未找到 Playwright；Python 依赖安装不完整，无法继续。" >&2
    exit 1
fi

echo -e "\n${GREEN}╭────────────────────────────────────────────────────╮${NC}"
echo -e "${GREEN}│${NC}  ${GREEN}✓ Easel 安装完成${NC}                              ${GREEN}│${NC}"
echo -e "${GREEN}╰────────────────────────────────────────────────────╯${NC}"
echo -e "\n  ${CYAN}开始使用：${NC}"
if [ -x "$PROJECT_ROOT/.venv/bin/easel" ]; then
    echo -e "    ${CYAN}source .venv/bin/activate${NC}    # 先激活虚拟环境，easel 命令才可用"
    echo -e "    ${DIM}# 新开终端都要先激活；或不激活直接用 .venv/bin/easel <命令>${NC}"
fi
echo "    easel web                    # 启动 Web 工作台"
echo "    easel chat                   # 终端对话"
echo "    easel doctor                 # 检查环境"
echo "    easel ping                   # Gateway 连通性"
echo -e "\n  ${DIM}Easel profile：~/.openclaw-${PROFILE}/${NC}"
echo -e "  ${DIM}项目目录：$PROJECT_ROOT${NC}\n"
