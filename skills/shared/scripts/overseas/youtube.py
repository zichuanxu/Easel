"""YouTube：YouTube Studio（studio.youtube.com），Google 账号登录（只认本机真 Chrome）。

登录判定：youtube.com 上的登录 cookie + 不在 Google 登录页。昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "youtube"
NAME = "YouTube"
PROFILE = "YouTubeProfile"
HOME_URL = "https://studio.youtube.com/"
LOGIN_URL = ("https://accounts.google.com/ServiceLogin?service=youtube"
             "&continue=https%3A%2F%2Fstudio.youtube.com%2F")
COOKIE_URL = "https://www.youtube.com"
AUTH_COOKIES = ("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID")
LOGIN_MARKERS = ("accounts.google.com", "servicelogin")
KINDS = frozenset({"video"})
LIMITS = Limits(caption=5000, title=100)
VISIBILITY = ("public", "unlisted", "private")
VISIBILITY_DEFAULT = "public"
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"title": post.title.strip(), "description": caption_text(post, with_title=False),
            "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
