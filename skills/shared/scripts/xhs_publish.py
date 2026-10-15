#!/usr/bin/env python3
"""xhs_publish.py — 小红书发布（Playwright 驱动本机 Chrome，有窗口）.

流程与选择器移植自 xpzouying/xiaohongshu-mcp（Go/go-rod）。确定性 IO 固化在脚本，
文案/策略仍由上层 LLM 决定。

浏览器：默认开 **CloakBrowser**（源码级抹掉自动化痕迹的 Chromium，`~/.cloakbrowser`）的窗口，
每个账号一套固定指纹（存在登录目录 .easel-fingerprint.json，macOS 上是 macOS 身份）；没装 Cloak 再开
**本机正式版 Chrome（找不到用 Edge）**。鼠标沿曲线移过去点、按词组输入（human_input.py）。2026-10 账号因「第三方脚本 / AI 托管发文」被封 30 天：当时用的是 Playwright
自带内核的无头模式，UA 直接写着 HeadlessChrome。所以小红书这条链不再无头运行
（EASEL_XHS_HEADLESS=1 可强开，仅限没有桌面的机器，很容易被识别）。
另有发帖频率闸门（_activity_check）和「笔记含 AI 合成内容」声明（_declare_ai）。

【半自动】默认（未设 EASEL_DOMESTIC_AUTO_PUBLISH=1）填完表单后停在发布按钮前，由用户亲自点「发布」，
脚本只被动观察结果（semi_auto.await_human_publish）；真发前还过 publish_guard（冷却/重复，退出码 9/8）。

移植的关键健壮技巧（源见各处 REF 注释）：
  - 切「上传图文/视频」tab：重试 + 遮挡检测 + 移除弹层
  - 逐图上传并等预览出现（≤60s）；视频等发布按钮可点击（≤10min = 处理完成）
  - 话题：输 # + 联想下拉点选，真绑话题
  - 发布按钮：新版 <xhs-publish-btn> + 旧版 .bg-red 双兼容
  - 发布成功校验：URL 离开 /publish/publish 才算成功（消除假成功）
  - 真人节奏：曲线移动鼠标再点、按词组输入、滚轮翻页（human_input.py）

子命令:
  check          验 playwright + chromium 内核
  login          有头扫码登录并持久化 cookie
  plan           离线打印发布步骤与选择器（不启浏览器）
  publish        图文发布（--images 逗号分隔）
  publish-video  视频发布（--video）
  selftest       离线自检（选择器字典 / 参数解析 / 标题长度算法）

真实发布需：playwright + chromium 内核 + 已扫码登录 + 外网可达（默认走项目代理）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import login_state  # noqa: E402
import login_qr
import login_transport
import content_guard  # noqa: E402  出站内容安全闸门
import human_input  # noqa: E402  真人节奏的鼠标/键盘
import real_browser  # noqa: E402  可见真实浏览器启动器（Cloak/Chrome）
import publish_guard  # noqa: E402  发布闸门：平台冷却 + 重复发布拦截
import semi_auto  # noqa: E402  半自动交接：填完表单停在发布按钮前，由人亲自点发布

# --------------------------------------------------------------------------- #
# 选择器集中维护（小红书改版时单点更新）。REF = xiaohongshu-mcp 对应源。
# --------------------------------------------------------------------------- #
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
EXPLORE_URL = "https://www.xiaohongshu.com/explore"
CREATOR_LOGIN_URL = "https://creator.xiaohongshu.com/login"
CREATOR_HOME_URL = "https://creator.xiaohongshu.com/new/home"
CREATOR_ACCOUNT_URL = "https://creator.xiaohongshu.com/api/galaxy/user/info"
TITLE_MAX = 20  # 小红书标题上限（全角计法，见 calc_title_length）

SELECTORS = {
    # 登录（REF login.go）
    "login_ok": ".main-container .user .link-wrapper .channel",
    "qrcode": ".login-container .qrcode-img, .qrcode-img, [class*='qrcode' i] img, "
              "[class*='qrcode' i] canvas, [class*='qr-code' i], img[src*='qrcode' i], "
              ".sso-login-wrapper img, .sso-login-wrapper canvas, "
              ".login-container img[alt*='二维码']",
    "logged_out": ".login-container, .login-modal, .login-box, "
                  ".sso-login-wrapper, .qrcode-img, [class*='qrcode' i], [class*='qr-code' i]",
    "login_entry": ".side-bar-component.login-btn, button.login-btn",
    "qr_switch": "button:has-text('扫码登录'), [role='tab']:has-text('扫码登录'), "
                 ".login-type:has-text('扫码登录'), .sso-login-wrapper > div > div > img",
    # 进页/切 tab（REF publish.go mustClickPublishTab）
    "upload_content": "div.upload-content",
    "creator_tab": "div.creator-tab",
    "pop_cover": "div.d-popover",
    # 上传（REF publish.go uploadImages / publish_video.go uploadVideo）
    "upload_input_first": ".upload-input",
    "upload_input_more": "input[type=file]",
    "img_preview": ".img-preview-area .pr",
    # 标题/正文（REF publish.go submitPublish / getContentElement）
    "title_input": "div.d-input input, input[placeholder*='标题']",
    "content_quill": "div.ql-editor",
    "content_editable": "div.editor-container [contenteditable='true'], [contenteditable='true']",
    "content_placeholder": "p[data-placeholder*='输入正文描述']",
    "title_overflow": "div.title-container div.max_suffix",
    "content_overflow": "div.edit-container div.length-error",
    # 话题（REF publish.go inputTag）
    "topic_container": "#creator-editor-topic-container",
    "topic_item": "#creator-editor-topic-container .item",
    # 发布按钮（REF publish.go findPublishButton）
    "publish_btn_new": "xhs-publish-btn",
    "publish_btn_old": ".publish-page-publish-btn button.bg-red",
}

PROFILE_NAME = "XiaohongshuProfile"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QR_OUT = PROJECT_ROOT / "outputs" / "_login" / "xhs-login-qrcode.png"

# 启动参数 / Cloak 数据目录 / 指纹文件名常量统一在 real_browser（值不变）
LAUNCH_ARGS = real_browser.LAUNCH_ARGS
IGNORE_DEFAULT_ARGS = real_browser.IGNORE_DEFAULT_ARGS
CLOAK_IGNORE_DEFAULT_ARGS = real_browser.CLOAK_IGNORE_DEFAULT_ARGS
CLOAK_DATA_DIR = real_browser.CLOAK_DATA_DIR
FINGERPRINT_FILE = real_browser.FINGERPRINT_FILE


# --------------------------------------------------------------------------- #
# 纯函数（可离线自测）
# --------------------------------------------------------------------------- #
def calc_title_length(s: str) -> int:
    """小红书标题长度：UTF-16 码元非 ASCII 计 2、ASCII 计 1，再 (n+1)//2 上取整。
    REF pkg/xhsutil/title.go CalcTitleLength。20 全角字 → 20。"""
    utf16 = s.encode("utf-16-le")
    byte_len = 0
    for i in range(0, len(utf16), 2):
        code = utf16[i] | (utf16[i + 1] << 8)
        byte_len += 2 if code > 127 else 1
    return (byte_len + 1) // 2


# 发布运行中的状态文件：_publish 过了发布闸门才设置（web_publisher 同款）。之后任何 _die / 处罚退出都先把
# 原因落成 error 终态，web / agent 看到的状态不会停在 starting「发布中」。发布路径上没有吞 SystemExit 的地方，
# 所以不会提前误报 error。
_ACTIVE_PUBLISH_STATUS_FILE: str | None = None


def _mark_publish_error(msg: str) -> None:
    if _ACTIVE_PUBLISH_STATUS_FILE:
        try:
            login_state.write_status(_ACTIVE_PUBLISH_STATUS_FILE, "error", msg[:300])
        except OSError:
            pass   # 写不进（如 Windows 上与 web 轮询读撞车）也要按原退出码退出


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    semi_auto.note_exit_reason(msg)
    _mark_publish_error(msg)
    sys.exit(code)


def _abspaths(csv: str | None) -> list[str]:
    """逗号分隔路径 → 绝对路径列表，校验存在。"""
    if not csv:
        return []
    out = []
    for raw in csv.split(","):
        raw = raw.strip()
        if not raw:
            continue
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            _die(f"文件不存在：{p}")
        out.append(str(p))
    return out


def _profile_dir(base: str | None) -> Path:
    root = Path(base).expanduser() if base else Path.home() / ".easel-browser-profiles"
    return root / PROFILE_NAME


def _cloak_executable() -> Path | None:
    """本机已装的 CloakBrowser 内核（逻辑在 real_browser.cloak_executable）。

    无头 Playwright Chromium 会被小红书 300012；同一出口下 Cloak 无头已实测能出码。
    """
    return real_browser.cloak_executable()


def _host_fingerprint_platform() -> str:
    """Cloak 指纹的平台身份（逻辑在 real_browser）。"""
    return real_browser.host_fingerprint_platform()


def _read_fingerprint(path: Path) -> dict | None:
    return real_browser.read_fingerprint(path)


def _account_fingerprint(base: str | None) -> dict:
    """这个账号固定用的 Cloak 指纹，存在 XiaohongshuProfile/.easel-fingerprint.json；第一次用时生成，
    之后永不重新生成（平台身份与本机不符除外）。实现见 real_browser.account_fingerprint。"""
    return real_browser.account_fingerprint(
        _profile_dir(base), fingerprint_file=FINGERPRINT_FILE, platform_label="小红书",
        host_fn=_host_fingerprint_platform)


def browser_engine() -> tuple[str, str]:
    """小红书实际会用哪个浏览器：("cloak", 可执行文件) / ("chrome"|"msedge", "") / ("bundled", "")。"""
    return real_browser.resolve_engine("EASEL_XHS_BROWSER", cloak_fn=_cloak_executable,
                                       channel_fn=_browser_channel)


def _browser_choice() -> str:
    """EASEL_XHS_BROWSER=chrome 跳过 Cloak 直接用本机 Chrome；默认 auto（Cloak 优先）。"""
    return (os.environ.get("EASEL_XHS_BROWSER") or "auto").strip().lower()


class _ProfileLock:
    """同一份 XiaohongshuProfile 不能同时开两个 Cloak：账号页 whoami 和登录会把内核打成 exit 21。"""

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
                os.lseek(self.fd, 0, os.SEEK_SET)
                os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
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
                    raise TimeoutError(f"登录目录正被占用：{self.path}") from last
                time.sleep(0.4)

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
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


def _clear_stale_chrome_locks(profile: Path) -> None:
    real_browser.clear_stale_chrome_locks(profile)


def _browser_channel() -> str | None:
    """本机装的正式版浏览器：Chrome 优先，其次 Edge；都没有返回 None。"""
    return real_browser.browser_channel()


def _login_error(page) -> str:
    """区分明确 IP 风险和其它错误页，不泄露 URL 中的登录参数。"""
    try:
        url = page.url or ""
        title = page.title() or ""
        try:
            text = page.inner_text("body", timeout=2000)[:3000]
        except Exception:
            text = ""
        if any(message in title + text for message in (
                "工程师正在", "工程师在紧急", "系统维护中", "系统正在维护", "页面维护中")):
            return ("小红书当前入口显示维护页面，暂时无法完成登录校验。"
                    "这不是二维码过期或账号退出，请稍后重试。")
        codes = parse_qs(urlparse(url).query).get("error_code", [])
        code = codes[0] if codes and codes[0].isdigit() and len(codes[0]) <= 32 else ""
        error_page = "website-login/error" in url or "安全限制" in title or bool(code)
        if not error_page:
            return ""
        if code == "300012" or "IP存在风险" in re.sub(r"\s+", "", text).upper():
            detail = f"（错误码 {code}）" if code else ""
            return (f"小红书返回 IP 风险限制{detail}，二维码无法获取。"
                    "请在可信网络重试；服务器/机房出口可能被平台限制，Easel 无法保证解除风控。")
        detail = f"（错误码 {code}）" if code else ""
        return f"小红书登录被平台拦截{detail}，不一定是 IP 问题。请检查网络，或使用 --headed 查看平台提示。"
    except Exception:
        return ""


def _risk_blocked(page) -> bool:
    return "IP 风险限制" in _login_error(page)


def _visible_login_element(page, selectors: str):
    for selector in selectors.split(","):
        for element in page.query_selector_all(selector.strip()):
            if element.is_visible():
                return element
    return None


def _open_login_dialog(page) -> None:
    creator = urlparse(page.url or "").hostname == "creator.xiaohongshu.com"
    if not _visible_login_element(page, SELECTORS["logged_out"]):
        try:
            page.wait_for_selector(
                f"{SELECTORS['logged_out']}, {SELECTORS['login_entry']}, {SELECTORS['login_ok']}",
                state="visible", timeout=45000 if creator else 15000)
        except Exception:
            pass
    if creator:
        try:
            page.wait_for_selector(".sso-login-wrapper", state="visible", timeout=15000)
            page.wait_for_selector(".sso-login-wrapper [data-testid='loading']",
                                   state="hidden", timeout=15000)
        except Exception:
            pass
    if _visible_login_element(page, SELECTORS["logged_out"]):
        return
    if urlparse(page.url or "").hostname == "www.xiaohongshu.com":
        button = _visible_login_element(page, SELECTORS["login_entry"])
        if button:
            button.click(timeout=3000, no_wait_after=True)


def _missing_qr_reason(page) -> str:
    try:
        text = page.inner_text("body", timeout=2000).strip()
    except Exception:
        return "登录页面尚未就绪，请检查网络连接后重试"
    if not text:
        return "登录页面空白，平台脚本未完成加载，请检查网络连接后重试"
    if "扫一扫" in text or "扫码登录" in text:
        return "已切换扫码登录，但二维码未加载或无法识别，请稍后重试"
    if "短信登录" in text or "发送验证码" in text:
        return "页面仍停留在短信登录，扫码切换控件未就绪或失效；可用 --headed 查看平台提示"
    return "未找到可识别的登录二维码，登录弹窗未打开或页面结构已变化"


def _capture_login_qr(page, qr_out: Path, *, creator_only: bool = False) -> bool:
    """首页无法出码时只尝试一次官方创作平台入口；False 表示已登录。"""
    failures = []
    for url in ((CREATOR_LOGIN_URL,) if creator_only else (None, CREATOR_LOGIN_URL)):
        entry = "创作平台" if url else "小红书首页"
        try:
            if url:
                page.goto(url, wait_until="commit", timeout=30000)
        except Exception as error:
            reason = f"打不开小红书创作平台（{type(error).__name__}），请检查网络连接后重试"
            failures.append(f"{entry}：{reason}")
            continue
        if _is_logged_in(page):
            return False
        reason = _login_error(page)
        if not reason:
            try:
                _open_login_dialog(page)
                reason = _login_error(page)
                if reason:
                    failures.append(f"{entry}：{reason}")
                    continue
                login_qr.prepare_qr(page, qr_out, SELECTORS["qrcode"],
                                    SELECTORS["qr_switch"], minimum_size=96)
                return True
            except Exception as error:
                if _is_logged_in(page):
                    return False
                reason = _login_error(page) or _missing_qr_reason(page)
                print(f"小红书抓码失败（{entry}/{type(error).__name__}）：{reason}", file=sys.stderr)
        failures.append(f"{entry}：{reason}")
    raise RuntimeError("；".join(failures))


def _is_logged_in(page) -> bool:
    if _login_error(page):
        return False
    try:
        for element in page.query_selector_all(SELECTORS["logged_out"]):
            if element.is_visible():
                return False
    except Exception:
        pass
    try:
        for element in page.query_selector_all(SELECTORS["login_ok"]):
            if element.is_visible():
                return True
    except Exception:
        pass
    try:
        url = urlparse(page.url or "")
        if (url.hostname == "creator.xiaohongshu.com"
                and not parse_qs(url.query).get("error_code")
                and (url.path.startswith(("/publish/", "/new/", "/home/")) or url.path == "/home")):
            for account in page.query_selector_all(".user-info"):
                if not account.is_visible():
                    continue
                avatar = account.query_selector("img.user_avatar")
                name = account.query_selector("span")
                if (avatar and avatar.is_visible() and avatar.get_attribute("src")
                        and name and name.is_visible() and name.inner_text().strip()):
                    return True
    except Exception:
        pass
    return False


def _qr_state(page) -> str:
    try:
        text = page.inner_text(
            ".sso-login-wrapper, .login-container, .login-modal, .login-box",
            timeout=1000)
    except Exception:
        return ""
    compact = re.sub(r"\s+", "", text)
    if any(message in compact for message in (
            "扫码成功", "扫描成功", "已扫码", "请在手机上确认", "请在APP上确认")):
        return "scanned"
    if any(message in compact for message in (
            "二维码已失效", "二维码失效", "二维码已过期", "二维码过期", "二维码无效")):
        return "expired"
    return ""


def _refresh_expired_qr(page, qr_out: Path) -> bool:
    if _qr_state(page) != "expired":
        return False
    selectors = (
        ".sso-login-wrapper button:has-text('刷新'), "
        ".sso-login-wrapper [role='button']:has-text('刷新'), "
        ".sso-login-wrapper a:text-is('点击刷新'), "
        ".sso-login-wrapper span:text-is('点击刷新'), "
        ".sso-login-wrapper div:text-is('点击刷新'), "
        ".login-container button:has-text('刷新'), "
        ".login-container span:text-is('刷新二维码'), "
        ".login-container div:text-is('刷新二维码'), "
        ".login-container a:text-is('点击刷新'), "
        ".login-container span:text-is('点击刷新'), "
        ".login-container div:text-is('点击刷新')"
    )
    button = _visible_login_element(page, selectors)
    if button is None:
        return False
    button.click(timeout=3000)
    page.wait_for_timeout(800)
    if _qr_state(page) == "scanned":
        return False
    login_qr.capture_qr(page, qr_out, SELECTORS["qrcode"], minimum_size=96)
    return True


def _verify_login(page, timeout_s: float = 6) -> bool:
    deadline = time.monotonic() + timeout_s
    confirmed = 0
    while time.monotonic() < deadline:
        if _is_logged_in(page):
            confirmed += 1
            if confirmed >= 2:
                return True
        else:
            confirmed = 0
        if _login_error(page) or _visible_login_element(page, SELECTORS["logged_out"]):
            return False
        page.wait_for_timeout(500)
    return False


def _check_account_login(page) -> bool:
    outcomes = []
    deadline = time.monotonic() + 14
    for destination in (CREATOR_HOME_URL, EXPLORE_URL):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcomes.append("unknown")
                break
            page.goto(destination, wait_until="commit", timeout=min(4000, remaining * 1000))
            remaining = deadline - time.monotonic()
            if remaining > 0 and _verify_login(page, timeout_s=min(4, remaining)):
                return True
            outcomes.append("unknown" if _login_error(page) or not _visible_login_element(
                page, SELECTORS["logged_out"]) else "logged_out")
        except Exception:
            outcomes.append("unknown")
    if any(outcome != "logged_out" for outcome in outcomes):
        raise RuntimeError("小红书登录校验暂未完成：网络超时、维护/风控页面或账号界面未就绪；保留上次登录状态")
    return False


def _creator_account(context) -> dict | None:
    try:
        response = context.request.get(
            CREATOR_ACCOUNT_URL, headers={"Referer": CREATOR_HOME_URL}, timeout=5000)
        if response.status != 200:
            return None
        payload = response.json()
        account = payload.get("data")
        if (payload.get("success") is True and isinstance(account, dict)
                and isinstance(account.get("userId"), str) and account["userId"].strip()):
            return account
    except Exception:
        pass
    return None


def _web_account(context) -> dict | None:
    try:
        response = context.request.get(EXPLORE_URL, timeout=4000)
        if response.status != 200:
            return None
        return _web_account_html(response.text())
    except Exception:
        return None


def _initial_state(html: str) -> dict:
    if len(html) > 2_000_000:
        return {}
    match = re.search(
        r"<script\b[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*([\s\S]*?)</script>",
        html, re.IGNORECASE)
    if not match:
        return {}
    serialized = re.sub(
        r'"(?:\\.|[^"\\])*"|\bundefined\b',
        lambda token: "null" if token.group() == "undefined" else token.group(),
        match.group(1).strip().rstrip(";"))
    try:
        state = json.loads(serialized)
        return state if isinstance(state, dict) else {}
    except ValueError:
        return {}


def _unwrap_state(value):
    if isinstance(value, dict) and "userId" not in value and "basicInfo" not in value:
        if "value" in value:
            return value["value"]
        if "_value" in value:
            return value["_value"]
    return value


def _state_account(state: dict) -> dict | None:
    user = state.get("user")
    account = _unwrap_state(user.get("userInfo")) if isinstance(user, dict) else None
    if (not isinstance(account, dict) or _unwrap_state(user.get("loggedIn")) is not True
            or not isinstance(account.get("userId"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", account["userId"])):
        return None
    identity = _account_identity(account)
    return {**account, "userName": identity["name"], "userAvatar": identity["avatar"]}


def _web_account_html(html: str) -> dict | None:
    return _state_account(_initial_state(html))


def _self_profile_identity(state: dict, user_id: str) -> dict:
    identity = {"name": "", "avatar": ""}
    account = _state_account(state)
    if account is None or account["userId"] != user_id:
        return identity
    profile = _unwrap_state(state["user"].get("userPageData"))
    if not isinstance(profile, dict) or profile.get("userId", user_id) != user_id:
        return identity
    basic = profile.get("basicInfo")
    return _account_identity(basic) if isinstance(basic, dict) else identity


def _self_profile_account(context, account: dict) -> dict:
    user_id = account.get("userId")
    if not isinstance(user_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", user_id):
        return account
    destination = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    try:
        response = context.request.get(
            destination, headers={"Referer": EXPLORE_URL}, timeout=4000)
        current_url = urlparse(response.url)
        if (response.status != 200 or current_url.hostname != "www.xiaohongshu.com"
                or current_url.path.rstrip("/") != urlparse(destination).path):
            return account
        fallback = _self_profile_identity(_initial_state(response.text()), user_id)
        identity = _account_identity(account)
        return {**account, "userName": fallback["name"] or identity["name"],
                "userAvatar": fallback["avatar"] or identity["avatar"]}
    except Exception:
        return account


def _authenticated_account(context) -> dict | None:
    account = _web_account(context)
    if account is not None and all(_account_identity(account).values()):
        return account
    creator = _creator_account(context)
    if account is None:
        return creator
    if creator is None or creator.get("userId") != account.get("userId"):
        return account
    identity = _account_identity(account)
    fallback = _account_identity(creator)
    return {
        **account,
        "userName": identity["name"] or fallback["name"],
        "userAvatar": identity["avatar"] or fallback["avatar"],
    }


def _account_identity(account: dict) -> dict:
    name = next((account[key].strip()[:40] for key in ("userName", "nickname", "user_name", "name")
                 if isinstance(account.get(key), str) and account[key].strip()), "")
    avatar = ""
    for key in ("userAvatar", "imageb", "images", "avatar", "user_avatar"):
        candidate = account.get(key)
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        try:
            parsed = urlparse(candidate)
            if (parsed.scheme in ("https", "http") and parsed.hostname
                    and not parsed.username and not parsed.password
                    and not any(ord(character) < 32 for character in candidate)):
                avatar = candidate
                break
        except ValueError:
            continue
    return {"name": name, "avatar": avatar}


def _page_account_identity(page, user_id: str | None = None) -> dict:
    identity = {"name": "", "avatar": ""}
    if urlparse(page.url or "").hostname == "creator.xiaohongshu.com":
        for account in page.query_selector_all(".user-info"):
            if not account.is_visible():
                continue
            avatar = account.query_selector("img.user_avatar")
            name = account.query_selector("span")
            if avatar and avatar.is_visible() and name and name.is_visible():
                return _account_identity({
                    "userName": name.inner_text(),
                    "userAvatar": avatar.get_attribute("src"),
                })
        return identity
    profile_url = (f"https://www.xiaohongshu.com/user/profile/{user_id}"
                   if isinstance(user_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", user_id) else "")
    for channel in ([] if profile_url else page.query_selector_all(SELECTORS["login_ok"])):
        if not channel.is_visible():
            continue
        account = channel.evaluate("""element => {
            const anchor = element.closest('a[href]') || element.querySelector('a[href]')
                || element.closest('.user')?.querySelector('a[href*="/user/profile/"]');
            return {
                href: anchor?.getAttribute('href') || '',
                avatar: anchor?.querySelector('img')?.getAttribute('src') || ''
            };
        }""")
        if not isinstance(account, dict):
            continue
        href = account.get("href")
        if not isinstance(href, str):
            continue
        candidate = urlparse(href)
        if (candidate.scheme or candidate.netloc
                or not re.fullmatch(r"/user/profile/[A-Za-z0-9_-]+/?", candidate.path)):
            continue
        profile_url = "https://www.xiaohongshu.com" + candidate.path
        identity["avatar"] = _account_identity({"userAvatar": account.get("avatar")})["avatar"]
        break
    if not profile_url:
        return identity
    try:
        page.goto(profile_url, wait_until="commit", timeout=4000)
        current_url = urlparse(page.url or "")
        if (current_url.hostname != "www.xiaohongshu.com"
                or current_url.path.rstrip("/") != urlparse(profile_url).path.rstrip("/")):
            return identity
        try:
            page.wait_for_function(
                """() => {
                    const profile = window.__INITIAL_STATE__?.user?.userPageData;
                    return !!(profile?.basicInfo || profile?.value?.basicInfo || profile?._value?.basicInfo);
                }""",
                timeout=1500)
        except Exception:
            pass
        try:
            state = page.evaluate("""() => {
                const user = window.__INITIAL_STATE__?.user;
                return user ? JSON.parse(JSON.stringify({user: {
                    loggedIn: user.loggedIn, userInfo: user.userInfo, userPageData: user.userPageData
                }})) : {};
            }""")
            if isinstance(state, dict):
                own_account = _state_account(state)
                if own_account is not None and own_account["userId"] != urlparse(profile_url).path.rstrip("/").split("/")[-1]:
                    return {"name": "", "avatar": ""}
                extracted = _self_profile_identity(state, urlparse(profile_url).path.rstrip("/").split("/")[-1])
                if all(extracted.values()):
                    return extracted
                identity.update({key: value for key, value in extracted.items() if value})
        except Exception:
            pass
        selectors = ".user-profile .user-info, .user-page .user-info, .user .user-info, .user-profile .info-part"
        page.wait_for_selector(selectors, state="visible", timeout=3000)
        for account in page.query_selector_all(selectors):
            if not account.is_visible():
                continue
            name = account.query_selector(".user-name, .username, .name")
            avatar = account.query_selector("img.avatar, img.user-avatar, img.avatar-item, .avatar img")
            if name and name.is_visible():
                text = name.inner_text().strip()
                if text:
                    identity["name"] = text.splitlines()[0][:40]
            if avatar and avatar.is_visible():
                identity["avatar"] = _account_identity({"userAvatar": avatar.get_attribute("src")})["avatar"]
            if identity["name"]:
                break
    except Exception:
        pass
    return identity


def _proxy(explicit: str | None, disable: bool) -> str | None:
    """外网代理：--no-proxy 关；--proxy 显式；否则取 env（小红书是外网，默认需代理）。"""
    if disable:
        return None
    if explicit:
        return explicit
    return os.environ.get("https_proxy") or os.environ.get("http_proxy") \
        or os.environ.get("EASEL_PROXY")


# --------------------------------------------------------------------------- #
# 浏览器动作（移植自 xiaohongshu-mcp，需 playwright）
# --------------------------------------------------------------------------- #
def _human_type(page, locator, text: str) -> None:
    """鼠标点进输入框，再按真人节奏输入（human_input.type_text）。"""
    human_input.click(page, locator)
    human_input.pause(page, 200, 600)
    human_input.type_text(page, text)


def _click_publish_tab(page, tabname: str) -> None:
    """点「上传图文/上传视频」tab：重试 15s + 遮挡检测 + 移弹层。REF mustClickPublishTab。"""
    page.wait_for_selector(SELECTORS["upload_content"], timeout=15000)
    deadline = time.time() + 15
    while time.time() < deadline:
        tabs = page.query_selector_all(SELECTORS["creator_tab"])
        for tab in tabs:
            try:
                if not tab.is_visible():
                    continue
                if (tab.inner_text() or "").strip() != tabname:
                    continue
            except Exception:
                continue
            # 遮挡检测（REF isElementBlocked：elementFromPoint 命中的是不是自己）
            blocked = tab.evaluate(
                """(el) => { const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) return true;
                    const t = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                    return !(t === el || el.contains(t)); }""")
            if blocked:
                cover = page.query_selector(SELECTORS["pop_cover"])
                if cover:
                    cover.evaluate("el => el.remove()")
                page.wait_for_timeout(200)
                continue
            human_input.click(page, tab)
            return
        page.wait_for_timeout(200)
    _die(f"未找到发布 TAB：{tabname}（页面结构可能已变，检查 SELECTORS.creator_tab）")


def _upload_images(page, paths: list[str]) -> None:
    """逐张上传并等预览出现（≤60s/张）。REF uploadImages/waitForUploadComplete。"""
    for i, path in enumerate(paths):
        sel = SELECTORS["upload_input_first"] if i == 0 else SELECTORS["upload_input_more"]
        page.set_input_files(sel, path)
        print(f"  上传图片 {i+1}/{len(paths)}: {path}", file=sys.stderr)
        deadline = time.time() + 60
        while time.time() < deadline:
            if len(page.query_selector_all(SELECTORS["img_preview"])) >= i + 1:
                break
            page.wait_for_timeout(500)
        else:
            _die(f"第 {i+1} 张图片上传超时（60s）")
        page.wait_for_timeout(1000)


def _upload_video(page, path: str) -> None:
    """上传视频，等发布按钮可点击（≤10min = 处理完成）。REF publish_video.go uploadVideo。"""
    sel = SELECTORS["upload_input_first"]
    if not page.query_selector(sel):
        sel = SELECTORS["upload_input_more"]
    page.set_input_files(sel, path)
    print(f"  上传视频：{path}（等待处理，最长 10min）", file=sys.stderr)
    _wait_publish_clickable(page, timeout_s=600)


def _content_element(page):
    """正文输入框：先 ql-editor（旧版），再 contenteditable（新版），最后退回 placeholder 定位。
    REF getContentElement。小红书已把正文编辑器从 Quill 换成 contenteditable。"""
    el = page.query_selector(SELECTORS["content_quill"])
    if el:
        return el
    el = page.query_selector(SELECTORS["content_editable"])
    if el:
        return el
    ph = page.query_selector(SELECTORS["content_placeholder"])
    if ph:
        cur = ph
        for _ in range(5):
            parent = cur.evaluate_handle("el => el.parentElement").as_element()
            if not parent:
                break
            role = parent.get_attribute("role") or ""
            if role == "textbox" or parent.get_attribute("contenteditable") == "true":
                return parent
            cur = parent
    return None


def _check_overflow(page) -> None:
    """标题/正文超限：读平台自身的溢出提示元素。REF checkTitleMaxLength/checkContentMaxLength。"""
    for key, name in (("title_overflow", "标题"), ("content_overflow", "正文")):
        el = page.query_selector(SELECTORS[key])
        if el and el.is_visible():
            _die(f"{name}超出平台长度限制：{(el.inner_text() or '').strip()}")


def _input_tags(page, content_el, tags: list[str]) -> None:
    """话题：正文末尾输 # + 联想下拉点第一项，真绑话题。REF inputTag。

    注意：必须把 # 与话题名**连续输入**、中途不能再 click 正文——否则光标会被挪走，
    # 和话题名被拆开，小红书识别不到连续的 #话题 token，联想不出、绑不上话题。
    """
    if not tags:
        return
    human_input.click(page, content_el)
    # 光标移到正文末尾，避免 # 插到正文中间。Control+End 在 macOS 上不是「到文末」，直接设选区
    content_el.evaluate("""(el) => { const r = document.createRange(); r.selectNodeContents(el);
        r.collapse(false); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }""")
    page.wait_for_timeout(400)
    for tag in tags:
        tag = tag.lstrip("#").strip()
        if not tag:
            continue
        page.keyboard.type(" ")          # 与正文/上一话题分隔，确保 # 起一个新 token
        page.keyboard.type("#")
        page.wait_for_timeout(300)
        for ch in tag:                   # 逐字输入话题名——不再 click（避免移光标拆开 #话题）
            page.keyboard.type(ch)
            page.wait_for_timeout(random.randint(30, 110))
        page.wait_for_timeout(1000)
        item = page.query_selector(SELECTORS["topic_item"])
        if item:
            human_input.click(page, item)   # 点联想第一项 = 真正绑定话题
        else:
            page.keyboard.type(" ")      # 无联想则退化为空格分隔（至少保留 #文字）
        page.wait_for_timeout(500)


def _wait_publish_clickable(page, timeout_s: int = 15):
    """等发布按钮可点击（新旧兼容）。REF findPublishButton/waitForPublishButtonClickable。"""
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        for w in page.query_selector_all(SELECTORS["publish_btn_new"]):
            if not w.is_visible():
                continue
            if (w.get_attribute("is-publish") or "") == "false":
                continue
            if (w.get_attribute("submit-disabled") or "") == "true":
                last = "新版发布按钮不可点击"
                continue
            return ("new", w)
        for b in page.query_selector_all(SELECTORS["publish_btn_old"]):
            if not b.is_visible():
                continue
            if b.get_attribute("disabled") is not None:
                last = "旧版发布按钮 disabled"
                continue
            if (b.get_attribute("aria-disabled") or "") == "true":
                last = "旧版发布按钮 aria-disabled"
                continue
            return ("old", b)
        page.wait_for_timeout(1000)
    _die(f"等待发布按钮可点击超时{('：' + last) if last else ''}")


def _diag_after_publish(page) -> str:
    """点发布后失败时，抓屏幕上可见的弹框/报错/toast 文案，供排错。
    截图默认不存（正常使用不截图）；排错时设 EASEL_PUBLISH_DEBUG=1 才会存失败截图。"""
    bits = []
    for sel in (".d-modal", "[role=dialog]", "[class*=modal]", "[class*=dialog]",
                ".d-message", ".d-toast", "[class*=toast]", "[class*=error]", "[class*=tip]"):
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible():
                    t = (el.inner_text() or "").strip().replace("\n", " / ")
                    if t and t not in " ".join(bits):
                        bits.append(f"[{sel}] {t[:120]}")
        except Exception:
            pass
    shot = ""
    if os.environ.get("EASEL_PUBLISH_DEBUG"):
        try:
            out = PROJECT_ROOT / "outputs" / "_login" / "xhs-publish-fail.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out))
            shot = f"（调试截图见 {out}）"
        except Exception:
            pass
    return ("屏幕可见元素：" + " | ".join(bits[:6]) if bits else "屏幕无可识别弹框/报错") + shot


def _confirm_publish_dialog(page) -> None:
    """点发布后若弹二次确认框，点其确认按钮（保守：仅当可见且文案匹配）。"""
    deadline = time.time() + 5
    while time.time() < deadline:
        for b in page.query_selector_all("button, .d-button, [role=button]"):
            try:
                if not b.is_visible():
                    continue
                tx = (b.inner_text() or "").strip()
                if tx in ("确认发布", "确定发布", "继续发布", "立即发布", "确认", "确定"):
                    human_input.click(page, b)
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                pass
        page.wait_for_timeout(500)


# 只收确属 toast/通知的容器（不含 [class*=message]：会匹配消息列表等普通区域，误判处罚/成功）
XHS_TOAST_SELECTORS = (".d-message", ".d-toast", ".d-notification", "[class*=toast]", "[role=alert]")
# 小红书发布成功后跳到的页面（URL 片段）
XHS_POST_PUBLISH_URL_MARK = "/publish/success"
EXIT_NOT_PUBLISHED = 1   # 窗口被关 / 等用户点发布超时：未发布，不重试


def _publish_succeeded(page) -> str:
    """发布成功的非阻塞判定：返回成功依据文字，没成功返回空串。
    小红书发布成功后**原地清空表单回到上传页**（不换 URL）。
    成功信号任一：跳离 /publish/publish、出现「成功」toast、或编辑表单已重置（标题框+图片预览消失）。"""
    if "/publish/publish" not in page.url:
        return f"已跳转：{page.url}"
    for sel in (".d-message", ".d-toast", "[class*=toast]", "[class*=message]"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible() and "成功" in (el.inner_text() or ""):
                return "检测到成功提示"
        except Exception:
            pass
    # 表单已重置：填过的标题框 + 上传的图片预览都消失 = 已提交回到空上传页
    try:
        if (not page.query_selector(SELECTORS["title_input"])
                and not page.query_selector(SELECTORS["img_preview"])):
            return "编辑表单已清空复位"
    except Exception:
        pass
    return ""


def _publish_succeeded_strict(page) -> str:
    """半自动模式的严格成功判定：只认「发布成功」toast，或跳到已知的发布成功页（/publish/success）。
    **不认**：泛泛的「成功」（如「上传成功」「保存成功」）、表单被清空、URL 只是离开了 /publish/publish
    （登录过期被踢去 /login 也会离开）。返回成功依据文字，没成功返回空串。
    自动点击逃生口仍走较宽松的 `_publish_succeeded`（行为不变）。"""
    try:
        if XHS_POST_PUBLISH_URL_MARK in (page.url or ""):
            return f"已跳转到发布成功页：{page.url}"
    except Exception:
        return ""
    try:
        if any("发布成功" in t for t in semi_auto._toast_texts(page, XHS_TOAST_SELECTORS)):
            return "检测到「发布成功」提示"
    except Exception:
        return ""
    return ""


def _scan_block_toasts(page) -> str | None:
    """扫 toast/通知元素文本里的平台处罚提示；命中则设冷却并返回原文，否则 None。"""
    try:
        texts = semi_auto._toast_texts(page, XHS_TOAST_SELECTORS)
    except Exception:
        return None
    for text in texts:
        if publish_guard.classify_block_text(text):
            publish_guard.on_block_detected("xiaohongshu", text)
            return text
    return None


def _exit_if_blocked(page) -> None:
    """命中平台处罚提示（_scan_block_toasts 已设冷却）→ 状态落 error（带原文）并退出 9，不重试。"""
    text = _scan_block_toasts(page)
    if text:
        _mark_publish_error(f"小红书提示处罚/限制：{text[:120]}。已设为冷却，请勿重试，先向用户汇报。")
        sys.exit(publish_guard.EXIT_COOLDOWN)


def _wait_publish_success(page, timeout_s: int = 40) -> None:
    """（自动点击逃生口路径）点发布后等成功信号；期间扫 toast，命中处罚提示 → 设冷却并 exit 9。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        _exit_if_blocked(page)
        how = _publish_succeeded(page)
        if how:
            print(f"✅ 发布成功（{how}）")
            return
        page.wait_for_timeout(500)
    _exit_if_blocked(page)
    _die("发布未确认成功：点击发布后未跳离发布页/未见成功提示（不要自动重试，请到创作中心核对）。" + _diag_after_publish(page))


def _normalize_content(text: str) -> str:
    """小红书编辑器「不支持连续空行输入」——把 2+ 连续空行压成单个空行，行尾空白清掉。"""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)      # 行尾空白
    text = re.sub(r"\n{3,}", "\n\n", text)       # 连续空行（3+ 换行）→ 一个空行
    return text.strip("\n")


# 「笔记含 AI 合成内容」声明。小红书要求 AI 生成/合成的内容主动声明；入口在发布页下方的
# 「内容类型声明」下拉里（有的版本收在「更多设置」后面）。按文字定位，改版时改这里。
AI_DECLARE_ENTRY_TEXTS = ("添加内容类型声明", "内容类型声明")
AI_DECLARE_MORE_TEXTS = ("更多设置",)
AI_DECLARE_OPTION_TEXT = "笔记含AI合成内容"
AI_DECLARE_FAILED_MSG = ("没能勾上「笔记含AI合成内容」声明，已停在发布前、没有发出去（页面可能改版）。"
                         "可以在打开的窗口里手动勾选后自己点发布；确认内容不是 AI 生成的，加 --no-ai-declare 再发。")


def _visible_text(page, text: str):
    """页面上文字恰好是 text 的第一个可见元素（Locator），没有返回 None。"""
    loc = page.get_by_text(text, exact=True)
    try:
        for i in range(min(loc.count(), 6)):
            el = loc.nth(i)
            if el.is_visible():
                return el
    except Exception:
        return None
    return None


# 「笔记含AI合成内容」这几个字出现在表单上（不在还开着的下拉/选项列表里）= 已经选上。
_AI_DECLARED_JS = """(text) => {
    const pop = "[role=listbox],[role=option],[role=menu],[class*=dropdown],[class*=popover],"
        + "[class*=option],[class*=menu]";
    return Array.from(document.querySelectorAll('body *')).some(e =>
        e.children.length === 0 && (e.textContent || '').trim() === text
        && e.offsetParent !== null && !e.closest(pop));
}"""


def _ai_declared(page) -> bool:
    try:
        return bool(page.evaluate(_AI_DECLARED_JS, AI_DECLARE_OPTION_TEXT))
    except Exception:
        return False


def _declare_ai(page) -> bool:
    """勾上「笔记含AI合成内容」。只有确认表单上显示了选中值（不是下拉里的选项）才返回 True；
    判断不了一律当没勾上——宁可停下不发，也不能没声明就发出去。
    选择器按文字猜的，还没在真机上校准过；改版或首次跑不通就停在发布前（退出码 6）。"""
    if _ai_declared(page):
        return True
    entry = None
    for _ in range(2):
        for t in AI_DECLARE_ENTRY_TEXTS:
            entry = _visible_text(page, t)
            if entry:
                break
        if entry:
            break
        more = None
        for t in AI_DECLARE_MORE_TEXTS:
            more = _visible_text(page, t)
            if more:
                break
        if not more:
            human_input.scroll(page, 600)
            continue
        human_input.click(page, more)
        human_input.pause(page, 500, 1000)
    if not entry:
        return False
    human_input.click(page, entry)
    human_input.pause(page, 500, 1000)
    option = _visible_text(page, AI_DECLARE_OPTION_TEXT)
    if not option:
        return False
    human_input.click(page, option)
    human_input.pause(page, 600, 1200)
    return _ai_declared(page)


AI_DECLARE_MANUAL_NOTE = "请在窗口里手动勾选 AI 声明"


def _fill_form(page, title, content, tags, declare_ai: bool, semi: bool) -> str:
    """标题→正文→话题→AI 声明→长度校验。返回交接时要提醒用户的附加说明（没有则空串）。
    AI 声明勾不上：半自动模式不退出，改为提醒用户在窗口里手动勾；自动逃生口模式仍 exit 6（宁可不发）。"""
    content = _normalize_content(content)         # 修连续空行导致的发布失败
    title_el = page.query_selector(SELECTORS["title_input"])
    if not title_el:
        _die("未找到标题输入框（检查 SELECTORS.title_input）")
    _human_type(page, title_el, title)
    human_input.pause(page, 400, 1200)

    content_el = _content_element(page)
    if not content_el:
        _die("未找到正文输入框（检查 SELECTORS.content_*）")
    _human_type(page, content_el, content)
    human_input.pause(page, 500, 1500)
    human_input.click(page, title_el)  # REF waitAndClickTitleInput：回点标题增强稳定性
    _input_tags(page, content_el, tags)

    note = ""
    if declare_ai and not _declare_ai(page):
        if not semi:
            _die(AI_DECLARE_FAILED_MSG, 6)
        note = AI_DECLARE_MANUAL_NOTE

    _check_overflow(page)
    return note


def _status_note_callback(status_file, note: str):
    """on_status 回调：await_human_publish 写完 awaiting_user_click 后，把附加说明补进状态文件的 message。"""
    if not note:
        return None

    def cb(state: str, message: str) -> None:
        if state == "awaiting_user_click":
            print(f"⚠️ {note}", flush=True)
            try:
                login_state.write_status(status_file, state, f"{message} {note}。")
            except OSError:
                pass
    return cb


def _fill_and_submit(page, title, content, tags, declare_ai: bool = True, on_click=None,
                     semi: bool | None = None, status_file: str | None = None,
                     handoff_timeout: float = 3600, on_unconfirmed=None) -> str:
    """填表单 →（半自动）停在发布按钮前等用户亲自点发布 /（逃生口）自动点发布 → 成功判定。
    返回 "published"；其它结局（窗口关闭/超时/处罚提示/失败）直接 sys.exit，不重试。
    on_click：发布后记频率闸门（半自动＝检测到用户已发布时；自动＝点下发布按钮后立刻）。
    on_unconfirmed：自动路径已点发布但结果未确认时调用（调用方借此记账防误二发，见 _publish）。"""
    if semi is None:
        semi = not semi_auto.auto_click_allowed("xiaohongshu")
    note = _fill_form(page, title, content, tags, declare_ai, semi)

    if semi:
        outcome = semi_auto.await_human_publish(
            page, platform="xiaohongshu", is_published=lambda pg: bool(_publish_succeeded_strict(pg)),
            toast_selectors=XHS_TOAST_SELECTORS, status_file=status_file,
            timeout_s=handoff_timeout, on_status=_status_note_callback(status_file, note))
        if outcome == "blocked":
            sys.exit(publish_guard.EXIT_COOLDOWN)
        if outcome != "published":
            why = "窗口已被关闭" if outcome == "closed" else "等待你点击发布超时"
            _die(f"小红书未发布：{why}，没有确认发布成功。请先到创作中心核对，不要自动重试。", EXIT_NOT_PUBLISHED)
        print("✅ 小红书发布成功（用户亲自点击，脚本检测到发布结果）")
        if on_click:
            on_click()
        return "published"

    kind, btn = _wait_publish_clickable(page, 15)
    human_input.pause(page, 1500, 4000)   # 发之前回看一眼
    if kind == "new":
        # xhs-publish-btn 是宽横条(闭合 Shadow DOM)，内含[暂存离开][发布]两个按钮；
        # 点 host 中心会落在两按钮间隙→无效。发布按钮在右侧约 62% 处（实测像素为品牌红）。
        human_input.click(page, btn, x_frac=0.62)
    else:
        human_input.click(page, btn)
    if on_click:
        on_click()
    page.wait_for_timeout(1000)
    _confirm_publish_dialog(page)   # 若弹二次确认框，点确认
    try:
        _wait_publish_success(page, 40)
    except SystemExit as e:
        # 已点过发布但没确认成功（非平台处罚）：记一笔 unconfirmed，让重复闸门挡住误二发
        if e.code != publish_guard.EXIT_COOLDOWN and on_unconfirmed:
            on_unconfirmed()
        raise
    return "published"


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def _allow_headless() -> bool:
    """EASEL_XHS_HEADLESS=1：允许无头（只给没有桌面的机器用，很容易被小红书识别成脚本）。"""
    return real_browser.allow_headless("EASEL_XHS_HEADLESS")


def _launch(p, headed: bool, base: str | None, proxy: str | None, *, login_assets: bool = False):
    """开小红书用的浏览器（实现见 real_browser.launch）。默认一律开窗口；
    内核优先 CloakBrowser（账号固定指纹、数据在登录目录的 cloak-browser/ 子目录），
    其次本机正式版 Chrome / Edge，最后才是 Playwright 自带的 Chromium。

    login_assets：上游为网络不稳时「登录页白屏 / 出不来二维码」加的静态资源直连兜底
    （login_transport：把 xhscdn 的脚本/样式交给 Python requests 取，失败再回浏览器）。
    它让这几个请求不再是浏览器自己的 TLS 指纹，所以只在登录流程里按需打开
    （_login_attempt 传 True）；发布 / 校验 / 看数据一律不装，保持流量全部出自真浏览器。"""
    ctx = real_browser.launch(
        p, profile_dir=_profile_dir(base), headed=headed, proxy=proxy,
        fingerprint_file=FINGERPRINT_FILE, platform_label="小红书",
        headless_env="EASEL_XHS_HEADLESS", browser_env="EASEL_XHS_BROWSER",
        engine=browser_engine(), fingerprint_fn=lambda: _account_fingerprint(base),
        chrome_hint="xhs_publish.py login 或 Web 账号页「登录」")
    if login_assets:
        try:
            login_transport.install(ctx, "xiaohongshu")
        except Exception as e:  # noqa: BLE001 — 只是兜底网络的可选优化，装不上不能挡住登录
            print(f"登录页静态资源直连兜底没装上（忽略）：{_short_err(e)}", file=sys.stderr)
    return ctx


def browser_report(base: str | None = None) -> tuple[bool, list[str]]:
    """check 用：小红书会用哪个浏览器、能不能用。Cloak / 本机 Chrome 能用时不要求 Playwright 自带内核。"""
    lines: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
        lines.append("✅ playwright 已安装")
    except Exception as e:
        return False, [f"❌ playwright 不可用：{e}"]
    engine, exe = browser_engine()
    fp_path = _profile_dir(base) / FINGERPRINT_FILE
    if engine == "cloak":
        lines.append(f"✅ CloakBrowser：{exe}（小红书操作都开它的窗口）")
        lines.append(f"   固定指纹：{'已生成 ' + str(fp_path) if fp_path.is_file() else '第一次打开时生成，存到 ' + str(fp_path)}")
        lines.append(f"   浏览器数据：{_profile_dir(base) / CLOAK_DATA_DIR}（与 Chrome 的登录态分开，换浏览器要重新扫码）")
        return True, lines
    if engine in ("chrome", "msedge"):
        why = "EASEL_XHS_BROWSER=chrome" if _browser_choice() == "chrome" else "没装 CloakBrowser"
        lines.append(f"✅ 本机浏览器：{'Google Chrome' if engine == 'chrome' else 'Microsoft Edge'}"
                     f"（{why}，小红书操作都开它的窗口）")
        return True, lines
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
        ok = bool(path and Path(path).exists())
    except Exception:
        ok = False
    lines.append("⚠️ 没找到 CloakBrowser 和本机 Chrome / Edge：会用 Playwright 自带的 Chromium，更容易被小红书识别成脚本"
                 if ok else "❌ 没有可用的浏览器：装 CloakBrowser（pip install cloakbrowser && python -m cloakbrowser install）或 Google Chrome")
    return ok, lines


def cmd_check(_a) -> int:
    ok, lines = browser_report()
    for ln in lines:
        print(ln)
    if _allow_headless():
        print("⚠️ EASEL_XHS_HEADLESS=1：允许无头运行，很容易被小红书识别成脚本")
    print(f"登录态目录：{_profile_dir(None)}")
    return 0 if ok else 3


def _wait_sel(page, selector: str, timeout_ms: int = 15000, what: str = "元素") -> object:
    """等待选择器出现，容忍登录页导航竞态。

    小红书登录页会多次跳转（探索页 → 登录引导），Playwright 在导航瞬间
    查询旧 DOM 会抛 "Execution context was destroyed"——这不是选择器错误，
    是页面在跳。重试直到 deadline 而非一次失败就报错。
    """
    deadline = time.time() + timeout_ms / 1000
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            el = page.wait_for_selector(selector, timeout=2500)
            if el is not None:
                return el
        except Exception as e:  # navigation / context destroyed / timeout
            last_err = e
        page.wait_for_timeout(800)
    if last_err is not None and "Timeout" not in type(last_err).__name__:
        raise last_err
    raise TimeoutError(f"等待 {what} 超时（{timeout_ms}ms）：{selector}")


def _query_safe(page, selector: str):
    """query_selector 的容错版：导航瞬间 context 被销毁会抛异常，这里吞掉返回
    None。裸 query_selector 在页面跳转期会崩，用它做一次性登录态探测更稳。"""
    try:
        return page.query_selector(selector)
    except Exception:
        return None


# 登录完成后，到底有没有真的落下登录态：
# 本机实测过「扫码后页面已是登录态 → 立刻关浏览器」，重开 profile 里却没有 web_session、创作平台
# 退回 /login —— 脚本还打印了「登录成功，cookie 已持久化」。所以先等登录 cookie 出现再关，
# 关完再用同一份 profile 重开一次亲眼确认，确认过了才报成功。
LOGIN_COOKIE = "web_session"      # 小红书的登录凭证 cookie（.xiaohongshu.com，持久化，约一年有效）
LOGIN_COOKIE_WAIT_S = 10
CREATOR_SETTLE_S = 3              # 创作平台登录那条路径不认得它的 cookie 名，只能多留几秒让它落盘
# 重开确认时最多等多久看到发布页真渲染出来。只在「确认不了」时才等满（正常 1~3 秒就看到了），
# 所以给慢网留足余量：等太短会把已保存的登录误报成没保存。
VERIFY_SETTLE_S = 15
WEB_LOGIN_PLATFORM = "xiaohongshu"   # = web/app.py LOGIN_RUNNERS 的键，Web 账号页读 outputs/_login/<键>.json

RISK_BLOCKED_MSG = ("小红书判定当前网络为风险 IP（安全限制 300012「IP存在风险，请切换可靠网络环境」）——"
                    "二维码在此环境无法弹出。解决：①去掉 EASEL_XHS_HEADLESS，在有桌面的本机开窗口登录"
                    "（或加 `--headed-fallback`，被拦时自动改开窗口）；"
                    "②用干净/家宽 IP 的代理 `--proxy socks5://...`；"
                    "③在正常网络的机器上 login 拿到登录态，再把持久化目录 {profile} 整个拷到本机复用。")
HEADED_FALLBACK_MSG = "小红书拦截了无头浏览器，已弹出浏览器窗口，请在窗口里扫码登录，不要关掉它。"
NOT_SAVED_MSG = "登录看似成功但登录态没能保存，请重试"
VERIFY_FAILED_MSG = ("登录已完成，但确认登录态时浏览器/网络出错：{err}。"
                     "可稍后在账号页刷新重新校验（或跑 whoami）；仍显示未登录就再登录一次（已保存会直接通过）")
LOGIN_CRASH_PREFIX = "登录窗口被关闭或浏览器异常："
WINDOW_CLOSED_MSG = (LOGIN_CRASH_PREFIX + "登录窗口已关闭，登录没有完成。请重新登录"
                     "（刚才若已扫码成功，重新登录会直接显示已登录）")


class _HeadlessBlocked(Exception):
    """无头模式被 300012 风控拦截，且调用方允许改开有头窗口重来（--headed-fallback）。"""


class _WindowClosed(Exception):
    """登录窗口被用户关掉了（或浏览器崩了），页面已不可用。"""


_NEEDS_VERIFY = object()   # _login_attempt 的返回值：页面已是登录态，要关浏览器后重开确认


def _short_err(e: BaseException, limit: int = 160) -> str:
    text = " ".join(str(e).split())
    text = f"{type(e).__name__}: {text}" if text else type(e).__name__
    return text if len(text) <= limit else text[:limit] + "…"


def _login_crash_msg(e: BaseException) -> str:
    """登录中途的意外异常 → 给 Web / 终端的一句话。窗口被关单独说清楚，其余带上异常摘要。"""
    if isinstance(e, _WindowClosed) or "TargetClosed" in type(e).__name__ \
            or "has been closed" in str(e):
        return WINDOW_CLOSED_MSG
    return LOGIN_CRASH_PREFIX + _short_err(e)


def _ensure_window_open(page) -> None:
    """窗口被关后 Playwright 的查询会被 _is_logged_in 等吞掉、只有等待才抛异常；先主动查一下，
    把「窗口被关」明确报出来，而不是一直当成「还没扫码」空等到超时。"""
    try:
        closed = page.is_closed()
    except Exception:
        closed = False
    if closed:
        raise _WindowClosed()


def _close_quietly(ctx) -> None:
    """关浏览器。窗口已被用户关掉 / 浏览器已崩时 close 也可能抛，不能让它盖掉真正的结果或异常。"""
    try:
        ctx.close()
    except Exception as e:  # noqa: BLE001
        print(f"关闭浏览器时出错（忽略）：{_short_err(e)}", file=sys.stderr)


def _has_login_cookie(cookies) -> bool:
    """cookies（Playwright context.cookies() 的列表）里有没有小红书的登录凭证。纯函数，便于单测。"""
    for c in cookies or ():
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain") or "").lstrip(".")
        if (c.get("name") == LOGIN_COOKIE and c.get("value")
                and (domain == "xiaohongshu.com" or domain.endswith(".xiaohongshu.com"))):
            return True
    return False


def _settle_login_cookies(ctx, page) -> bool:
    """页面刚变成登录态：等登录 cookie 真出现再放行关浏览器。返回是否等到了。
    这期间窗口被关 → _WindowClosed / TargetClosedError 往上抛，由 cmd_login 落 error 终态。"""
    deadline = time.time() + LOGIN_COOKIE_WAIT_S
    while time.time() < deadline:
        _ensure_window_open(page)
        try:
            has_cookie = _has_login_cookie(ctx.cookies())
        except Exception:
            has_cookie = False
        if has_cookie:
            page.wait_for_timeout(1000)   # 出现后再留一口气，让 Chromium 把它写进 profile
            return True
        page.wait_for_timeout(500)
    try:
        on_creator = "creator.xiaohongshu.com" in (page.url or "")
    except Exception:
        on_creator = False
    if on_creator:
        page.wait_for_timeout(CREATOR_SETTLE_S * 1000)
    return False


def _publish_page_ready(page) -> bool:
    """创作平台发布页以登录态真渲染出来了：发布流程第一步就要等的上传区 / 发布 tab 在页面上。"""
    url = (page.url or "").split("?", 1)[0]
    if "creator.xiaohongshu.com" not in url or "/login" in url:
        return False
    return any(_query_safe(page, SELECTORS[k]) is not None for k in ("upload_content", "creator_tab"))


def _verify_saved_login(p, base: str | None, proxy: str | None) -> bool:
    """用同一份 profile 重开创作平台发布页，看到发布页真渲染出来（正向信号）才算登录态已保存。

    不能只看「URL 没带 /login」：未登录时是前端等接口 401 才跳 /login，慢网下能拖好几秒，
    URL 在跳走前一直是发布页 —— 那样会把没存上的登录报成成功。"""
    ctx = _launch(p, headed=False, base=base, proxy=proxy)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=45000)
        deadline = time.time() + VERIFY_SETTLE_S
        seen = 0
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            if "/login" in (page.url or ""):
                return False            # 被踢回登录页：登录态没存上
            seen = seen + 1 if _publish_page_ready(page) else 0
            if seen >= 2:               # 连着两次都在，不是跳走前的一闪
                return True
        return False                    # 等满也没看到发布页：确认不了就不报成功
    finally:
        _close_quietly(ctx)


def _web_login_marker_path(a) -> Path | None:
    """CLI 直跑登录（没有 --status-file、用默认登录目录）时，也要让 Web 账号页知道已登录。"""
    if getattr(a, "status_file", None) or getattr(a, "profile_base", None):
        return None   # Web 发起的登录自己写这个文件；别的登录目录不是 Web 账号页看的那份
    try:
        import output_paths
        return output_paths.validate_output_path(
            output_paths.OUTPUTS_DIR / "_login" / f"{WEB_LOGIN_PLATFORM}.json", allow_system=True)
    except Exception:
        return None


def _report_login_success(a, sf: str | None, message: str, line: str = "") -> None:
    """先落终态（状态文件 + Web 登录标记），最后才打印 line：打印出错（如 Windows 控制台编码
    装不下 emoji）也不能让状态停在 verifying、更不能被当成登录异常改写成 error。"""
    login_state.write_status(sf, "success", message)
    marker = _web_login_marker_path(a)
    if marker is not None:
        try:
            login_state.write_status(str(marker), "success", message)
        except OSError:
            pass
    if line:
        try:
            print(line)
        except (UnicodeError, OSError):
            pass


def _login_attempt(p, a, *, headed: bool, sf: str | None, qr_out: Path, timeout_s: int,
                   window_msg: str) -> object:
    """跑一轮登录：返回退出码，或 _NEEDS_VERIFY（页面已是登录态，交给调用方关浏览器后确认）。
    无头被风控拦、且允许改开窗口时抛 _HeadlessBlocked（finally 先把这个浏览器关掉）。

    二维码抓取 / 过期刷新 / 扫码状态 / 平台维护与风控页识别用上游的 _capture_login_qr、_qr_state、
    _refresh_expired_qr、_login_error；登录完成后的「等 cookie → 关浏览器 → 重开确认」仍是我们自己的流程。"""
    fallback = bool(getattr(a, "headed_fallback", False)) and not headed
    try:
        # login_assets=True：登录页静态资源直连兜底只在登录里开（见 _launch 的说明）
        ctx = _launch(p, headed=headed, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy),
                      login_assets=True)
    except Exception as e:
        login_state.write_status(sf, "error", "浏览器没能打开。请关闭弹窗，等 10 秒再点登录，不要连点。")
        _die(f"启动浏览器失败：{e}", 1)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def risk_blocked_headless() -> None:
        if fallback:
            raise _HeadlessBlocked()
        login_state.write_status(sf, "error", "IP 存在风险，需干净网络/代理")
        _die(RISK_BLOCKED_MSG.format(profile=_profile_dir(a.profile_base)), 4)

    try:
        if headed:
            login_state.write_status(sf, "window_login", window_msg)
        explore_failed = False
        try:
            page.goto(EXPLORE_URL, wait_until="commit", timeout=30000)
        except Exception as e:
            # 首页打不开不再直接报死：_capture_login_qr 会改走官方创作平台入口
            explore_failed = True
            print(f"小红书首页无法打开（{type(e).__name__}），尝试官方创作平台入口", file=sys.stderr)

        # 等待页面稳定并完成可能的跳转（登录引导 / 风险拦截 / 已登录态）
        for _ in range(0 if explore_failed else 10):
            page.wait_for_timeout(800)
            reason = _login_error(page)
            if reason:
                if not headed and "IP 风险限制" in reason:
                    risk_blocked_headless()   # 无头被 300012 拦：允许就改开窗口，否则报错退出
                break   # 窗口里的风控 / 维护页交给 _capture_login_qr 改走创作平台入口，或让用户在窗口里处理
            try:
                if _is_logged_in(page):
                    break
            except Exception:
                pass

        if _is_logged_in(page):
            _report_login_success(a, sf, "已登录", line="✅ 已登录（登录态已在持久化目录），无需扫码")
            return 0
        # 页面没认出登录态，但创作平台账号接口认账号（上游的前置检查）：不用扫码。
        # 放在页面已经打开之后才调：浏览器的第一个请求不能是一次没有页面上下文的裸接口调用。
        if _creator_account(ctx) is not None:
            _report_login_success(a, sf, "已登录", line="✅ 已登录（创作平台账号接口已确认），无需扫码")
            return 0

        # 抠二维码存 PNG（首页出不了码时只再试一次创作平台入口；返回 False 表示其实已登录）
        qr = False
        try:
            qr = _capture_login_qr(page, qr_out, creator_only=explore_failed)
            if not qr:
                _report_login_success(a, sf, "已登录",
                                      line="✅ 已登录（创作平台登录态已在持久化目录），无需扫码")
                return 0
        except Exception as e:
            if not headed:
                if _risk_blocked(page):
                    risk_blocked_headless()
                login_state.write_status(sf, "error", _short_err(e, 300))
                print(f"小红书登录异常：{e}（可加 --headed 观察）", file=sys.stderr)
                return 1
            login_state.write_status(
                sf, "window_login",
                f"{e}。请在弹出的浏览器窗口里完成登录（扫码或短信），不要关掉那个窗口。")
        if qr:
            if headed:
                login_state.write_status(
                    sf, "window_login",
                    "请在弹出的浏览器窗口里扫码，不要关掉那个窗口。也可以扫下面这张图。",
                    qr=str(qr_out))
            else:
                login_state.write_status(sf, "qr_ready", "二维码已就绪，请扫码", qr=str(qr_out))
            print(f"📱 二维码已保存：{qr_out}")
            print("   用小红书 App 扫码登录。若走 Easel Web UI，可在 outputs 里查看这张图。")
            print("   （二维码有时效，约几分钟；过期请重跑 login）")
        print(f"⏳ 等待扫码确认（最长 {timeout_s}s）...", file=sys.stderr)

        # 轮询登录成功（扫码成功瞬间页面会跳转，_is_logged_in 自己吞掉查询异常、重试继续等）。
        # 窗口被关：_ensure_window_open 或等待本身抛异常，由 cmd_login 统一落 error 终态。
        deadline = time.time() + timeout_s
        next_refresh = time.monotonic() + 5
        next_account_check = next_refresh
        scanned = False
        refreshes = 0
        while time.time() < deadline:
            _ensure_window_open(page)
            logged_in = _is_logged_in(page)
            reason = _login_error(page) if not logged_in else ""
            state = _qr_state(page) if not logged_in else ""
            if state == "scanned" and not scanned:
                scanned = True
                login_state.write_status(sf, "scanned", "扫码成功，请在小红书 App 中确认；正在等待登录完成")
            if not logged_in and (reason or scanned) and time.monotonic() >= next_account_check:
                # 扫码后页面不一定马上跳到能被 _is_logged_in 认出的样子：用创作平台账号接口兜一下。
                # 限频：风控/维护页会一直挂着，不限频就每轮（约 2s）调一次接口
                logged_in = _creator_account(ctx) is not None
                next_account_check = time.monotonic() + 10
            if logged_in:
                # 这里还不能报成功：先等登录 cookie 落下，关浏览器后再重开确认（见 _verify_saved_login）
                if not _settle_login_cookies(ctx, page):
                    print(f"⚠️ 页面已是登录态，但没等到 {LOGIN_COOKIE} cookie；关掉浏览器后重开确认…",
                          file=sys.stderr)
                return _NEEDS_VERIFY
            if reason and not headed:
                login_state.write_status(sf, "error", reason[:300])
                print(f"小红书登录异常：{reason}", file=sys.stderr)
                return 1
            if qr and not scanned and state == "expired":
                if refreshes >= 3 or not _refresh_expired_qr(page, qr_out):
                    login_state.write_status(sf, "expired", "小红书二维码已失效，请关闭后重新获取二维码")
                    return 1
                refreshes += 1
                login_state.write_status(sf, "qr_ready", "二维码已刷新，请重新扫码", qr=str(qr_out))
            if qr and time.monotonic() >= next_refresh:
                if not scanned:
                    try:   # 二维码约几分钟一换，定期重截，Web 上显示的不会是旧码
                        login_qr.capture_qr(page, qr_out, SELECTORS["qrcode"], attempts=1,
                                            minimum_size=96)
                    except RuntimeError:
                        pass
                next_refresh = time.monotonic() + 5
            page.wait_for_timeout(2000)
        if scanned:
            login_state.write_status(
                sf, "error",
                "已扫码，但未能确认账号登录成功。请确认已在 App 中同意登录；平台维护或网络异常也可能导致校验超时。")
            print("已扫码，但账号登录校验超时；请检查 App 确认状态、平台提示和服务器网络。", file=sys.stderr)
            return 1
        login_state.write_status(sf, "expired", "二维码超时未扫")
        print(f"⏱️ {timeout_s}s 内未检测到登录成功（二维码可能已过期）。请重跑 login 再扫。",
              file=sys.stderr)
        return 1
    finally:
        _close_quietly(ctx)


def _login_flow(p, a, sf: str | None, qr_out: Path, timeout_s: int) -> int:
    try:
        result = _login_attempt(p, a, headed=bool(a.headed) or not _allow_headless(), sf=sf, qr_out=qr_out,
                                timeout_s=timeout_s,
                                window_msg="请在弹出的浏览器窗口里扫码，不要关掉那个窗口。")
    except _HeadlessBlocked:
        # 只在 EASEL_XHS_HEADLESS=1 时走到这里：小红书拦「未登录 + 无头」，有头窗口不拦。
        # 所以被拦时不必放弃，改开窗口让用户在窗口里扫一次，登录态落进同一份 profile。
        login_state.write_status(sf, "window_login", HEADED_FALLBACK_MSG)
        print(f"⚠️ {HEADED_FALLBACK_MSG}", file=sys.stderr)
        result = _login_attempt(p, a, headed=True, sf=sf, qr_out=qr_out, timeout_s=timeout_s,
                                window_msg=HEADED_FALLBACK_MSG)
    if result is not _NEEDS_VERIFY:
        return result
    login_state.write_status(sf, "verifying", "登录成功，正在确认登录态已保存…")
    try:
        saved = _verify_saved_login(p, a.profile_base, _proxy(a.proxy, a.no_proxy))
    except Exception as e:   # noqa: BLE001
        # 重开浏览器 / 打开发布页本身出错：说明不了登录态没存上，别报 NOT_SAVED 吓人重扫；
        # 也不报成功（没确认过）。给出可操作的下一步。
        msg = VERIFY_FAILED_MSG.format(err=_short_err(e))
        login_state.write_status(sf, "error", msg)
        print(f"⚠️ {msg}", file=sys.stderr)
        return 1
    if not saved:
        login_state.write_status(sf, "error", NOT_SAVED_MSG)
        print(f"❌ {NOT_SAVED_MSG}（重开浏览器后创作平台发布页仍打不开，要求登录）", file=sys.stderr)
        return 1
    try:
        qr_out.unlink()  # 登录成功清掉二维码图，避免误扫过期码
    except OSError:
        pass
    _report_login_success(a, sf, "登录成功", line="✅ 登录成功，已重开浏览器确认登录态已保存，下次免登")
    return 0


def cmd_login(a) -> int:
    """开 Chrome 窗口登录（二维码也抠成 PNG 供 Web 显示），登录成功并确认登录态已落盘后才报成功。
    REF login.go FetchQrcodeImage/WaitForLogin。远程无桌面环境靠图片扫码，非有头窗口；
    --headed-fallback：仅 EASEL_XHS_HEADLESS=1 时有用，无头被风控拦就改开窗口。"""
    publish_guard.warn_if_cooldown("xiaohongshu")   # 登录由用户主动发起：冷却期内不拦，只警告
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _die(f"需要 playwright：{e}", 3)

    qr_out = Path(a.qr_out).expanduser() if a.qr_out else DEFAULT_QR_OUT
    timeout_s = a.timeout or 180
    sf = getattr(a, "status_file", None)
    login_state.write_status(sf, "starting", "正在启动…")
    # 整个流程（含改开窗口、关浏览器后的重开确认）都持有这把锁，别让 whoami 插进来开同一份 profile
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(90)
    except TimeoutError:
        login_state.write_status(sf, "error", "账号页正在校验小红书，登录目录被占用。请关闭弹窗，等 10 秒再点登录。")
        _die("小红书登录目录正被占用（多半是后台 whoami）", 1)

    rc: int | None = None
    try:
        with sync_playwright() as p:
            rc = _login_flow(p, a, sf, qr_out, timeout_s)
        return rc
    except Exception as e:  # noqa: BLE001
        if rc is not None:
            # 流程已经落了终态，只是收尾停 Playwright 时出错：不改结论
            print(f"停止 Playwright 时出错（忽略）：{_short_err(e)}", file=sys.stderr)
            return rc
        # 窗口被用户关掉（TargetClosedError）、浏览器崩溃等意外：必须落 error 终态再退出，
        # 否则状态停在 window_login / verifying，Web 弹窗会一直转圈。（_die 抛的 SystemExit 不经过这里）
        msg = _login_crash_msg(e)
        login_state.write_status(sf, "error", msg)
        print(f"❌ {msg}", file=sys.stderr)
        return 1
    finally:
        lock.release()


def _plan_lines(kind: str, title: str, content: str, media: list[str], tags: list[str]) -> list[str]:
    tab = "上传图文" if kind == "image" else "上传视频"
    tl = calc_title_length(title) if title else 0
    lines = [
        f"发布类型：{kind}    发布页：{PUBLISH_URL}",
        f"标题：{title}（长度 {tl}/{TITLE_MAX}{'  ⚠️超限' if tl > TITLE_MAX else ''}）",
        f"正文：{content[:40]}{'...' if len(content) > 40 else ''}",
        f"媒体：{media}",
        f"话题：{tags}",
        "步骤：",
        f"  1. goto {PUBLISH_URL} → WaitLoad+DOMStable",
        f"  2. 点 tab「{tab}」（重试+遮挡检测）",
        f"  3. {'逐图上传等预览(≤60s/张)' if kind == 'image' else '上传视频等处理(≤10min)'}",
        "  4. 输标题/正文（鼠标点进去，按词组输入）+ 话题联想点选",
        "  5. 勾「笔记含AI合成内容」声明（--no-ai-declare 跳过；半自动下勾不上则提醒你手动勾）",
        "  6. 平台 DOM 长度校验",
        ("  7. 【半自动】停在发布按钮前，由你亲自点「发布」（脚本不点）" if not semi_auto.auto_click_allowed("xiaohongshu")
         else "  7. 【自动逃生口已开】等发布按钮可点击 → 鼠标移过去点"),
        "  8. 成功校验：URL 离开 /publish/publish / 成功提示 / 表单复位（成功后才记账）",
    ]
    return lines


# --------------------------------------------------------------------------- #
# 频率闸门：同一个账号发得太密就是「托管」特征。记录在登录目录里（按账号算），只记成功的。
# --------------------------------------------------------------------------- #
ACTIVITY_FILE = ".easel-activity.json"
DAY_S = 24 * 3600
# 种类 → (两次之间至少隔几分钟的环境变量, 默认, 24 小时内最多几次的环境变量, 默认)
ACTIVITY_LIMITS = {
    "publish": ("EASEL_XHS_MIN_GAP_MIN", 60, "EASEL_XHS_DAILY_MAX", 3),
    "reply": ("EASEL_XHS_REPLY_GAP_MIN", 0, "EASEL_XHS_REPLY_DAILY_MAX", 30),
    "comment": ("EASEL_XHS_COMMENT_GAP_MIN", 10, "EASEL_XHS_COMMENT_DAILY_MAX", 5),
}
ACTIVITY_NAMES = {"publish": "发笔记", "reply": "回复评论", "comment": "去别人笔记下评论"}


def _env_int(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name) or "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


def _activity_path(base: str | None) -> Path:
    return _profile_dir(base) / ACTIVITY_FILE


def _load_activity(base: str | None) -> dict:
    try:
        d = json.loads(_activity_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def activity_budget(base: str | None, kind: str, now: float | None = None) -> tuple[int, str]:
    """现在还能做几次 kind（0 = 不能做），以及不能做时的原因。"""
    now = time.time() if now is None else now
    gap_env, gap_def, max_env, max_def = ACTIVITY_LIMITS[kind]
    gap_s = _env_int(gap_env, gap_def) * 60
    day_max = _env_int(max_env, max_def)
    stamps = [t for t in _load_activity(base).get(kind, []) if isinstance(t, (int, float)) and now - t < DAY_S]
    name = ACTIVITY_NAMES[kind]
    if len(stamps) >= day_max:
        wait = int((min(stamps) + DAY_S - now) // 60) + 1
        return 0, (f"24 小时内已经{name} {len(stamps)} 次（上限 {day_max}，{max_env} 可调），"
                   f"约 {wait} 分钟后再来")
    if stamps and gap_s and now - max(stamps) < gap_s:
        wait = int((max(stamps) + gap_s - now) // 60) + 1
        return 0, f"距上次{name}不到 {gap_s // 60} 分钟（{gap_env} 可调），约 {wait} 分钟后再来"
    return day_max - len(stamps), ""


def record_activity(base: str | None, kind: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    d = _load_activity(base)
    d[kind] = [t for t in d.get(kind, []) if isinstance(t, (int, float)) and now - t < DAY_S] + [now]
    path = _activity_path(base)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        print(f"⚠️ 没能记下这次操作的时间（频率闸门会少算一次）：{e}", file=sys.stderr)


def cmd_plan(a) -> int:
    kind = "video" if a.video else "image"
    media = [str(Path(a.video).expanduser())] if a.video else (
        [s.strip() for s in (a.images or "").split(",") if s.strip()])
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    for ln in _plan_lines(kind, a.title or "<title>", a.content or "<content>", media, tags):
        print(ln)
    return 0


def _record_unconfirmed(media, title: str) -> None:
    """自动点击路径：已点发布但结果未确认 → 记账（unconfirmed），防止误二发。记账失败不影响退出。"""
    try:
        publish_guard.record_publish("xiaohongshu", media, title, url="", unconfirmed=True)
        print("⚠️ 发布结果未确认，已按「可能已发出」记账（unconfirmed）；再发同内容会被重复闸门拦下。", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 未确认发布的记账失败：{e}", file=sys.stderr)


def _publish(a, kind: str) -> int:
    global _ACTIVE_PUBLISH_STATUS_FILE
    _ACTIVE_PUBLISH_STATUS_FILE = None   # 上一次运行（同进程）留下的不算；过了发布闸门再设
    sf_pub = getattr(a, "status_file", None)
    if sf_pub:
        semi_auto.guard_status_on_exit(sf_pub)   # 任何退出路径：状态文件停在非终态时补写 error
    if not a.title:
        _die("--title 必填")
    if calc_title_length(a.title) > TITLE_MAX:
        _die(f"标题过长（{calc_title_length(a.title)}/{TITLE_MAX}），请精简")
    if kind == "image":
        media = _abspaths(a.images)
        if not media:
            _die("--images 至少一张图片")
    else:
        if not a.video:
            _die("--video 必填")
        media = [_abspaths(a.video)[0]]
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]

    # 出站内容安全闸门：真发前扫描标题/正文/话题，检出 API key/内部 URL/代理 IP/模型名/
    # "由 AI 生成" 等内部设置泄露即阻止发布（dry-run 只告警）。--allow-unsafe 手动放行。
    content_guard.guard_or_die([a.title, a.content, " ".join(tags)],
                               exec_mode=bool(a.exec),
                               allow_unsafe=getattr(a, "allow_unsafe", False),
                               label="小红书发布内容")

    declare_ai = not getattr(a, "no_ai_declare", False)
    left, why = activity_budget(a.profile_base, "publish")
    if not a.exec:
        print("dry-run（加 --exec 真正发布）：\n")
        for ln in _plan_lines(kind, a.title, a.content or "", media, tags):
            print(ln)
        print(f"AI 合成声明：{'会勾选「笔记含AI合成内容」' if declare_ai else '不勾（--no-ai-declare）'}")
        if not left:
            print(f"⚠️ 现在 --exec 会被频率闸门拦下：{why}")
        return 0
    # 发布闸门：平台冷却（exit 9）+ 重复发布（exit 8）。放在起浏览器之前。
    publish_guard.guard_before_publish("xiaohongshu", media, a.title,
                                       allow_repost=getattr(a, "allow_repost", False))
    _ACTIVE_PUBLISH_STATUS_FILE = sf_pub or None   # 从这里起是发布运行：之后每个退出都落 error 终态
    if not left:
        _die(f"小红书发得太密，这次不发：{why}", 5)

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        _die(f"需要 playwright：{e}", 3)
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(90)
    except TimeoutError:
        _die("小红书登录目录正被占用，请稍后再发")
    try:
        with sync_playwright() as p:
            ctx = _launch(p, headed=a.headed, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(300000)
            try:
                page.goto(PUBLISH_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                # 登录态探测容忍导航竞态：发布页也可能仍在跳转，跳转瞬间裸 query 会抛
                # context-destroyed；重试几次再据 url 判定「未登录」，避免误报。
                logged = False
                for _ in range(4):
                    if _query_safe(page, SELECTORS["login_ok"]) is not None:
                        logged = True
                        break
                    page.wait_for_timeout(500)
                if not logged and "login" in page.url.lower():
                    _die("未登录，请先 `login` 扫码")
                human_input.pause(page, 1500, 3500)   # 页面打开先看一眼
                if kind == "image":
                    _click_publish_tab(page, "上传图文")
                    human_input.pause(page, 800, 2000)
                    _upload_images(page, media)
                else:
                    _click_publish_tab(page, "上传视频")
                    human_input.pause(page, 800, 2000)
                    _upload_video(page, media[0])
                human_input.pause(page, 1000, 3000)
                _fill_and_submit(page, a.title, a.content or "", tags, declare_ai=declare_ai,
                                 on_click=lambda: record_activity(a.profile_base, "publish"),
                                 status_file=getattr(a, "status_file", None),
                                 handoff_timeout=getattr(a, "handoff_timeout", 3600),
                                 on_unconfirmed=lambda: _record_unconfirmed(media, a.title))
                # 已确认发布成功 → 记账（供重复拦截）
                publish_guard.record_publish("xiaohongshu", media, a.title)
                semi_auto.report_final(sf_pub, "success", "发布成功（已检测到「发布成功」）。")
            except PWTimeout as e:
                # 自动逃生口下可能是点过发布之后才超时：提示放在 {e} 前面，状态消息截到 300 字也不会丢
                _die(f"步骤超时，没有确认发布结果（请先到创作中心核对，不要自动重试；选择器可能已失效，检查 SELECTORS）：{e}")
            finally:
                if not a.keep_open:
                    ctx.close()
    finally:
        lock.release()
    # 发布成功 → 落统一内容日历（对话页自动记录；发布页由 web 设 AUTORECORD=0 跳过防重复）
    try:
        import calendar_ops
        calendar_ops.record_publish("xiaohongshu", a.title,
                                    ptype="视频" if kind == "video" else "图文",
                                    tags=(a.tags or ""), note=(a.content or ""), source="chat")
    except Exception:
        pass
    return 0


def cmd_publish(a) -> int:
    return _publish(a, "image")


def cmd_publish_video(a) -> int:
    return _publish(a, "video")


def _marker_logged_in() -> bool:
    """本地登录记录（outputs/_login/xiaohongshu.json，Web 账号页看的那份）是不是「已登录」。"""
    path = _web_login_marker_path(argparse.Namespace(status_file=None, profile_base=None))
    try:
        return bool(path) and json.loads(path.read_text(encoding="utf-8")).get("state") == "success"
    except (OSError, ValueError):
        return False


def cmd_whoami(a) -> int:
    """读登录态 + 昵称/头像，输出单行 JSON（供 Web 后端 / agent 解析）。

    默认**不开浏览器**，只读本地登录记录：每次校验都开一个小红书窗口，既打扰人、又是一次自动化
    登录访问。2026-10 合并后没重启的旧 Web 后端还在定时调本命令，结果隔一会儿就弹一个窗口。
    --live 才真开浏览器校验（用户明确要求时用）。xhs 须直连（--no-proxy），走代理会被判风险。"""
    if not getattr(a, "live", False):
        print(json.dumps({"loggedIn": _marker_logged_in(), "name": "", "avatar": "", "passive": True},
                         ensure_ascii=False))
        return 0
    publish_guard.exit_if_cooldown("xiaohongshu", "登录态校验",
                                   stdout_json={"loggedIn": False, "name": "", "avatar": ""})
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(json.dumps({"loggedIn": False, "name": "", "avatar": "", "error": f"playwright:{e}"}))
        return 0
    result = {"loggedIn": False, "name": "", "avatar": ""}
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(4)
    except TimeoutError:
        result["error"] = "profile-busy"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    try:
        with sync_playwright() as p:
            ctx = _launch(p, headed=False, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                account = _authenticated_account(ctx)
                if account is not None:
                    result["loggedIn"] = True
                    if not all(_account_identity(account).values()):
                        account = _self_profile_account(ctx, account)
                    result.update(_account_identity(account))
                    if not all((result["name"], result["avatar"])):
                        try:
                            fallback = _page_account_identity(page, account.get("userId"))
                            for field in ("name", "avatar"):
                                if not result[field]:
                                    result[field] = fallback[field]
                        except Exception:
                            pass
                else:
                    logged = _check_account_login(page)
                    result["loggedIn"] = logged
                    if logged:
                        result.update(_page_account_identity(page))
            finally:
                ctx.close()
    except Exception as e:  # noqa: BLE001 — whoami 永远输出 JSON，异常视作未登录
        result["error"] = str(e)
    finally:
        lock.release()
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_selftest(_a) -> int:
    print("xhs_publish 自检（离线）...", file=sys.stderr)
    # 标题长度算法（REF title.go）
    assert calc_title_length("") == 0
    assert calc_title_length("abcd") == 2, "4 ASCII → (4+1)//2 = 2"
    assert calc_title_length("你好") == 2, "2 全角 → 4 字节 → 2"
    assert calc_title_length("你" * 20) == 20, "20 全角 → 20（上限）"
    assert calc_title_length("a") == 1
    # 选择器字典完整
    need = ["login_ok", "qrcode", "creator_tab", "upload_input_first", "img_preview",
            "title_input", "content_quill", "topic_item", "publish_btn_new", "publish_btn_old"]
    for k in need:
        assert k in SELECTORS and SELECTORS[k], f"缺选择器 {k}"
    # 路径解析
    try:
        _abspaths("/no/such/file_xyz.jpg")
        raise AssertionError("不存在文件未报错")
    except SystemExit:
        pass
    # profile 目录路由
    assert _profile_dir(None).name == PROFILE_NAME
    assert "cloak-research-profile" not in str(_profile_dir(None))
    cloak = _cloak_executable()
    assert cloak is None or cloak.is_file()
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="easel-xhs-lock-"))
    try:
        held = _ProfileLock(tmp)
        held.acquire(1)
        blocked = _ProfileLock(tmp)
        try:
            blocked.acquire(0.3)
            raise AssertionError("第二把锁应失败")
        except TimeoutError:
            pass
        finally:
            blocked.release()
        held.release()
        held.acquire(1)
        held.release()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # 代理逻辑
    assert _proxy(None, True) is None, "--no-proxy 应禁用"
    assert _proxy("http://x:1", False) == "http://x:1", "显式代理优先"
    # plan 渲染
    lines = _plan_lines("image", "标题", "正文", ["/a.jpg"], ["#tag"])
    assert any("上传图文" in ln for ln in lines) and any("成功校验" in ln for ln in lines)
    lines_v = _plan_lines("video", "t", "c", ["/a.mp4"], [])
    assert any("上传视频" in ln for ln in lines_v)
    print("✅ selftest 通过（标题算法 + 选择器字典 + 路径/代理/路由 + plan 渲染）")
    return 0


def main() -> int:
    login_state.configure_stdio()
    ap = argparse.ArgumentParser(
        description="小红书发布（Playwright 驱动本机 Chrome 窗口；流程移植自 xiaohongshu-mcp）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    def add_common(p):
        p.add_argument("--profile-base", help="登录态根目录（默认 ~/.easel-browser-profiles）")
        p.add_argument("--proxy", help="外网代理（默认取 env，小红书是外网需代理）")
        p.add_argument("--no-proxy", action="store_true", help="禁用代理")

    def add_content(p):
        p.add_argument("--title", help="标题（≤20 全角）")
        p.add_argument("--content", help="正文")
        p.add_argument("--images", help="图片路径，逗号分隔（图文发布）")
        p.add_argument("--video", help="视频路径（视频发布）")
        p.add_argument("--tags", help="话题，逗号分隔（如 'AI,教程'）")
        p.add_argument("--exec", action="store_true", help="真正发布（默认 dry-run）")
        p.add_argument("--allow-unsafe", action="store_true",
                       help="放行内容安全闸门（检出内部设置泄露也照发，谨慎）")
        p.add_argument("--headed", action="store_true",
                       help="开窗口（默认就开；仅 EASEL_XHS_HEADLESS=1 时才可能无头）")
        p.add_argument("--keep-open", action="store_true", help="发布后不关浏览器")
        p.add_argument("--no-ai-declare", action="store_true",
                       help="不勾「笔记含AI合成内容」（仅当内容确实不是 AI 生成/合成的）")
        p.add_argument("--allow-repost", action="store_true",
                       help="放行重复发布拦截（仅当用户明确要求重发同一内容）")
        p.add_argument("--handoff-timeout", type=float, default=3600,
                       help="半自动：等用户亲自点「发布」的最长秒数（默认 3600）")
        p.add_argument("--status-file", help="半自动状态 JSON 输出路径（awaiting_user_click / success / error）")

    sub.add_parser("check", help="检查 playwright/内核").set_defaults(func=cmd_check)

    p = sub.add_parser("login", help="扫码登录并持久化（开 Chrome 窗口，二维码也抠成图片）")
    add_common(p)
    p.add_argument("--qr-out", help=f"二维码图片输出路径（默认 {DEFAULT_QR_OUT}）")
    p.add_argument("--status-file", help="登录状态 JSON 输出路径（供 Web 后端轮询）")
    p.add_argument("--timeout", type=int, help="等待扫码超时秒数（默认 180）")
    p.add_argument("--headed", action="store_true", help="开窗口（默认就开；仅 EASEL_XHS_HEADLESS=1 时有区别）")
    p.add_argument("--headed-fallback", action="store_true",
                   help="EASEL_XHS_HEADLESS=1 时：无头被风控拦截（300012）就改开窗口登录")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("plan", help="发布步骤预览（离线）")
    add_content(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("publish", help="图文发布")
    add_common(p); add_content(p)
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("publish-video", help="视频发布")
    add_common(p); add_content(p)
    p.set_defaults(func=cmd_publish_video)

    p = sub.add_parser("whoami", help="读登录态（输出 JSON）；默认只读本地登录记录，不开浏览器")
    add_common(p)
    p.add_argument("--live", action="store_true",
                   help="真开浏览器窗口校验 + 读昵称/头像（只在用户明确要求时用）")
    p.set_defaults(func=cmd_whoami)

    sub.add_parser("selftest", help="离线自检").set_defaults(func=cmd_selftest)

    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
