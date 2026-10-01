"""海外发布浏览器底座（overseas/base.py）的离线测试：不起真浏览器。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import base  # noqa: E402


class FakeContext:
    def __init__(self, cookies=()):
        self._cookies = list(cookies)
        self.asked: list = []

    def cookies(self, urls=None):
        self.asked.append(urls)
        return list(self._cookies)


class FakePage:
    """urls：每次 wait_for_timeout 之后依次切到的地址（模拟客户端跳转）。"""

    def __init__(self, url="https://example.com/home", cookies=(), urls=None):
        self.context = FakeContext(cookies)
        self._urls = list(urls or [])
        self.url = url
        self.waits = 0
        self.closed = False

    def wait_for_timeout(self, _ms):
        self.waits += 1
        if self._urls:
            self.url = self._urls.pop(0)

    def is_closed(self):
        return self.closed


MOD = SimpleNamespace(COOKIE_URL="https://example.com", AUTH_COOKIES=("sid",), LOGIN_MARKERS=("/login",))
MOD.is_logged_in = lambda page: (base.has_auth_cookie(page, MOD.COOKIE_URL, MOD.AUTH_COOKIES)
                                 and not base.on_login_page(page, MOD.LOGIN_MARKERS))
SID = [{"name": "sid", "value": "v"}]


def test_has_auth_cookie_needs_named_nonempty_cookie():
    assert base.has_auth_cookie(FakePage(cookies=SID), MOD.COOKIE_URL, ("sid",))
    assert not base.has_auth_cookie(FakePage(cookies=[{"name": "sid", "value": ""}]), MOD.COOKIE_URL, ("sid",))
    assert not base.has_auth_cookie(FakePage(cookies=[{"name": "other", "value": "v"}]), MOD.COOKIE_URL, ("sid",))
    page = FakePage(cookies=SID)
    base.has_auth_cookie(page, MOD.COOKIE_URL, ("sid",))
    assert page.context.asked == [["https://example.com"]]


def test_has_auth_cookie_swallows_errors():
    class Boom:
        def cookies(self, urls=None):
            raise RuntimeError("closed")

    page = FakePage()
    page.context = Boom()
    assert base.has_auth_cookie(page, MOD.COOKIE_URL, ("sid",)) is False


def test_on_login_page_is_case_insensitive():
    assert base.on_login_page(FakePage(url="https://x.com/i/flow/LOGIN"), ("/i/flow/login",))
    assert not base.on_login_page(FakePage(url="https://x.com/home"), ("/i/flow/login",))


def test_settle_needs_a_stable_logged_in_streak():
    page = FakePage(cookies=SID)
    assert base.settle(page, MOD, rounds=5, step_ms=1, stable=3) is True
    assert page.waits == 3


def test_settle_catches_late_redirect_to_login():
    """会话过期但 cookie 还在：几秒后客户端跳回登录页，不能算已登录（Review Focus 1）。"""
    page = FakePage(cookies=SID, urls=["https://example.com/home", "https://example.com/login"])
    assert base.settle(page, MOD, rounds=6, step_ms=1, stable=3) is False


def test_settle_times_out_without_cookie():
    page = FakePage()
    assert base.settle(page, MOD, rounds=4, step_ms=1, stable=2) is False
    assert page.waits == 4


def test_launch_options_use_real_chrome_flags_and_proxy():
    opts = base.launch_options(headed=True, env={"EASEL_PROXY": "http://127.0.0.1:7890"})
    assert opts["headless"] is False
    assert "--disable-blink-features=AutomationControlled" in opts["args"]
    assert "--no-proxy-server" not in opts["args"]          # 海外不强制直连（国内照旧）
    assert opts["ignore_default_args"] == ["--enable-automation"]
    assert opts["proxy"] == {"server": "http://127.0.0.1:7890"}
    assert "proxy" not in base.launch_options(headed=False, env={})
    assert base.launch_options(headed=False, env={})["headless"] is True


class FakeChromium:
    def __init__(self, fail_chrome: Exception | None):
        self.fail_chrome = fail_chrome
        self.calls: list[dict] = []

    def launch_persistent_context(self, user_data_dir, **kw):
        self.calls.append(kw)
        if kw.get("channel") == "chrome" and self.fail_chrome:
            raise self.fail_chrome
        return SimpleNamespace(pages=[], kw=kw)


def test_open_context_prefers_installed_chrome(tmp_path):
    ctx = base.open_context(SimpleNamespace(chromium=FakeChromium(None)), tmp_path / "Prof", headed=False, env={})
    assert ctx.kw["channel"] == "chrome"
    assert (tmp_path / "Prof").is_dir()


def test_open_context_falls_back_when_chrome_missing(tmp_path, capsys):
    """本机没装 Chrome：退回自带 Chromium 并提示，不崩（Review Focus 3）。"""
    err = RuntimeError("Chromium distribution 'chrome' is not found at /Applications/Google Chrome.app")
    chromium = FakeChromium(err)
    ctx = base.open_context(SimpleNamespace(chromium=chromium), tmp_path / "Prof", headed=True, env={})
    assert "channel" not in ctx.kw
    assert len(chromium.calls) == 2
    assert "Chrome" in capsys.readouterr().err


def test_open_context_reraises_other_errors(tmp_path):
    chromium = FakeChromium(RuntimeError("Target page, context or browser has been closed"))
    with pytest.raises(RuntimeError, match="closed"):
        base.open_context(SimpleNamespace(chromium=chromium), tmp_path / "Prof", headed=True, env={})


def test_profile_dir_uses_module_profile(tmp_path):
    assert base.profile_dir(SimpleNamespace(PROFILE="XProfile"), tmp_path) == tmp_path / "XProfile"
    assert base.profile_dir(SimpleNamespace(PROFILE="XProfile")) == base.PROFILE_ROOT / "XProfile"


def test_profile_lock_is_exclusive(tmp_path):
    a = base.ProfileLock(tmp_path / "Prof")
    b = base.ProfileLock(tmp_path / "Prof")
    a.acquire(1)
    try:
        with pytest.raises(TimeoutError):
            b.acquire(0.3)
    finally:
        a.release()
    b.acquire(1)
    b.release()


def test_ensure_window_open_raises_when_closed():
    page = FakePage()
    page.closed = True
    with pytest.raises(base.WindowClosed):
        base.ensure_window_open(page)


@pytest.mark.parametrize("exc,expected", [
    (base.WindowClosed(), True),
    (type("TargetClosedError", (Exception,), {})("Target closed"), True),
    (RuntimeError("Target page, context or browser has been closed"), True),
    (RuntimeError("net::ERR_NAME_NOT_RESOLVED"), False),
])
def test_is_window_closed_error(exc, expected):
    assert base.is_window_closed_error(exc) is expected


def test_read_identity_best_effort():
    class El:
        def __init__(self, text="", src=""):
            self.text, self.src = text, src

        def inner_text(self):
            return self.text

        def get_attribute(self, _name):
            return self.src

    class Page:
        def query_selector(self, sel):
            return {"#name": El(text="Alice\n@alice"), "img.av": El(src="https://cdn/a.jpg"),
                    "img.data": El(src="data:image/png;base64,xx")}.get(sel)

    assert base.read_identity(Page(), "#missing, #name", "img.data, img.av") == {
        "name": "Alice", "avatar": "https://cdn/a.jpg"}
    assert base.read_identity(Page(), "#missing", "") == {"name": "", "avatar": ""}


def test_short_err_truncates():
    assert base.short_err(RuntimeError("x" * 500)).endswith("…")
    assert base.short_err(RuntimeError("")) == "RuntimeError"


class UAChromium(FakeChromium):
    """launch 出的上下文第一页报告给定 UA；记录关闭次数。"""

    def __init__(self, ua, fail_chrome=None):
        super().__init__(fail_chrome)
        self.ua = ua
        self.closed = 0

    def launch_persistent_context(self, user_data_dir, **kw):
        self.calls.append(kw)
        if kw.get("channel") == "chrome" and self.fail_chrome:
            raise self.fail_chrome
        outer = self

        class Page:
            def evaluate(self, _js):
                return outer.ua

        class Ctx:
            pages = [Page()]

            def close(self):
                outer.closed += 1

        ctx = Ctx()
        ctx.kw = kw
        return ctx


HEADLESS_UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/154.0.0.0 Safari/537.36"


def test_headless_relaunches_with_plain_chrome_user_agent(tmp_path):
    """X 对 UA 带 HeadlessChrome 的无头浏览器一律回 403（真机校准）：换成普通 Chrome 的 UA 重开。"""
    ch = UAChromium(HEADLESS_UA)
    ctx = base.open_context(SimpleNamespace(chromium=ch), tmp_path / "Prof", headed=False, env={})
    assert len(ch.calls) == 2 and ch.closed == 1
    assert ctx.kw["user_agent"] == HEADLESS_UA.replace("HeadlessChrome", "Chrome")
    assert ctx.kw["channel"] == "chrome"


def test_headless_fallback_chromium_also_gets_plain_user_agent(tmp_path, capsys):
    ch = UAChromium(HEADLESS_UA, fail_chrome=RuntimeError("Chromium distribution 'chrome' is not found"))
    ctx = base.open_context(SimpleNamespace(chromium=ch), tmp_path / "Prof", headed=False, env={})
    assert "channel" not in ctx.kw
    assert ctx.kw["user_agent"] == HEADLESS_UA.replace("HeadlessChrome", "Chrome")


def test_headed_keeps_default_user_agent(tmp_path):
    ch = UAChromium(HEADLESS_UA)
    ctx = base.open_context(SimpleNamespace(chromium=ch), tmp_path / "Prof", headed=True, env={})
    assert len(ch.calls) == 1 and "user_agent" not in ctx.kw


def test_settle_unsure_when_cookie_present_but_never_stable():
    """有登录 cookie、却等满都没稳定成登录态：说不准（None），调用方不能当成「未登录」。"""
    mod = SimpleNamespace(COOKIE_URL="https://example.com", AUTH_COOKIES=("sid",), LOGIN_MARKERS=("/login",),
                          is_logged_in=lambda page: False)
    assert base.settle(FakePage(cookies=SID), mod, rounds=3, step_ms=1, stable=2) is None


def test_settle_login_form_means_logged_out():
    """平台不跳登录页、直接在首页给登录表单（Instagram）：看到表单就是可信的「未登录」。"""
    class FormPage(FakePage):
        def query_selector(self, sel):
            return object() if sel == 'input[name="username"]' else None

    mod = SimpleNamespace(COOKIE_URL="https://example.com", AUTH_COOKIES=("sid",), LOGIN_MARKERS=("/login",),
                          LOGIN_FORM='input[name="username"]', is_logged_in=lambda page: False)
    page = FormPage(cookies=SID)
    assert base.settle(page, mod, rounds=5, step_ms=1, stable=2) is False
    assert page.waits == 1
