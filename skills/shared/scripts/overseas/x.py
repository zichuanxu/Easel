"""X（Twitter）：x.com 网页版。

登录判定：auth_token 登录 cookie + 不在登录流程页。身份读左侧栏的账号切换按钮（首行是显示名）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "x"
NAME = "X"
PROFILE = "XProfile"
HOME_URL = "https://x.com/home"
LOGIN_URL = "https://x.com/i/flow/login"
COOKIE_URL = "https://x.com"
AUTH_COOKIES = ("auth_token",)
LOGIN_MARKERS = ("/i/flow/login", "/logout", "/login")
KINDS = frozenset({"video", "image", "text"})
LIMITS = Limits(caption=280, images=4, weighted=True)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = '[data-testid="SideNav_AccountSwitcher_Button"]'
AVATAR_SELECTORS = '[data-testid="SideNav_AccountSwitcher_Button"] img'
PUBLISH_URL = "https://x.com/compose/post"
READY_KINDS = frozenset({"video"})       # 图文 / 纯文字在 PR 3 接通
# 发帖弹窗（首页还有一个内嵌发帖框，同样的 testid，一律限定在弹窗里）；真机校准于 2026-10-01
_DIALOG = '[role="dialog"]'
TEXTBOX = f'{_DIALOG} [data-testid="tweetTextarea_0"]'
FILE_INPUT = f'{_DIALOG} input[data-testid="fileInput"]'
MEDIA_READY = f'{_DIALOG} [aria-label="Remove media"]'     # 视频挂上后才出现
POST_BUTTON = f'{_DIALOG} [data-testid="tweetButton"]'
TOAST = '[data-testid="toast"]'
TOAST_LINK = f'{TOAST} a[href*="/status/"]'
POST_WAIT_S = 90
PROCESS_WAIT_MS = 300000


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)


def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(TEXTBOX, 30000):
        raise base.StepFailed("没打开发帖框")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(MEDIA_READY, 120000):
        raise base.StepFailed("视频没挂上（没出现 Remove media）")
    drv.type_text(TEXTBOX, fields["caption"])
    if not drv.wait_enabled(POST_BUTTON, PROCESS_WAIT_MS):
        raise base.StepFailed("视频处理超时，发布按钮一直不能点")
    drv.commit(POST_BUTTON)
    for _ in range(POST_WAIT_S):
        if "sent" in drv.text(TOAST).lower():
            href = drv.attr(TOAST_LINK, "href")
            url = f"https://x.com{href}" if href.startswith("/") else href
            return base.Result("success", url=url, message="已发布到 X")
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但没等到「已发送」提示")
