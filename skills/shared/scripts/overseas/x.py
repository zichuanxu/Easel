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


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
