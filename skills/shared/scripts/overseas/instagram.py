"""Instagram：instagram.com 网页版（桌面版支持发帖和 Reels）。

登录判定：sessionid 登录 cookie + 不在登录 / 安全验证页（真机校准于 2026-10-01）。
身份：首页信息流里全是别人的头像，只认左侧导航栏里指向 /<用户名>/、带头像的那一项（个人主页入口）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "instagram"
NAME = "Instagram"
PROFILE = "InstagramProfile"
HOME_URL = "https://www.instagram.com/"
LOGIN_URL = "https://www.instagram.com/accounts/login/"
COOKIE_URL = "https://www.instagram.com"
AUTH_COOKIES = ("sessionid",)
LOGIN_MARKERS = ("/accounts/login", "/challenge")
# 会话失效时 Instagram 不跳登录页，直接在首页给登录表单：看到它就是未登录（旧 sessionid 可能还在）
LOGIN_FORM = 'input[name="username"]'
KINDS = frozenset({"video", "image"})
LIMITS = Limits(caption=2200, hashtags=30, images=10)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = ""        # 不用选择器，见 read_identity
AVATAR_SELECTORS = ""
PUBLISH_URL = HOME_URL
READY_KINDS: frozenset[str] = frozenset()
_ME_JS = """() => {
  for (const a of document.querySelectorAll('a[href]')) {
    const img = a.querySelector('img');
    const r = a.getBoundingClientRect();
    if (img && r.width > 0 && r.left < 100 && /^\\/[^/]+\\/$/.test(a.getAttribute('href') || '')) {
      return {name: a.getAttribute('href').split('/').join(''), avatar: img.src || ''};
    }
  }
  return null;
}"""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return (base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)
            and not base.shows_login_form(page, LOGIN_FORM))


def read_identity(page) -> dict:
    try:
        me = page.evaluate(_ME_JS)
    except Exception:  # noqa: BLE001 — 读身份尽力而为，不抛错
        me = None
    if not me:
        return {"name": "", "avatar": ""}
    avatar = me.get("avatar") or ""
    return {"name": (me.get("name") or "")[:40], "avatar": avatar if avatar.startswith("http") else ""}


def publish(drv, fields: dict, post: Post) -> base.Result:
    raise base.StepFailed(f"{NAME} 发布还没接通")
