"""Threads：threads.com 网页版（可用 Instagram 账号登录）。

登录判定：sessionid 登录 cookie + 不在登录页。Threads 每帖只能加 1 个话题标签（2024 起），真机校准时确认。
昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "threads"
NAME = "Threads"
PROFILE = "ThreadsProfile"
HOME_URL = "https://www.threads.com/"
LOGIN_URL = "https://www.threads.com/login"
COOKIE_URL = "https://www.threads.com"
AUTH_COOKIES = ("sessionid",)
LOGIN_MARKERS = ("/login",)
KINDS = frozenset({"video", "image", "text"})
LIMITS = Limits(caption=500, hashtags=1, images=10)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
