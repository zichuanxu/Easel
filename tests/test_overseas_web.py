"""Web 账号页接入海外平台：LOGIN_RUNNERS、/api/accounts 的 region 与不可用原因、登录 / whoami 命令拼装、退出。
不起浏览器、不连平台。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
from overseas import PLATFORMS  # noqa: E402

OVERSEAS = ["tiktok", "youtube", "instagram", "x", "threads"]


def test_login_runners_register_overseas_platforms():
    for key in OVERSEAS:
        cfg = web.LOGIN_RUNNERS[key]
        assert cfg["backend"] == "overseas" and cfg["region"] == "overseas"
        assert cfg["op"] == key
        assert cfg["profile"] == PLATFORMS[key].PROFILE
        assert cfg["name"] == PLATFORMS[key].NAME
    for key, cfg in web.LOGIN_RUNNERS.items():
        if key not in OVERSEAS:
            assert cfg["region"] == "domestic", key
    assert web.OVERSEAS_LOGIN_TIMEOUT == 600


@pytest.fixture
def login_dir(monkeypatch, tmp_path):
    d = tmp_path / "_login"
    d.mkdir()
    monkeypatch.setattr(web, "LOGIN_DIR", d)
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    monkeypatch.setattr(web, "_account_logged_in", lambda *_a: False)   # 不读真机的公众号 / B 站配置
    return d


def test_accounts_api_reports_region(login_dir, monkeypatch):
    monkeypatch.setattr(web, "_can_open_window", lambda: True)
    rows = {r["platform"]: r for r in asyncio.run(web.api_accounts())}
    assert rows["youtube"]["region"] == "overseas" and rows["youtube"]["supported"] is True
    assert rows["xiaohongshu"]["region"] == "domestic"


def test_overseas_unavailable_without_desktop(login_dir, monkeypatch):
    """没桌面（Linux 服务器）：海外登录不可用并说明原因，接口直接 400（Review Focus 4）。"""
    monkeypatch.setattr(web, "_can_open_window", lambda: False)
    rows = {r["platform"]: r for r in asyncio.run(web.api_accounts())}
    assert rows["x"]["supported"] is False
    assert "桌面" in rows["x"]["note"]
    assert rows["xiaohongshu"]["supported"] is True
    with pytest.raises(web.HTTPException) as ei:
        asyncio.run(web.api_login_start("x"))
    assert ei.value.status_code == 400


def test_login_start_runs_overseas_window_login(login_dir, monkeypatch):
    monkeypatch.setattr(web, "_can_open_window", lambda: True)
    captured: dict[str, list[str]] = {}

    class FakePopen:
        def __init__(self, cmd, **_kw):
            captured["cmd"] = list(cmd)
            status = cmd[cmd.index("--status-file") + 1]
            Path(status).write_text(json.dumps({"state": "window_login", "message": "已弹出 Chrome 窗口"}),
                                    encoding="utf-8")

        def poll(self):
            return None

    monkeypatch.setattr(web.subprocess, "Popen", FakePopen)
    res = asyncio.run(web.api_login_start("youtube"))
    assert res["state"] == "window_login"
    cmd = captured["cmd"]
    assert cmd[1].endswith("overseas_publisher.py") and cmd[2] == "login"
    assert cmd[cmd.index("--platform") + 1] == "youtube"
    assert cmd[cmd.index("--timeout") + 1] == "600"


def test_whoami_runs_overseas_script(login_dir, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"loggedIn": True, "name": "Alice", "avatar": ""}), stderr="")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    res = asyncio.run(web.api_account_whoami("threads"))
    assert res["loggedIn"] is True and res["name"] == "Alice"
    assert calls[0][1].endswith("overseas_publisher.py")
    assert calls[0][2:] == ["whoami", "--platform", "threads"]
    marker = json.loads((login_dir / "threads.json").read_text(encoding="utf-8"))
    assert marker["state"] == "success"


def test_logout_removes_overseas_profile(login_dir, monkeypatch, tmp_path):
    profiles = tmp_path / "profiles"
    (profiles / "XProfile").mkdir(parents=True)
    monkeypatch.setattr(web, "BROWSER_PROFILES", profiles)
    (login_dir / "x.json").write_text("{}", encoding="utf-8")
    res = asyncio.run(web.api_logout("x"))
    assert "XProfile" in res["deleted"]
    assert not (profiles / "XProfile").exists()
    assert not (login_dir / "x.json").exists()


@pytest.mark.parametrize("platform,os_name,env,expected", [
    ("darwin", "posix", {}, True),
    ("win32", "nt", {}, True),
    ("linux", "posix", {}, False),
    ("linux", "posix", {"DISPLAY": ":0"}, True),
    ("linux", "posix", {"WAYLAND_DISPLAY": "wayland-0"}, True),
])
def test_can_open_window(platform, os_name, env, expected):
    assert web._can_open_window(platform=platform, env=env, os_name=os_name) is expected


def _outputs_with(tmp_path, monkeypatch, name, data):
    outputs = tmp_path / "outputs"
    (outputs / "proj").mkdir(parents=True)
    (outputs / "proj" / name).write_bytes(data)
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(web, "PUBLISH_DIR", outputs / "_publish")
    return outputs


def test_publish_overseas_runs_async_with_exact_title(monkeypatch, tmp_path):
    """海外平台走异步发布；title 原样传（发布中心对非 YouTube 平台传空，不能被拿正文前 20 字顶上）。"""
    _outputs_with(tmp_path, monkeypatch, "clip.mp4", b"\x00")
    started = {}

    def fake_start(platform, cmd, title, body, cfg, status_file, code_file):
        started.update(platform=platform, cmd=list(cmd), title=title)
        return {"async": True, "pending": True}

    monkeypatch.setattr(web, "_start_async_publish", fake_start)
    req = web.PublishRequest(title="", body="Hello world #ai", media=["proj/clip.mp4"], tags="", visibility="only_me")
    res = asyncio.run(web.api_publish("tiktok", req))
    assert res["async"] is True
    cmd = started["cmd"]
    assert cmd[1].endswith("overseas_publisher.py") and cmd[2] == "publish"
    assert cmd[cmd.index("--platform") + 1] == "tiktok"
    assert cmd[cmd.index("--title") + 1] == ""
    assert cmd[cmd.index("--desc") + 1] == "Hello world #ai"
    assert cmd[cmd.index("--visibility") + 1] == "only_me"
    assert cmd[cmd.index("--media") + 1].endswith("clip.mp4")
    assert "--exec" in cmd and "--status-file" in cmd


def test_second_publish_same_platform_while_running_is_409(monkeypatch, tmp_path):
    """同一平台上一条还在发：第二次请求直接 409。排队等登录目录锁会在第一条发完后把同一条再发一遍（Final review 3）。"""
    _outputs_with(tmp_path, monkeypatch, "clip.mp4", b"\x00")
    release = threading.Event()
    runs: list[str] = []

    def fake_bg(platform, *_a):
        runs.append(platform)
        release.wait(5)

    monkeypatch.setattr(web, "_run_publish_bg", fake_bg)
    monkeypatch.setattr(web, "_PUBLISH_THREADS", {}, raising=False)
    req = web.PublishRequest(body="Hello", media=["proj/clip.mp4"])
    try:
        assert asyncio.run(web.api_publish("x", req))["async"] is True
        with pytest.raises(web.HTTPException) as ei:
            asyncio.run(web.api_publish("x", req))
        assert ei.value.status_code == 409 and "正在发布" in ei.value.detail
        assert asyncio.run(web.api_publish("threads", req))["async"] is True     # 别的平台不受影响
    finally:
        release.set()
    for t in list(web._PUBLISH_THREADS.values()):
        t.join(5)
    assert asyncio.run(web.api_publish("x", req))["async"] is True               # 上一条结束后可以再发
    assert runs.count("x") == 2


def test_publish_overseas_requires_video_for_now(monkeypatch, tmp_path):
    _outputs_with(tmp_path, monkeypatch, "a.png", b"\x89PNG")
    for platform in OVERSEAS:
        with pytest.raises(web.HTTPException) as ei:
            asyncio.run(web.api_publish(platform, web.PublishRequest(body="hi", media=["proj/a.png"])))
        assert ei.value.status_code == 400
