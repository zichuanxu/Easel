"""TikTok：TikTok Studio 网页版（www.tiktok.com/tiktokstudio）。

登录判定：sessionid 登录 cookie + 不在登录页。昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "tiktok"
NAME = "TikTok"
PROFILE = "TikTokProfile"
HOME_URL = "https://www.tiktok.com/tiktokstudio"
LOGIN_URL = "https://www.tiktok.com/login"
COOKIE_URL = "https://www.tiktok.com"
AUTH_COOKIES = ("sessionid", "sessionid_ss")
LOGIN_MARKERS = ("/login",)
KINDS = frozenset({"video", "image"})
LIMITS = Limits(caption=2200, images=35)
VISIBILITY = ("everyone", "friends", "only_me")
VISIBILITY_DEFAULT = "everyone"
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post), "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
