"""海外平台发布的浏览器底座：启动本机 Chrome、登录目录、代理、等待落定、读身份、登录目录锁。

与国内平台（web_publisher.py / xhs_publish.py）互不影响：国内一律直连（--no-proxy-server），
这里不加；配了 EASEL_PROXY 才走代理，否则用系统网络设置。
"""
from __future__ import annotations

import os
import random
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .post import TAG_AT_LINE_END

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


def _headless_user_agent(ctx) -> str:
    """无头 Chrome 的 UA 带「HeadlessChrome」，X 对这样的未登录访问一律回 403（真机校准于 2026-10-01）。
    读出默认 UA，带这个标记就返回换成普通「Chrome」的 UA；读不到或不带标记返回空串。"""
    try:
        ua = first_page(ctx).evaluate("navigator.userAgent") or ""
    except Exception:  # noqa: BLE001
        return ""
    return ua.replace("HeadlessChrome", "Chrome") if "HeadlessChrome" in ua else ""


def open_context(p, profile: Path, *, headed: bool, env=None):
    """优先用本机 Google Chrome（Google 登录只认真 Chrome），没装就退回自带 Chromium 并提示。
    无头启动时把 UA 里的 HeadlessChrome 换成 Chrome 再重开一次（多 1 秒左右）。"""
    profile.mkdir(parents=True, exist_ok=True)
    opts = launch_options(headed, env)
    channel = {"channel": "chrome"}
    try:
        ctx = p.chromium.launch_persistent_context(str(profile), **channel, **opts)
    except Exception as e:  # noqa: BLE001
        if not _chrome_missing(e):
            raise
        print(f"⚠️ {CHROME_MISSING_HINT}", file=sys.stderr)
        channel = {}
        ctx = p.chromium.launch_persistent_context(str(profile), **opts)
    if headed:
        return ctx
    ua = _headless_user_agent(ctx)
    if not ua:
        return ctx
    close_quietly(ctx)
    return p.chromium.launch_persistent_context(str(profile), **channel, **opts, user_agent=ua)


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


def shows_login_form(page, selector: str) -> bool:
    """页面上有登录表单（有的平台会话失效时不跳登录页，直接在首页给表单，如 Instagram）。"""
    if not selector:
        return False
    try:
        return page.query_selector(selector) is not None
    except Exception:  # noqa: BLE001
        return False


def settle(page, mod, *, rounds: int = 12, step_ms: int = 800, stable: int = 3) -> bool | None:
    """等客户端跳转落定再下结论，三种结果：
    - True：连续 stable 轮都是登录态。会话过期时登录 cookie 往往还在、页面过几秒才跳回登录页——只看第一眼会误判。
    - False：可信的未登录——落到登录页 / 出现登录表单（模块的 LOGIN_FORM），或等满了连登录 cookie 都没有。
    - None：说不准——有登录 cookie 却一直没稳定成登录态（慢网、页面卡住）。调用方不能据此当成未登录。"""
    streak = 0
    login_form = getattr(mod, "LOGIN_FORM", "")
    for _ in range(rounds):
        page.wait_for_timeout(step_ms)
        try:
            if on_login_page(page, mod.LOGIN_MARKERS) or shows_login_form(page, login_form):
                return False
            streak = streak + 1 if mod.is_logged_in(page) else 0
        except Exception:  # noqa: BLE001
            streak = 0
        if streak >= stable:
            return True
    try:
        has_cookie = has_auth_cookie(page, mod.COOKIE_URL, mod.AUTH_COOKIES)
    except Exception:  # noqa: BLE001 — 判断不了就当说不准
        return None
    return None if has_cookie else False


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


# ---- 发布：页面驱动、结果、失败现场 ----------------------------------------------------------

# 话题 / @ 联想框：X、Threads 是 listbox（Instagram、TikTok 的列表打空格就收，不用认）
SUGGESTIONS = '[role="listbox"]'
SUGGESTION_WAIT_MS = 800        # Threads 的话题框是异步弹出的，补完空格等它这么久再判断

# 落到这些页面 = 平台要人工验证（验证码 / 安全检查），无头浏览器过不去，调用方改开有头窗口
BLOCK_MARKERS = ("captcha", "/challenge", "checkpoint", "/account/access", "/suspended")


# 等不到发布按钮能点时的提示（按形式）：纯文字多半是文案超了平台上限
POST_DISABLED_MSG = {"video": "视频处理超时，发布按钮一直不能点", "image": "图片处理超时，发布按钮一直不能点",
                     "text": "发布按钮一直不能点（文案可能超长）"}


class StepFailed(RuntimeError):
    """发布流程某一步做不下去（找不到元素、超时）：多半是平台改版，调用方保存失败现场。"""


class Blocked(RuntimeError):
    """平台拦了无头浏览器（验证码 / 安全检查页）：调用方可改开有头窗口重试一次。"""


@dataclass
class Result:
    status: str          # success：确认已发出；failed：明确失败；unknown：点了发布但没等到成功信号
    url: str = ""
    message: str = ""


class PageDriver:
    """平台发布流程只通过它操作页面，离线测试里换成按剧本走的假驱动。
    pace：每个动作后随机停顿的秒数区间（像人一样操作，测试里传 (0, 0)）。
    block_wait_ms：落到验证页时等用户在窗口里过验证的最长时间；0 = 不等直接抛 Blocked（无头时）。
    committed：已经点了最终的发布按钮，之后出任何错都可能已经发出去了。"""

    def __init__(self, page, *, pace: tuple[float, float] = (0.25, 0.7), block_wait_ms: int = 0):
        self.page = page
        self.pace = pace
        self.block_wait_ms = block_wait_ms
        self.committed = False

    def _rest(self) -> None:
        lo, hi = self.pace
        if hi > 0:
            self.page.wait_for_timeout(int(random.uniform(lo, hi) * 1000))

    def goto(self, url: str, timeout_ms: int = 60000) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if not self._blocked():
            return
        if not self._wait_unblocked():
            raise Blocked(f"被带到了验证页：{self.url()}")
        # 用户在窗口里过了验证：平台多半把人带回首页，重开一次目标页
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if self._blocked():
            raise Blocked(f"过了验证又被带到验证页：{self.url()}")

    def _blocked(self) -> bool:
        now = self.url().lower()
        return any(m in now for m in BLOCK_MARKERS)

    def _wait_unblocked(self, step_ms: int = 2000) -> bool:
        waited = 0
        while waited < self.block_wait_ms:
            self.page.wait_for_timeout(step_ms)
            waited += step_ms
            if not self._blocked():
                return True
        return False

    def url(self) -> str:
        try:
            return self.page.url or ""
        except Exception:  # noqa: BLE001
            return ""

    def count(self, sel: str) -> int:
        try:
            return self.page.locator(sel).count()
        except Exception:  # noqa: BLE001
            return 0

    def visible(self, sel: str) -> bool:
        try:
            loc = self.page.locator(sel)
            return any(loc.nth(i).is_visible() for i in range(min(loc.count(), 5)))
        except Exception:  # noqa: BLE001
            return False

    def click(self, sel: str, timeout_ms: int = 15000) -> None:
        try:
            self.page.locator(sel).first.click(timeout=timeout_ms)
        except Exception as e:  # noqa: BLE001
            raise StepFailed(f"点不到 {sel}：{short_err(e)}") from e
        self._rest()

    def commit(self, sel: str, timeout_ms: int = 15000) -> None:
        """点最终的发布 / 分享按钮。点之前就记下 committed：点击本身报错也可能已经发出去了。"""
        self.committed = True
        self.click(sel, timeout_ms)

    def upload(self, sel: str, files, timeout_ms: int = 30000) -> None:
        try:
            self.page.locator(sel).first.set_input_files([str(f) for f in files], timeout=timeout_ms)
        except Exception as e:  # noqa: BLE001
            raise StepFailed(f"选不了文件（{sel}）：{short_err(e)}") from e
        self._rest()

    def type_text(self, sel: str, text: str, *, clear: bool = True, timeout_ms: int = 15000) -> None:
        """点进输入框（可先全选删掉预填内容）再逐行输入、行间回车：
        富文本编辑器（DraftJS 等）只认真实的键盘事件，直接 fill 会被忽略。"""
        self.click(sel, timeout_ms)
        kb = self.page.keyboard
        if clear:
            kb.press("Meta+A" if sys.platform == "darwin" else "Control+A")
            kb.press("Backspace")
        for i, line in enumerate(text.split("\n")):
            if i:
                kb.press("Enter")
            if line:
                kb.type(line, delay=random.randint(15, 45))
            # 行尾是话题 / @ 时联想框开着，这时回车会选中联想项（X 默认选第一项）：先补空格收掉
            if TAG_AT_LINE_END.search(line):
                kb.type(" ")
                self.wait_for(SUGGESTIONS, SUGGESTION_WAIT_MS)   # 等不到就算了（X / Instagram / TikTok 已经收了）
            # Threads 的话题框打空格不收；Esc 只收联想框、不关发帖弹窗（真机校准）。没联想框时绝不按 Esc
            if self.visible(SUGGESTIONS):
                kb.press("Escape")
                # 等联想框真的收起来再回车：Threads 上 Esc 后立刻回车，回车会被正在关的联想框吞掉（真机校准）
                self.wait_for(SUGGESTIONS, SUGGESTION_WAIT_MS, state="hidden")
        self._rest()

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def wait_for(self, sel: str, timeout_ms: int = 15000, state: str = "visible") -> bool:
        try:
            self.page.locator(sel).first.wait_for(state=state, timeout=timeout_ms)
            return True
        except Exception:  # noqa: BLE001
            return False

    def wait_count(self, sel: str, n: int, timeout_ms: int = 120000, step_ms: int = 500) -> bool:
        """等页面上至少有 n 个匹配（多张图的预览都挂上了）。"""
        waited = 0
        while self.count(sel) < n:
            if waited >= timeout_ms:
                return False
            self.page.wait_for_timeout(step_ms)
            waited += step_ms
        return True

    def wait_enabled(self, sel: str, timeout_ms: int = 60000) -> bool:
        """等按钮真能点：is_enabled 且 aria-disabled 不是 true（视频处理完之前发布按钮是灰的）。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            try:
                loc = self.page.locator(sel).first
                if loc.count() and loc.is_enabled() and loc.get_attribute("aria-disabled") != "true":
                    return True
            except Exception:  # noqa: BLE001
                pass
            if time.monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(500)

    def text(self, sel: str) -> str:
        try:
            return self.page.locator(sel).first.inner_text(timeout=2000) or ""
        except Exception:  # noqa: BLE001
            return ""

    def attr(self, sel: str, name: str) -> str:
        try:
            return self.page.locator(sel).first.get_attribute(name, timeout=2000) or ""
        except Exception:  # noqa: BLE001
            return ""

    def pause(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)

    def dismiss(self, selectors, rounds: int = 2) -> None:
        """点掉挡路的提示（开通知、新功能引导、内容检查询问……）：可见就点，点不到不报错。"""
        for _ in range(rounds):
            hit = False
            for sel in selectors:
                if not self.visible(sel):
                    continue
                try:
                    self.page.locator(sel).first.click(timeout=3000)
                    hit = True
                    self.page.wait_for_timeout(600)
                except Exception:  # noqa: BLE001
                    pass
            if not hit:
                return

    def settle(self, mod) -> bool | None:
        return settle(self.page, mod)


def save_failure(page, key: str) -> Path | None:
    """失败现场：截图 + 页面 HTML 存到 outputs/_login/<平台>-publish-fail.png/.html，对着它改选择器。"""
    try:
        import output_paths
        png = output_paths.validate_output_path(
            output_paths.OUTPUTS_DIR / "_login" / f"{key}-publish-fail.png", allow_system=True, create_parent=True)
        page.screenshot(path=str(png), full_page=True)
        png.with_suffix(".html").write_text(page.content(), encoding="utf-8")
        return png
    except Exception:  # noqa: BLE001 — 保存现场失败不能盖掉发布本身的结果
        return None
