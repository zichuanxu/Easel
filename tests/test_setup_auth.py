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


def _run_auth(tmp_path: Path, **env: str) -> tuple[str, dict[str, str]]:
    """跑认证段，返回 (stdout, 实际写进 openclaw 的配置)。"""
    calls = tmp_path / "oc-calls.log"
    script = textwrap.dedent(f"""
        set -u
        PROJECT_ROOT={tmp_path}
        CFG={calls}
        : > "$CFG"
        ok()   {{ echo "OK|$*"; }}
        warn() {{ echo "WARN|$*"; }}
        oc_write_anthropic() {{ echo "models.providers.anthropic.baseUrl = $1" >> "$CFG"; }}
        _oc() {{
            if [ "${{1:-}}" = "config" ] && [ "${{2:-}}" = "set" ]; then
                echo "$3 = $4" >> "$CFG"
            fi
            return 0
        }}
        OC=_oc
    """) + "\n" + _auth_block()

    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          timeout=60, env={"PATH": os.environ["PATH"], **env})
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
