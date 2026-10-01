"""海外平台发布的浏览器底座：启动本机 Chrome、登录目录、代理、等待落定、读身份、登录目录锁。

与国内平台（web_publisher.py / xhs_publish.py）互不影响：国内一律直连（--no-proxy-server），
这里不加；配了 EASEL_PROXY 才走代理，否则用系统网络设置。
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROFILE_ROOT = Path.home() / ".easel-browser-profiles"
# 不加 --no-sandbox / --disable-gpu：真 Chrome 会为这些参数弹「不受支持的命令行标记」提示条
LAUNCH_ARGS = ("--disable-blink-features=AutomationControlled", "--no-first-run",
               "--no-default-browser-check")
CHROME_MISSING_HINT = ("没找到本机 Google Chrome，改用 Playwright 自带的 Chromium；"
                       "YouTube（Google）登录可能会被拦，建议先安装 Chrome")


class PlaywrightMissing(RuntimeError):
    """没装 Playwright。"""


class WindowClosed(RuntimeError):
    """用户把登录窗口关掉了。"""


def short_err(e: BaseException, limit: int = 160) -> str:
    text = " ".join(str(e).split())
    text = f"{type(e).__name__}: {text}" if text else type(e).__name__
    return text if len(text) <= limit else text[:limit] + "…"


def profile_dir(mod, root: str | Path | None = None) -> Path:
    return (Path(root).expanduser() if root else PROFILE_ROOT) / mod.PROFILE


def launch_options(headed: bool, env=None) -> dict:
    env = os.environ if env is None else env
    opts = {
        "headless": not headed,
        "args": list(LAUNCH_ARGS),
        # 去掉「Chrome 正受到自动测试软件的控制」提示条和 navigator.webdriver 标记（Google 登录会看它）
        "ignore_default_args": ["--enable-automation"],
        "viewport": {"width": 1280, "height": 860},
        "locale": "en-US",
    }
    proxy = (env.get("EASEL_PROXY") or "").strip()
    if proxy:
        opts["proxy"] = {"server": proxy}
    return opts


def _chrome_missing(e: BaseException) -> bool:
    s = str(e).lower()
    return "chrome" in s and ("not found" in s or "doesn't exist" in s or "no such file" in s)


def open_context(p, profile: Path, *, headed: bool, env=None):
    """优先用本机 Google Chrome（Google 登录只认真 Chrome），没装就退回自带 Chromium 并提示。"""
    profile.mkdir(parents=True, exist_ok=True)
    opts = launch_options(headed, env)
    try:
        return p.chromium.launch_persistent_context(str(profile), channel="chrome", **opts)
    except Exception as e:  # noqa: BLE001
        if not _chrome_missing(e):
            raise
        print(f"⚠️ {CHROME_MISSING_HINT}", file=sys.stderr)
        return p.chromium.launch_persistent_context(str(profile), **opts)


def close_quietly(ctx) -> None:
    try:
        ctx.close()
    except Exception as e:  # noqa: BLE001 — 窗口已被关 / 浏览器已崩时 close 也会抛，不能盖掉真正的结果
        print(f"关闭浏览器时出错（忽略）：{short_err(e)}", file=sys.stderr)


@contextmanager
def launch(profile: Path, *, headed: bool):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise PlaywrightMissing(f"需要 playwright：{e}") from e
    with sync_playwright() as p:
        ctx = open_context(p, profile, headed=headed)
        try:
            yield ctx
        finally:
            close_quietly(ctx)


def first_page(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def has_auth_cookie(page, url: str, names) -> bool:
    try:
        cookies = page.context.cookies([url])
    except Exception:  # noqa: BLE001
        return False
    return any(c.get("name") in names and c.get("value") for c in cookies or ())


def on_login_page(page, markers) -> bool:
    try:
        url = (page.url or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(m.lower() in url for m in markers)


def settle(page, mod, *, rounds: int = 12, step_ms: int = 800, stable: int = 3) -> bool:
    """等客户端跳转落定再下结论：连续 stable 轮都是登录态才算已登录；落到登录页、或等满都没稳定，算未登录。
    会话过期时登录 cookie 往往还在，页面要过几秒才跳回登录页——只看第一眼会误判成已登录。"""
    streak = 0
    for _ in range(rounds):
        page.wait_for_timeout(step_ms)
        try:
            if on_login_page(page, mod.LOGIN_MARKERS):
                return False
            streak = streak + 1 if mod.is_logged_in(page) else 0
        except Exception:  # noqa: BLE001
            streak = 0
        if streak >= stable:
            return True
    return False


def _split(selectors: str) -> list[str]:
    return [s.strip() for s in (selectors or "").split(",") if s.strip()]


def read_identity(page, name_selectors: str, avatar_selectors: str) -> dict:
    """尽力读昵称和头像：逐个选择器试，读不到就留空，不抛错。选择器内部不要含逗号（逗号用来分隔候选）。"""
    out = {"name": "", "avatar": ""}
    for sel in _split(name_selectors):
        try:
            el = page.query_selector(sel)
            text = (el.inner_text() or "").strip() if el else ""
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            out["name"] = text.splitlines()[0].strip()[:40]
            break
    for sel in _split(avatar_selectors):
        try:
            el = page.query_selector(sel)
            src = (el.get_attribute("src") or "") if el else ""
        except Exception:  # noqa: BLE001
            src = ""
        if src.startswith("http"):
            out["avatar"] = src
            break
    return out


def ensure_window_open(page) -> None:
    """窗口被关后，Playwright 的查询会被吞掉、只有等待才抛异常：先主动查一下，明确报「窗口被关」。"""
    try:
        closed = page.is_closed()
    except Exception:  # noqa: BLE001
        closed = False
    if closed:
        raise WindowClosed()


def is_window_closed_error(e: BaseException) -> bool:
    if isinstance(e, WindowClosed) or "TargetClosed" in type(e).__name__:
        return True
    return "has been closed" in str(e)


class ProfileLock:
    """同一个登录目录同时只能有一个浏览器：登录窗口开着时，whoami / 发布等着或放弃，别再开第二个。
    （与 xhs_publish._ProfileLock 同一做法；海外这份独立，不改国内代码。）"""

    def __init__(self, profile: Path):
        self.path = profile / ".easel.lock"
        self.fd: int | None = None

    def acquire(self, timeout_s: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + timeout_s
        last: OSError | None = None
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as e:
                last = e
                if self.fd is not None:
                    try:
                        os.close(self.fd)
                    except OSError:
                        pass
                    self.fd = None
                if time.time() >= deadline:
                    raise TimeoutError(f"登录目录正被占用：{self.path.parent}") from last
                time.sleep(0.2)

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
