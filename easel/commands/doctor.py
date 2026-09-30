"""easel doctor — 检查开发环境是否就绪。"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from easel.gateway_endpoint import healthz_url, port_source, resolve_gateway_port
from easel.openclaw_cmd import openclaw_base_cmd

# 项目根目录（Easel/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# OpenClaw 已验证的稳定下限（= 我们实测跑通过的最老版本）。低于它会命中 anthropic provider 必须
# 原子写入、models.providers.*.timeoutSeconds 被判 Unrecognized key 等破坏性变更（见 issue #9/#11）。
#
# 别拿「记忆检索 memory.search.*」当抬高下限的理由：2026.6.11 **没有** memory.search（实测
# `config set memory.search.…` 报 Unrecognized key），那是 2026.9.x 才有的 schema，setup.sh:613
# 已经按「先试新的、失败退回 agents.defaults.memorySearch」探测处理，不需要版本下限兜。
MIN_OPENCLAW = (2026, 6, 11)

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
NC = "\033[0m"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = f"{GREEN}OK{NC}" if ok else f"{RED}FAIL{NC}"
    print(f"  {label:<40s} {status}")
    if not ok and detail:
        print(f"    └─ {detail}")
    return ok


def _node_version_ok(strict: bool) -> bool:
    """检查 Node.js 版本。

    strict=True 对齐 openclaw@latest（2026.9.x）的引擎：>=24.16.0 <25 || >=26.1.0（25.x/26.0 被排除）。
    strict=False 用于已装较旧 OpenClaw（我们支持的下限 2026.6.11）。**下限是 22.19**，不是 20.10：
    实测 openclaw@2026.6.11 的 package.json engines 就是 `">=22.19.0"`，且其 openclaw.mjs 里还有
    一道硬运行时检查（MIN_NODE_MAJOR=22 / MIN_NODE_MINOR=19，不满足直接 process.exit(1)）。
    写 20.10 的后果是：Node 20.10–22.18 上 doctor 报绿，而每一条 openclaw 命令都起不来。
    """
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        # e.g. "v24.21.0"
        m = re.match(r"v(\d+)\.(\d+)", result.stdout.strip())
        if not m:
            return False
        major, minor = int(m.group(1)), int(m.group(2))
        if strict:
            return (major == 24 and minor >= 16) or (major == 26 and minor >= 1) or major >= 27
        return (major, minor) >= (22, 19)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _openclaw_version() -> tuple[int, int, int] | None:
    """解析 `openclaw --version`，返回 (year, month, patch)；无法确定时返回 None。"""
    try:
        # 不能裸调 ["openclaw", ...]：Windows 上它是 npm 装的 `.cmd` shim，
        # CreateProcess 不按 PATHEXT 解析、裸名找不到文件 → FileNotFoundError
        # → 版本被误判「未知」。统一走 openclaw_cmd 的解析（Windows 上解析为
        # node + openclaw.mjs，Unix 上为直接可执行路径）。
        result = subprocess.run(
            openclaw_base_cmd() + ["--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        # e.g. "OpenClaw 2026.9.4 (3a9d69d)"
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _python_version_ok() -> bool:
    import sys
    return sys.version_info >= (3, 10)


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _venv_available() -> bool:
    return _module_available("venv")


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    except (ImportError, OSError, RuntimeError):
        return False


def _gateway_healthy() -> bool:
    """Check OpenClaw gateway is running via healthz endpoint.

    端口走 easel/gateway_endpoint.py：非默认 profile（Easel 的 ``--profile easel``）
    不是 18789，写死就会「gateway 活着、doctor 报 FAIL」。
    """
    try:
        with urllib.request.urlopen(healthz_url(), timeout=5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _skills_synced() -> tuple[bool, str]:
    """检查 agent 真正读取的那个 workspace 里有没有 skills。

    这里的目标目录**不能**硬编码：OpenClaw 的默认布局在 2026.6.x / 2026.9.x 之间变过
    （见 easel/openclaw_workspace.py）。以前这里写死了旧布局，而 sync.sh 写的是新布局，
    于是同步脚本报 "synced"、doctor 报绿，agent 却读不到任何技能（issue #19）。
    """
    from easel.openclaw_workspace import workspace_dir

    ws = workspace_dir()
    skills_dir = ws / "skills"
    try:
        ok = skills_dir.is_dir() and any(skills_dir.iterdir())
    except OSError:
        ok = False
    return ok, f"agent 实际读取的 workspace 是 {ws}，其中 skills/ 为空或不存在"


def _env_key_valid() -> bool:
    """Check .env 配置了可用的认证。

    以下任一通道满足即可：
    - 标准 API key：ANTHROPIC_API_KEY
    - Anthropic-compatible 服务：EASEL_LLM_API_KEY + EASEL_LLM_BASE_URL

    ping 才是权威连通性测试；这里只做静态配置存在性检查。
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return False

    # 认证变量 → 是否已填入非占位值
    auth_vars: dict[str, str] = {}
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key in (
                "ANTHROPIC_API_KEY", "EASEL_LLM_API_KEY", "EASEL_LLM_BASE_URL",
                "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "OPENAI_API_KEY", "OPENAI_BASE_URL",
                "OPENAI_MAAS_API_KEY", "OPENAI_MAAS_ENDPOINT",
            ):
                auth_vars[key] = value
    except OSError:
        return False

    def _set(name: str) -> bool:
        v = auth_vars.get(name, "")
        return bool(v) and "REPLACE_ME" not in v

    # 标准 key 通道
    if _set("ANTHROPIC_API_KEY"):
        return True
    # Anthropic-compatible 服务：key + base_url 同时配好
    if _set("EASEL_LLM_API_KEY") and _set("EASEL_LLM_BASE_URL"):
        return True
    if _set("ANTHROPIC_AUTH_TOKEN") and _set("ANTHROPIC_BASE_URL"):
        return True
    if _set("OPENAI_API_KEY"):
        return True
    if _set("OPENAI_MAAS_API_KEY") and _set("OPENAI_MAAS_ENDPOINT"):
        return True
    return False


def _openclaw_config_path() -> Path:
    """easel 用独立 profile，不碰用户本机的 OpenClaw 配置；路径走 openclaw_workspace 的唯一真相。"""
    from easel.openclaw_workspace import config_path
    return config_path()


CLAUDE_CLI_RUNTIME = "claude-cli"

# OpenClaw 拉起 Claude CLI 子进程前从环境里删掉的变量，原样抄自 OpenClaw 2026.9.6
# dist/cli-constants-0f4y8Jm6.mjs 的 CLAUDE_CLI_CLEAR_ENV（约 453 行），升级 OpenClaw 时对一下。
# 探测登录态时必须照删：doctor 所在 shell 里导出的 ANTHROPIC_API_KEY / OAuth token 会让
# `claude auth status` 报已登录，而 gateway 里的 claude 根本拿不到它们 —— 不删就是假 PASS。
# 这份清单**不含** CLAUDE_CONFIG_DIR（实测 gateway 的 claude 会话落在 env.vars 指定的目录），
# 它由 _claude_config_dir 单独解析。
CLAUDE_CLI_CLEAR_ENV = frozenset({
    "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_OLD", "ANTHROPIC_API_TOKEN", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_OAUTH_TOKEN", "ANTHROPIC_UNIX_SOCKET",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_DISABLE_1M_CONTEXT",
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "MAX_THINKING_TOKENS",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR", "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "CLAUDE_CODE_PLUGIN_CACHE_DIR",
    "CLAUDE_CODE_PLUGIN_SEED_DIR", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_USE_COWORK_PLUGINS",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_USE_VERTEX",
    "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_HEADERS", "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
    "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_HEADERS", "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
    "OTEL_LOGS_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_SDK_DISABLED", "OTEL_TRACES_EXPORTER",
})

# openclaw.json 的 env 条目里带 ${NAME} 引用的，OpenClaw 整条不注入进程环境（$${NAME} 是转义，
# 不算）—— 见 2026.9.6 dist/config-env-vars-BHI12YH5.mjs 的 isConfigRuntimeEnvVarAllowed。
_ENV_SUBSTITUTION_RE = re.compile(r"(?<!\$)\$\{[A-Z_][A-Z0-9_]*\}")


def _runtime_id_of(entry: object) -> str | None:
    runtime = entry.get("agentRuntime") if isinstance(entry, dict) else None
    rid = runtime.get("id") if isinstance(runtime, dict) else None
    return rid.strip() if isinstance(rid, str) and rid.strip() else None


def _agent_runtime_id(cfg: dict) -> str | None:
    """primary 实际跑在哪个 agent runtime 上，选择顺序与 OpenClaw 一致：

    1. 模型级：agents.defaults.models["<provider/model>"].agentRuntime.id
    2. 供应商级：models.providers.<provider>.agentRuntime.id
    3. 老写法：primary 写成 "claude-cli/<model>" 本身就是 Claude CLI runtime

    都没有返回 None，即常规的 provider 路由（按 models.providers 里的认证走）。
    """
    agents = cfg.get("agents") if isinstance(cfg.get("agents"), dict) else {}
    defaults = agents.get("defaults") if isinstance(agents.get("defaults"), dict) else {}
    model = defaults.get("model") if isinstance(defaults.get("model"), dict) else {}
    primary = model.get("primary")
    if not isinstance(primary, str) or not primary:
        return None
    per_model = defaults.get("models") if isinstance(defaults.get("models"), dict) else {}
    rid = _runtime_id_of(per_model.get(primary))
    if rid or "/" not in primary:
        return rid
    provider = primary.split("/", 1)[0]
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    providers = models.get("providers") if isinstance(models.get("providers"), dict) else {}
    rid = _runtime_id_of(providers.get(provider))
    if rid:
        return rid
    return CLAUDE_CLI_RUNTIME if provider == CLAUDE_CLI_RUNTIME else None


def _uses_claude_cli() -> bool:
    """primary 是否走 Claude CLI runtime。配置读不出来就当不是 —— 那种情况由 model routing 那条报。"""
    try:
        cfg = json.loads(_openclaw_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(cfg, dict) and _agent_runtime_id(cfg) == CLAUDE_CLI_RUNTIME


def _claude_config_dir(cfg: dict) -> tuple[str, str]:
    """gateway 里的 claude 实际拿到的 CLAUDE_CONFIG_DIR，返回 (值, 来源)；没有就是 ("", "")。

    照 OpenClaw 2026.9.6 把配置注入进程环境的规则（dist/config-env-vars-BHI12YH5.mjs）：
    - 进程环境里已有非空白值就用它，配置不覆盖；
    - 否则取 openclaw.json 的 env 块。内联的 env.CLAUDE_CONFIG_DIR 在 env.vars 之后处理、
      同名时盖掉后者；空白值、带 ${NAME} 引用的值整条不注入；
    - 值**原样**传下去：OpenClaw 不展开 ~ / $VAR，claude 也不展开（Claude Code 2.1.285 实测
      CLAUDE_CONFIG_DIR='~/x' 会在当前目录下建出字面的 `~/x`）。所以这里也不展开。
    """
    process_value = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if process_value.strip():
        return process_value, "进程环境的 CLAUDE_CONFIG_DIR"
    env_block = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
    env_vars = env_block.get("vars") if isinstance(env_block.get("vars"), dict) else {}
    for value, source in ((env_block.get("CLAUDE_CONFIG_DIR"), "openclaw.json 的 env.CLAUDE_CONFIG_DIR"),
                          (env_vars.get("CLAUDE_CONFIG_DIR"), "openclaw.json 的 env.vars.CLAUDE_CONFIG_DIR")):
        if isinstance(value, str) and value.strip() and not _ENV_SUBSTITUTION_RE.search(value):
            return value, source
    return "", ""


def _claude_login_cmd(config_dir: str, os_name: str | None = None) -> str:
    """可直接粘贴的登录命令。带上 gateway 用的配置目录，否则登进去的是另一份登录态。"""
    if not config_dir:
        return "claude auth login"
    if (os_name or os.name) == "nt":
        # PowerShell 单引号串不做任何展开，内部的 ' 写成 ''
        quoted = config_dir.replace("'", "''")
        return f"$env:CLAUDE_CONFIG_DIR='{quoted}'; claude auth login"
    return f"CLAUDE_CONFIG_DIR={shlex.quote(config_dir)} claude auth login"


def _claude_cli_ready(cfg: dict) -> tuple[bool, str]:
    """Claude CLI runtime 的就绪检查：gateway 直接 spawn PATH 上的 `claude`，复用它的登录态。

    这条路线不经过 models.providers，也不需要任何 API Key，所以按 provider 认证去查只会报
    假 FAIL；真正会让对话失败的是「找不到 claude」和「claude 没登录」这两件事。
    只认 PATH 上的 claude：2026.9 起 cliBackends 的启动细节归插件管，gateway/cli-backends.md
    明确不让写进 openclaw.json，这里不去解析 command 覆盖。
    """
    claude = shutil.which("claude")
    if not claude:
        return False, ("primary 走 Claude CLI runtime，但 PATH 上找不到 claude —— "
                       "先安装 Claude Code，并确保 claude 在 PATH 上（gateway 也是从 PATH 找它）")

    # 探测用的环境要和 gateway 给 claude 的一致：先删 OpenClaw 会删的认证/传输变量，
    # 再把 CLAUDE_CONFIG_DIR 换成 gateway 那边实际生效的值，查的才是 gateway 那份登录态。
    config_dir, source = _claude_config_dir(cfg)
    if config_dir and not os.path.isabs(config_dir):
        # 相对路径会按 gateway 的工作目录解析，doctor 这边复现不了；照原样拿去探测还会在
        # 当前目录建出字面的 `~` 之类的目录。这是确定的配置错误，不是「拿不准」。
        return False, (f"{source} 是 {config_dir!r}，不是绝对路径 —— OpenClaw 原样传给 claude，"
                       "两边都不展开 ~ / $VAR，实际会落到 gateway 工作目录下；改成绝对路径")
    env = {k: v for k, v in os.environ.items() if k not in CLAUDE_CLI_CLEAR_ENV}
    env.pop("CLAUDE_CONFIG_DIR", None)
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = config_dir

    try:
        proc = subprocess.run(
            [claude, "auth", "status", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, env=env,
        )
        status = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return True, ""  # 超时 / 起不来 / 输出不是 JSON：拿不准，放行，交给 `easel ping`
    # 只认明确的 loggedIn=false（实测未登录：退出码 1 + {"loggedIn": false, ...}）。
    # 退出码本身不作数：老版本不认 --json、输出为空之类的都算拿不准。
    if isinstance(status, dict) and status.get("loggedIn") is False:
        return False, f"Claude CLI 未登录 —— 运行 {_claude_login_cmd(config_dir)}"
    return True, ""


def _primary_model_routable() -> tuple[bool, str]:
    """检查 agents.defaults.model.primary 指向的 provider 在 openclaw 里真的配了认证。

    上面的 `.env (API Key)` 只查 .env 静态有没有填值，查不出 setup 有没有真把 provider
    写进 openclaw.json。两边脱节时（例如认证判定被占位符卡住、provider 一个字没写却照样
    设了 primary），doctor 会全绿而对话直接报
    "No route-compatible authentication source is configured for <provider>"。
    这条就是补上 openclaw 侧的对账。primary 走 Claude CLI runtime 时不需要 provider，
    改查 claude 在不在、登没登录（见 _claude_cli_ready）。

    返回 (是否可路由, 失败提示)。拿不准的情况一律放行，不制造假告警。
    """
    cfg_path = _openclaw_config_path()
    if not cfg_path.is_file():
        return False, f"{cfg_path} 不存在 — 先跑 bash setup.sh（Windows: setup.ps1）"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"{cfg_path} 读不出来（{exc}）"

    primary = (((cfg.get("agents") or {}).get("defaults") or {})
               .get("model") or {}).get("primary") or ""
    if not primary:
        return False, "未设置 agents.defaults.model.primary — 重新跑 setup 脚本"
    if _agent_runtime_id(cfg) == CLAUDE_CLI_RUNTIME:
        return _claude_cli_ready(cfg)
    if "/" not in primary:
        # 不是 provider/model 形式，解析不出 provider，交给 `easel ping` 去判，不在这里猜。
        return True, ""

    provider = primary.split("/", 1)[0]
    providers = (cfg.get("models") or {}).get("providers") or {}
    entry = providers.get(provider)
    if not isinstance(entry, dict):
        return False, (f"primary 是 {primary}，但 models.providers.{provider} 不存在 —— "
                       "在 .env 填好真实 key 后重新跑 setup 脚本")
    # apiKey / 本地适配器 / OAuth 任一即可。字段名随 OpenClaw 版本变过，这里从宽认。
    has_auth = bool(str(entry.get("apiKey") or "").strip()) or bool(entry.get("localService")) \
        or any(k for k, v in entry.items() if "oauth" in k.lower() and v)
    if not has_auth:
        return False, (f"models.providers.{provider} 没有 apiKey —— "
                       "在 .env 填好真实 key 后重新跑 setup 脚本")
    return True, ""


def cmd_doctor(_args) -> int:
    print("Easel — 环境检查\n")
    all_ok = True

    # 1. Runtime prerequisites
    all_ok &= _check("Python >= 3.10", _python_version_ok(),
                      "请安装 Python 3.10 或更高版本")
    all_ok &= _check("Python venv module", _venv_available(),
                      "Debian/Ubuntu 请安装 python3-venv")
    # openclaw 版本决定 Node 引擎要求：2026.9.x 需要 Node 24.16+，2026.6.x 需要 22.19+（实测其
    # engines，见 _node_version_ok 的说明）。未装 openclaw 时按 setup 的默认安装目标
    # （openclaw@latest）从严要求 24.16+。
    oc_ver = _openclaw_version()
    node_strict = oc_ver is None or oc_ver >= (2026, 9, 0)
    node_floor = "24.16" if node_strict else "22.19"
    has_node = shutil.which("node") is not None
    node_ok = _node_version_ok(node_strict)
    node_detail = (f"请安装 Node.js >= {node_floor}: https://nodejs.org/" if not has_node
                   else f"Node.js 版本不满足当前 OpenClaw 要求，请升级到 >= {node_floor}: https://nodejs.org/")
    all_ok &= _check(f"Node.js >= {node_floor}", node_ok, node_detail)
    all_ok &= _check("FFmpeg", shutil.which("ffmpeg") is not None,
                      "媒体处理需要 FFmpeg；请安装后重试")

    # 2. openclaw command + 版本
    has_openclaw = shutil.which("openclaw") is not None
    all_ok &= _check("openclaw command", has_openclaw,
                      "请安装 openclaw: npm i -g openclaw")
    if has_openclaw:
        min_str = ".".join(map(str, MIN_OPENCLAW))
        ver_str = ".".join(map(str, oc_ver)) if oc_ver else "未知"
        oc_ver_ok = oc_ver is not None and oc_ver >= MIN_OPENCLAW
        all_ok &= _check(
            f"OpenClaw >= {min_str}", oc_ver_ok,
            f"当前 {ver_str}，过旧会有 provider/schema 兼容问题；请升级：npm i -g openclaw@latest",
        )

    for module in ("fastapi", "uvicorn", "sse_starlette", "multipart"):
        all_ok &= _check(f"Python package: {module}", _module_available(module),
                          "运行 pip install -e . 安装 Easel 运行依赖")

    frontend_ready = (PROJECT_ROOT / "web" / "frontend" / "dist" / "index.html").is_file()
    all_ok &= _check("Web frontend build", frontend_ready,
                      "运行 cd web/frontend && npm ci && npm run build")
    all_ok &= _check("Playwright Chromium", _chromium_available(),
                      "运行 python3 -m playwright install chromium")

    # 3. .env file with valid key
    # Claude CLI runtime 复用本机 Claude Code 的登录态，不读任何 API Key —— 照查 .env 只会给
    # 这类机器报假 FAIL。它真正的就绪检查（claude 在不在 PATH、登没登录）在下一条 model routing 里。
    uses_claude_cli = _uses_claude_cli()
    if uses_claude_cli:
        all_ok &= _check(".env (API Key)", True)
        print("    └─ agent 走 Claude CLI（复用 Claude Code 登录），不需要 API Key")
    else:
        env_ok = _env_key_valid()
        all_ok &= _check(".env (API Key)", env_ok,
                          "填 ANTHROPIC_API_KEY，或 EASEL_LLM_API_KEY + EASEL_LLM_BASE_URL")

    # .env 填了 ≠ setup 真的把 provider 写进了 openclaw；不对账就会「doctor 全绿但对话报错」。
    route_ok, route_detail = _primary_model_routable()
    route_label = "OpenClaw model routing" + (" (Claude CLI)" if uses_claude_cli else "")
    all_ok &= _check(route_label, route_ok, route_detail)

    # 4. OpenClaw gateway running
    gw_ok = _gateway_healthy()
    all_ok &= _check(f"OpenClaw gateway (localhost:{resolve_gateway_port()})", gw_ok,
                      f"运行 python -m easel gateway start（端口来自 {port_source()}）")

    # 5. Skills synced
    synced, synced_detail = _skills_synced()
    all_ok &= _check("Skills synced", synced,
                      f"{synced_detail}；重新运行 setup.ps1（Windows）或 bash openclaw/sync.sh（Linux/macOS）")

    # 6. Key project files
    gateway_label = "scripts/gateway.ps1" if os.name == "nt" else "scripts/gateway.sh"
    gateway_path = PROJECT_ROOT / "scripts" / ("gateway.ps1" if os.name == "nt" else "gateway.sh")
    key_files = [
        ("openclaw/openclaw.json5", PROJECT_ROOT / "openclaw" / "openclaw.json5"),
        ("skills/openclaw/", PROJECT_ROOT / "skills" / "openclaw"),
        (gateway_label, gateway_path),
    ]
    for label, path in key_files:
        all_ok &= _check(label, path.exists())

    print()
    if all_ok:
        print(f"{GREEN}✓ 环境就绪{NC} — 运行 python -m easel ping 验证连通性")
    else:
        print(f"{YELLOW}⚠ 有未满足项{NC} — 请按上述提示修复后重试")

    return 0 if all_ok else 1
