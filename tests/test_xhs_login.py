"""小红书登录链路的回归测试（不起真浏览器、不连小红书）。

钉住的真机现场（日本出口的 Mac）：
1. 小红书只拦「未登录 + 无头」（300012 安全限制），有头窗口不拦 —— 无头登录在这里必然失败。
   修法：--headed-fallback，被拦就改开有头窗口；Web 在本机有桌面时自动带上。
2. 扫码后页面一变成登录态就关浏览器，重开 profile 里却没有 web_session，脚本还打印了
   「登录成功，cookie 已持久化」。修法：等登录 cookie 落下再关，关完无头重开、看到发布页真渲染出来
   才报成功（只看 URL 不带 /login 不够：未登录时 401 跳转会拖好几秒）。
3. CLI 登录不写 Web 的登录标记，whoami 又把「未登录」缓存 10 分钟 —— 卡片一直显示未登录。
   修法：CLI 登录写标记；服务端 whoami 缓存和前端 localStorage 缓存都记住标记指纹，变了就作废。
4. runner 中途死掉（窗口被关、浏览器崩）停在非终态 → Web 弹窗永远转圈；重复点登录又起第二个 runner。

浏览器部分用一个按剧本走的假 Playwright（FakeWorld）：时间由假时钟推进，不真 sleep。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
import output_paths  # noqa: E402
import xhs_publish as xhs  # noqa: E402


# ── 登录 cookie 判定 ────────────────────────────────────────────────────


@pytest.mark.parametrize("cookies,expected", [
    ([{"name": "web_session", "domain": ".xiaohongshu.com", "value": "040069b"}], True),
    ([{"name": "web_session", "domain": "www.xiaohongshu.com", "value": "x"}], True),
    ([{"name": "web_session", "domain": "xiaohongshu.com", "value": "x"}], True),
    # 真机失败现场：只有设备类 cookie，没有 web_session
    ([{"name": n, "domain": ".xiaohongshu.com", "value": "v"}
      for n in ("a1", "webId", "gid", "id_token", "websectiga")], False),
    ([{"name": "web_session", "domain": ".xiaohongshu.com", "value": ""}], False),
    ([{"name": "web_session", "domain": ".notxiaohongshu.com", "value": "x"}], False),
    ([{"name": "web_session", "domain": ".example.com", "value": "x"}], False),
    ([], False),
    (None, False),
    (["garbage", 42], False),
])
def test_has_login_cookie(cookies, expected):
    assert xhs._has_login_cookie(cookies) is expected


# ── 假 Playwright：按剧本模拟小红书在本机的真实行为 ─────────────────────────

LOGIN_401_URL = "https://creator.xiaohongshu.com/login?redirectReason=401"
PUBLISH_PREFIX = "https://creator.xiaohongshu.com/publish/"


class FakeTimeout(Exception):
    """名字里带 Timeout：_wait_sel 靠类型名区分「超时」和「页面跳转」。"""


class TargetClosedError(Exception):
    """与 Playwright 同名：窗口被关后，页面上的等待/操作抛它。"""

    def __init__(self, msg: str = "Target page, context or browser has been closed"):
        super().__init__(msg)


class FakeWorld:
    """一台机器 + 一份 profile 的剧本。

    - 未登录 + 无头打开 explore → 跳 300012 安全限制页；有头不拦。
    - 有头窗口出码后，经过 login_after 次等待，用户扫码完成（页面变成登录态）。
    - web_session 在页面变成登录态之后再过 cookie_delay 次等待才出现（cookie_delay=None：永远不出现）。
    - 关浏览器时只有已经出现的 web_session 才会落进 profile（persist=False：怎么都存不上）。
    - 未登录打开创作平台发布页：redirect_delay=0 立刻跳 /login；>0 则前端先停在发布页 URL
      （不渲染发布区），过这么多次等待才因 401 跳 /login —— 慢网现场。
    - close_after_qr_waits：出码后第 N 次等待时用户关掉窗口（之后 is_closed() 为真）。
    - close_after_login_waits：页面已是登录态后第 N 次等待时窗口被关，等待本身抛 TargetClosedError。
    - launch_errors：{第几次启动(从 1 数): 异常}，模拟浏览器起不来。
    """

    def __init__(self, *, login_after: int = 3, cookie_delay: int | None = 0, persist: bool = True,
                 redirect_delay: int = 0, close_after_qr_waits: int | None = None,
                 close_after_login_waits: int | None = None,
                 launch_errors: dict[int, Exception] | None = None):
        self.clock = 1_000_000.0
        self.login_after = login_after
        self.cookie_delay = cookie_delay
        self.persist = persist
        self.redirect_delay = redirect_delay
        self.close_after_qr_waits = close_after_qr_waits
        self.close_after_login_waits = close_after_login_waits
        self.launch_errors = dict(launch_errors or {})
        self.saved = False            # profile 里有没有登录态
        self.launches: list[bool] = []   # 每次启动是否无头
        self.contexts: list[FakeContext] = []
        self.overlaps: list[int] = []    # 上一个浏览器还没关就又启动的那几次（同一份 profile 不许同时开两个）

    # 假 time 模块（xhs_publish 里 time.time()/time.sleep() 走这里）
    def time(self) -> float:
        return self.clock

    def sleep(self, s: float) -> None:
        self.clock += s


class FakeElement:
    def screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"\x89PNG fake qr")


class FakePage:
    def __init__(self, ctx: "FakeContext"):
        self.ctx = ctx
        self.world = ctx.world
        self._url = "about:blank"
        self.closed = False
        self.qr_shown = False
        self.waits_since_qr = 0
        self.waits_since_login = 0
        self.login_waits = 0
        self.pending_redirect = 0

    @property
    def url(self) -> str:
        return self._url

    def is_closed(self) -> bool:
        return self.closed

    def _check_open(self) -> None:
        if self.closed:
            raise TargetClosedError()

    def title(self) -> str:
        self._check_open()
        return "安全限制" if "website-login/error" in self._url else "小红书"

    def goto(self, url: str, **_kw) -> None:
        self._check_open()
        self.pending_redirect = 0
        if url == xhs.EXPLORE_URL:
            if self.ctx.headless and not self.ctx.logged_in:
                self._url = "https://www.xiaohongshu.com/website-login/error?error_code=300012"
            else:
                self._url = url
        elif url == xhs.PUBLISH_URL:
            if self.ctx.logged_in:
                self._url = url
            elif self.world.redirect_delay > 0:
                self._url = url                  # 前端还没拿到 401：URL 暂时还是发布页
                self.pending_redirect = self.world.redirect_delay
            else:
                self._url = LOGIN_401_URL
        else:
            self._url = url

    def wait_for_timeout(self, ms: int) -> None:
        self._check_open()
        self.world.clock += ms / 1000
        if self.pending_redirect:
            self.pending_redirect -= 1
            if not self.pending_redirect:
                self._url = LOGIN_401_URL
        was_logged_in = self.ctx.logged_in
        if self.qr_shown and not self.ctx.logged_in:
            self.waits_since_qr += 1
            if (self.world.close_after_qr_waits is not None
                    and self.waits_since_qr >= self.world.close_after_qr_waits):
                self.closed = True               # 用户关掉了窗口
                return
            if self.waits_since_qr >= self.world.login_after:
                self.ctx.logged_in = True
        elif self.ctx.logged_in and not self.ctx.cookie_live and self.world.cookie_delay is not None:
            self.waits_since_login += 1
        if (self.ctx.logged_in and not self.ctx.cookie_live and self.world.cookie_delay is not None
                and self.waits_since_login >= self.world.cookie_delay):
            self.ctx.cookie_live = True
        if was_logged_in and self.world.close_after_login_waits is not None:
            self.login_waits += 1
            if self.login_waits >= self.world.close_after_login_waits:
                self.closed = True               # 扫码成功后用户立刻关窗口：正在等的那一下直接抛
                raise TargetClosedError()

    def query_selector(self, selector: str):
        self._check_open()
        if (selector == xhs.SELECTORS["login_ok"] and self.ctx.logged_in
                and self._url.startswith(xhs.EXPLORE_URL)):
            return object()
        # 发布页只有真登录了才渲染上传区 / 发布 tab（未登录时前端空着等 401 跳走）
        if (selector in (xhs.SELECTORS["upload_content"], xhs.SELECTORS["creator_tab"])
                and self.ctx.logged_in and self._url.startswith(PUBLISH_PREFIX)):
            return object()
        return None

    def wait_for_selector(self, selector: str, timeout: int = 0):
        self._check_open()
        if (selector == xhs.SELECTORS["qrcode"] and self._url.startswith(xhs.EXPLORE_URL)
                and not self.ctx.logged_in):
            self.qr_shown = True
            return FakeElement()
        self.world.clock += timeout / 1000
        raise FakeTimeout(f"waiting for {selector}")


class FakeContext:
    def __init__(self, world: FakeWorld, headless: bool):
        self.world = world
        self.headless = headless
        self.logged_in = world.saved      # 启动时从 profile 读回来的登录态
        self.cookie_live = world.saved
        self.pages = [FakePage(self)]
        self.closed = False

    def new_page(self) -> FakePage:
        page = FakePage(self)
        self.pages.append(page)
        return page

    def cookies(self) -> list[dict]:
        jar = [{"name": "a1", "domain": ".xiaohongshu.com", "value": "device"}]
        if self.cookie_live:
            jar.append({"name": "web_session", "domain": ".xiaohongshu.com", "value": "sess"})
        return jar

    def close(self) -> None:
        if self.cookie_live and self.world.persist:
            self.world.saved = True
        self.closed = True


class FakePlaywright:
    def __init__(self, world: FakeWorld):
        self.world = world
        self.chromium = self

    def launch_persistent_context(self, _profile: str, **kwargs) -> FakeContext:
        world = self.world
        world.launches.append(bool(kwargs["headless"]))
        n = len(world.launches)
        if any(not c.closed for c in world.contexts):
            world.overlaps.append(n)
            raise AssertionError(f"第 {n} 次启动时上一个浏览器还没关（同一份 profile 不许同时开两个）")
        if n in world.launch_errors:
            raise world.launch_errors[n]
        ctx = FakeContext(world, headless=bool(kwargs["headless"]))
        world.contexts.append(ctx)
        return ctx


@pytest.fixture
def fake_browser(monkeypatch, tmp_path):
    """装好假 Playwright + 假时钟，并记录每次写的登录状态。返回 (world_factory, statuses)。
    收尾时检查：任何时候都没有两个浏览器同时开着同一份 profile。"""
    statuses: list[tuple[str, str, str]] = []
    worlds: list[FakeWorld] = []

    def make(**kw) -> FakeWorld:
        world = FakeWorld(**kw)
        worlds.append(world)
        monkeypatch.setattr(xhs, "time", world)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(
            sync_playwright=lambda: contextlib.nullcontext(FakePlaywright(world))))
        return world

    def record(_path, state, message="", qr=""):
        statuses.append((state, message, qr))

    monkeypatch.setattr(xhs.login_state, "write_status", record)
    monkeypatch.setattr(xhs, "_cloak_executable", lambda: None)
    monkeypatch.setattr(xhs, "_browser_channel", lambda: None)
    # 这些剧本覆盖「允许无头」时的登录链路（没有桌面的机器）；默认一律开窗口见下面的单独测试
    monkeypatch.setenv("EASEL_XHS_HEADLESS", "1")
    yield make, statuses
    for world in worlds:
        assert not world.overlaps, f"浏览器重叠启动：第 {world.overlaps} 次"
        assert all(c.closed for c in world.contexts), "有浏览器没关就退出了"


def _login_args(tmp_path: Path, **kw) -> types.SimpleNamespace:
    # profile_base 一律指向 tmp：绝不能碰真机的 ~/.easel-browser-profiles/XiaohongshuProfile
    base = dict(qr_out=str(tmp_path / "qr.png"), timeout=60, status_file=str(tmp_path / "status.json"),
                profile_base=str(tmp_path / "profiles"), proxy=None, no_proxy=True,
                headed=False, headed_fallback=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_headless_blocked_falls_back_to_headed_window(fake_browser, tmp_path, capsys):
    """无头被 300012 拦 + --headed-fallback：关掉无头、改开有头窗口扫码，确认保存后才报成功。"""
    make, statuses = fake_browser
    world = make()
    rc = xhs.cmd_login(_login_args(tmp_path, headed_fallback=True))
    assert rc == 0
    # 无头（被拦）→ 有头（扫码）→ 无头（确认登录态已保存）
    assert world.launches == [True, False, True]
    states = [s for s, _, _ in statuses]
    assert states[0] == "starting"
    assert (("window_login", xhs.HEADED_FALLBACK_MSG, "")) in statuses
    assert any(s == "window_login" and qr for s, _, qr in statuses), "窗口里出的码没同步给 Web"
    assert states[-2:] == ["verifying", "success"]
    assert "error" not in states and "qr_ready" not in states
    assert "登录成功" in capsys.readouterr().out


def test_headless_blocked_without_fallback_dies_with_hint(fake_browser, tmp_path, capsys):
    """不带 --headed-fallback 时行为不变：300012 直接报错退出，但提示里给出 --headed 这条路。"""
    make, statuses = fake_browser
    world = make()
    with pytest.raises(SystemExit) as exc:
        xhs.cmd_login(_login_args(tmp_path))
    assert exc.value.code == 4
    assert world.launches == [True]
    assert statuses[-1][0] == "error"
    assert "--headed" in capsys.readouterr().err


def test_waits_for_login_cookie_before_closing(fake_browser, tmp_path):
    """真机现场：页面先变登录态、web_session 稍后才出现。等到它再关，登录态就能存上。"""
    make, statuses = fake_browser
    world = make(cookie_delay=4)
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 0
    assert world.saved
    assert [s for s, _, _ in statuses][-1] == "success"


@pytest.mark.parametrize("world_kw", [
    {"cookie_delay": None},          # 登录 cookie 始终没出现
    {"persist": False},              # 出现了但没落进 profile
], ids=["cookie-never-set", "cookie-not-persisted"])
def test_unsaved_login_is_reported_as_error(fake_browser, tmp_path, capsys, world_kw):
    """重开浏览器后创作平台仍要求登录 → 不许报成功：写 error、打印原因、返回非 0。"""
    make, statuses = fake_browser
    world = make(**world_kw)
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 1
    assert world.launches == [False, True]          # 有头登录 + 无头重开确认
    assert statuses[-1] == ("error", xhs.NOT_SAVED_MSG, "")
    assert "verifying" in [s for s, _, _ in statuses]
    assert "success" not in [s for s, _, _ in statuses]
    captured = capsys.readouterr()
    assert xhs.NOT_SAVED_MSG in captured.err
    assert "登录成功" not in captured.out


@pytest.mark.parametrize("redirect_delay", [5, 1000], ids=["late-401-redirect", "never-renders"])
def test_verify_needs_publish_page_not_just_stable_url(fake_browser, tmp_path, capsys, redirect_delay):
    """慢网现场：登录态没存上，重开后发布页 URL 先稳住好几秒、才因 401 跳 /login（或一直不渲染）。
    旧逻辑「URL 稳 2 秒 + 不带 /login」会误报成功；必须看到发布页真渲染出来才算。"""
    make, statuses = fake_browser
    world = make(persist=False, redirect_delay=redirect_delay)
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 1
    assert world.launches == [False, True]
    states = [s for s, _, _ in statuses]
    assert "success" not in states
    assert statuses[-1] == ("error", xhs.NOT_SAVED_MSG, "")
    assert "登录成功" not in capsys.readouterr().out


def test_verify_browser_failure_is_not_reported_as_unsaved(fake_browser, tmp_path, capsys):
    """重开确认时浏览器自己起不来：说明不了登录态没存上 —— 不报 NOT_SAVED（免得吓人重扫），也不报成功。"""
    make, statuses = fake_browser
    world = make(launch_errors={2: RuntimeError("browser crashed on launch")})
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 1
    assert world.launches == [False, True]
    state, message, _ = statuses[-1]
    assert state == "error"
    assert message != xhs.NOT_SAVED_MSG
    assert message.startswith("登录已完成，但确认登录态时浏览器/网络出错")
    assert "browser crashed on launch" in message
    assert "success" not in [s for s, _, _ in statuses]
    assert "登录成功" not in capsys.readouterr().out


@pytest.mark.parametrize("world_kw", [
    # 还没扫码就把窗口关了：_is_logged_in 会吞掉查询异常，必须主动发现窗口没了
    {"login_after": 100, "close_after_qr_waits": 1},
    # 扫码成功、正在等登录 cookie 落盘时关了窗口：等待本身抛 TargetClosedError
    {"cookie_delay": None, "close_after_login_waits": 2},
], ids=["closed-before-scan", "closed-during-settle"])
def test_closed_window_ends_in_error_not_spinner(fake_browser, tmp_path, capsys, world_kw):
    """窗口被关不能让 runner 带着 window_login / 异常栈退出：落 error 终态、返回 1，不重开确认。"""
    make, statuses = fake_browser
    world = make(**world_kw)
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 1
    assert world.launches == [False]
    state, message, _ = statuses[-1]
    assert state == "error"
    assert message == xhs.WINDOW_CLOSED_MSG
    assert message.startswith("登录窗口被关闭或浏览器异常：")
    states = [s for s, _, _ in statuses]
    assert "verifying" not in states and "success" not in states
    assert xhs.WINDOW_CLOSED_MSG in capsys.readouterr().err


def test_unexpected_browser_error_ends_in_error(fake_browser, tmp_path, monkeypatch):
    """别的意外异常（不是窗口被关）也要落 error 终态，并带上异常摘要。"""
    make, statuses = fake_browser
    make()

    def boom(*_a, **_kw):
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(xhs, "_settle_login_cookies", boom)
    rc = xhs.cmd_login(_login_args(tmp_path, headed=True))
    assert rc == 1
    state, message, _ = statuses[-1]
    assert state == "error"
    assert message.startswith("登录窗口被关闭或浏览器异常：")
    assert "RuntimeError" in message and "renderer crashed" in message


def test_already_logged_in_exits_early(fake_browser, tmp_path):
    """已登录的 profile：无头也不被拦，直接报已登录，不出码、不重开确认。"""
    make, statuses = fake_browser
    world = make()
    world.saved = True
    rc = xhs.cmd_login(_login_args(tmp_path, headed_fallback=True))
    assert rc == 0
    assert world.launches == [True]
    assert statuses[-1][:2] == ("success", "已登录")


def test_success_status_written_before_print_and_survives_print_error(monkeypatch):
    """先落 success 再打印 ✅；打印炸了（如 Windows 控制台编码）也不能让状态停在 verifying。"""
    written: list[str] = []
    monkeypatch.setattr(xhs.login_state, "write_status",
                        lambda _p, state, message="", qr="": written.append(state))

    class GbkConsole:
        def write(self, text):
            assert written == ["success"], "打印前必须已经落了 success"
            raise UnicodeEncodeError("gbk", text, 0, 1, "illegal multibyte sequence")

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", GbkConsole())
    a = types.SimpleNamespace(status_file="x.json", profile_base="/elsewhere")   # 不写 Web 标记
    xhs._report_login_success(a, "x.json", "登录成功", line="✅ 登录成功")
    assert written == ["success"]


# ── CLI 登录也要让 Web 知道（outputs/_login/xiaohongshu.json）─────────────────


@pytest.fixture
def outputs_root(monkeypatch, tmp_path):
    root = tmp_path / "project"
    (root / "outputs").mkdir(parents=True)
    monkeypatch.setattr(output_paths, "PROJECT_ROOT", root)
    monkeypatch.setattr(output_paths, "OUTPUTS_DIR", root / "outputs")
    return root / "outputs"


def test_cli_login_writes_web_marker(outputs_root):
    # 先确认 xhs_publish 用到的就是被改到 tmp 的那个 output_paths：漏 patch 时宁可这里失败，
    # 也不能往真机的 outputs/_login 里写
    assert sys.modules["output_paths"] is output_paths
    assert output_paths.OUTPUTS_DIR == outputs_root
    a = types.SimpleNamespace(status_file=None, profile_base=None)
    xhs._report_login_success(a, None, "登录成功")
    marker = outputs_root / "_login" / "xiaohongshu.json"
    data = json.loads(marker.read_text(encoding="utf-8"))
    # 与 login_state.write_status / web._write_login_marker 同格式，Web 的 _account_logged_in 认它
    assert set(data) == {"state", "message", "qr", "ts"}
    assert data["state"] == "success"


@pytest.mark.parametrize("a", [
    types.SimpleNamespace(status_file="x.json", profile_base=None),   # Web 发起的登录自己写
    types.SimpleNamespace(status_file=None, profile_base="/tmp/elsewhere"),   # 不是 Web 看的那份登录目录
], ids=["web-initiated", "other-profile"])
def test_web_marker_only_for_cli_default_profile(outputs_root, a):
    assert xhs._web_login_marker_path(a) is None


def test_web_marker_path_is_registered_system_path(outputs_root):
    a = types.SimpleNamespace(status_file=None, profile_base=None)
    path = xhs._web_login_marker_path(a)
    assert path == (outputs_root / "_login" / "xiaohongshu.json").resolve()
    assert xhs.WEB_LOGIN_PLATFORM in web.LOGIN_RUNNERS


# ── Web：什么时候给小红书登录加 --headed-fallback ─────────────────────────────


@pytest.mark.parametrize("platform,os_name,env,expected", [
    ("darwin", "posix", {}, True),
    ("win32", "nt", {}, True),
    ("linux", "posix", {}, False),                              # 无桌面服务器：弹不出窗口
    ("linux", "posix", {"DISPLAY": ":0"}, True),
    ("linux", "posix", {"WAYLAND_DISPLAY": "wayland-0"}, True),
    ("darwin", "posix", {"EASEL_XHS_HEADED_FALLBACK": "0"}, False),   # 远程访问时强制关
    ("linux", "posix", {"EASEL_XHS_HEADED_FALLBACK": "1"}, True),     # 强制开
    ("linux", "posix", {"EASEL_XHS_HEADED_FALLBACK": " "}, False),    # 空白 = 没设
])
def test_xhs_headed_fallback_available(platform, os_name, env, expected):
    assert web._xhs_headed_fallback_available(platform=platform, env=env, os_name=os_name) is expected


class FakeProc:
    def __init__(self, code: int | None):
        self.code = code

    def poll(self):
        return self.code


@pytest.fixture
def login_dir(monkeypatch, tmp_path):
    d = tmp_path / "_login"
    d.mkdir()
    monkeypatch.setattr(web, "LOGIN_DIR", d)
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    return d


@pytest.mark.parametrize("available", [True, False])
def test_login_start_adds_headed_fallback_flag(monkeypatch, login_dir, available):
    monkeypatch.setattr(web, "_xhs_headed_fallback_available", lambda: available)
    captured: dict[str, list[str]] = {}

    class FakePopen(FakeProc):
        def __init__(self, cmd, **_kw):
            super().__init__(None)
            captured["cmd"] = list(cmd)
            status = cmd[cmd.index("--status-file") + 1]
            Path(status).write_text(json.dumps({"state": "qr_ready", "message": ""}), encoding="utf-8")

    monkeypatch.setattr(web.subprocess, "Popen", FakePopen)
    res = asyncio.run(web.api_login_start("xiaohongshu"))
    assert res["state"] == "qr_ready"
    cmd = captured["cmd"]
    assert cmd[1].endswith("xhs_publish.py") and cmd[2] == "login"
    assert "--no-proxy" in cmd                      # 小红书必须直连，走代理会被判风险
    assert ("--headed-fallback" in cmd) is available


def _write_status(login_dir: Path, state: str, message: str = "") -> None:
    (login_dir / "xiaohongshu.json").write_text(
        json.dumps({"state": state, "message": message, "qr": "", "ts": 0}), encoding="utf-8")


def test_login_start_reuses_live_runner(monkeypatch, login_dir):
    """重复点登录：上一个 runner 还活着（窗口还开着）就接着用，不删它的状态/二维码、不起第二个。"""
    _write_status(login_dir, "window_login", xhs.HEADED_FALLBACK_MSG)
    qr = login_dir / "xiaohongshu.png"
    qr.write_bytes(b"\x89PNG qr")
    web.LOGIN_PROCESSES["xiaohongshu"] = live = FakeProc(None)

    def no_popen(*_a, **_kw):
        raise AssertionError("runner 还活着却又起了一个")

    monkeypatch.setattr(web.subprocess, "Popen", no_popen)
    res = asyncio.run(web.api_login_start("xiaohongshu"))
    assert res["mode"] == "qr"
    assert res["state"] == "window_login"
    assert res["message"] == xhs.HEADED_FALLBACK_MSG
    assert res["qr"] == "_login/xiaohongshu.png"
    assert qr.is_file() and (login_dir / "xiaohongshu.json").is_file()
    assert web.LOGIN_PROCESSES["xiaohongshu"] is live


def test_login_start_replaces_dead_runner(monkeypatch, login_dir):
    _write_status(login_dir, "error", "上一次失败")
    web.LOGIN_PROCESSES["xiaohongshu"] = FakeProc(1)
    started: list[list[str]] = []

    class FakePopen(FakeProc):
        def __init__(self, cmd, **_kw):
            super().__init__(None)
            started.append(list(cmd))
            _write_status(login_dir, "qr_ready")

    monkeypatch.setattr(web.subprocess, "Popen", FakePopen)
    res = asyncio.run(web.api_login_start("xiaohongshu"))
    assert len(started) == 1
    assert res["state"] == "qr_ready"


# ── Web：runner 死在非终态 → 弹窗必须拿到 error，不能一直转圈 ─────────────────────


@pytest.mark.parametrize("state", ["window_login", "verifying", "qr_ready", "scanned", "sms_required"])
def test_login_status_dead_runner_in_nonterminal_state_is_error(login_dir, state):
    _write_status(login_dir, state, "进行中")
    web.LOGIN_PROCESSES["xiaohongshu"] = FakeProc(1)
    s = web._login_status("xiaohongshu")
    assert s["state"] == "error"
    assert "退出码 1" in s["message"] and "登录没有完成" in s["message"]


@pytest.mark.parametrize("state", ["unknown", "starting"])
def test_login_status_dead_runner_before_status_is_error(login_dir, state):
    if state != "unknown":
        _write_status(login_dir, state)
    web.LOGIN_PROCESSES["xiaohongshu"] = FakeProc(2)
    s = web._login_status("xiaohongshu")
    assert s["state"] == "error"
    assert "退出码 2" in s["message"]


@pytest.mark.parametrize("state", ["success", "error", "expired"])
def test_login_status_keeps_terminal_state_of_dead_runner(login_dir, state):
    _write_status(login_dir, state, "终态")
    web.LOGIN_PROCESSES["xiaohongshu"] = FakeProc(0)
    s = web._login_status("xiaohongshu")
    assert (s["state"], s["message"]) == (state, "终态")


def test_login_status_live_runner_stays_nonterminal(login_dir):
    _write_status(login_dir, "window_login", xhs.HEADED_FALLBACK_MSG)
    web.LOGIN_PROCESSES["xiaohongshu"] = FakeProc(None)
    assert web._login_status("xiaohongshu")["state"] == "window_login"


def test_login_status_does_not_miss_final_success(login_dir):
    """runner 在我们查它的那一刻写完 success 并退出：先查进程再读文件，才不会把它误判成死在 verifying。"""
    _write_status(login_dir, "verifying", "登录成功，正在确认登录态已保存…")

    class FinishingProc:
        def poll(self):
            _write_status(login_dir, "success", "登录成功")
            return 0

    web.LOGIN_PROCESSES["xiaohongshu"] = FinishingProc()
    assert web._login_status("xiaohongshu")["state"] == "success"


# ── Web：登录标记指纹（loginTs）让前后端的 whoami 缓存都能发现「之后有人登录过」──────
# （用抖音演示：小红书的 whoami 已不起浏览器，见 test_xhs_whoami_never_launches_browser）


@pytest.fixture
def whoami_env(monkeypatch, login_dir, tmp_path):
    import publish_guard
    monkeypatch.setattr(publish_guard, "COOLDOWN_PATH", tmp_path / "cooldown.json")   # 不碰真实冷却记录
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    calls: list[list[str]] = []
    answer = {"loggedIn": False, "name": "", "avatar": ""}

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(answer), stderr="")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    return login_dir / "douyin.json", calls, answer


def _whoami() -> dict:
    return asyncio.run(web.api_account_whoami("douyin", manual=1))


def _simulate_cli_login(marker: Path) -> None:
    marker.write_text(json.dumps({"state": "success", "message": "登录成功", "qr": "", "ts": 0}),
                      encoding="utf-8")


def test_whoami_rechecks_when_marker_changes_after_cache(whoami_env):
    """缓存了「未登录」之后 CLI 登录写了标记 → 下一次 whoami 必须重新真校验，而不是顶着旧结果。"""
    marker, calls, answer = whoami_env
    assert _whoami()["loggedIn"] is False
    assert len(calls) == 1

    _simulate_cli_login(marker)
    answer["loggedIn"] = True
    assert _whoami()["loggedIn"] is True
    assert len(calls) == 2

    # whoami 自己回写的标记不能让自己的缓存作废，否则缓存形同虚设
    assert _whoami()["loggedIn"] is True
    assert len(calls) == 2


def test_whoami_marker_check_is_clock_independent(whoami_env):
    """只比指纹相等、不比先后：别的进程改写标记时 mtime 比缓存时刻还「早」（时钟不一致），也要作废。"""
    marker, calls, answer = whoami_env
    answer["loggedIn"] = True
    _whoami()
    _whoami()
    assert len(calls) == 1          # 标记没变：走缓存

    cached_at = web._WHOAMI_CACHE["douyin"][0]
    _simulate_cli_login(marker)
    os.utime(marker, (cached_at - 3600, cached_at - 3600))
    _whoami()
    assert len(calls) == 2


def test_login_ts_matches_between_accounts_and_whoami(whoami_env, monkeypatch):
    """前端拿 whoami 返回的 loginTs 记进缓存，再跟 /api/accounts 的比相等：两边必须是同一枚指纹。"""
    marker, _calls, answer = whoami_env
    monkeypatch.setattr(web, "_account_logged_in", lambda *_a: False)   # 不读真机的公众号/B 站配置

    def accounts() -> dict[str, float | None]:
        return {a["platform"]: a["loginTs"] for a in asyncio.run(web.api_accounts())}

    assert accounts()["douyin"] is None
    assert _whoami()["loginTs"] is None         # 未登录：whoami 删了标记

    answer["loggedIn"] = True
    web._WHOAMI_CACHE.clear()
    res = _whoami()
    assert res["loginTs"] == marker.stat().st_mtime_ns / 1e9
    assert accounts()["douyin"] == res["loginTs"]
    assert _whoami()["loginTs"] == res["loginTs"]   # 走缓存时也带当前指纹

    _simulate_cli_login(marker)
    os.utime(marker, ns=(1, 1))
    assert accounts()["douyin"] != res["loginTs"]
    assert accounts()["kuaishou"] is None


# ── 默认开本机 Chrome 窗口（2026-10 无头 + 自带内核导致账号被判「第三方脚本」封号）──────────


class _RecordingChromium:
    def __init__(self):
        self.calls: list[dict] = []
        self.chromium = self

    def launch_persistent_context(self, profile: str, **kwargs):
        self.calls.append(kwargs)
        return object()


@pytest.mark.parametrize("headed", [False, True])
def test_launch_falls_back_to_real_chrome_window(monkeypatch, tmp_path, headed):
    monkeypatch.delenv("EASEL_XHS_HEADLESS", raising=False)
    monkeypatch.setattr(xhs, "_browser_channel", lambda: "chrome")
    monkeypatch.setattr(xhs, "_cloak_executable", lambda: None)      # 没装 Cloak：退回本机 Chrome
    pw = _RecordingChromium()
    xhs._launch(pw, headed=headed, base=str(tmp_path), proxy=None)
    kw = pw.calls[0]
    assert kw["headless"] is False                     # 调用方要无头也不给
    assert kw["channel"] == "chrome"
    assert "executable_path" not in kw
    assert "--enable-automation" in kw["ignore_default_args"]
    assert kw["no_viewport"] is True
    for flag in ("--no-sandbox", "--disable-gpu", "--disable-extensions"):
        assert flag not in kw["args"]


def test_launch_headless_only_when_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("EASEL_XHS_HEADLESS", "1")
    monkeypatch.setattr(xhs, "_browser_channel", lambda: None)
    monkeypatch.setattr(xhs, "_cloak_executable", lambda: None)
    pw = _RecordingChromium()
    xhs._launch(pw, headed=False, base=str(tmp_path), proxy=None)
    assert pw.calls[0]["headless"] is True
    assert "no_viewport" not in pw.calls[0]


def test_login_opens_window_by_default(fake_browser, tmp_path, monkeypatch):
    """不允许无头时，登录一上来就开窗口（不再先无头碰一次小红书、被 300012 拦了才改窗口）。"""
    make, _statuses = fake_browser
    monkeypatch.delenv("EASEL_XHS_HEADLESS")
    world = make()
    rc = xhs.cmd_login(_login_args(tmp_path))
    assert rc == 0
    assert world.launches and not any(world.launches)


def test_xhs_whoami_never_launches_browser(whoami_env, monkeypatch, tmp_path):
    """小红书账号卡片的校验只读登录标记 + 上次创作数据里的昵称，绝不在后台开浏览器。"""
    _marker, calls, _answer = whoami_env
    xhs_marker = web.LOGIN_DIR / "xiaohongshu.json"
    ana = tmp_path / "_analytics"
    ana.mkdir()
    monkeypatch.setattr(web, "ANALYTICS_CACHE_DIR", ana)
    res = asyncio.run(web.api_account_whoami("xiaohongshu"))
    assert res["loggedIn"] is False and res["name"] == ""
    _simulate_cli_login(xhs_marker)
    (ana / "xiaohongshu-latest.json").write_text(json.dumps({"nickname": "小红薯A"}), encoding="utf-8")
    res = asyncio.run(web.api_account_whoami("xiaohongshu"))
    assert res["loggedIn"] is True and res["name"] == "小红薯A"
    assert calls == []
    assert xhs_marker.is_file()          # 也不会因为「没校验」去删标记


# ── 优先 CloakBrowser：账号固定指纹 + 独立数据目录 ───────────────────────────────


@pytest.fixture
def cloak_bin(monkeypatch, tmp_path):
    exe = tmp_path / "Chromium"
    exe.write_text("", encoding="utf-8")
    monkeypatch.delenv("EASEL_XHS_HEADLESS", raising=False)
    monkeypatch.delenv("EASEL_XHS_BROWSER", raising=False)
    monkeypatch.setattr(xhs, "_cloak_executable", lambda: exe)
    monkeypatch.setattr(xhs, "_browser_channel",
                        lambda: (_ for _ in ()).throw(AssertionError("有 Cloak 就不该找 Chrome")))
    monkeypatch.setattr(xhs, "_host_fingerprint_platform", lambda: "macos")
    return exe


def test_cloak_preferred_with_fixed_fingerprint(cloak_bin, tmp_path):
    pw = _RecordingChromium()
    base = str(tmp_path / "profiles")
    xhs._launch(pw, headed=False, base=base, proxy=None)
    xhs._launch(pw, headed=False, base=base, proxy=None)
    first, second = pw.calls
    assert first["executable_path"] == str(cloak_bin) and "channel" not in first
    assert first["headless"] is False and first["no_viewport"] is True
    seeds = [a for a in first["args"] if a.startswith("--fingerprint=")]
    assert len(seeds) == 1 and seeds == [a for a in second["args"] if a.startswith("--fingerprint=")]
    assert "--fingerprint-platform=macos" in first["args"]
    assert "--lang=zh-CN" in first["args"] and "locale" not in first   # 不走 Playwright 的 CDP 语言模拟
    assert {"--enable-automation", "--enable-unsafe-swiftshader"} <= set(first["ignore_default_args"])
    assert "--no-sandbox" not in first["args"]
    fp = json.loads((Path(base) / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE).read_text(encoding="utf-8"))
    assert seeds == [f"--fingerprint={fp['seed']}"] and fp["platform"] == "macos"


def test_cloak_uses_own_data_dir_inside_account_dir(cloak_bin, tmp_path):
    seen = []

    class Rec(_RecordingChromium):
        def launch_persistent_context(self, profile, **kwargs):
            seen.append(profile)
            return object()

    xhs._launch(Rec(), headed=False, base=str(tmp_path / "profiles"), proxy=None)
    assert seen == [str(tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.CLOAK_DATA_DIR)]


@pytest.mark.parametrize("content", ["{oops", '{"seed": "x", "platform": "macos"}', '{"seed": 5, "platform": "macos"}',
                                     '{"seed": 12345, "platform": "linux"}'])
def test_bad_fingerprint_file_is_regenerated(cloak_bin, tmp_path, content):
    path = tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    fp = xhs._account_fingerprint(str(tmp_path / "profiles"))
    assert 10000 <= fp["seed"] <= 99999 and fp["platform"] == "macos"
    assert json.loads(path.read_text(encoding="utf-8"))["seed"] == fp["seed"]


def test_existing_fingerprint_is_kept(cloak_bin, tmp_path):
    path = tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE
    path.parent.mkdir(parents=True)
    path.write_text('{"seed": 54321, "platform": "macos"}', encoding="utf-8")
    pw = _RecordingChromium()
    xhs._launch(pw, headed=False, base=str(tmp_path / "profiles"), proxy=None)
    assert "--fingerprint=54321" in pw.calls[0]["args"]


def test_env_can_force_chrome(cloak_bin, tmp_path, monkeypatch):
    monkeypatch.setenv("EASEL_XHS_BROWSER", "chrome")
    monkeypatch.setattr(xhs, "_browser_channel", lambda: "chrome")
    pw = _RecordingChromium()
    xhs._launch(pw, headed=False, base=str(tmp_path / "profiles"), proxy=None)
    assert pw.calls[0]["channel"] == "chrome" and "executable_path" not in pw.calls[0]
    assert not (tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE).exists()


def test_cloak_executable_finds_newest_mac_build(monkeypatch, tmp_path):
    monkeypatch.delenv("EASEL_CLOAK_BROWSER", raising=False)
    monkeypatch.setenv("CLOAKBROWSER_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(xhs.sys, "platform", "darwin")
    exes = []
    for i, v in enumerate(("145.0.7632.109.2", "152.0.1.1")):
        exe = tmp_path / f"chromium-{v}" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
        os.utime(exe, (1000 + i, 1000 + i))
        exes.append(exe)
    assert xhs._cloak_executable() == exes[1]
    (tmp_path / "chromium-9.0.0.0" / "chrome.exe").parent.mkdir()
    (tmp_path / "chromium-9.0.0.0" / "chrome.exe").write_text("", encoding="utf-8")
    assert xhs._cloak_executable() == exes[1]          # Mac 上不认 Windows 的 chrome.exe


def test_cloak_executable_none_without_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("EASEL_CLOAK_BROWSER", raising=False)
    monkeypatch.setenv("CLOAKBROWSER_CACHE_DIR", str(tmp_path / "nope"))
    assert xhs._cloak_executable() is None


def test_fingerprint_from_other_platform_is_regenerated(cloak_bin, tmp_path, capsys):
    path = tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE
    path.parent.mkdir(parents=True)
    path.write_text('{"seed": 12345, "platform": "windows"}', encoding="utf-8")
    fp = xhs._account_fingerprint(str(tmp_path / "profiles"))
    assert fp["platform"] == "macos"
    assert "和本机不符" in capsys.readouterr().err


def test_fingerprint_creation_keeps_first_writer(cloak_bin, tmp_path, monkeypatch):
    """两个进程同时第一次打开：后到的不能覆盖先到的 seed，读先到的那份。"""
    base = str(tmp_path / "profiles")
    path = tmp_path / "profiles" / xhs.PROFILE_NAME / xhs.FINGERPRINT_FILE
    path.parent.mkdir(parents=True)
    real_link = os.link

    def racing_link(src, dst):
        Path(dst).write_text('{"seed": 22222, "platform": "macos"}', encoding="utf-8")   # 别人抢先落盘
        return real_link(src, dst)

    monkeypatch.setattr(xhs.os, "link", racing_link)
    monkeypatch.setattr(xhs.time, "sleep", lambda _s: None)
    assert xhs._account_fingerprint(base)["seed"] == 22222
    assert not list(path.parent.glob("*.tmp"))


def test_check_does_not_require_bundled_chromium_with_cloak(cloak_bin):
    ok, lines = xhs.browser_report()
    assert ok and any("CloakBrowser" in ln for ln in lines)


def test_logout_keeps_fingerprint_and_rate_limit_files(login_dir, monkeypatch, tmp_path):
    profiles = tmp_path / "profiles"
    pdir = profiles / xhs.PROFILE_NAME
    (pdir / xhs.CLOAK_DATA_DIR / "Default").mkdir(parents=True)
    (pdir / "Default").mkdir()
    (pdir / "Cookies").write_text("x", encoding="utf-8")
    (pdir / xhs.FINGERPRINT_FILE).write_text('{"seed": 12345, "platform": "macos"}', encoding="utf-8")
    (pdir / xhs.ACTIVITY_FILE).write_text('{"publish": [1]}', encoding="utf-8")
    monkeypatch.setattr(web, "BROWSER_PROFILES", profiles)
    assert set(web.PROFILE_KEEP_ON_LOGOUT) == {xhs.FINGERPRINT_FILE, xhs.ACTIVITY_FILE}
    res = asyncio.run(web.api_logout("xiaohongshu"))
    assert xhs.PROFILE_NAME in res["deleted"]
    assert sorted(c.name for c in pdir.iterdir()) == sorted([xhs.ACTIVITY_FILE, xhs.FINGERPRINT_FILE])


# ── 不再莫名弹窗：whoami 默认不开浏览器，小红书数据抓取必须明确 --manual ─────────────
# 现场（2026-10-02）：合并后没重启的旧 Web 后端还在定时调 `xhs_publish.py whoami`，而磁盘上的新脚本
# 一律开窗口 → 隔一会儿弹一个 Cloak 窗口打开小红书。


def test_whoami_is_passive_by_default(monkeypatch, outputs_root, capsys):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)   # 真要起浏览器会 ImportError
    marker = outputs_root / "_login" / "xiaohongshu.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    args = types.SimpleNamespace(live=False, profile_base=None, proxy=None, no_proxy=True)
    assert xhs.cmd_whoami(args) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["loggedIn"] is False and out["passive"] is True and "error" not in out
    marker.write_text(json.dumps({"state": "success"}), encoding="utf-8")
    xhs.cmd_whoami(args)
    assert json.loads(capsys.readouterr().out.strip())["loggedIn"] is True


def test_xhs_stats_refuse_without_manual(monkeypatch, capsys):
    import account_stats
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    monkeypatch.setattr(account_stats, "_scrape", lambda *a: (_ for _ in ()).throw(AssertionError("不该抓")))
    args = types.SimpleNamespace(platform="xiaohongshu", manual=False, no_proxy=False, proxy=None,
                                 headed=False, profile_base=None)
    assert account_stats.cmd_fetch(args) == 2
    assert "manual-only" in json.loads(capsys.readouterr().out.strip())["error"]


def test_web_passes_manual_only_for_xhs():
    assert web._analytics_cmd("xiaohongshu")[-1] == "--manual"
    assert "--manual" not in web._analytics_cmd("douyin")
