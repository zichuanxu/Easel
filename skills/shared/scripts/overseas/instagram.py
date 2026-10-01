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
READY_KINDS = frozenset({"video"})       # 图文在 PR 3 接通
# 新建帖子流程：New post → 选文件 →（Reels 提示 OK）→ Crop → Next → Edit → Next → 写说明 → Share
# 真机校准于 2026-10-01
DIALOG = '[role="dialog"]'
NEW_POST = 'svg[aria-label="New post"]'
FILE_INPUT = f'{DIALOG} input[type="file"]'
REEL_OK = f'{DIALOG} button:text-is("OK")'
NEXT = f'{DIALOG} div[role="button"]:text-is("Next")'
CAPTION = f'{DIALOG} [role="textbox"][aria-label^="Add a caption"]'
SHARE = f'{DIALOG} div[role="button"]:text-is("Share")'
POPUPS = ('button:text-is("Not Now")',)      # 首页「开启通知」弹窗
POST_WAIT_S = 300                            # Reels 要转码，最长等 5 分钟
SHARE_ENABLED_WAIT_MS = 60000


def heading(text: str) -> str:
    return f'{DIALOG} [role="heading"]:text-is("{text}")'

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
    drv.goto(PUBLISH_URL)
    drv.dismiss(POPUPS)
    if not drv.wait_for(NEW_POST, 20000):
        raise base.StepFailed("找不到新建帖子入口（New post）")
    drv.click(NEW_POST)
    if not drv.wait_for(FILE_INPUT, 15000, state="attached"):
        raise base.StepFailed("新建帖子弹窗没打开")
    drv.upload(FILE_INPUT, post.media)
    if drv.wait_for(REEL_OK, 8000):
        drv.click(REEL_OK)
    for step in ("Crop", "Edit"):
        if not drv.wait_for(heading(step), 60000):
            raise base.StepFailed(f"没到 {step} 页")
        drv.click(NEXT)
    if not drv.wait_for(CAPTION, 30000):
        raise base.StepFailed("没到写说明那一步")
    drv.type_text(CAPTION, fields["caption"], clear=False)
    if not drv.wait_enabled(SHARE, SHARE_ENABLED_WAIT_MS):
        raise base.StepFailed("分享按钮一直不能点")
    drv.commit(SHARE)
    for _ in range(POST_WAIT_S):
        # 还停在写说明页时弹窗文字里有用户自己写的说明（可能就含 shared / couldn't），先把它去掉再判断
        mine = drv.text(CAPTION) if drv.count(CAPTION) else ""      # 说明框不在了就别等它（text 找不到要等 2 秒）
        text = drv.text(DIALOG).replace(mine, "").lower()
        if "shared" in text and "couldn" not in text:
            return base.Result("success", message="已发布到 Instagram")
        if "couldn" in text or "try again" in text:
            return base.Result("failed", message=drv.text(DIALOG)[:120])
        drv.pause(1000)
    return base.Result("unknown", message="点了分享，但没等到「已分享」提示")
