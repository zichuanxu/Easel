"""五个海外平台模块的契约测试：注册表、形式与上限、文案拼接、登录判定（假页面，不起浏览器）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import PLATFORMS, REQUIRED_ATTRS, get  # noqa: E402
from overseas.post import Post  # noqa: E402


class FakeContext:
    def __init__(self, cookies):
        self._cookies = cookies

    def cookies(self, urls=None):
        return list(self._cookies)


class FakePage:
    def __init__(self, url, cookies=()):
        self.url = url
        self.context = FakeContext(list(cookies))


def test_registry_has_five_platforms_with_unique_profiles():
    assert list(PLATFORMS) == ["tiktok", "youtube", "instagram", "x", "threads"]
    assert len({m.PROFILE for m in PLATFORMS.values()}) == 5
    for key, m in PLATFORMS.items():
        assert m.KEY == key
        for attr in REQUIRED_ATTRS:
            assert hasattr(m, attr), f"{key} 缺 {attr}"
        assert ("image" in m.KINDS) == (m.LIMITS.images > 0)
        if m.VISIBILITY:
            assert m.VISIBILITY_DEFAULT in m.VISIBILITY
        else:
            assert m.VISIBILITY_DEFAULT == ""


def test_names_and_profiles_match_spec():
    assert {k: (m.NAME, m.PROFILE) for k, m in PLATFORMS.items()} == {
        "tiktok": ("TikTok", "TikTokProfile"),
        "youtube": ("YouTube", "YouTubeProfile"),
        "instagram": ("Instagram", "InstagramProfile"),
        "x": ("X", "XProfile"),
        "threads": ("Threads", "ThreadsProfile"),
    }


def test_get_unknown_platform():
    with pytest.raises(KeyError, match="不支持的海外平台"):
        get("weibo")


@pytest.mark.parametrize("key,kinds", [
    ("tiktok", {"video", "image"}),
    ("youtube", {"video"}),
    ("instagram", {"video", "image"}),
    ("x", {"video", "image", "text"}),
    ("threads", {"video", "image", "text"}),
])
def test_kinds_match_spec(key, kinds):
    assert PLATFORMS[key].KINDS == kinds


def test_limits_match_spec():
    yt, tt, ig, x, th = (PLATFORMS[k].LIMITS for k in ("youtube", "tiktok", "instagram", "x", "threads"))
    assert (yt.title, yt.caption) == (100, 5000)
    assert tt.caption == 2200
    assert (ig.caption, ig.hashtags, ig.images) == (2200, 30, 10)
    assert (x.caption, x.images, x.weighted) == (280, 4, True)
    assert (th.caption, th.images) == (500, 10)


def test_youtube_compose_splits_title_and_description():
    f = PLATFORMS["youtube"].compose(Post(title="My Short", desc="Body", tags="ai, easel"))
    assert f == {"title": "My Short", "description": "Body\n\n#ai #easel", "visibility": "public"}


def test_tiktok_compose_caption_and_visibility():
    f = PLATFORMS["tiktok"].compose(Post(title="T", desc="D", tags="x", visibility="only_me"))
    assert f == {"caption": "T\n\nD\n\n#x", "visibility": "only_me"}
    assert PLATFORMS["tiktok"].compose(Post(title="T"))["visibility"] == "everyone"


@pytest.mark.parametrize("key", ["instagram", "x", "threads"])
def test_caption_only_platforms(key):
    assert PLATFORMS[key].compose(Post(title="T", tags="a")) == {"caption": "T\n\n#a"}


@pytest.mark.parametrize("key", ["tiktok", "youtube", "instagram", "x", "threads"])
def test_is_logged_in_needs_auth_cookie_and_not_login_page(key):
    m = PLATFORMS[key]
    good = [{"name": m.AUTH_COOKIES[0], "value": "v"}]
    assert m.is_logged_in(FakePage(m.HOME_URL, good))
    assert not m.is_logged_in(FakePage(m.HOME_URL, []))
    assert not m.is_logged_in(FakePage(m.LOGIN_URL, good))


@pytest.mark.parametrize("key", ["tiktok", "youtube", "instagram", "x", "threads"])
def test_read_identity_never_raises(key):
    class Empty:
        def query_selector(self, _sel):
            return None

    assert PLATFORMS[key].read_identity(Empty()) == {"name": "", "avatar": ""}


def test_instagram_identity_from_sidebar_profile_link():
    """Instagram 首页信息流里全是别人的头像：只认左侧导航栏指向 /<用户名>/ 的那一项（真机校准）。"""
    class Page:
        def __init__(self, me):
            self.me = me

        def query_selector(self, _sel):
            return None

        def evaluate(self, _js):
            return self.me

    ig = PLATFORMS["instagram"]
    assert ig.read_identity(Page({"name": "demo_user", "avatar": "https://cdn/a.jpg"})) == {
        "name": "demo_user", "avatar": "https://cdn/a.jpg"}
    assert ig.read_identity(Page({"name": "demo_user", "avatar": "data:image/png;base64,x"})) == {
        "name": "demo_user", "avatar": ""}
    assert ig.read_identity(Page(None)) == {"name": "", "avatar": ""}


def test_threads_identity_from_sidebar_profile_link():
    """Threads：用户名取左侧导航栏的 /@<用户名> 链接，头像取 alt 带该用户名的图（真机校准）。"""
    class Page:
        def __init__(self, me):
            self.me = me

        def query_selector(self, _sel):
            return None

        def evaluate(self, _js):
            return self.me

    th = PLATFORMS["threads"]
    assert th.read_identity(Page({"name": "demo_user", "avatar": "https://cdn/a.jpg"})) == {
        "name": "demo_user", "avatar": "https://cdn/a.jpg"}
    assert th.read_identity(Page({"name": "demo_user", "avatar": ""})) == {"name": "demo_user", "avatar": ""}
    assert th.read_identity(Page(None)) == {"name": "", "avatar": ""}


def test_tiktok_identity_selectors():
    """TikTok Studio：昵称在首页用户信息的链接里，头像取页头右上角（真机校准）。"""
    class El:
        def __init__(self, text="", src=""):
            self.text, self.src = text, src

        def inner_text(self):
            return self.text

        def get_attribute(self, _name):
            return self.src

    class Page:
        def query_selector(self, sel):
            return {'[data-tt="NewHome_UserInfo_a"]': El(text="demo_user"),
                    '[data-tt="Header_NewHeader_Clickable"] img': El(src="https://cdn/a.jpg")}.get(sel)

    assert PLATFORMS["tiktok"].read_identity(Page()) == {"name": "demo_user", "avatar": "https://cdn/a.jpg"}


def test_youtube_identity_reads_header_avatar():
    """YouTube：没有频道时 Studio 会跳回 youtube.com，只能从页头头像按钮读头像（真机校准）。"""
    class El:
        def get_attribute(self, _name):
            return "https://yt3.example/a=s88"

        def inner_text(self):
            return ""

    class Page:
        def query_selector(self, sel):
            return El() if sel == "#avatar-btn img" else None

    assert PLATFORMS["youtube"].read_identity(Page()) == {"name": "", "avatar": "https://yt3.example/a=s88"}

