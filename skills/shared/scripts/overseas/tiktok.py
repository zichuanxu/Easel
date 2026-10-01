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
READY_KINDS = frozenset({"video", "image"})
# TikTok Studio 上传页；真机校准于 2026-10-01
FILE_INPUT = 'input[type="file"][accept^="video"]'
UPLOADED = '[data-e2e="upload_status_container"]'           # 上传完显示「Uploaded」
CAPTION = '[data-e2e="caption_container"] .public-DraftEditor-content'   # 预填了文件名，要先清空
VISIBILITY_BUTTON = '[data-e2e="video_visibility_container"] button[role="combobox"]'
VISIBILITY_LABEL = {"everyone": "Everyone", "friends": "Friends", "only_me": "Only you"}
POST_BUTTON = '[data-e2e="post_video_button"]'
# 新功能引导（react-joyride）、「开启内容检查？」等弹窗：选不开启
POPUPS = ('.react-joyride__tooltip button:has-text("Got it")',
          '.TUXModal-overlay button:has-text("Cancel")',
          '.TUXModal-overlay button:has-text("Got it")')
POST_NOW = '.TUXModal-overlay button:has-text("Post now")'  # 内容检查没跑完时的确认
# 图文：上传页的 Photos 标签（真机校准于 2026-10-01）。说明框、可见范围与视频页相同
PHOTO_URL = "https://www.tiktok.com/tiktokstudio/upload?tab=photo"
PHOTO_INPUT = 'input[type="file"][accept*="image"]'
PHOTO_READY = 'button[aria-label="Delete photo"]'          # 每张图一个
PHOTO_POST_BUTTON = 'button:has(:text-is("Post"))'          # 图文页的 Post 没有 data-e2e；页面上唯一
UPLOAD_WAIT_S = 300
POST_WAIT_S = 180


def option(label: str) -> str:
    return f'[role="option"]:has-text("{label}")'


def compose(post: Post) -> dict:
    return {"caption": caption_text(post), "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)


def publish(drv, fields: dict, post: Post) -> base.Result:
    if post.kind == "image":
        return _publish_photos(drv, fields, post)
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(FILE_INPUT, 30000, state="attached"):
        raise base.StepFailed("上传页没打开（找不到选择视频）")
    drv.upload(FILE_INPUT, post.media)
    for _ in range(UPLOAD_WAIT_S):
        if "uploaded" in drv.text(UPLOADED).lower():
            break
        drv.dismiss(POPUPS, rounds=1)
        drv.pause(1000)
    else:
        raise base.StepFailed("视频上传超时")
    _fill_and_post(drv, fields, POST_BUTTON)
    return _await_posted(drv)


def _publish_photos(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PHOTO_URL)
    if not drv.wait_for(PHOTO_INPUT, 30000, state="attached"):
        raise base.StepFailed("图文上传页没打开（找不到选择图片）")
    drv.upload(PHOTO_INPUT, post.media)
    if not drv.wait_count(PHOTO_READY, len(post.media), UPLOAD_WAIT_S * 1000):
        raise base.StepFailed("图片上传超时（不是每张都出现了删除按钮）")
    _fill_and_post(drv, fields, PHOTO_POST_BUTTON)
    return _await_posted(drv)


def _fill_and_post(drv, fields: dict, button: str) -> None:
    """写说明（视频页预填了文件名，先清空）→ 选可见范围 → 等发布按钮能点 → 点发布。"""
    drv.dismiss(POPUPS)
    drv.type_text(CAPTION, fields["caption"], clear=True)
    drv.dismiss(POPUPS)
    drv.click(VISIBILITY_BUTTON)
    drv.click(option(VISIBILITY_LABEL[fields["visibility"]]))
    if not drv.wait_enabled(button, 120000):
        raise base.StepFailed("发布按钮一直不能点")
    drv.commit(button)


def _await_posted(drv) -> base.Result:
    for _ in range(POST_WAIT_S):
        if "/tiktokstudio/content" in drv.url():
            return base.Result("success", message="已发布到 TikTok")
        if drv.visible(POST_NOW):
            try:
                drv.click(POST_NOW, 5000)
            except base.StepFailed:
                pass                 # 确认框自己消失了（内容检查刚好跑完）：接着等跳转
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但页面没跳到作品管理")
