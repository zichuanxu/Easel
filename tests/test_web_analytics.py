"""创作数据接口：single-flight、落盘、?cached=1 读缓存、与 whoami 共用浏览器锁。

全部 monkeypatch 掉 subprocess.run，绝不起浏览器、不碰真实平台；落盘目录一律用 tmp_path。

运行：pytest tests/test_web_analytics.py -q
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402

SAMPLE = {"platform": "douyin", "fetched_at": 1_700_000_000, "followers": 12}


class FakeRun:
    """假的 subprocess.run：记录调用次数与同时在跑的数量。"""

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


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "ANALYTICS_CACHE_DIR", tmp_path / "_analytics")
    web._BROWSER_LOCKS.clear()
    web._ANALYTICS_INFLIGHT.clear()
    web._WHOAMI_CACHE.clear()
    return tmp_path


def _patch(monkeypatch, fake):
    monkeypatch.setattr(web.subprocess, "run", fake)


def test_single_flight(env, monkeypatch):
    fake = FakeRun(delay=0.2)
    _patch(monkeypatch, fake)

    async def go():
        return await asyncio.gather(web.api_analytics("douyin"), web.api_analytics("douyin"))

    a, b = asyncio.run(go())
    assert fake.calls == 1
    assert a == b == SAMPLE


def test_success_writes_latest(env, monkeypatch):
    _patch(monkeypatch, FakeRun())
    res = asyncio.run(web.api_analytics("douyin"))
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
        asyncio.run(web.api_analytics("douyin"))
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
        return await asyncio.gather(web._account_whoami("douyin"), web.api_analytics("douyin"))

    asyncio.run(go())
    assert fake.calls == 2
    assert fake.max_running == 1
