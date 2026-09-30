"""认证配置链路的回归测试。

钉住四个真实踩过的坑：

1. setup.sh 用 `-z ANTHROPIC_API_KEY` 判「没配 Anthropic」。.env.example 默认就带着
   `ANTHROPIC_API_KEY=sk-ant-REPLACE_ME`，用户照 README 加了 OpenAI 兼容服务但没删那行时，
   整条 OpenAI 分支被跳过 —— provider 一个字没写，却照样把 primary 设成了 openai/xxx，
   对话直接报 "No route-compatible authentication source is configured for openai"。
2. `easel doctor` 只静态查 .env，查不出上面那种「.env 填了但 openclaw 没写」，于是全绿。
3. setup.ps1 里 `if (Is-UsableKey $x -and $y.ContainsKey(...))` 会进命令解析模式，
   `-and` 被当成参数名静默吞掉，后半个守卫失效（PS 5.1 与 7 同样中招）。
4. install_tool 用 [Environment]::GetEnvironmentVariable 读用户 PATH 会展开 %VAR%，
   写回又是 REG_SZ，把用户 PATH 里的间接引用永久压平。

setup.sh 的用例是把脚本里那段**原文**抠出来跑（按内容锚点切，不写死行号），
$OC 换成记录器，所以测的是真代码、不是复制品。
"""
from __future__ import annotations

import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETUP_SH = PROJECT_ROOT / "setup.sh"
SETUP_PS1 = PROJECT_ROOT / "setup.ps1"

sys.path.insert(0, str(PROJECT_ROOT))
from easel.commands import doctor  # noqa: E402


# ── setup.sh：把真代码切出来在沙箱里跑 ────────────────────────────────


@functools.lru_cache(maxsize=1)
def _bash_works() -> bool:
    """有没有能真跑 POSIX 脚本的 bash。

    不能只看 `shutil.which("bash")`：Windows 上 System32\\bash.exe 是 WSL 的入口，
    没装发行版时它照样在 PATH 里，跑起来却只会打印「has no installed distributions」，
    于是断言拿到一串 UTF-16 的错误提示、报得莫名其妙。跑一下才算数。
    """
    try:
        p = subprocess.run(["bash", "-c", "echo ok"], capture_output=True, text=True,
                           timeout=30, errors="replace")
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0 and p.stdout.strip() == "ok"


# setup.sh 是 Linux/macOS 的安装路径，Windows 走 setup.ps1（另有静态用例守着）。
needs_bash = pytest.mark.skipif(not _bash_works(), reason="没有可用的 bash，跳过 setup.sh 用例")


def _slice(lines: list[str], start: str, end: str, *, keep_end: bool) -> str:
    """按内容锚点截取，避免行号漂移后测试悄悄测了别的东西。"""
    i = next(n for n, line in enumerate(lines) if line.startswith(start))
    j = next(n for n, line in enumerate(lines) if n > i and line.startswith(end))
    return "\n".join(lines[i: j + 1 if keep_end else j])


def _auth_block() -> str:
    lines = SETUP_SH.read_text(encoding="utf-8").splitlines()
    helper = _slice(lines, "usable_key() {", "}", keep_end=True)
    body = _slice(lines, 'DEFAULT_PRIMARY_MODEL="anthropic',
                  "# 整个 agent run 的总时长上限", keep_end=False)
    return helper + "\n\n" + body


# 替身 claude：记下每次调用的参数、看到的 CLAUDE_CONFIG_DIR / ANTHROPIC_API_KEY（没设就记 <unset>）。
# `auth status` 的退出码/输出照本机实测：已登录 0，未登录 1，两种都输出 JSON；
# 设了 FAKE_CLAUDE_STATUS_OUT（哪怕是空串）就原样吐它、退出码 1，模拟老版本/输出坏掉。
FAKE_CLAUDE = """#!/bin/sh
printf '%s|%s|%s\\n' "$*" "${CLAUDE_CONFIG_DIR-<unset>}" "${ANTHROPIC_API_KEY-<unset>}" >> "$FAKE_CLAUDE_LOG"
if [ "$1 $2" = "auth status" ]; then
    if [ -n "${FAKE_CLAUDE_STATUS_OUT+x}" ]; then
        printf '%s' "$FAKE_CLAUDE_STATUS_OUT"
        exit 1
    fi
    printf '{"loggedIn": %s, "authMethod": "claude.ai"}\\n' "${FAKE_CLAUDE_LOGGED_IN:-true}"
    [ "${FAKE_CLAUDE_LOGGED_IN:-true}" = true ]
fi
"""


def _run_auth(tmp_path: Path, *, oc_state: dict[str, str] | None = None,
              claude_on_path: bool = True, **env: str) -> tuple[str, dict[str, str]]:
    """跑认证段，返回 (stdout, 实际写进 openclaw 的配置)。

    - 与 setup.sh 一样开 `set -euo pipefail`；stdin 接 /dev/null，段里 `[ -t 0 ]` 的交互分支
      （例如拉起 `claude auth login`）在测试里一律不走，`pytest -s` 时也一样。
    - 假 claude 永远排在 PATH 最前：本机真 claude 在 ~/.local/bin，哪条用例都不许碰到它。
      claude_on_path=False 时不放替身，由调用方给一个根本没有 claude 的 PATH。
    - `$OC config get <path>` 从 oc_state 里答，没有就退出码 1（与 OpenClaw 一致）；
      `config unset <path>` 记成 `<path> = <unset>`；每次 set 带的参数另记一份，见 _oc_flags。
    - stdout 末尾多一行 `RESTART|<值>`：段内算出的「gateway 要不要 restart」。
    """
    q = shlex.quote
    calls = tmp_path / "oc-calls.log"
    state = tmp_path / "oc-state"
    state.write_text("".join(f"{k}={v}\n" for k, v in (oc_state or {}).items()), encoding="utf-8")
    script = textwrap.dedent(f"""
        set -euo pipefail
        PROJECT_ROOT={q(str(tmp_path))}
        CFG={q(str(calls))}
        OC_STATE={q(str(state))}
        : > "$CFG"
        : > "$CFG.flags"
        info() {{ echo "INFO|$*"; }}
        ok()   {{ echo "OK|$*"; }}
        warn() {{ echo "WARN|$*"; }}
        oc_write_anthropic() {{ echo "models.providers.anthropic.baseUrl = $1" >> "$CFG"; }}
        _oc() {{
            [ "${{1:-}}" = "config" ] || return 0
            case "${{2:-}}" in
                set)
                    echo "$3 = $4" >> "$CFG"
                    echo "$3|${{*:5}}" >> "$CFG.flags"
                    ;;
                unset)
                    echo "$3 = <unset>" >> "$CFG"
                    ;;
                get)
                    while IFS= read -r line; do
                        case "$line" in "$3="*) printf '%s\\n' "${{line#"$3="}}"; return 0 ;; esac
                    done < "$OC_STATE"
                    return 1
                    ;;
            esac
            return 0
        }}
        OC=_oc
    """) + "\n" + _auth_block() + '\necho "RESTART|${GATEWAY_RESTART_NEEDED:-}"\n'

    run_env = {"PATH": os.environ["PATH"], "FAKE_CLAUDE_LOG": str(tmp_path / "claude-calls.log"), **env}
    if claude_on_path:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE, encoding="utf-8")
        fake.chmod(0o755)
        run_env["PATH"] = f"{bin_dir}{os.pathsep}{run_env['PATH']}"
    # errors="replace"：bash 3.2 吞字节报错时 stderr 里有半个 UTF-8 字符，别让解码错误盖住真正的报错
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, errors="replace",
                          timeout=60, stdin=subprocess.DEVNULL, env=run_env)
    assert proc.returncode == 0, f"认证段执行失败：{proc.stderr}"
    written: dict[str, str] = {}
    if calls.is_file():
        for line in calls.read_text(encoding="utf-8").splitlines():
            if " = " in line:
                k, v = line.split(" = ", 1)
                written[k] = v
    return proc.stdout, written


PLACEHOLDER = "sk-ant-REPLACE_ME"
DEEPSEEK = {
    "OPENAI_API_KEY": "sk-deepseek-fake",
    "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
    "OPENAI_MODEL": "deepseek-chat",
    "CLAUDE_MODEL": "openai/deepseek-chat",
}


@needs_bash
def test_placeholder_does_not_block_openai_branch(tmp_path):
    """核心回归：占位符没删 + 配了 OpenAI 兼容服务 → provider 必须真的写出来。"""
    out, written = _run_auth(tmp_path, ANTHROPIC_API_KEY=PLACEHOLDER, **DEEPSEEK)
    assert written.get("models.providers.openai.apiKey") == "sk-deepseek-fake"
    assert written.get("models.providers.openai.baseUrl") == "https://api.deepseek.com/v1"
    assert written.get("agents.defaults.model.primary") == "openai/deepseek-chat"
    assert "WARN|认证未配置" not in out


@needs_bash
def test_placeholder_present_or_absent_gives_same_result(tmp_path):
    """删不删那行占位符，结果必须完全一致 —— 用户没义务知道要删它。"""
    _, with_ph = _run_auth(tmp_path, ANTHROPIC_API_KEY=PLACEHOLDER, **DEEPSEEK)
    _, without = _run_auth(tmp_path, **DEEPSEEK)
    assert with_ph == without


@needs_bash
def test_nothing_configured_writes_no_primary(tmp_path):
    """什么都没配时不许写 primary：写了只会指向不存在的 provider，比「没配置」更难查。"""
    out, written = _run_auth(tmp_path, ANTHROPIC_API_KEY=PLACEHOLDER,
                             CLAUDE_MODEL="openai/deepseek-chat")
    assert written == {}, f"不该写任何配置，实际写了 {written}"
    assert "WARN|认证未配置" in out


@needs_bash
def test_real_anthropic_key_still_works(tmp_path):
    """别把闸修成谁都过不去：正经 key 必须照常同步。"""
    out, written = _run_auth(tmp_path, ANTHROPIC_API_KEY="sk-ant-real",
                             CLAUDE_MODEL="anthropic/claude-sonnet-4-6")
    assert written["models.providers.anthropic.baseUrl"] == "https://api.anthropic.com"
    assert written["agents.defaults.model.primary"] == "anthropic/claude-sonnet-4-6"


@needs_bash
def test_anthropic_takes_priority_over_openai(tmp_path):
    """两个都配了真 key 时，优先级保持原样（Anthropic 胜出）。"""
    _, written = _run_auth(tmp_path, ANTHROPIC_API_KEY="sk-ant-real", **DEEPSEEK)
    assert "models.providers.openai.apiKey" not in written
    assert "models.providers.anthropic.baseUrl" in written


@pytest.mark.parametrize("value", [
    "REPLACE_ME", "sk-ant-REPLACE_ME", "replace_me",
    "your-api-key", "YOUR_API_KEY", "your api key", "",
])
@needs_bash
def test_usable_key_rejects_placeholders(tmp_path, value):
    lines = SETUP_SH.read_text(encoding="utf-8").splitlines()
    helper = _slice(lines, "usable_key() {", "}", keep_end=True)
    proc = subprocess.run(
        ["bash", "-c", helper + '\nif usable_key "$1"; then echo YES; else echo NO; fi',
         "_", value],
        capture_output=True, text=True, timeout=30)
    assert proc.stdout.strip() == "NO", f"{value!r} 不该被当成可用 key"


@pytest.mark.parametrize("value", ["sk-ant-abc123", "sk-proj-xyz", "local-adapter"])
@needs_bash
def test_usable_key_accepts_real_keys(tmp_path, value):
    lines = SETUP_SH.read_text(encoding="utf-8").splitlines()
    helper = _slice(lines, "usable_key() {", "}", keep_end=True)
    proc = subprocess.run(
        ["bash", "-c", helper + '\nif usable_key "$1"; then echo YES; else echo NO; fi',
         "_", value],
        capture_output=True, text=True, timeout=30)
    assert proc.stdout.strip() == "YES", f"{value!r} 该被当成可用 key"


def test_setup_sh_has_no_bare_placeholder_comparisons():
    """别再回到「各写各的 != 占位符」：认证判定统一走 usable_key。"""
    text = SETUP_SH.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "sk-ant-REPLACE_ME" not in body, "认证判定里仍有硬编码占位符比较"


# ── setup.sh：本机 Claude Code 登录路线（EASEL_AGENT_RUNTIME=claude-cli）──────────
#
# 目标终态与本机手配的一致：模型级 agentRuntime=claude-cli、primary=anthropic/<模型>、
# env.vars.CLAUDE_CONFIG_DIR=<绝对路径>、不写 models.providers.anthropic。
# 读写全走 $OC（替身从 oc_state 答 get）；「找不到 claude」的用例单独造一个只有基础工具的 PATH。

# 这批用例要 python3 + 符号链接造 PATH；setup.sh 本来也只是 Linux/macOS 的安装路径。
needs_posix = pytest.mark.skipif(os.name == "nt", reason="setup.sh 只在 Linux/macOS 上跑，Windows 走 setup.ps1")

MODEL_PATCH = {"anthropic/claude-opus-5": {"agentRuntime": {"id": "claude-cli"}}}


def _cli_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"HOME": str(tmp_path / "home"), "EASEL_AGENT_RUNTIME": "claude-cli", **extra}


def _claude_calls(tmp_path: Path) -> list[tuple[str, ...]]:
    log = tmp_path / "claude-calls.log"
    if not log.is_file():
        return []
    return [tuple(line.split("|", 2)) for line in log.read_text(encoding="utf-8").splitlines()]


def _oc_flags(tmp_path: Path) -> dict[str, list[str]]:
    """每次 `$OC config set <path> ...` 在 value 之后带的参数（--strict-json / --merge …）。"""
    flags: dict[str, list[str]] = {}
    for line in (tmp_path / "oc-calls.log.flags").read_text(encoding="utf-8").splitlines():
        path, _, rest = line.partition("|")
        flags[path] = rest.split()
    return flags


def _models(written: dict[str, str]) -> dict:
    return json.loads(written["agents.defaults.models"])


def _restart(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith("RESTART|")).split("|", 1)[1]


def _warns(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("WARN|")]


@needs_bash
@needs_posix
def test_claude_cli_route_writes_expected_config(tmp_path):
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path))
    home = str(tmp_path / "home")
    assert {**written, "agents.defaults.models": _models(written)} == {
        "agents.defaults.models": MODEL_PATCH,
        "env.vars.CLAUDE_CONFIG_DIR": f"{home}/.claude-easel",
        "agents.defaults.model.primary": "anthropic/claude-opus-5",
    }
    # 只给补丁、让 OpenClaw 递归合并：丢了 --merge 就是整表替换，丢了 --strict-json 就按字符串存
    assert _oc_flags(tmp_path)["agents.defaults.models"] == ["--strict-json", "--merge"]
    assert any(line.startswith("OK|Claude CLI 路线已配置") for line in out.splitlines())
    assert not _warns(out) or all("配置目录改为" in w or "/reset" in w for w in _warns(out))
    # 登录态是按 gateway 会用的那个目录查的
    assert _claude_calls(tmp_path) == [("auth status --json", f"{home}/.claude-easel", "<unset>")]
    assert _restart(out) == "true"      # 第一次写入配置目录 → 要 restart


@needs_bash
@needs_posix
def test_claude_cli_route_beats_api_key(tmp_path):
    """显式选择优先：.env 里同时留着 ANTHROPIC_API_KEY 也不写 provider、探测时也不带它。"""
    _, written = _run_auth(tmp_path, **_cli_env(
        tmp_path, ANTHROPIC_API_KEY="sk-ant-real", CLAUDE_MODEL="anthropic/claude-sonnet-4-6"))
    assert "models.providers.anthropic.baseUrl" not in written
    assert written["agents.defaults.model.primary"] == "anthropic/claude-sonnet-4-6"
    assert _models(written) == {"anthropic/claude-sonnet-4-6": {"agentRuntime": {"id": "claude-cli"}}}
    assert all(api_key == "<unset>" for _, _, api_key in _claude_calls(tmp_path)), \
        "shell 里的 ANTHROPIC_API_KEY 带进了登录探测，会误判成已登录"


@needs_bash
@needs_posix
def test_claude_cli_route_is_idempotent(tmp_path):
    """已经配好的机器再跑一遍：除了（值不变的）primary 什么都不写，也不 restart。"""
    home = str(tmp_path / "home")
    out, written = _run_auth(tmp_path, oc_state={
        "env.vars.CLAUDE_CONFIG_DIR": f"{home}/.claude-easel",
        'agents.defaults.models["anthropic/claude-opus-5"].agentRuntime.id': "claude-cli",
    }, **_cli_env(tmp_path))
    assert written == {"agents.defaults.model.primary": "anthropic/claude-opus-5"}
    assert _restart(out) == "false"
    assert not _warns(out)


@pytest.mark.parametrize("model,expected", [
    ("claude-cli/claude-opus-4-7", "anthropic/claude-opus-4-7"),   # 老写法换成 anthropic/
    ("claude-opus-4-7", "anthropic/claude-opus-4-7"),              # 裸模型名补上 provider
    ("", "anthropic/claude-opus-5"),                               # 没填：OpenClaw 自己的默认
])
@needs_bash
@needs_posix
def test_claude_cli_route_model_normalization(tmp_path, model, expected):
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, CLAUDE_MODEL=model))
    assert written["agents.defaults.model.primary"] == expected
    assert list(_models(written)) == [expected]
    assert not any("CLAUDE_MODEL" in w for w in _warns(out))


@pytest.mark.parametrize("model", ["openai/gpt-4o", "anthropic/", "claude-cli/", "gpt-4o"])
@needs_bash
@needs_posix
def test_claude_cli_route_foreign_model_falls_back_with_warning(tmp_path, model):
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, CLAUDE_MODEL=model))
    assert written["agents.defaults.model.primary"] == "anthropic/claude-opus-5"
    assert any(w.startswith(f"WARN|CLAUDE_MODEL={model} ") for w in _warns(out))


@pytest.mark.parametrize("value,expected", [
    (None, "{home}/.claude-easel"),         # 没设
    ("", "{home}/.claude-easel"),           # 设了空值
    ("~/x", "{home}/x"),                    # 带引号写进 .env / 从环境传进来时 ~ 不会被 shell 展开
    ("{tmp}/abs-dir", "{tmp}/abs-dir"),
    ("{tmp}/abs-dir//", "{tmp}/abs-dir"),   # 末尾的 / 不算数
], ids=["unset", "empty", "tilde", "absolute", "trailing-slash"])
@needs_bash
@needs_posix
def test_claude_cli_route_config_dir(tmp_path, value, expected):
    fmt = {"home": str(tmp_path / "home"), "tmp": str(tmp_path)}
    extra = {} if value is None else {"EASEL_CLAUDE_CONFIG_DIR": value.format(**fmt)}
    _, written = _run_auth(tmp_path, **_cli_env(tmp_path, **extra))
    assert written["env.vars.CLAUDE_CONFIG_DIR"] == expected.format(**fmt)
    assert _claude_calls(tmp_path)[0][1] == expected.format(**fmt)


@pytest.mark.parametrize("value", ["relative/dir", "~other/x", "~", "~/", "{home}", "{home}/"])
@needs_bash
@needs_posix
def test_claude_cli_route_rejects_bad_config_dir(tmp_path, value):
    """相对路径会落到 gateway 工作目录下（OpenClaw 原样传、claude 也不展开）；家目录本身也不行。
    不配这条路线，primary 也不动。"""
    value = value.format(home=str(tmp_path / "home"))
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, EASEL_CLAUDE_CONFIG_DIR=value))
    assert written == {}
    assert any("不能用" in w for w in _warns(out))
    assert _claude_calls(tmp_path) == []


@needs_bash
@needs_posix
def test_claude_cli_route_shared_uses_personal_login(tmp_path):
    """shared：不写 env.vars，探测时也不带 CLAUDE_CONFIG_DIR —— 连 shell 里导出的那个都要摘掉。"""
    out, written = _run_auth(tmp_path, **_cli_env(
        tmp_path, EASEL_CLAUDE_CONFIG_DIR="shared", CLAUDE_CONFIG_DIR="/from/shell"))
    assert "env.vars.CLAUDE_CONFIG_DIR" not in written
    assert written["agents.defaults.model.primary"] == "anthropic/claude-opus-5"
    assert _claude_calls(tmp_path)[0][1] == "<unset>"
    assert _restart(out) == "false"
    # gateway 从这个 shell 起会继承导出的 CLAUDE_CONFIG_DIR、盖过配置，得提醒
    assert any("CLAUDE_CONFIG_DIR=/from/shell" in w for w in _warns(out))


@needs_bash
@needs_posix
def test_claude_cli_route_shared_unsets_previous_dir(tmp_path):
    out, written = _run_auth(tmp_path, oc_state={"env.vars.CLAUDE_CONFIG_DIR": "/old/claude-easel"},
                             **_cli_env(tmp_path, EASEL_CLAUDE_CONFIG_DIR="shared"))
    assert written["env.vars.CLAUDE_CONFIG_DIR"] == "<unset>"
    assert _restart(out) == "true"


@pytest.mark.parametrize("previous,changed", [
    ("{home}/.claude-easel", False),
    ("{home}/.claude-easel/", False),       # 手写多了个 / 也是同一个目录
    ("/old/claude-easel", True),
    (None, True),
], ids=["same", "same-trailing-slash", "different", "absent"])
@needs_bash
@needs_posix
def test_claude_cli_route_restart_only_when_dir_changes(tmp_path, previous, changed):
    """env.vars 只在 gateway 启动时注入：目录变了才要 restart，并提醒旧会话要 /reset。"""
    home = str(tmp_path / "home")
    state = {} if previous is None else {"env.vars.CLAUDE_CONFIG_DIR": previous.format(home=home)}
    out, written = _run_auth(tmp_path, oc_state=state, **_cli_env(tmp_path))
    assert _restart(out) == ("true" if changed else "false")
    assert ("env.vars.CLAUDE_CONFIG_DIR" in written) is changed
    assert any("/reset" in w for w in _warns(out)) is changed


@needs_bash
@needs_posix
def test_claude_cli_route_warns_about_inline_env_override(tmp_path):
    """内联的 env.CLAUDE_CONFIG_DIR 在 OpenClaw 里盖过 env.vars —— setup 写的会不生效。"""
    out, _ = _run_auth(tmp_path, oc_state={"env.CLAUDE_CONFIG_DIR": "/inline/dir"}, **_cli_env(tmp_path))
    assert any("env.CLAUDE_CONFIG_DIR=/inline/dir" in w for w in _warns(out))


@needs_bash
@needs_posix
def test_claude_cli_route_without_claude_binary(tmp_path):
    """找不到 claude：什么都不写（primary 也不动），也不悄悄退回同时配着的 API key。"""
    sysbin = tmp_path / "sysbin"
    sysbin.mkdir()
    for tool in ("bash", "python3", "sed", "tr", "env", "cat", "printenv"):
        found = shutil.which(tool)
        assert found, f"测试机上缺 {tool}"
        (sysbin / tool).symlink_to(found)
    assert shutil.which("claude", path=str(sysbin)) is None
    out, written = _run_auth(tmp_path, claude_on_path=False,
                             **_cli_env(tmp_path, PATH=str(sysbin), ANTHROPIC_API_KEY="sk-ant-real"))
    assert written == {}
    assert any("找不到 claude" in w for w in _warns(out))
    assert any("https://claude.com/claude-code" in w for w in _warns(out))


@needs_bash
@needs_posix
def test_claude_cli_route_logged_out_non_interactive(tmp_path):
    """没登录不回滚配置（配置本身是对的），给出能直接粘贴的登录命令；非交互时不去拉起登录。
    家目录故意带空格：提示里的命令要照样能粘贴。"""
    home = tmp_path / "home dir"
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, HOME=str(home), FAKE_CLAUDE_LOGGED_IN="false"))
    claude_dir = f"{home}/.claude-easel"
    assert written["agents.defaults.model.primary"] == "anthropic/claude-opus-5"
    assert written["env.vars.CLAUDE_CONFIG_DIR"] == claude_dir
    login = [w for w in _warns(out) if "claude auth login" in w]
    assert login, "没有给出登录命令"
    command = login[0].split("运行 ", 1)[1]
    assert shlex.split(command) == [f"CLAUDE_CONFIG_DIR={claude_dir}", "claude", "auth", "login"]
    assert all(not args.startswith("auth login") for args, _, _ in _claude_calls(tmp_path))


@pytest.mark.parametrize("status_out", ["", "error: unknown option '--json'", "{not json"],
                         ids=["empty", "old-cli", "garbage"])
@needs_bash
@needs_posix
def test_claude_cli_route_unclear_login_status_passes(tmp_path, status_out):
    """与 easel doctor 同一判据：只有明确的 loggedIn=false 才算没登录，其余一律放行。"""
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, FAKE_CLAUDE_STATUS_OUT=status_out))
    assert written["agents.defaults.model.primary"] == "anthropic/claude-opus-5"
    assert not any("未登录" in w for w in _warns(out))


def _utf8_locale() -> str | None:
    try:
        listed = subprocess.run(["locale", "-a"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    available = {line.strip() for line in listed.splitlines()}
    return next((loc for loc in ("en_US.UTF-8", "C.UTF-8", "en_US.utf8", "C.utf8") if loc in available), None)


@needs_bash
@needs_posix
def test_claude_cli_route_under_utf8_locale(tmp_path):
    """真机现场：LANG=en_US.UTF-8 + macOS 自带 bash 3.2，`$VAR（` 会把全角字符吞进变量名，
    set -u 直接中断安装。harness 默认只带 PATH（C locale）看不出来，这里按用户的 locale 再跑一遍。"""
    loc = _utf8_locale()
    if loc is None:
        pytest.skip("本机没有 UTF-8 locale")
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, LANG=loc, LC_ALL=loc))
    assert written["agents.defaults.model.primary"] == "anthropic/claude-opus-5"
    assert any(line.startswith("OK|Claude CLI 路线已配置") for line in out.splitlines())


@needs_bash
@needs_posix
def test_unknown_agent_runtime_warns_and_uses_api_route(tmp_path):
    """EASEL_AGENT_RUNTIME 拼错会悄悄落回 API 路线，得说一声。"""
    out, written = _run_auth(tmp_path, **_cli_env(tmp_path, EASEL_AGENT_RUNTIME="claude",
                                                  ANTHROPIC_API_KEY="sk-ant-real"))
    assert any(w.startswith("WARN|EASEL_AGENT_RUNTIME=claude ") for w in _warns(out))
    assert written["models.providers.anthropic.baseUrl"] == "https://api.anthropic.com"
    assert _claude_calls(tmp_path) == []


STALE_RUNTIME = 'agents.defaults.models["anthropic/claude-opus-5"].agentRuntime'


@needs_bash
@needs_posix
def test_api_route_strips_stale_claude_cli_runtime(tmp_path):
    """从 Claude CLI 换回 API key、模型名没变：残留的 runtime 会让 agent 悄悄继续走 Claude CLI。

    只摘 primary 那个模型的 agentRuntime（unset 这一条路径），其他键、其他模型都不碰。
    """
    env = _cli_env(tmp_path, ANTHROPIC_API_KEY="sk-ant-real", CLAUDE_MODEL="anthropic/claude-opus-5")
    del env["EASEL_AGENT_RUNTIME"]
    out, written = _run_auth(tmp_path, oc_state={f"{STALE_RUNTIME}.id": "claude-cli"}, **env)
    assert written[STALE_RUNTIME] == "<unset>"
    assert "agents.defaults.models" not in written
    assert written["models.providers.anthropic.baseUrl"] == "https://api.anthropic.com"
    assert _claude_calls(tmp_path) == []
    assert _restart(out) == "false"


@pytest.mark.parametrize("state", [
    {f"{STALE_RUNTIME}.id": "pi"},      # 别的 runtime 不归我们管
    {},                                  # 没有 runtime
], ids=["other-runtime", "no-runtime"])
@needs_bash
@needs_posix
def test_api_route_leaves_other_runtimes_alone(tmp_path, state):
    env = _cli_env(tmp_path, ANTHROPIC_API_KEY="sk-ant-real", CLAUDE_MODEL="anthropic/claude-opus-5")
    del env["EASEL_AGENT_RUNTIME"]
    _, written = _run_auth(tmp_path, oc_state=state, **env)
    assert not any(k.startswith("agents.defaults.models") for k in written), written


# ── setup.sh：收尾的 gateway 启动 + 向导菜单 ────────────────────────────────


@pytest.mark.parametrize("flag,expected", [("true", "restart"), ("false", "start")])
@needs_bash
@needs_posix
def test_setup_sh_restarts_gateway_only_when_needed(tmp_path, flag, expected):
    """gateway.sh start 见到网关活着就直接退出 —— 配置目录改了却只 start，新目录永远不生效。"""
    lines = SETUP_SH.read_text(encoding="utf-8").splitlines()
    step = _slice(lines, 'if [ "$GATEWAY_RESTART_NEEDED" = true ]; then', "fi", keep_end=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gateway.sh").write_text('printf "%s\\n" "$*" >> "$GATEWAY_LOG"\n',
                                                    encoding="utf-8")
    log = tmp_path / "gateway-calls.log"
    script = (f"set -euo pipefail\nPROJECT_ROOT={shlex.quote(str(tmp_path))}\n"
              f"GATEWAY_RESTART_NEEDED={flag}\n{step}\n")
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30,
                          stdin=subprocess.DEVNULL,
                          env={"PATH": os.environ["PATH"], "GATEWAY_LOG": str(log)})
    assert proc.returncode == 0, proc.stderr
    assert log.read_text(encoding="utf-8").split() == [expected]


@pytest.mark.parametrize("live_polls,exit_code,calls", [
    (3, 0, ["stop", "start"]),      # 旧进程几秒后下线 → 等到了再 start
    (999, 1, ["stop"]),             # 一直不下线 → 明说没重启成、非 0 退出，不去 start
], ids=["slow-shutdown", "never-stops"])
@needs_bash
@needs_posix
def test_gateway_restart_waits_for_old_gateway(tmp_path, live_polls, exit_code, calls):
    """stop 后旧进程还在应答 healthz 时，start 会当成「已在运行」直接退出，旧 env 留下来。
    只切 gateway.sh 的 restart 分支来跑：sleep、gateway_live 换成替身，$0 指向记录参数的假脚本。"""
    lines = (PROJECT_ROOT / "scripts" / "gateway.sh").read_text(encoding="utf-8").splitlines()
    branch = _slice(lines, "    restart)", "        ;;", keep_end=True)
    fake_self = tmp_path / "gateway-self"
    fake_self.write_text('#!/bin/sh\necho "$1" >> "$GW_LOG"\n', encoding="utf-8")
    fake_self.chmod(0o755)
    polls = tmp_path / "polls"
    script = textwrap.dedent(f"""
        set -euo pipefail
        sleep() {{ :; }}
        gateway_live() {{
            n=$(cat {shlex.quote(str(polls))} 2>/dev/null || echo 0)
            echo $((n + 1)) > {shlex.quote(str(polls))}
            [ "$n" -lt {live_polls} ]
        }}
    """) + "case restart in\n" + branch + "\nesac\n"
    log = tmp_path / "gw.log"
    proc = subprocess.run(["bash", "-c", script, str(fake_self)], capture_output=True, text=True,
                          errors="replace", timeout=30, stdin=subprocess.DEVNULL,
                          env={"PATH": os.environ["PATH"], "GW_LOG": str(log)})
    assert proc.returncode == exit_code, proc.stderr
    assert log.read_text(encoding="utf-8").split() == calls
    if exit_code:
        assert "NOT restarted" in proc.stderr


def test_setup_sh_wizard_keeps_options_and_adds_claude_cli():
    """向导 1–3 项和默认值原样不动，新增第 4 项。"""
    text = SETUP_SH.read_text(encoding="utf-8")
    menu = [line.strip() for line in text.splitlines() if re.match(r'\s*echo "    \d\) ', line)]
    assert menu == [
        'echo "    1) Anthropic API"',
        'echo "    2) OpenAI / OpenAI-compatible API"',
        'echo "    3) 其他 Anthropic-compatible API"',
        'echo "    4) 本机 Claude Code 登录（Claude CLI，无需 API Key）"',
        'echo "    0) 稍后配置"',
    ]
    assert 'case "${PROVIDER_CHOICE:-1}" in' in text
    option4 = text.split('        4)\n', 1)[1].split(';;', 1)[0]
    assert "EASEL_AGENT_RUNTIME=claude-cli" in option4 and "command -v claude" in option4


@pytest.mark.parametrize("path", [SETUP_SH, PROJECT_ROOT / "scripts" / "gateway.sh",
                                  PROJECT_ROOT / "openclaw" / "sync.sh"], ids=lambda p: p.name)
def test_shell_vars_braced_before_non_ascii(path):
    """`$VAR（` 在 macOS 自带 bash 3.2 + UTF-8 locale 下会把全角字符的字节吞进变量名，
    set -u 当场 unbound variable、整个安装中断（真机 LANG=en_US.UTF-8 实测）。紧跟非 ASCII
    字符的变量一律写成 ${VAR}。注释行不执行，不管。"""
    pattern = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]")
    offenders = [(n, line.strip()) for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if not line.lstrip().startswith("#") and pattern.search(line)]
    assert not offenders, "这些行的变量后面紧跟非 ASCII 字符，要写成 ${VAR}：\n" + \
        "\n".join(f"  {n}: {line}" for n, line in offenders)


# ── doctor：.env 填了 ≠ openclaw 真写了 ────────────────────────────────


def _routable(tmp_path, cfg: dict | None, monkeypatch) -> tuple[bool, str]:
    monkeypatch.setenv("EASEL_OPENCLAW_STATE_DIR", str(tmp_path))
    if cfg is not None:
        (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    return doctor._primary_model_routable()


def _cfg(primary: str, providers: dict) -> dict:
    return {"agents": {"defaults": {"model": {"primary": primary}}},
            "models": {"providers": providers}}


def test_doctor_catches_primary_without_provider(tmp_path, monkeypatch):
    """就是坑 1 留下的残局：primary 指着 openai，但根本没有 openai provider。"""
    ok, detail = _routable(tmp_path, _cfg("openai/deepseek-chat", {}), monkeypatch)
    assert not ok
    assert "models.providers.openai 不存在" in detail


def test_doctor_catches_provider_without_key(tmp_path, monkeypatch):
    ok, detail = _routable(
        tmp_path, _cfg("openai/gpt-4o", {"openai": {"baseUrl": "https://x/v1", "apiKey": ""}}),
        monkeypatch)
    assert not ok and "没有 apiKey" in detail


def test_doctor_catches_missing_primary(tmp_path, monkeypatch):
    ok, _ = _routable(tmp_path, {"models": {"providers": {"openai": {"apiKey": "sk-x"}}}}, monkeypatch)
    assert not ok


def test_doctor_catches_missing_config(tmp_path, monkeypatch):
    ok, detail = _routable(tmp_path, None, monkeypatch)
    assert not ok and "不存在" in detail


@pytest.mark.parametrize("primary,providers", [
    ("openai/gpt-4o", {"openai": {"apiKey": "sk-x"}}),
    # 本地适配器：apiKey 是占位的 local-adapter，靠 localService 起真服务
    ("rednote-openai/gpt-5.5",
     {"rednote-openai": {"apiKey": "local-adapter", "localService": {"command": "python3"}}}),
    # OAuth 型 provider 配置里没有 apiKey，不能误判成坏配置
    ("anthropic/claude-sonnet-4-6", {"anthropic": {"oauthToken": "tok"}}),
    # 非 provider/model 形式：解析不出 provider 就别猜，交给 easel ping
    ("some-bare-model", {}),
])
def test_doctor_passes_valid_configs(tmp_path, monkeypatch, primary, providers):
    ok, detail = _routable(tmp_path, _cfg(primary, providers), monkeypatch)
    assert ok, f"{primary} 被误判为不可路由：{detail}"


# ── doctor：Claude CLI runtime 不走 provider、不要 key，改查 claude 的登录态 ─────────
#
# 现场：agent 跑在 OpenClaw 自带的 claude-cli runtime 上（复用本机 Claude Code 登录），
# openclaw.json 里根本没有 models.providers.anthropic，.env 里也没有 key —— 对话好好的，
# doctor 却报两条 FAIL。CI（ubuntu + windows）上没有真 claude，全部用替身。

CLI_PRIMARY = "anthropic/claude-opus-5"


def _cli_cfg(primary: str = CLI_PRIMARY, env: dict | None = None) -> dict:
    """本机真实形态：模型级 agentRuntime=claude-cli，没有 models.providers.anthropic。"""
    cfg: dict = {"agents": {"defaults": {
        "model": {"primary": primary},
        "models": {primary: {"agentRuntime": {"id": "claude-cli"}}}}}}
    if env is not None:
        cfg["env"] = env
    return cfg


class _FakeClaude:
    """替身：记下 doctor 怎么调 claude，并按预设回 `claude auth status --json`。

    默认的退出码/输出照本机实测：未登录 → 1 + loggedIn=false；已登录 → 0 + loggedIn=true。
    """

    def __init__(self, monkeypatch, *, logged_in: bool = True, path: str | None = "/fake/bin/claude",
                 stdout: str | None = None, returncode: int | None = None,
                 raises: BaseException | None = None):
        self.calls: list[tuple[list[str], dict]] = []
        self.logged_in = logged_in
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setattr(doctor.shutil, "which", lambda name: path if name == "claude" else None)
        monkeypatch.setattr(doctor.subprocess, "run", self._run)

    def _run(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.raises is not None:
            raise self.raises
        out = self.stdout if self.stdout is not None else \
            json.dumps({"loggedIn": self.logged_in, "authMethod": "claude.ai"})
        rc = self.returncode if self.returncode is not None else (0 if self.logged_in else 1)
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")

    @property
    def env(self) -> dict:
        return self.calls[-1][1]["env"]


def test_doctor_claude_cli_logged_in_passes(tmp_path, monkeypatch):
    """本机现场：没有 anthropic provider 也要判可路由，并且真去问了 claude 的登录态。"""
    fake = _FakeClaude(monkeypatch)
    claude_dir = str(tmp_path / "claude-easel")
    cfg = _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": claude_dir}})
    assert _routable(tmp_path, cfg, monkeypatch) == (True, "")
    assert [argv for argv, _ in fake.calls] == [["/fake/bin/claude", "auth", "status", "--json"]]
    # 没有进程级的值时，用 openclaw.json 的 env.vars —— gateway 里的 claude 读的就是这份登录态
    assert fake.env["CLAUDE_CONFIG_DIR"] == claude_dir


def test_doctor_claude_cli_logged_out_fails_with_login_hint(tmp_path, monkeypatch):
    _FakeClaude(monkeypatch, logged_in=False)
    claude_dir = str(tmp_path / "claude easel")      # 带空格：提示里的命令得能直接粘贴
    ok, detail = _routable(tmp_path, _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": claude_dir}}),
                           monkeypatch)
    assert not ok
    assert "claude auth login" in detail
    # 登录命令必须带上 gateway 用的那个配置目录，否则登进去的是另一份
    assert doctor._claude_login_cmd(claude_dir) in detail


# ---- 探测环境要和 gateway 给 claude 的一致 ----

def test_doctor_claude_cli_process_env_beats_config(tmp_path, monkeypatch):
    """OpenClaw 只在进程环境没有这个值时才用配置补，doctor 必须照同一规则。"""
    fake = _FakeClaude(monkeypatch)
    shell_dir = str(tmp_path / "from-shell")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", shell_dir)
    cfg = _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": str(tmp_path / "from-config")}})
    assert _routable(tmp_path, cfg, monkeypatch) == (True, "")
    assert fake.env["CLAUDE_CONFIG_DIR"] == shell_dir


def test_doctor_claude_cli_blank_process_env_counts_as_unset(tmp_path, monkeypatch):
    fake = _FakeClaude(monkeypatch)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "   ")
    claude_dir = str(tmp_path / "from-config")
    assert _routable(tmp_path, _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": claude_dir}}),
                     monkeypatch) == (True, "")
    assert fake.env["CLAUDE_CONFIG_DIR"] == claude_dir


def test_doctor_claude_cli_inline_env_form(tmp_path, monkeypatch):
    """内联的 env.CLAUDE_CONFIG_DIR 同样生效，且与 env.vars 同名时它后处理、胜出。"""
    fake = _FakeClaude(monkeypatch)
    inline, via_vars = str(tmp_path / "inline"), str(tmp_path / "vars")
    _routable(tmp_path, _cli_cfg(env={"CLAUDE_CONFIG_DIR": inline}), monkeypatch)
    assert fake.env["CLAUDE_CONFIG_DIR"] == inline
    _routable(tmp_path, _cli_cfg(env={"CLAUDE_CONFIG_DIR": inline,
                                      "vars": {"CLAUDE_CONFIG_DIR": via_vars}}), monkeypatch)
    assert fake.env["CLAUDE_CONFIG_DIR"] == inline


@pytest.mark.parametrize("value", ["", "   ", "${HOME}/.claude-easel"],
                         ids=["empty", "blank", "env-ref"])
def test_doctor_claude_cli_config_values_openclaw_skips(tmp_path, monkeypatch, value):
    """空白值、带 ${NAME} 引用的值 OpenClaw 整条不注入 —— gateway 的 claude 就没有这个变量。"""
    fake = _FakeClaude(monkeypatch)
    assert _routable(tmp_path, _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": value}}),
                     monkeypatch) == (True, "")
    assert "CLAUDE_CONFIG_DIR" not in fake.env


def test_doctor_claude_cli_skipped_inline_falls_back_to_vars(tmp_path, monkeypatch):
    fake = _FakeClaude(monkeypatch)
    via_vars = str(tmp_path / "vars")
    _routable(tmp_path, _cli_cfg(env={"CLAUDE_CONFIG_DIR": "${CLAUDE_HOME}",
                                      "vars": {"CLAUDE_CONFIG_DIR": via_vars}}), monkeypatch)
    assert fake.env["CLAUDE_CONFIG_DIR"] == via_vars


@pytest.mark.parametrize("value", ["~/.claude-easel", "$HOME/.claude-easel", "claude-easel"])
def test_doctor_claude_cli_relative_config_dir_fails_without_probing(tmp_path, monkeypatch, value):
    """OpenClaw 原样传、claude 也不展开 ~ / $VAR（2.1.285 实测会在当前目录建出字面的 `~/x`）。

    doctor 若自己展开，查的是 gateway 根本不用的目录 —— 假 PASS；照原样去探测，又会在
    当前目录建出字面的 `~` 目录。所以不探测，直接指出要写绝对路径。
    """
    fake = _FakeClaude(monkeypatch)
    ok, detail = _routable(tmp_path, _cli_cfg(env={"vars": {"CLAUDE_CONFIG_DIR": value}}),
                           monkeypatch)
    assert not ok
    assert "绝对路径" in detail and "env.vars.CLAUDE_CONFIG_DIR" in detail
    assert fake.calls == []


def test_doctor_claude_cli_probe_drops_vars_openclaw_clears(tmp_path, monkeypatch):
    """shell 里导出的 key / OAuth token 会让 auth status 报已登录，而 gateway 的 claude 拿不到它们。"""
    fake = _FakeClaude(monkeypatch)
    cleared = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK")
    for key in cleared:
        monkeypatch.setenv(key, "from-doctor-shell")
    monkeypatch.setenv("EASEL_UNRELATED_VAR", "keep-me")
    assert _routable(tmp_path, _cli_cfg(), monkeypatch) == (True, "")
    for key in cleared:
        assert key not in fake.env, f"{key} 没从探测环境里删掉"
    assert fake.env["EASEL_UNRELATED_VAR"] == "keep-me"


def test_claude_cli_clear_env_matches_openclaw_minimum():
    """清单抄自 OpenClaw 2026.9.6 的 CLAUDE_CLI_CLEAR_ENV；认证/传输类一个都不能少，
    而 CLAUDE_CONFIG_DIR 不在其中 —— gateway 的 claude 靠它选登录态。"""
    must_clear = {
        "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_OLD", "ANTHROPIC_API_TOKEN", "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_OAUTH_TOKEN",
        "ANTHROPIC_UNIX_SOCKET", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
        "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
        "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    }
    assert must_clear <= doctor.CLAUDE_CLI_CLEAR_ENV
    assert "CLAUDE_CONFIG_DIR" not in doctor.CLAUDE_CLI_CLEAR_ENV


# ---- 拿不准一律放行：只有明确的 loggedIn=false 才算未登录 ----

@pytest.mark.parametrize("stdout,returncode", [
    ("", 1),                                           # 输出为空
    ("error: unknown option '--json'", 1),             # 老版本不认 --json
    ("not json at all", 0),
    ('{"authMethod": "none"}', 1),                     # 没有 loggedIn
    ('{"loggedIn": "false"}', 1),                      # loggedIn 不是布尔
    ("[false]", 1),                                    # JSON 但不是对象
], ids=["empty", "old-cli", "non-json-exit0", "no-field", "non-bool", "non-object"])
def test_doctor_claude_cli_unclear_status_passes(tmp_path, monkeypatch, stdout, returncode):
    fake = _FakeClaude(monkeypatch, stdout=stdout, returncode=returncode)
    assert _routable(tmp_path, _cli_cfg(), monkeypatch) == (True, "")
    assert len(fake.calls) == 1


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired(["claude"], 20), OSError("boom")],
                         ids=["timeout", "oserror"])
def test_doctor_claude_cli_probe_errors_pass(tmp_path, monkeypatch, exc):
    _FakeClaude(monkeypatch, raises=exc)
    assert _routable(tmp_path, _cli_cfg(), monkeypatch) == (True, "")


def test_doctor_claude_cli_missing_binary_fails(tmp_path, monkeypatch):
    fake = _FakeClaude(monkeypatch, path=None)
    ok, detail = _routable(tmp_path, _cli_cfg(), monkeypatch)
    assert not ok
    assert "PATH" in detail and "claude" in detail
    assert fake.calls == []


@pytest.mark.parametrize("cfg", [
    # 老写法：primary 直接写成 claude-cli/<model>
    _cfg("claude-cli/claude-opus-4-7", {}),
    # 供应商级 runtime：provider 在，但没有 apiKey —— CLI 路线本来就不要 key
    _cfg(CLI_PRIMARY, {"anthropic": {"agentRuntime": {"id": "claude-cli"}}}),
], ids=["legacy-prefix", "provider-scoped"])
def test_doctor_recognizes_other_claude_cli_forms(tmp_path, monkeypatch, cfg):
    fake = _FakeClaude(monkeypatch)
    assert _routable(tmp_path, cfg, monkeypatch) == (True, "")
    assert len(fake.calls) == 1, "没有走 Claude CLI 的登录态检查"

    fake.logged_in = False
    ok, detail = _routable(tmp_path, cfg, monkeypatch)
    assert not ok and "claude auth login" in detail


def test_doctor_provider_route_unchanged_without_runtime(tmp_path, monkeypatch):
    """没配 runtime 的常规 provider 路由照旧：缺 provider 就报，也不去碰 claude。"""
    fake = _FakeClaude(monkeypatch)
    ok, detail = _routable(tmp_path, _cfg(CLI_PRIMARY, {}), monkeypatch)
    assert not ok
    assert "models.providers.anthropic 不存在" in detail
    assert fake.calls == []


@pytest.mark.parametrize("config_dir,os_name,expected", [
    ("", "posix", "claude auth login"),
    ("", "nt", "claude auth login"),
    ("/Users/a/.claude-easel", "posix", "CLAUDE_CONFIG_DIR=/Users/a/.claude-easel claude auth login"),
    ("/Users/a b/it's", "posix", "CLAUDE_CONFIG_DIR='/Users/a b/it'\"'\"'s' claude auth login"),
    (r"C:\Users\a\.claude-easel", "nt", r"$env:CLAUDE_CONFIG_DIR='C:\Users\a\.claude-easel'; claude auth login"),
    (r"C:\Users\it's $x", "nt", r"$env:CLAUDE_CONFIG_DIR='C:\Users\it''s $x'; claude auth login"),
])
def test_claude_login_cmd_is_shell_correct(config_dir, os_name, expected):
    """提示里的命令要能原样粘贴：POSIX 走 shlex.quote，Windows 给 PowerShell 单引号串（不展开 $）。"""
    assert doctor._claude_login_cmd(config_dir, os_name) == expected


@pytest.mark.parametrize("cli_route", [True, False])
def test_cmd_doctor_api_key_line_on_claude_cli_route(tmp_path, monkeypatch, capsys, cli_route):
    """CLI 路线不需要 key：`.env (API Key)` 不能因为 .env 没 key 报 FAIL；常规路线照旧 FAIL。"""
    fake = _FakeClaude(monkeypatch)
    monkeypatch.setenv("EASEL_OPENCLAW_STATE_DIR", str(tmp_path))
    cfg = _cli_cfg() if cli_route else _cfg("openai/gpt-4o", {"openai": {"apiKey": "sk-x"}})
    (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    # 其余检查与本用例无关，且有的会起真进程 / 连真网关 / 真 import 依赖，全部钉死
    monkeypatch.setattr(doctor, "_env_key_valid", lambda: False)
    monkeypatch.setattr(doctor, "_openclaw_version", lambda: (2026, 9, 6))
    monkeypatch.setattr(doctor, "_node_version_ok", lambda strict: True)
    monkeypatch.setattr(doctor, "_module_available", lambda name: True)
    monkeypatch.setattr(doctor, "_chromium_available", lambda: True)
    monkeypatch.setattr(doctor, "_gateway_healthy", lambda: False)
    monkeypatch.setattr(doctor, "_skills_synced", lambda: (True, ""))

    doctor.cmd_doctor(None)
    lines = capsys.readouterr().out.splitlines()
    key_line = next(line for line in lines if line.strip().startswith(".env (API Key)"))
    if cli_route:
        assert "OK" in key_line and "FAIL" not in key_line
        assert any("不需要 API Key" in line for line in lines)
        assert len(fake.calls) == 1, "一次 doctor 只该问一次 claude auth status"
    else:
        assert "FAIL" in key_line
        assert not any("不需要 API Key" in line for line in lines)
        assert fake.calls == []


# ── setup.ps1：-and 必须处在表达式模式 ────────────────────────────────


def test_ps1_logical_and_not_in_command_position():
    """`if (Foo $x -and $y)` 里 -and 会被当成 Foo 的参数名静默吞掉，函数调用必须加括号。"""
    offenders = [
        (n, line) for n, line in enumerate(SETUP_PS1.read_text(encoding="utf-8").splitlines(), 1)
        if not line.lstrip().startswith("#")
        and re.search(r"\(\s*[A-Z]\w*-\w+[^()]*\s-(and|or)\s", line)
    ]
    assert not offenders, "这些行的 -and/-or 处在命令参数位，守卫会被静默丢弃：\n" + \
        "\n".join(f"  {n}: {line.strip()}" for n, line in offenders)


def test_ps1_auth_branches_guard_base_url():
    """三条分支都得真的检查配套的 BASE_URL/ENDPOINT 在不在。"""
    text = SETUP_PS1.read_text(encoding="utf-8")
    for key, companion in [
        ("OPENAI_MAAS_API_KEY", "OPENAI_MAAS_ENDPOINT"),
        ("EASEL_LLM_API_KEY", "EASEL_LLM_BASE_URL"),
        ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"),
    ]:
        pattern = rf"\(\(Is-UsableKey \$envValues\['{key}'\]\) -and " \
                  rf"\$envValues\.ContainsKey\('{companion}'\)\)"
        assert re.search(pattern, text), f"{key} 分支缺少括号化的 {companion} 守卫"


# ── install_tool：别展开、别降级用户 PATH ──────────────────────────────


def _install_tool_code() -> str:
    """只取代码行 —— 注释里会原样引用那两个被淘汰的 API 名来解释「为什么不用」。"""
    src = (PROJECT_ROOT / "skills" / "shared" / "scripts" / "install_tool.py").read_text(encoding="utf-8")
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))


def test_user_path_read_does_not_expand_env_refs():
    """读用户 PATH 必须拿原值：GetEnvironmentVariable 会把 %USERPROFILE% 展开成字面路径。"""
    code = _install_tool_code()
    assert "GetEnvironmentVariable('Path','User')" not in code, \
        "又用回了会展开 %VAR% 的 API"
    assert "DoNotExpandEnvironmentNames" in code, "没有按原值读取用户 PATH"


def test_user_path_write_preserves_value_kind():
    """写回必须沿用原 ValueKind，否则 REG_EXPAND_SZ 会被降级成 REG_SZ。"""
    code = _install_tool_code()
    assert "SetEnvironmentVariable('Path'" not in code, "又用回了固定写 REG_SZ 的 API"
    assert re.search(r"SetValue\('Path',.*\$kind\)", code), "写回时没有沿用原 ValueKind"


def test_user_path_dir_never_interpolated_into_script():
    """目录只能经环境变量递进去：PATH 里一个单引号就能让拼串写法变成代码执行。"""
    sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))
    import install_tool

    assert "$env:EASEL_NEW_DIR" in install_tool._PS_APPEND_USER_PATH
    # 脚本是模块级常量，不带任何格式化占位，不可能把目录拼进去
    assert "%s" not in install_tool._PS_APPEND_USER_PATH
    assert ".format(" not in install_tool._PS_APPEND_USER_PATH


def test_json_output_survives_non_utf8_locale():
    """配方表输出全是中文，stdout 是管道时不能被系统 locale 编码噎死。

    Windows 上 stdout 一旦被面板/agent 捕获，Python 就按 cp936/cp1252 写，中文直接
    UnicodeEncodeError、stdout 一个字节不出 —— 调用方只看到「配方表是空的」，
    安装接口的 id 白名单随之永远为空，装什么都被拒。这里用 PYTHONIOENCODING
    在 Linux 上复现同一条件。
    """
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "skills" / "shared" / "scripts" / "install_tool.py"),
         "--json", "list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert proc.returncode == 0, f"非 UTF-8 locale 下崩了：{proc.stderr[-500:]}"
    ids = {t["id"] for t in json.loads(proc.stdout)["tools"]}
    assert "node" in ids, f"配方表没出来：{ids}"


@pytest.mark.skipif(os.name == "nt", reason="Windows 上这个调用会真改注册表，不能在测试里跑")
def test_user_path_is_noop_off_windows():
    """非 Windows 平台一律不碰系统配置。

    注意别把这条写成无条件跑：`_ensure_user_path` 在 Windows 上是**真的**去改当前
    用户的 PATH 注册表项的，测试里调一次就会把参数里那个假目录永久写进去。
    """
    sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))
    import install_tool

    assert install_tool._ensure_user_path("/tmp/whatever") == "skip"
