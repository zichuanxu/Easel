"""Threads：threads.com 网页版（可用 Instagram 账号登录）。

登录判定：sessionid 登录 cookie + 不在登录页（真机校准于 2026-10-01）。
Threads 每帖只能加 1 个话题标签（2024 起），发布时再确认。
身份：用户名取左侧导航栏「Profile」链接 /@<用户名>（链接本身不带头像），头像取 alt 以该用户名开头的图（发帖框旁）。
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
NAME_SELECTORS = ""        # 不用选择器，见 read_identity
AVATAR_SELECTORS = ""
_ME_JS = """() => {
  let user = '';
  for (const a of document.querySelectorAll('a[href^="/@"]')) {
    const r = a.getBoundingClientRect();
    if (r.width > 0 && r.left < 100) { user = a.getAttribute('href').slice(2); break; }
  }
  if (!user) return null;
  const img = [...document.querySelectorAll('img')].find(i => (i.alt || '').startsWith(user + "'s"));
  return {name: user, avatar: img ? img.src : ''};
}"""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    try:
        me = page.evaluate(_ME_JS)
    except Exception:  # noqa: BLE001 — 读身份尽力而为，不抛错
        me = None
    if not me:
        return {"name": "", "avatar": ""}
    avatar = me.get("avatar") or ""
    return {"name": (me.get("name") or "")[:40], "avatar": avatar if avatar.startswith("http") else ""}
