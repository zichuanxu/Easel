"""Claude CLI 路线：agent 跑在 OpenClaw 自带的 claude-cli runtime 上，复用本机 Claude Code 的登录、不用 API Key。

与 setup.sh 的 EASEL_AGENT_RUNTIME=claude-cli 分支同一套写法，Web 设置「一键接入 Claude Code」用它：
- 主模型写 anthropic/<模型>，并在 agents.defaults.models["anthropic/<模型>"].agentRuntime 标 claude-cli（不写 provider）；
- env.vars.CLAUDE_CONFIG_DIR 给 agent 一份独立的 Claude Code 配置目录（默认 ~/.claude-easel，shared = 个人 ~/.claude），
  个人 ~/.claude 里的插件、hooks、CLAUDE.md 不会带进 agent。
改这里的规则时，setup.sh 里对应的 case 分支要一起改。
"""
from __future__ import annotations

import os

CLAUDE_CLI_RUNTIME = "claude-cli"
DEFAULT_MODEL = "anthropic/claude-opus-5"      # = setup.sh 的 CLAUDE_CLI_DEFAULT_MODEL
DEFAULT_CONFIG_DIR_NAME = ".claude-easel"
_CONFIG_DIR_ERROR = "EASEL_CLAUDE_CONFIG_DIR={raw} 不能用：要绝对路径（或 ~/ 开头）且不能是家目录本身"


def normalize_model(raw: str) -> str | None:
    """模型名归一成 anthropic/<模型>：空 = 默认；老写法 claude-cli/x 改成 anthropic/x；裸 claude-x 补上 provider；
    别家 provider 返回 None（调用方决定报错还是打回默认）。"""
    m = (raw or "").strip()
    if not m:
        return DEFAULT_MODEL
    for prefix in ("anthropic/", "claude-cli/"):
        if m.startswith(prefix):
            rest = m[len(prefix):]
            return f"anthropic/{rest}" if rest else None
    if "/" not in m and m.startswith("claude-") and m != "claude-":
        return f"anthropic/{m}"
    return None


def resolve_config_dir(raw: str, home: str | os.PathLike) -> tuple[str, str]:
    """EASEL_CLAUDE_CONFIG_DIR → (目录, 错误)。目录为空串 = 不隔离（个人 ~/.claude）。

    OpenClaw 把 env.vars 原样交给 claude，两边都不展开 ~ / $VAR，所以这里展开并要求绝对路径；
    末尾的 / 不算改目录；整个家目录当配置目录会把 .claude.json 之类直接铺进 ~，不行。"""
    home_s = _strip_slash(str(home))
    v = (raw or "").strip()
    if not v:
        d = os.path.join(home_s, DEFAULT_CONFIG_DIR_NAME)
    elif v == "shared":
        return "", ""
    elif v.startswith("~/") and len(v) > 2:
        d = os.path.join(home_s, v[2:])
    elif os.path.isabs(v):
        d = v
    else:
        return "", _CONFIG_DIR_ERROR.format(raw=v)
    d = _strip_slash(d)
    if d == home_s:
        return "", _CONFIG_DIR_ERROR.format(raw=v)
    return d, ""


def _strip_slash(value: object) -> str:
    s = value if isinstance(value, str) else ""
    while len(s) > 1 and s.endswith(("/", "\\")):
        s = s[:-1]
    return s


def apply_route(cfg: dict, model_ref: str, config_dir: str) -> bool:
    """就地改 openclaw.json 的内容：主模型 + 模型级 agentRuntime + env.vars.CLAUDE_CONFIG_DIR。

    返回 Claude Code 配置目录是否变了：env.vars 只在 gateway 进程启动时注入，变了要重启 gateway，
    已有会话还绑着旧目录下的 Claude 会话，要 /reset。"""
    defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
    defaults.setdefault("model", {})["primary"] = model_ref
    entry = defaults.setdefault("models", {}).setdefault(model_ref, {})
    runtime = entry.get("agentRuntime") if isinstance(entry.get("agentRuntime"), dict) else {}
    entry["agentRuntime"] = {**runtime, "id": CLAUDE_CLI_RUNTIME}

    env_block = cfg.get("env") if isinstance(cfg.get("env"), dict) else None
    env_vars = env_block.get("vars") if env_block is not None and isinstance(env_block.get("vars"), dict) else None
    previous = _strip_slash(env_vars.get("CLAUDE_CONFIG_DIR")) if env_vars is not None else ""
    if config_dir:
        cfg.setdefault("env", {}).setdefault("vars", {})["CLAUDE_CONFIG_DIR"] = config_dir
    elif env_vars is not None:
        env_vars.pop("CLAUDE_CONFIG_DIR", None)
    return previous != config_dir


def login_problem(cfg: dict) -> str:
    """claude 找不到 / 明确没登录时给用户的一句话（同 easel doctor，带配置目录的登录命令）；就绪或拿不准返回空。"""
    from easel.commands.doctor import _claude_cli_ready

    ok, message = _claude_cli_ready(cfg)
    return "" if ok else message


def ensure_resume_link(config_dir: str) -> str:
    """建续聊软链（同 setup.sh 里的 python -m easel.claude_cli_link）。就绪返回空，否则返回说明。"""
    from easel import claude_cli_link
    from easel.openclaw_workspace import workspace_dir

    try:
        ok, message = claude_cli_link.ensure_link(config_dir or None, workspace_dir())
    except Exception as exc:  # noqa: BLE001 — 工作区解析不出来之类：不挡接入，提示怎么补
        return f"续聊软链没建成（{exc}）：处理后运行 python -m easel.claude_cli_link"
    return "" if ok else message
