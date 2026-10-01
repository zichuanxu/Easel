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
