"""扫码登录进行中，账号校验（whoami）不能把登录 runner 的实时状态删掉（不起真浏览器、不连平台）。

钉住的真机现场（视频号）：账号页一打开就在后台对视频号跑 whoami（起无头浏览器，十几秒），
用户紧接着点「扫码登录」。runner 截好二维码、写了 qr_ready；whoami 随后得出「未登录」（确实还没扫），
按「确认未登录就删登录标记」把 outputs/_login/weixin-channels.json 删了 —— 可这个文件同时是 runner
的实时状态文件。后端从此读到 unknown，弹窗一直「等待中… / 准备二维码…」，直到 runner 超时写 expired。
无头 Chromium 允许两个进程同时打开同一个 profile，所以两边谁也拦不住谁。
"""
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

import app as web  # noqa: E402

PF = "weixin-channels"


class FakeProc:
    """poll() 依次返回 codes 里的值，用完后停在最后一个。"""

    def __init__(self, *codes: int | None):
        self.codes = list(codes) or [None]

    def poll(self):
        return self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]


def _write_status(d: Path, state: str, message: str = "") -> None:
    (d / f"{PF}.json").write_text(
        json.dumps({"state": state, "message": message, "qr": "", "ts": 0}), encoding="utf-8")


def _state(d: Path) -> str | None:
    f = d / f"{PF}.json"
    return json.loads(f.read_text(encoding="utf-8"))["state"] if f.is_file() else None


@pytest.fixture
def env(monkeypatch, tmp_path):
    d = tmp_path / "_login"
    d.mkdir()
    monkeypatch.setattr(web, "LOGIN_DIR", d)
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    calls: list[list[str]] = []
    answer = {"loggedIn": False, "name": "", "avatar": ""}
    during: list = []   # 子进程「跑着」的时候要发生的事（模拟并发）

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        for fn in during:
            fn()
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(answer), stderr="")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    return d, calls, answer, during


def _whoami() -> dict:
    return asyncio.run(web.api_account_whoami(PF))


def _start_runner(d: Path) -> None:
    web.LOGIN_PROCESSES[PF] = FakeProc(None)
    (d / f"{PF}.png").write_bytes(b"\x89PNG qr")
    _write_status(d, "qr_ready", "扫码登录 微信视频号")


def test_whoami_during_login_leaves_runner_alone(env):
    """等扫码时校验：不起第二个浏览器、不删状态文件，弹窗照常拿到 qr_ready + 二维码。"""
    d, calls, _answer, _during = env
    _start_runner(d)
    res = _whoami()
    assert calls == []
    assert res["loggedIn"] is False
    s = web._login_status(PF)
    assert s["state"] == "qr_ready"
    assert s["qr"] == f"_login/{PF}.png"
    assert PF not in web._WHOAMI_CACHE   # 登录结束后得重新真校验


def test_whoami_started_before_login_keeps_runner_status(env):
    """校验先起、跑到一半用户点了扫码登录：校验结论「未登录」不能删掉 runner 刚写的 qr_ready。"""
    d, calls, _answer, during = env
    during.append(lambda: _start_runner(d))
    res = _whoami()
    assert len(calls) == 1
    assert res["loggedIn"] is False
    assert _state(d) == "qr_ready"
    assert web._login_status(PF)["state"] == "qr_ready"
    assert PF not in web._WHOAMI_CACHE


def test_whoami_keeps_marker_written_during_check(env):
    """校验期间别处（CLI 直跑登录）写了登录成功：过时的「未登录」不能把它删掉，也不进缓存。"""
    d, calls, _answer, during = env
    during.append(lambda: _write_status(d, "success", "登录成功"))
    res = _whoami()
    assert len(calls) == 1
    assert _state(d) == "success"
    assert res["loggedIn"] is True       # 回落到标记里的已知状态
    assert PF not in web._WHOAMI_CACHE


def test_whoami_waits_for_runner_finishing_success(env):
    """runner 写完 success 还在关浏览器（前端一看到 success 就会调 whoami）：等它退出再真校验，
    拿到昵称；不能因为 runner 还活着就返回没有昵称的结果、被前端缓存 10 分钟。"""
    d, calls, answer, _during = env
    _write_status(d, "success", "登录成功")
    web.LOGIN_PROCESSES[PF] = FakeProc(None, 0)
    answer.update(loggedIn=True, name="在逃空指针")
    res = _whoami()
    assert len(calls) == 1
    assert res["loggedIn"] is True and res["name"] == "在逃空指针"
    assert _state(d) == "success"
    assert web._WHOAMI_CACHE[PF][1]["name"] == "在逃空指针"


def test_whoami_gives_up_waiting_on_stuck_runner(env, monkeypatch):
    """runner 写了终态却迟迟不退：等到上限就按「登录还在进行」处理，不起浏览器。"""
    d, calls, _answer, _during = env
    monkeypatch.setattr(web, "LOGIN_RUNNER_EXIT_WAIT", 0)
    _write_status(d, "expired", "二维码超时未扫")
    web.LOGIN_PROCESSES[PF] = FakeProc(None)
    res = _whoami()
    assert calls == []
    assert res["loggedIn"] is False
    assert _state(d) == "expired"


def test_whoami_without_login_still_clears_stale_marker(env):
    """没有登录在跑、标记也没人动：确认未登录照旧删掉过时的 success 标记（原有自愈行为不变）。"""
    d, calls, _answer, _during = env
    _write_status(d, "success", "很久以前登录过")
    web.LOGIN_PROCESSES[PF] = FakeProc(0)   # 上一次 runner 早就退了
    res = _whoami()
    assert len(calls) == 1
    assert res["loggedIn"] is False
    assert _state(d) is None
    assert web._WHOAMI_CACHE[PF][1]["loggedIn"] is False
