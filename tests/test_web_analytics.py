"""创作数据接口：single-flight、落盘、?cached=1 读缓存、与 whoami 共用浏览器锁、有时限的抓取子进程。

全部 monkeypatch 掉抓取/校验子进程，绝不起浏览器、不碰真实平台；落盘目录一律用 tmp_path。
国内浏览器平台（小红书等）不做后台抓取，要抓必须带 manual=1，所以涉及小红书抓取的用例都显式带上。

运行：pytest tests/test_web_analytics.py -q
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
import publish_guard  # noqa: E402  web/app 已把 skills/shared/scripts 放进 sys.path

SAMPLE = {"platform": "douyin", "loggedIn": True, "fetched_at": 1_700_000_000, "followers": 12}


class FakeRun:
    """假的 subprocess.run / _run_analytics_command：记录调用次数与同时在跑的数量。"""

    def __init__(self, stdout: str | None = None, delay: float = 0.05):
        self.stdout = json.dumps(SAMPLE) if stdout is None else stdout
        self.delay = delay
        self.calls = 0
        self.running = 0
        self.max_running = 0
        self._lock = threading.Lock()

    def __call__(self, cmd, **kw):
        with self._lock:
            self.calls += 1
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        time.sleep(self.delay)
        with self._lock:
            self.running -= 1
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="boom" if not self.stdout else "")


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """每个用例都落进临时目录：创作数据落盘、冷却记录、浏览器锁、whoami 缓存、single-flight 登记全部隔离。"""
    monkeypatch.setattr(web, "ANALYTICS_CACHE_DIR", tmp_path / "_analytics")
    monkeypatch.setattr(publish_guard, "COOLDOWN_PATH", tmp_path / "cooldown.json")   # 不碰真实冷却记录
    monkeypatch.setattr(web, "_analytics_inflight", {})
    monkeypatch.setattr(web, "_BROWSER_LOCKS", {})
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    monkeypatch.setattr(web, "LOGIN_DIR", tmp_path / "_login")
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    return tmp_path


def _patch(monkeypatch, fake):
    """校验走 subprocess.run，抓取走 _run_analytics_command(cmd, env, timeout)：两处都换成同一个假的。"""
    monkeypatch.setattr(web.subprocess, "run", fake)
    monkeypatch.setattr(web, "_run_analytics_command",
                        lambda cmd, env, timeout: fake(cmd, env=env, timeout=timeout))


def test_single_flight(env, monkeypatch):
    fake = FakeRun(delay=0.2)
    _patch(monkeypatch, fake)

    async def go():
        return await asyncio.gather(web.api_analytics("douyin", manual=1), web.api_analytics("douyin", manual=1))

    a, b = asyncio.run(go())
    assert fake.calls == 1
    assert a == b == SAMPLE


def test_success_writes_latest(env, monkeypatch):
    _patch(monkeypatch, FakeRun())
    res = asyncio.run(web.api_analytics("douyin", manual=1))
    f = env / "_analytics" / "douyin-latest.json"
    assert json.loads(f.read_text(encoding="utf-8")) == res


def test_cached_hit_no_subprocess(env, monkeypatch):
    d = env / "_analytics"
    d.mkdir()
    (d / "douyin-latest.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    fake = FakeRun()
    _patch(monkeypatch, fake)
    assert asyncio.run(web.api_analytics("douyin", cached=1)) == SAMPLE
    assert fake.calls == 0


def test_cached_miss_404(env, monkeypatch):
    fake = FakeRun()
    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as e:
        asyncio.run(web.api_analytics("douyin", cached=1))
    assert e.value.status_code == 404
    assert fake.calls == 0


def test_unsupported_platform_404(env):
    for cached in (0, 1):
        with pytest.raises(HTTPException) as e:
            asyncio.run(web.api_analytics("nope", cached=cached))
        assert e.value.status_code == 404


def test_no_json_502_keeps_old_latest(env, monkeypatch):
    d = env / "_analytics"
    d.mkdir()
    old = d / "douyin-latest.json"
    old.write_text(json.dumps(SAMPLE), encoding="utf-8")
    _patch(monkeypatch, FakeRun(stdout=""))
    with pytest.raises(HTTPException) as e:
        asyncio.run(web.api_analytics("douyin", manual=1))
    assert e.value.status_code == 502
    assert json.loads(old.read_text(encoding="utf-8")) == SAMPLE


def test_whoami_and_analytics_serialized(env, monkeypatch):
    who = json.dumps({"loggedIn": True, "name": "x", "avatar": ""})

    class Fake(FakeRun):
        def __call__(self, cmd, **kw):
            self.stdout = who if "whoami" in cmd else json.dumps(SAMPLE)
            return super().__call__(cmd, **kw)

    fake = Fake(delay=0.15)
    _patch(monkeypatch, fake)
    monkeypatch.setattr(web, "_write_login_marker", lambda *a, **k: None)

    async def go():
        return await asyncio.gather(web._account_whoami("douyin", manual=True), web.api_analytics("douyin", manual=1))

    asyncio.run(go())
    assert fake.calls == 2
    assert fake.max_running == 1


def test_not_logged_in_does_not_overwrite_latest(env, monkeypatch):
    d = env / "_analytics"
    d.mkdir()
    old = d / "douyin-latest.json"
    old.write_text(json.dumps(SAMPLE), encoding="utf-8")
    bad = {"loggedIn": False, "followers": None}
    _patch(monkeypatch, FakeRun(stdout=json.dumps(bad)))
    assert asyncio.run(web.api_analytics("douyin", manual=1)) == bad   # 返回值照旧
    assert json.loads(old.read_text(encoding="utf-8")) == SAMPLE


def test_error_payload_is_502_and_does_not_overwrite_latest(env, monkeypatch):
    """脚本报 error（平台维护、网络抖动……）：按失败返回 502 + 原因，不当成一份数据，也不覆盖旧缓存。"""
    d = env / "_analytics"
    d.mkdir()
    old = d / "douyin-latest.json"
    old.write_text(json.dumps(SAMPLE), encoding="utf-8")
    _patch(monkeypatch, FakeRun(stdout=json.dumps({"loggedIn": True, "error": "x"})))
    with pytest.raises(HTTPException) as e:
        asyncio.run(web.api_analytics("douyin", manual=1))
    assert e.value.status_code == 502 and e.value.detail == "x"
    assert json.loads(old.read_text(encoding="utf-8")) == SAMPLE


def test_concurrent_waiters_share_error_and_inflight_cleared(env, monkeypatch):
    class Boom(FakeRun):
        def __call__(self, cmd, **kw):
            super().__call__(cmd, **kw)
            raise RuntimeError("spawn failed")

    fake = Boom(delay=0.1)
    _patch(monkeypatch, fake)

    async def go():
        rs = await asyncio.gather(web.api_analytics("douyin", manual=1), web.api_analytics("douyin", manual=1), return_exceptions=True)
        await asyncio.sleep(0)
        return rs, dict(web._analytics_inflight)

    rs, inflight = asyncio.run(go())
    assert fake.calls == 1
    assert all(isinstance(r, RuntimeError) and str(r) == "spawn failed" for r in rs)
    assert inflight == {}
    # 失败后下一次请求重新跑
    _patch(monkeypatch, FakeRun())
    assert asyncio.run(web.api_analytics("douyin", manual=1)) == SAMPLE


def test_timeout_504_and_inflight_cleared(env, monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 180)
    _patch(monkeypatch, boom)

    async def go():
        rs = await asyncio.gather(web.api_analytics("douyin", manual=1), web.api_analytics("douyin", manual=1), return_exceptions=True)
        await asyncio.sleep(0)
        return rs, dict(web._analytics_inflight)

    rs, inflight = asyncio.run(go())
    assert all(isinstance(r, HTTPException) and r.status_code == 504 for r in rs)
    assert inflight == {}


# ---------------------------------------------------------------------------
# 国内平台不做后台抓取：没有 manual 标志只读缓存；冷却期内拒绝
# ---------------------------------------------------------------------------
DOMESTIC = ["xiaohongshu", "douyin", "kuaishou", "zhihu", "weixin-channels", "wechat-oa"]


@pytest.mark.parametrize("pf", DOMESTIC)
def test_domestic_without_manual_never_launches(env, monkeypatch, pf):
    fake = FakeRun()
    _patch(monkeypatch, fake)
    with pytest.raises(HTTPException) as e:
        asyncio.run(web.api_analytics(pf))          # 没缓存 → 404，且不起子进程
    assert e.value.status_code == 404
    d = env / "_analytics"
    d.mkdir()
    (d / f"{pf}-latest.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    assert asyncio.run(web.api_analytics(pf)) == SAMPLE   # 有缓存 → 直接返回缓存
    assert fake.calls == 0


def test_domestic_manual_launches_and_bilibili_still_automatic(env, monkeypatch):
    fake = FakeRun()
    _patch(monkeypatch, fake)
    assert asyncio.run(web.api_analytics("douyin", manual=1)) == SAMPLE
    assert fake.calls == 1
    assert asyncio.run(web.api_analytics("bilibili")) == SAMPLE   # B站走 cookie API，保持自动
    assert fake.calls == 2


def test_manual_refused_during_cooldown(env, monkeypatch):
    fake = FakeRun()
    _patch(monkeypatch, fake)
    publish_guard.set_cooldown("douyin", "平台提示处罚")
    with pytest.raises(HTTPException) as e:
        asyncio.run(web.api_analytics("douyin", manual=1))
    assert e.value.status_code == 409 and "冷却期" in e.value.detail
    assert fake.calls == 0
    # 冷却期内仍可读缓存
    d = env / "_analytics"
    d.mkdir()
    (d / "douyin-latest.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    assert asyncio.run(web.api_analytics("douyin")) == SAMPLE


def test_subprocess_cooldown_exit_surfaces_chinese_message(env, monkeypatch):
    """account_stats 自己拒绝（退出码 9）时，后端把中文说明给前端，而不是通用 502 / 把错误 JSON 当数据。"""
    monkeypatch.setattr(web, "_run_analytics_command", lambda cmd, env, timeout: subprocess.CompletedProcess(
        cmd, 9, stdout=json.dumps({"error": "冷却", "loggedIn": False}), stderr=""))
    with pytest.raises(HTTPException) as e:
        asyncio.run(web._fetch_analytics("douyin"))
    assert e.value.status_code == 409


# ---------------------------------------------------------------------------
# 抓取有时限、结果可信：并发共享、取消不连累、失败可重试、空数据 / 脚本失败不算成功
# ---------------------------------------------------------------------------
def test_concurrent_refreshes_share_one_fetch(monkeypatch):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        calls = []

        async def fetch(platform):
            calls.append(platform)
            started.set()
            await finish.wait()
            return {"platform": platform}

        monkeypatch.setattr(web, "_fetch_analytics", fetch)
        first = asyncio.create_task(web.api_analytics("xiaohongshu", manual=1))
        await started.wait()
        second = asyncio.create_task(web.api_analytics("xiaohongshu", manual=1))
        await asyncio.sleep(0)
        finish.set()
        assert await first == await second == {"platform": "xiaohongshu"}
        assert calls == ["xiaohongshu"]
        await asyncio.sleep(0)
        assert web._analytics_inflight == {}
        assert await web.api_analytics("xiaohongshu", manual=1) == {"platform": "xiaohongshu"}
        assert calls == ["xiaohongshu", "xiaohongshu"]

    asyncio.run(scenario())


def test_cancelled_client_does_not_cancel_shared_fetch(monkeypatch):
    async def scenario():
        finish = asyncio.Event()

        async def fetch(platform):
            await finish.wait()
            return {"platform": platform}

        monkeypatch.setattr(web, "_fetch_analytics", fetch)
        client = asyncio.create_task(web.api_analytics("xiaohongshu", manual=1))
        await asyncio.sleep(0)
        client.cancel()
        with pytest.raises(asyncio.CancelledError):
            await client
        assert not web._analytics_inflight["xiaohongshu"].cancelled()
        other = asyncio.create_task(web.api_analytics("xiaohongshu", manual=1))
        finish.set()
        assert await other == {"platform": "xiaohongshu"}

    asyncio.run(scenario())


def test_failed_refresh_can_be_retried(monkeypatch):
    async def scenario():
        async def fetch(platform):
            raise HTTPException(502, "Unavailable")

        monkeypatch.setattr(web, "_fetch_analytics", fetch)
        for attempt in range(2):
            with pytest.raises(HTTPException):
                await web.api_analytics("xiaohongshu", manual=1)
            await asyncio.sleep(0)
            assert web._analytics_inflight == {}

    asyncio.run(scenario())


@pytest.mark.parametrize("code,payload,status", [
    (0, {"loggedIn": True, "followers": None, "likes": None, "metrics": [], "notes": []}, 502),
    (1, {"loggedIn": True, "followers": 7}, 502),
    (0, {"error": "Platform maintenance"}, 502),
    (0, {"loggedIn": True, "followers": 0}, None),
    (0, {"loggedIn": False}, None),
])
def test_failed_or_empty_payload_is_not_success(monkeypatch, code, payload, status):
    monkeypatch.setattr(web, "_run_analytics_command", lambda *args: subprocess.CompletedProcess(
        [], code, json.dumps(payload), ""))
    if status:
        with pytest.raises(HTTPException) as error:
            asyncio.run(web._fetch_analytics("xiaohongshu"))
        assert error.value.status_code == status
    else:
        assert asyncio.run(web._fetch_analytics("xiaohongshu")) == payload


def test_fetch_propagates_actionable_script_error(monkeypatch):
    monkeypatch.setattr(web, "_run_analytics_command", lambda *args: subprocess.CompletedProcess(
        [], 1, "", "ERROR: 小红书登录目录正被占用"))
    with pytest.raises(HTTPException, match="登录目录正被占用"):
        asyncio.run(web._fetch_analytics("xiaohongshu"))


def test_fetch_reports_bounded_timeout(monkeypatch):
    runner = Mock(side_effect=subprocess.TimeoutExpired("fetch", 90))
    monkeypatch.setattr(web, "_run_analytics_command", runner)
    with pytest.raises(HTTPException) as error:
        asyncio.run(web._fetch_analytics("xiaohongshu"))
    assert error.value.status_code == 504
    assert runner.call_args.args[2] == 90
    assert runner.call_args.args[1]["PYTHONIOENCODING"] == "utf-8"
    assert runner.call_args.args[1]["PYTHONUTF8"] == "1"


def test_subprocess_timeout_stops_browser_tree(monkeypatch):
    process = Mock(pid=123456)
    process.communicate.side_effect = [subprocess.TimeoutExpired("fetch", 1), ("", "")]
    popen = Mock(return_value=process)
    monkeypatch.setattr(web.subprocess, "Popen", popen)
    if os.name == "nt":
        killer = Mock()
        monkeypatch.setattr(web.subprocess, "run", killer)
    else:
        killer = Mock()
        monkeypatch.setattr(web.os, "killpg", killer)
    with pytest.raises(subprocess.TimeoutExpired):
        web._run_analytics_command(["python", "fetch"], {}, 1)
    assert popen.call_args.kwargs["encoding"] == "utf-8"
    assert popen.call_args.kwargs["start_new_session"] is (os.name != "nt")
    if os.name == "nt":
        assert killer.call_args.args[0] == ["taskkill", "/PID", "123456", "/T", "/F"]
    else:
        killer.assert_called_once_with(123456, signal.SIGKILL)
    process.kill.assert_called_once()
    assert process.communicate.call_count == 2
