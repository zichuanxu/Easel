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
PUBLISH_URL = HOME_URL
READY_KINDS = frozenset({"video"})       # 图文 / 纯文字在 PR 3 接通
# 首页「What's new?」打开发帖弹窗；真机校准于 2026-10-01
OPEN_COMPOSER = '[aria-label^="Empty text field"]'
DIALOG = '[role="dialog"]'
TEXTBOX = f'{DIALOG} [role="textbox"]'
FILE_INPUT = f'{DIALOG} input[type="file"]'
MEDIA_READY = f'{DIALOG} video'
POST_BUTTON = f'{DIALOG} div[role="button"]:text-is("Post")'   # 精确匹配，别点成 Post Options
POSTED_LINK = 'a[href*="/post/"]:has-text("View")'
POST_WAIT_S = 120
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


def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(OPEN_COMPOSER, 30000):
        raise base.StepFailed("找不到发帖入口（What's new?）")
    drv.click(OPEN_COMPOSER)
    if not drv.wait_for(TEXTBOX, 15000):
        raise base.StepFailed("发帖弹窗没打开")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(MEDIA_READY, 120000):
        raise base.StepFailed("视频没挂上（弹窗里没出现视频预览）")
    drv.type_text(TEXTBOX, fields["caption"], clear=False)
    drv.click(POST_BUTTON)
    for _ in range(POST_WAIT_S):
        if not drv.visible(DIALOG) and drv.visible(POSTED_LINK):
            href = drv.attr(POSTED_LINK, "href")
            url = f"https://www.threads.com{href}" if href.startswith("/") else href
            return base.Result("success", url=url, message="已发布到 Threads")
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但没等到「已发布」提示")
