"""overseas_publisher 登录 / whoami 状态机的离线测试：按剧本走的假浏览器，不起真 Chrome、不连平台。"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import overseas_publisher as op  # noqa: E402
from overseas import base  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeCookies:
    def __init__(self, page):
        self.page = page

    def cookies(self, urls=None):
        w, pg = self.page.world, self.page
        has = w.logged(pg) if pg.headed else (w.saved or w.stale)
        return [{"name": "sid", "value": "v"}] if has else []


class FakePage:
    def __init__(self, world, headed):
        self.world, self.headed = world, headed
        self.url = ""
        self.closed = False
        self.context = FakeCookies(self)

    def goto(self, url, **_kw):
        if self.world.goto_error:
            raise self.world.goto_error
        self.url = url

    def wait_for_timeout(self, ms):
        self.world.clock.t += ms / 1000
        if self.headed:
            self.world.waits += 1
            if self.world.close_window_after is not None and self.world.waits >= self.world.close_window_after:
                self.closed = True

    def is_closed(self):
        return self.closed


class FakeCtx:
    def __init__(self, page):
        self.pages = [page]

    def new_page(self):
        return self.pages[0]


class World:
    """logged_after：有头窗口里等了几次之后登录成功（None = 一直不登录）；already：一打开就是登录态；
    saved：关掉窗口、无头重开后是否还是登录态。"""

    def __init__(self, logged_after=None, saved=True, already=False, stale=False, flicker=()):
        self.clock = Clock()
        self.logged_after, self.saved, self.already = logged_after, saved, already
        self.stale = stale            # 无头重开后 cookie 还在，但页面始终不是登录态（说不准）
        self.flicker = set(flicker)   # 有头窗口里只在这几次等待时短暂显示登录态
        self.waits = 0
        self.launches: list[bool] = []
        self.goto_error: Exception | None = None
        self.verify_error: Exception | None = None
        self.close_window_after: int | None = None

    def logged(self, page) -> bool:
        if page.headed:
            return (self.already or self.waits in self.flicker
                    or (self.logged_after is not None and self.waits >= self.logged_after))
        return self.saved

    @contextmanager
    def launch(self, profile, *, headed):
        self.launches.append(headed)
        if not headed and self.verify_error:
            raise self.verify_error
        yield FakeCtx(FakePage(self, headed))


def make_mod(world):
    return SimpleNamespace(
        KEY="demo", NAME="Demo", PROFILE="DemoProfile",
        HOME_URL="https://demo.test/home", LOGIN_URL="https://demo.test/login", LOGIN_MARKERS=("/login",),
        COOKIE_URL="https://demo.test", AUTH_COOKIES=("sid",),
        is_logged_in=world.logged,
        read_identity=lambda page: {"name": "Alice", "avatar": "https://cdn/a.jpg"},
    )


@pytest.fixture
def states(monkeypatch):
    seen: list[tuple[str, str]] = []
    real = op.login_state.write_status

    def record(path, state, message="", qr=""):
        seen.append((state, message))
        real(path, state, message, qr)

    monkeypatch.setattr(op.login_state, "write_status", record)
    return seen


def run(world, tmp_path, timeout=60):
    sf = tmp_path / "demo.json"
    rc = op.run_login(make_mod(world), str(sf), timeout, launch=world.launch, clock=world.clock,
                      profile_root=tmp_path / "profiles")
    return rc, json.loads(sf.read_text(encoding="utf-8"))


def test_login_success_verifies_saved_profile(tmp_path, states):
    world = World(logged_after=3)
    rc, final = run(world, tmp_path)
    assert rc == 0
    assert [s for s, _ in states] == ["starting", "window_login", "verifying", "success"]
    assert "Demo" in states[1][1]
    assert final["message"] == "Alice"
    assert world.launches == [True, False]      # 有头窗口登录 → 无头重开确认


def test_already_logged_in_succeeds_without_waiting(tmp_path, states):
    """点「登录」时其实已经登录：直接进入确认，不干等（Review Focus 2）。"""
    world = World(already=True)
    rc, final = run(world, tmp_path)
    assert rc == 0 and final["state"] == "success"
    assert world.waits == 1                     # 只有等 cookie 落盘那一次


def test_not_saved_is_error(tmp_path, states):
    rc, final = run(World(logged_after=1, saved=False), tmp_path)
    assert rc == 1
    assert (final["state"], final["message"]) == ("error", op.NOT_SAVED_MSG)


def test_timeout_is_expired(tmp_path, states):
    rc, final = run(World(), tmp_path, timeout=10)
    assert rc == 1
    assert final["state"] == "expired" and "分钟" in final["message"]


def test_window_closed_is_error(tmp_path, states):
    world = World()
    world.close_window_after = 2
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert (final["state"], final["message"]) == ("error", op.WINDOW_CLOSED_MSG)


def test_verify_crash_is_error_with_next_step(tmp_path, states):
    world = World(logged_after=1)
    world.verify_error = RuntimeError("net::ERR_INTERNET_DISCONNECTED")
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert final["state"] == "error" and final["message"].startswith("登录已完成，但确认登录态时")


def test_goto_failure_is_error(tmp_path, states):
    world = World()
    world.goto_error = RuntimeError("net::ERR_CONNECTION_REFUSED")
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert final["state"] == "error" and "ERR_CONNECTION_REFUSED" in final["message"]


def test_playwright_missing_exits_3(tmp_path, states):
    @contextmanager
    def no_playwright(profile, *, headed):
        raise base.PlaywrightMissing("需要 playwright：No module named 'playwright'")
        yield  # pragma: no cover

    rc = op.run_login(make_mod(World()), str(tmp_path / "demo.json"), 60, launch=no_playwright,
                      profile_root=tmp_path / "profiles")
    assert rc == 3
    assert states[-1][0] == "error" and "playwright" in states[-1][1]


def test_profile_busy_is_error(tmp_path, states, monkeypatch):
    monkeypatch.setattr(op, "LOGIN_LOCK_WAIT_S", 0.2)
    world = World(already=True)
    lock = base.ProfileLock(tmp_path / "profiles" / "DemoProfile")
    lock.acquire(1)
    try:
        rc, final = run(world, tmp_path)
    finally:
        lock.release()
    assert rc == 1 and final["state"] == "error" and "占用" in final["message"]
    assert world.launches == []


def _whoami(world, tmp_path):
    return op.run_whoami(make_mod(world), launch=world.launch, profile_root=tmp_path / "profiles")


def test_whoami_without_profile_skips_browser(tmp_path):
    world = World()
    assert _whoami(world, tmp_path) == {"loggedIn": False, "name": "", "avatar": ""}
    assert world.launches == []


def test_whoami_logged_in_reads_identity(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    world = World(saved=True)
    assert _whoami(world, tmp_path) == {"loggedIn": True, "name": "Alice", "avatar": "https://cdn/a.jpg"}
    assert world.launches == [False]


def test_whoami_logged_out(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    assert _whoami(World(saved=False), tmp_path) == {"loggedIn": False, "name": "", "avatar": ""}


def test_whoami_busy_profile_is_unconfident(tmp_path, monkeypatch):
    """登录窗口开着时校验：拿不到锁就报校验失败（带 error），不开第二个浏览器（Review Focus 5）。"""
    monkeypatch.setattr(op, "WHOAMI_LOCK_WAIT_S", 0.2)
    world = World(saved=True)
    lock = base.ProfileLock(tmp_path / "profiles" / "DemoProfile")
    lock.acquire(1)
    try:
        res = _whoami(world, tmp_path)
    finally:
        lock.release()
    assert res["loggedIn"] is False and res.get("error")
    assert world.launches == []


def test_whoami_browser_error_is_unconfident(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    world = World()
    world.verify_error = RuntimeError("browser crashed")
    res = _whoami(world, tmp_path)
    assert res["loggedIn"] is False and "browser crashed" in res["error"]


def test_cli_whoami_prints_single_json_line(monkeypatch, capsys):
    monkeypatch.setattr(op, "run_whoami", lambda mod: {"loggedIn": True, "name": mod.NAME, "avatar": ""})
    assert op.main(["whoami", "--platform", "x"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads(lines[-1]) == {"loggedIn": True, "name": "X", "avatar": ""}


def test_cli_login_passes_platform_and_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(op, "run_login", lambda mod, sf, timeout: seen.update(key=mod.KEY, sf=sf, t=timeout) or 0)
    assert op.main(["login", "--platform", "youtube", "--status-file", "s.json", "--timeout", "90"]) == 0
    assert seen == {"key": "youtube", "sf": "s.json", "t": 90}
    assert op.main(["login", "--platform", "threads"]) == 0
    assert seen["t"] == op.DEFAULT_LOGIN_TIMEOUT == 600


def test_cli_rejects_unknown_platform():
    with pytest.raises(SystemExit) as ei:
        op.main(["whoami", "--platform", "weibo"])
    assert ei.value.code == 2


def test_cli_platforms_lists_all(capsys):
    assert op.main(["platforms"]) == 0
    out = capsys.readouterr().out
    for name in ("TikTok", "YouTube", "Instagram", "X", "Threads"):
        assert name in out
    assert "加权" in out and "标题≤100" in out


def test_selftest_passes(capsys):
    assert op.main(["selftest"]) == 0
    assert "✅" in capsys.readouterr().out


def test_login_window_stays_open_through_a_flicker(tmp_path, states):
    """旧 cookie 让页面短暂显示登录态又跳回登录页：不能就此关窗口（否则重登永远失败）。"""
    world = World(flicker={0}, logged_after=5)
    rc, final = run(world, tmp_path)
    assert rc == 0 and final["state"] == "success"
    assert world.waits >= 5


def test_verify_unsettled_is_not_reported_as_not_saved(tmp_path, states):
    """重开确认时页面一直没稳定（cookie 在、却始终不是登录态）：报「确认出错」，不报「没保存」。"""
    rc, final = run(World(logged_after=1, saved=False, stale=True), tmp_path)
    assert rc == 1
    assert final["state"] == "error" and final["message"].startswith("登录已完成，但确认登录态时")


def test_whoami_unsettled_is_unconfident(tmp_path):
    """慢网 / 一直没稳定：带 error 交给后端，不能当成可信的「未登录」去删登录标记。"""
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    res = _whoami(World(saved=False, stale=True), tmp_path)
    assert res["loggedIn"] is False and res.get("error")
