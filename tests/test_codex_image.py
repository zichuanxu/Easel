"""Codex CLI 生图后端：命令拼装、按 thread_id 取图、失败给出可读原因、设置页状态。

全程替换 subprocess.run，不启动真实 codex、不调用任何模型，不读写用户的 ~/.codex 和 .env。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import ai_image  # noqa: E402
import app as web  # noqa: E402
import codex_image as ci  # noqa: E402
import model_registry  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def _cfg(tmp_path: Path, **kw) -> ci.CodexConfig:
    base = {"bin": "/fake/codex", "model": ci.DEFAULT_MODEL, "timeout": 30, "home": tmp_path / "codex-home"}
    base.update(kw)
    return ci.CodexConfig(**base)


class FakeRun:
    """替身 codex_image._run：记录命令；按 thread_id 往 CODEX_HOME 落一张图（或不落）。"""

    def __init__(self, home: Path, *, write_image=True, events=None, returncode=0, stderr=""):
        self.home, self.write_image, self.events = home, write_image, events
        self.returncode, self.stderr, self.calls = returncode, stderr, []

    def __call__(self, cmd, timeout, cwd):
        self.calls.append((cmd, {"timeout": timeout, "cwd": cwd}))
        tid = f"thread-{len(self.calls)}"
        if self.write_image:
            d = self.home / "generated_images" / tid
            d.mkdir(parents=True, exist_ok=True)
            (d / f"exec-{len(self.calls)}.png").write_bytes(PNG)
        events = self.events if self.events is not None else [
            {"type": "thread.started", "thread_id": tid},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "图片已生成，但工具未返回路径。"}},
        ]
        stdout = "Reading additional input from stdin...\n" + "\n".join(json.dumps(e) for e in events)
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=stdout, stderr=self.stderr)


# ── 配置 ───────────────────────────────────────────────────

def test_default_model_is_gpt_6_1_sol_and_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "find_codex", lambda explicit=None: "/fake/codex")
    assert ci.load_config({}).model == "gpt-6.1-sol"
    cfg = ci.load_config({"IMG_CODEX_MODEL": " gpt-6-sol ", "IMG_CODEX_TIMEOUT": "90",
                          "CODEX_HOME": str(tmp_path)})
    assert (cfg.model, cfg.timeout, cfg.home) == ("gpt-6-sol", 90, tmp_path)


def test_bad_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(ci, "find_codex", lambda explicit=None: "/fake/codex")
    for bad in ("abc", "0", "-5", ""):
        assert ci.load_config({"IMG_CODEX_TIMEOUT": bad}).timeout == ci.DEFAULT_TIMEOUT


def test_missing_codex_gives_install_hint(monkeypatch):
    monkeypatch.setattr(ci, "find_codex", lambda explicit=None: None)
    with pytest.raises(ci.CodexImageError, match="npm i -g @openai/codex"):
        ci.load_config({})


def test_find_codex_explicit_path_only_accepts_a_file(tmp_path):
    f = tmp_path / "codex"
    f.write_text("x", encoding="utf-8")
    assert ci.find_codex(str(f)) == str(f)
    assert ci.find_codex(str(tmp_path / "nope")) is None


def test_find_codex_falls_back_to_install_dirs_when_path_is_bare(tmp_path, monkeypatch):
    bindir = tmp_path / "local-bin"
    bindir.mkdir()
    exe = bindir / ("codex.exe" if os.name == "nt" else "codex")
    exe.write_text("x", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(ci, "_candidate_dirs", lambda: [tmp_path / "missing", bindir])
    assert os.path.normcase(ci.find_codex() or "") == os.path.normcase(str(exe))


def test_quick_status_needs_login(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "find_codex", lambda explicit=None: "/fake/codex")
    assert ci.quick_status({"CODEX_HOME": str(tmp_path)}) == (False, "未登录（终端运行 codex login）")
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")
    assert ci.quick_status({"CODEX_HOME": str(tmp_path)}) == (True, "已配置")
    monkeypatch.setattr(ci, "find_codex", lambda explicit=None: None)
    assert ci.quick_status({})[0] is False


# ── 提示词 ─────────────────────────────────────────────────

def test_prompt_is_one_line_and_carries_orientation():
    p = ci.build_prompt("第一行\n第二行", "1024x1536", edit=False)
    assert "\n" not in p and "第一行 第二行" in p and "竖版" in p and "恰好一张" in p
    assert "横版" in ci.orientation("16:9") and "方形" in ci.orientation("1024x1024")
    assert "方形" in ci.orientation("auto")
    assert "以附带的图片为基础" in ci.build_prompt("改成夜景", "1:1", edit=True)


# ── 生成 ───────────────────────────────────────────────────

def test_generate_one_finds_image_by_thread_id_even_without_path_in_reply(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    fake = FakeRun(cfg.home)
    monkeypatch.setattr(ci, "_run", fake)
    out = ci.generate_one(cfg, "一只猫", "1024x1536")
    assert out.read_bytes() == PNG and out.parent.name == "thread-1"
    cmd, kw = fake.calls[0]
    assert cmd[:2] == ["/fake/codex", "exec"]
    for flag in ("--ephemeral", "--skip-git-repo-check", "--json"):
        assert flag in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("-m") + 1] == "gpt-6.1-sol"
    assert kw["timeout"] == 30
    assert not any(c.startswith("--image") for c in cmd)


def test_edit_passes_image_with_equals_form(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.png"
    src.write_bytes(PNG)
    fake = FakeRun(cfg.home)
    monkeypatch.setattr(ci, "_run", fake)
    ci.generate_one(cfg, "改成夜景", "1:1", image=str(src))
    cmd = fake.calls[0][0]
    img_args = [c for c in cmd if c.startswith("--image")]
    assert img_args == [f"--image={src.resolve()}"]      # 不能用 -i：它会把 prompt 也吞成图片
    assert cmd[-1].startswith("以附带的图片为基础")


def test_generate_n_runs_once_per_image(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    fake = FakeRun(cfg.home)
    monkeypatch.setattr(ci, "_run", fake)
    outs = ci.generate(cfg, "猫", 3, "1:1")
    assert len(fake.calls) == 3 and len({o.parent.name for o in outs}) == 3


def test_no_image_reports_codex_error_and_reply(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    fake = FakeRun(cfg.home, write_image=False, returncode=1, stderr="boom", events=[
        {"type": "thread.started", "thread_id": "t"},
        {"type": "turn.failed", "error": {"message": "usage limit reached"}},
    ])
    monkeypatch.setattr(ci, "_run", fake)
    with pytest.raises(ci.CodexImageError, match="usage limit reached"):
        ci.generate_one(cfg, "猫", "1:1")


def test_timeout_is_a_readable_error(tmp_path, monkeypatch):
    def slow(cmd, timeout, cwd):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(ci, "_run", slow)
    with pytest.raises(ci.CodexImageError, match="IMG_CODEX_TIMEOUT"):
        ci.generate_one(_cfg(tmp_path), "猫", "1:1")


def test_old_images_in_thread_dir_are_not_reused(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    old = cfg.home / "generated_images" / "thread-1" / "old.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(PNG)
    os.utime(old, (1, 1))
    monkeypatch.setattr(ci, "_run", FakeRun(cfg.home, write_image=False))
    with pytest.raises(ci.CodexImageError):
        ci.generate_one(cfg, "猫", "1:1")


# ── ai_image.py 分派 ───────────────────────────────────────

def test_use_codex_follows_mode_then_img_provider(monkeypatch):
    monkeypatch.delenv("IMG_PROVIDER", raising=False)
    assert ai_image.use_codex(None) is False
    assert ai_image.use_codex("codex") is True
    monkeypatch.setenv("IMG_PROVIDER", "codex-cli")
    assert ai_image.use_codex(None) is True
    assert ai_image.use_codex("sync") is False          # 显式 --mode 优先


def test_text2img_via_codex_copies_into_output(tmp_path, monkeypatch):
    src = tmp_path / "gen.png"
    src.write_bytes(PNG)
    monkeypatch.setenv("IMG_PROVIDER", "codex-cli")
    monkeypatch.setattr(ci, "load_config", lambda env=None: _cfg(tmp_path))
    monkeypatch.setattr(ci, "generate", lambda cfg, prompt, n, size, image=None, log=None: [src] * n)
    args = ai_image.parse_args(["text2img", "--prompt", "猫", "--n", "2", "--output", str(tmp_path / "out")])
    ai_image.cmd_text2img(args)
    outs = sorted((tmp_path / "out").glob("image-*.png"))
    assert len(outs) == 2 and all(o.read_bytes() == PNG for o in outs)


def test_codex_failure_exits_with_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ci, "load_config", lambda env=None: (_ for _ in ()).throw(ci.CodexImageError("找不到 codex 命令。")))
    args = ai_image.parse_args(["text2img", "--mode", "codex", "--prompt", "猫", "--output", str(tmp_path / "a.png")])
    with pytest.raises(SystemExit):
        ai_image.cmd_text2img(args)
    assert "找不到 codex" in capsys.readouterr().err


def test_check_reports_codex_readiness(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("IMG_PROVIDER", "codex-cli")
    monkeypatch.setattr(ci, "load_config", lambda env=None: _cfg(tmp_path))
    monkeypatch.setattr(ci, "login_status", lambda cfg: (False, "Not logged in"))
    with pytest.raises(SystemExit) as exc:
        ai_image.cmd_check(ai_image.parse_args(["check"]))
    assert exc.value.code == 2 and "codex login" in capsys.readouterr().out
    monkeypatch.setattr(ci, "login_status", lambda cfg: (True, "Logged in using ChatGPT"))
    ai_image.cmd_check(ai_image.parse_args(["check"]))
    assert "[就绪]" in capsys.readouterr().out


# ── 注册表与设置页 ─────────────────────────────────────────

def test_registry_lists_codex_only_when_selected():
    ids = lambda env: [p["id"] for p in model_registry.configured_providers("image", env)]  # noqa: E731
    assert "codex-cli" not in ids({})
    assert "codex-cli" in ids({"IMG_PROVIDER": "codex-cli"})


def _image_rows(tmp_path, monkeypatch, env_text: str, status=(True, "已配置")):
    env_file = tmp_path / ".env"
    env_file.write_text(env_text, encoding="utf-8")
    monkeypatch.setattr(web, "ENV_FILE", env_file)
    monkeypatch.setattr(ci, "quick_status", lambda env=None: status)
    return {r["slot"]: r for r in web._model_channels()["channels"]["image"]["rows"]}


def test_settings_image_channel_defaults_to_api_as_main(tmp_path, monkeypatch):
    rows = _image_rows(tmp_path, monkeypatch, "")
    assert rows["openai"]["role"] == "主" and rows["codex-cli"]["role"] == "备"
    codex = rows["codex-cli"]
    assert codex["keyless"] is True and codex["keyMasked"] == "免 key"
    assert codex["modelHint"].startswith("gpt-6.1-sol") and codex["model"] == ""


def test_settings_image_channel_codex_main_and_status(tmp_path, monkeypatch):
    rows = _image_rows(tmp_path, monkeypatch, "IMG_PROVIDER=codex-cli\nIMG_CODEX_MODEL=gpt-6-sol\n",
                       status=(False, "未登录（终端运行 codex login）"))
    assert rows["codex-cli"]["role"] == "主" and rows["openai"]["role"] == "备"
    assert rows["codex-cli"]["result"].startswith("未登录")
    assert rows["codex-cli"]["model"] == "gpt-6-sol"


def test_skill_page_does_not_count_unselected_codex_as_configured():
    assert web._skill_api_configured("ai-image-gen", {}) is False
    assert web._skill_api_configured("ai-image-gen", {"IMG_PROVIDER": "codex-cli"}) is True
    # 电商配图用自带脚本，不支持 Codex：既不列出，也不因选了 Codex 就算已配置
    ecom = web.SKILL_API_REQUIREMENTS["ecom-details-image"]
    assert [p["id"] for p in ecom["providers"]] == ["openai"]
    assert web._skill_api_configured("ecom-details-image", {"IMG_PROVIDER": "codex-cli"}) is False
    # 论文解读全 key 可选，仍然算已配置
    assert web._skill_api_configured("paper-explainer", {}) is True


def test_save_image_channel_writes_img_provider(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(web, "ENV_FILE", env_file)
    monkeypatch.setenv("EASEL_OPENCLAW_STATE_DIR", str(tmp_path / "openclaw-state"))
    monkeypatch.setattr(ci, "quick_status", lambda env=None: (True, "已配置"))
    local = "http://127.0.0.1:7860"
    with TestClient(web.app, base_url=local, client=("127.0.0.1", 51234), headers={"Origin": local}) as c:
        r = c.post("/api/settings/models/save", json={"channel": "image", "rows": [
            {"slot": "openai"}, {"slot": "codex-cli", "model": "gpt-6-sol", "primary": True}]})
    assert r.status_code == 200, r.text
    text = env_file.read_text(encoding="utf-8")
    assert "IMG_PROVIDER=codex-cli" in text and "IMG_CODEX_MODEL=gpt-6-sol" in text
    rows = {x["slot"]: x for x in r.json()["channels"]["image"]["rows"]}
    assert rows["codex-cli"]["role"] == "主"


# ── 进程与平台细节 ─────────────────────────────────────────

def test_run_returns_output_with_stdin_closed(tmp_path):
    code = "import sys; print('in=' + repr(sys.stdin.read()))"
    r = ci._run([sys.executable, "-c", code], 30, str(tmp_path))
    assert r.returncode == 0 and "in=''" in r.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX 进程组；Windows 走 taskkill /T")
def test_run_timeout_kills_grandchildren(tmp_path):
    import time
    pidfile = tmp_path / "grandchild.pid"
    code = ("import subprocess, sys, time; "
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            f"open({str(pidfile)!r}, 'w').write(str(g.pid)); time.sleep(60)")
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        ci._run([sys.executable, "-c", code], 2, str(tmp_path))
    assert time.time() - t0 < 20            # 孙进程攥着管道也不会卡住
    gpid = int(pidfile.read_text())
    for _ in range(30):
        try:
            os.kill(gpid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("孙进程还活着：超时没有结束整棵进程树")


def test_windows_cmd_shim_gets_metachars_neutralised(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_WINDOWS", True)
    cfg = _cfg(tmp_path, bin=r"C:\npm\codex.cmd")
    fake = FakeRun(cfg.home)
    monkeypatch.setattr(ci, "_run", fake)
    ci.generate_one(cfg, 'cat" & calc & "%PATH%', "1:1")
    prompt = fake.calls[0][0][-1]
    assert not any(c in prompt for c in '"&%') and "＆ calc" in prompt
    bad = tmp_path / "a&b.png"
    bad.write_bytes(PNG)
    with pytest.raises(ci.CodexImageError, match="改名"):
        ci.generate_one(cfg, "改图", "1:1", image=str(bad))


def test_windows_prefers_native_exe_over_cmd_shim(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_WINDOWS", True)
    shim = tmp_path / "codex.cmd"
    shim.write_text("@echo off", encoding="utf-8")
    exe = tmp_path / "node_modules" / "@openai" / "codex" / "vendor" / "x86_64-pc-windows-msvc" / "codex" / "codex.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    assert ci._prefer_exe(str(shim)) == str(exe)
    assert ci._prefer_exe(str(tmp_path / "codex.exe")) == str(tmp_path / "codex.exe")


def test_falls_back_to_path_mentioned_in_reply(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    img = tmp_path / "elsewhere" / "out.png"
    img.parent.mkdir()
    img.write_bytes(PNG)
    fake = FakeRun(cfg.home, write_image=False, events=[
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": f"已保存到 {img}。"}},
    ])
    monkeypatch.setattr(ci, "_run", fake)
    assert ci.generate_one(cfg, "猫", "1:1") == img


def test_login_status_reads_exit_code(tmp_path, monkeypatch):
    def fake(cmd, **kw):
        ok = cmd[-2:] == ["login", "status"]
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, stdout="Logged in using ChatGPT\n", stderr="")
    monkeypatch.setattr(ci.subprocess, "run", fake)
    assert ci.login_status(_cfg(tmp_path)) == (True, "Logged in using ChatGPT")
    monkeypatch.setattr(ci.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="Not logged in", stderr=""))
    assert ci.login_status(_cfg(tmp_path)) == (False, "Not logged in")


def test_copy_image_converts_format_when_extension_differs(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "src.png"
    Image.new("RGBA", (4, 4), (255, 0, 0, 128)).save(src)
    same = ai_image._copy_image(src, tmp_path / "a.png")
    assert same.read_bytes() == src.read_bytes()
    jpg = ai_image._copy_image(src, tmp_path / "b.jpg")
    assert jpg.suffix == ".jpg"
    with Image.open(jpg) as im:
        assert im.format == "JPEG"


def test_skill_drawer_ready_flag_follows_selection():
    spec = {p["id"]: p for p in web._api_spec_status("ai-image-gen", {})["providers"]}
    assert spec["codex-cli"]["ready"] is False
    spec = {p["id"]: p for p in web._api_spec_status("ai-image-gen", {"IMG_PROVIDER": "codex-cli"})["providers"]}
    assert spec["codex-cli"]["ready"] is True
