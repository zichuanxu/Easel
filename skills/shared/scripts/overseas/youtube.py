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
# 账号还没有频道、选择器未经真机校准：先不开放（PR 2 计划 Task 9 有频道后校准再改成 {"video"}）
READY_KINDS: frozenset[str] = frozenset()
NO_CHANNEL_MARKERS = ("channel_creation_token", "/create_channel")
CREATE = "#create-icon"
UPLOAD_ITEM = "tp-yt-paper-item#text-item-0"
FILE_INPUT = 'input[type="file"]'
TITLE = "#title-textarea #textbox"
DESCRIPTION = "#description-textarea #textbox"
NOT_FOR_KIDS = 'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
NEXT = "#next-button"
VISIBILITY_RADIO = {
    "public": 'tp-yt-paper-radio-button[name="PUBLIC"]',
    "unlisted": 'tp-yt-paper-radio-button[name="UNLISTED"]',
    "private": 'tp-yt-paper-radio-button[name="PRIVATE"]',
}
DONE = "#done-button"
PUBLISHED_LINK = 'a[href*="youtu.be/"], a[href*="/shorts/"], a[href*="watch?v="]'
POST_WAIT_S = 600       # 上传 + 处理


def compose(post: Post) -> dict:
    return {"title": post.title.strip(), "description": caption_text(post, with_title=False),
            "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)


def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if any(m in drv.url() for m in NO_CHANNEL_MARKERS):
        raise base.StepFailed("这个 Google 账号还没有 YouTube 频道：先在 youtube.com →「设置」→「账号」创建频道")
    if not drv.wait_for(CREATE, 30000):
        raise base.StepFailed("YouTube Studio 没打开（找不到「创建」）")
    drv.click(CREATE)
    drv.click(UPLOAD_ITEM)
    if not drv.wait_for(FILE_INPUT, 15000, state="attached"):
        raise base.StepFailed("上传窗口没打开")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(TITLE, 120000):
        raise base.StepFailed("上传后没出现标题框")
    drv.type_text(TITLE, fields["title"], clear=True)
    drv.type_text(DESCRIPTION, fields["description"], clear=True)
    drv.click(NOT_FOR_KIDS)
    for _ in range(3):
        drv.click(NEXT)
    drv.click(VISIBILITY_RADIO[fields["visibility"]])
    drv.click(DONE)
    for _ in range(POST_WAIT_S):
        if drv.visible(PUBLISHED_LINK):
            return base.Result("success", url=drv.attr(PUBLISHED_LINK, "href"), message="已发布到 YouTube")
        drv.pause(1000)
    return base.Result("unknown", message="点了完成，但没等到视频链接")
