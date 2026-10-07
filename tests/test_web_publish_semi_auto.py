"""Web 发布页的半自动 / 发布闸门集成：国内浏览器平台异步发布 + awaiting_user_click 状态、
exit 8/9 的中文终态、B站走 bili_upload.py、allowRepost 透传、浏览器注册表与发布脚本一致。
全程假子进程 / 假状态文件，不开浏览器、不连平台。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
import real_browser  # noqa: E402


@pytest.fixture
def pub_env(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    (outputs / "proj").mkdir(parents=True)
    (outputs / "proj" / "clip.mp4").write_bytes(b"\x00")
    (outputs / "proj" / "a.png").write_bytes(b"\x00")
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(web, "PUBLISH_DIR", outputs / "_publish")
    monkeypatch.setattr(web, "_PUBLISH_THREADS", {}, raising=False)
    monkeypatch.setattr(web, "_read_schedule", lambda: [])
    monkeypatch.setattr(web, "_write_schedule", lambda items: None)
    return outputs


def _capture_start(monkeypatch):
    got: dict = {}

    def fake_start(platform, cmd, title, body, cfg, status_file, code_file, **kw):
        got.update(platform=platform, cmd=list(cmd), status_file=status_file, kw=kw)
        return {"async": True, "pending": True}

    monkeypatch.setattr(web, "_start_async_publish", fake_start)
    return got


@pytest.mark.parametrize("platform,script,media", [
    ("xiaohongshu", "xhs_publish.py", "proj/a.png"),
    ("kuaishou", "web_publisher.py", "proj/clip.mp4"),
    ("weixin-channels", "web_publisher.py", "proj/clip.mp4"),
    ("zhihu", "web_publisher.py", "proj/a.png"),
])
def test_domestic_browser_platforms_publish_async_with_handoff(pub_env, monkeypatch, platform, script, media):
    got = _capture_start(monkeypatch)
    req = web.PublishRequest(title="T", body="正文", media=[media], allowRepost=True)
    res = asyncio.run(web.api_publish(platform, req))
    assert res["async"] is True
    cmd = got["cmd"]
    assert cmd[1].endswith(script) and "--exec" in cmd
    assert cmd[cmd.index("--status-file") + 1] == str(got["status_file"])
    assert float(cmd[cmd.index("--handoff-timeout") + 1]) == web.PUBLISH_HANDOFF_TIMEOUT
    assert "--allow-repost" in cmd
    # 总预算必须覆盖人工交接窗口，否则等人点发布时会被后台线程掐断
    assert got["kw"]["timeout"] > web.PUBLISH_HANDOFF_TIMEOUT


def test_allow_repost_not_passed_by_default(pub_env, monkeypatch):
    got = _capture_start(monkeypatch)
    asyncio.run(web.api_publish("zhihu", web.PublishRequest(title="T", body="正文")))
    assert "--allow-repost" not in got["cmd"]


def test_douyin_gets_allow_repost_and_handoff(pub_env, monkeypatch):
    got = _capture_start(monkeypatch)
    asyncio.run(web.api_publish("douyin", web.PublishRequest(title="T", body="b", media=["proj/clip.mp4"],
                                                             allowRepost=True)))
    assert "--allow-repost" in got["cmd"] and "--handoff-timeout" in got["cmd"]
    assert got["kw"]["timeout"] > web.PUBLISH_HANDOFF_TIMEOUT


def test_overseas_allow_repost(pub_env, monkeypatch):
    got = _capture_start(monkeypatch)
    asyncio.run(web.api_publish("x", web.PublishRequest(body="hi", allowRepost=True)))
    assert "--allow-repost" in got["cmd"]


def _run_bg(monkeypatch, tmp_path, rc, stderr="", stdout="", prior_status=None):
    status_file = tmp_path / "outputs" / "_publish" / "zhihu.json"
    monkeypatch.setattr(web, "PUBLISH_DIR", status_file.parent)
    status_file.unlink(missing_ok=True)   # 真实流程里 _start_async_publish 会先清成 starting
    web._write_publish_status(status_file, *(prior_status or ("starting", "")))
    monkeypatch.setattr(web.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], rc, stdout, stderr))
    web._run_publish_bg("zhihu", ["x"], "T", "b", web.LOGIN_RUNNERS["zhihu"], status_file,
                        status_file.with_suffix(".code"), 60)
    return web._read_publish_status("zhihu")


def test_bg_duplicate_exit8_becomes_duplicate_state(pub_env, monkeypatch, tmp_path):
    err = ("⛔ 检测到重复发布：知乎 在 2026-10-01 已发过标题相同的内容。\n"
           "   上一条：「T」（来源：publish-page）\n"
           "   默认不重复发布。仅当用户在对话中明确要求「再发一次同样的内容」时，才可加 --allow-repost；\n")
    st = _run_bg(monkeypatch, tmp_path, 8, stderr=err)
    assert st["state"] == "duplicate"
    assert "检测到重复发布" in st["message"] and "上一条" in st["message"]
    assert "--allow-repost" not in st["message"] and "⛔" not in st["message"]


def test_bg_cooldown_exit9_becomes_cooldown_state(pub_env, monkeypatch, tmp_path):
    err = ("⛔ 知乎 当前处于冷却期，已停止发布。\n   原因：平台处罚\n"
           "   不要重试、不要换方式绕过。请先把情况告知用户\n")
    st = _run_bg(monkeypatch, tmp_path, 9, stderr=err)
    assert st["state"] == "cooldown"
    assert "冷却期" in st["message"] and "不要重试" not in st["message"]


def test_bg_cooldown_keeps_script_written_message(pub_env, monkeypatch, tmp_path):
    st = _run_bg(monkeypatch, tmp_path, 9, prior_status=("error", "知乎 提示处罚/限制：账号异常。已设为冷却"))
    assert st["state"] == "cooldown" and "账号异常" in st["message"]


def test_bg_success_and_error_fallback(pub_env, monkeypatch, tmp_path):
    assert _run_bg(monkeypatch, tmp_path, 0)["state"] == "success"
    assert _run_bg(monkeypatch, tmp_path, 1, stderr="boom")["state"] == "error"


def test_bg_awaiting_state_is_not_clobbered_by_fallback_mid_run(pub_env, monkeypatch, tmp_path):
    """脚本写的 awaiting_user_click 是非终态；进程正常退出且脚本没写终态时兜底补成终态。"""
    st = _run_bg(monkeypatch, tmp_path, 0, prior_status=("awaiting_user_click", "请点发布"))
    assert st["state"] == "success"


def test_bilibili_goes_through_bili_upload_guard(pub_env, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    req = web.PublishRequest(title="标题", body="简介", media=["proj/clip.mp4"], tags="AI，教程", allowRepost=True)
    res = asyncio.run(web.api_publish("bilibili", req))
    cmd = seen["cmd"]
    assert res["ok"] is True
    assert "biliup" not in cmd[0] and cmd[1].endswith("bili_upload.py") and cmd[2] == "upload"
    assert "--exec" in cmd and "--allow-repost" in cmd
    assert cmd[cmd.index("--tid") + 1] == "36" and cmd[cmd.index("--tag") + 1] == "AI,教程"
    assert cmd[cmd.index("--cookie") + 1].endswith("cookies.json")


@pytest.mark.parametrize("rc,key", [(8, "duplicate"), (9, "cooldown")])
def test_bilibili_guard_exit_surfaces_message(pub_env, monkeypatch, rc, key):
    err = "⛔ 检测到重复发布：B站 已发过。\n   上一条：「T」\n" if rc == 8 else "⛔ B站 当前处于冷却期，已停止发布。\n"
    monkeypatch.setattr(web.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, rc, "", err))
    res = asyncio.run(web.api_publish("bilibili", web.PublishRequest(title="T", media=["proj/clip.mp4"])))
    assert res["ok"] is False and res[key] is True
    assert ("重复发布" if rc == 8 else "冷却期") in res["message"]


def test_status_endpoint_returns_new_states(pub_env):
    web._write_publish_status(web.PUBLISH_DIR / "zhihu.json", "awaiting_user_click", "请点发布")
    r = asyncio.run(web.api_publish_status("zhihu"))
    assert r["state"] == "awaiting_user_click" and r["message"] == "请点发布"


# ── 浏览器注册表与发布脚本一致 ─────────────────────────────────────────────


def test_real_browser_registry_matches_publishers():
    import douyin_publish
    import xhs_publish
    import web_publisher
    reg = real_browser.PLATFORMS
    assert reg["xiaohongshu"]["profile"] == xhs_publish.PROFILE_NAME
    assert reg["douyin"]["profile"] == douyin_publish.PROFILE_NAME
    assert reg["douyin"]["headless_env"] == douyin_publish.HEADLESS_ENV
    assert reg["douyin"]["browser_env"] == douyin_publish.BROWSER_ENV
    assert reg["xiaohongshu"]["fingerprint_file"] == xhs_publish.FINGERPRINT_FILE
    for key, cfg in web_publisher.PLATFORMS.items():
        assert reg[key]["profile"] == cfg["profile"], key
        assert reg[key]["headless_env"] == f"EASEL_{cfg['env_prefix']}_HEADLESS", key
        assert reg[key]["browser_env"] == f"EASEL_{cfg['env_prefix']}_BROWSER", key
        assert reg[key]["label"] == cfg["name"], key
    for key, cfg in reg.items():
        assert cfg["fingerprint_file"] == real_browser.FINGERPRINT_FILE
        assert web.LOGIN_RUNNERS[key]["profile"] == cfg["profile"], key


def test_launch_platform_uses_registry(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(real_browser, "launch", lambda p, **kw: seen.update(kw) or "ctx")
    assert real_browser.launch_platform(object(), "douyin", headed=False, base=str(tmp_path)) == "ctx"
    assert seen["profile_dir"] == tmp_path / "DouyinProfile"
    assert seen["headless_env"] == "EASEL_DOUYIN_HEADLESS" and seen["browser_env"] == "EASEL_DOUYIN_BROWSER"


def test_scrapers_use_publisher_engine():
    """account_stats / zhihu_comments_fetch 的非小红书抓取必须走 real_browser（同引擎同登录目录）。"""
    import account_stats
    import inspect
    import zhihu_comments_fetch
    assert "launch_platform" in inspect.getsource(account_stats._scrape)
    assert "chromium.launch_persistent_context" not in inspect.getsource(account_stats._scrape)
    assert "launch_platform" in inspect.getsource(zhihu_comments_fetch.fetch_comments)
    for key, cfg in account_stats.PLATFORMS.items():
        assert cfg["profile"] == real_browser.PLATFORMS[key]["profile"], key
    assert zhihu_comments_fetch.PROFILE_DIR.name == "ZhihuProfile"


@pytest.mark.parametrize("prior", [("success", "检测到已发布。"), ("verifying", "已检测到发布，正在核对…"),
                                   ("awaiting_user_click", "等你点发布")])
def test_bg_nonzero_exit_overrides_success_or_pending_to_error(pub_env, monkeypatch, tmp_path, prior):
    """脚本退出码非 0：即便状态文件写着 success / verifying，也必须落成终态 error。"""
    st = _run_bg(monkeypatch, tmp_path, 5, stderr="ERROR: 读回未见本次内容", prior_status=prior)
    assert st["state"] == "error" and "未确认" in st["message"]


def test_bg_nonzero_exit_keeps_script_written_error_reason(pub_env, monkeypatch, tmp_path):
    st = _run_bg(monkeypatch, tmp_path, 5, prior_status=("error", "快手读回未核实：列表无本次内容"))
    assert st["state"] == "error" and "快手读回未核实" in st["message"]


def test_bg_exit0_with_stale_verifying_becomes_success(pub_env, monkeypatch, tmp_path):
    st = _run_bg(monkeypatch, tmp_path, 0, prior_status=("verifying", "已检测到发布，正在核对…"))
    assert st["state"] == "success"


def test_verifying_is_not_a_terminal_publish_state():
    assert "verifying" not in web._PUBLISH_TERMINAL_STATES
