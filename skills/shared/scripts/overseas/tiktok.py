"""TikTok：TikTok Studio 网页版（www.tiktok.com/tiktokstudio）。

登录判定：sessionid 登录 cookie + 不在登录页。昵称取 Studio 首页用户信息里的链接，头像取页头右上角（真机校准于 2026-10-01）。
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
NAME_SELECTORS = '[data-tt="NewHome_UserInfo_a"]'
AVATAR_SELECTORS = '[data-tt="Header_NewHeader_Clickable"] img, [data-tt="components_Avatar_AvatarContainer"] img'
PUBLISH_URL = "https://www.tiktok.com/tiktokstudio/upload"
READY_KINDS: frozenset[str] = frozenset()


def compose(post: Post) -> dict:
    return {"caption": caption_text(post), "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)


def publish(drv, fields: dict, post: Post) -> base.Result:
    raise base.StepFailed(f"{NAME} 发布还没接通")
