"""YouTube：YouTube Studio（studio.youtube.com），Google 账号登录（只认本机真 Chrome）。

登录判定：youtube.com 上的登录 cookie + 不在 Google 登录页（真机校准于 2026-10-01）。
账号还没有 YouTube 频道时，Studio 会带 channel_creation_token 跳回 youtube.com：登录判定照样成立，
但上传要先建频道（发布前检查放在 PR 2）。头像取 youtube.com 页头的头像按钮；频道名要有频道后在 Studio 校准。
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
NAME_SELECTORS = ""        # 频道名在 Studio 里，要等账号有频道后再校准
AVATAR_SELECTORS = "#avatar-btn img"
PUBLISH_URL = "https://studio.youtube.com/"
READY_KINDS: frozenset[str] = frozenset()


def compose(post: Post) -> dict:
    return {"title": post.title.strip(), "description": caption_text(post, with_title=False),
            "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)


def publish(drv, fields: dict, post: Post) -> base.Result:
    raise base.StepFailed(f"{NAME} 发布还没接通")
