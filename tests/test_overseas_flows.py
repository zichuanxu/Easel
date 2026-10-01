"""海外平台发布流程（各平台模块的 publish）离线测试：按剧本走的假驱动，不起浏览器、不连平台。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import PLATFORMS, base  # noqa: E402
from overseas.post import Post  # noqa: E402

VIDEO = Path("/tmp/clip.mp4")


class FakeDriver:
    """记录动作；visible / enabled / text / attr 读剧本，hooks[(动作, 选择器)] 在动作后改剧本。"""

    def __init__(self, *, visible=(), enabled=(), texts=None, attrs=None, url="https://example.test/"):
        self.actions: list[tuple] = []
        self.visible_set = set(visible)
        self.enabled_set = set(enabled)
        self.texts = dict(texts or {})
        self.attrs = dict(attrs or {})
        self._url = url
        self.hooks: dict = {}
        self.paused = 0
        self.page = None

    def _do(self, act, sel, *extra):
        self.actions.append((act, sel, *extra))
        hook = self.hooks.get((act, sel))
        if hook:
            hook(self)

    def goto(self, url, timeout_ms=60000):
        self._url = url
        self._do("goto", url)

    def url(self):
        return self._url

    def count(self, sel):
        return 1 if sel in self.visible_set else 0

    def visible(self, sel):
        return sel in self.visible_set

    def click(self, sel, timeout_ms=15000):
        if sel not in self.visible_set:
            raise base.StepFailed(f"点不到 {sel}")
        self._do("click", sel)

    def upload(self, sel, files, timeout_ms=30000):
        self._do("upload", sel, tuple(str(f) for f in files))

    def type_text(self, sel, text, *, clear=True, timeout_ms=15000):
        self._do("type", sel, text)

    def press(self, key):
        self._do("press", key)

    def wait_for(self, sel, timeout_ms=15000, state="visible"):
        self._do("wait_for", sel)
        return sel in self.visible_set

    def wait_enabled(self, sel, timeout_ms=60000):
        self._do("wait_enabled", sel)
        return sel in self.enabled_set

    def text(self, sel):
        return self.texts.get(sel, "")

    def attr(self, sel, name):
        return self.attrs.get((sel, name), "")

    def pause(self, ms):
        self.paused += ms

    def dismiss(self, selectors, rounds=2):
        self._do("dismiss", tuple(selectors))

    def settle(self, mod):
        return True

    def acts(self, kind):
        return [a for a in self.actions if a[0] == kind]


def post(**kw):
    return Post(media=[VIDEO], title=kw.pop("title", ""), desc=kw.pop("desc", "Hello world"),
                tags=kw.pop("tags", "ai"), **kw)


# ---------------------------------------------------------------- X
X = PLATFORMS["x"]


def x_driver():
    d = FakeDriver(visible={X.TEXTBOX, X.POST_BUTTON}, enabled={X.POST_BUTTON})
    d.hooks[("upload", X.FILE_INPUT)] = lambda dr: dr.visible_set.add(X.MEDIA_READY)

    def sent(dr):
        dr.texts[X.TOAST] = "Your post was sent. View"
        dr.attrs[(X.TOAST_LINK, "href")] = "/demo/status/123"
    d.hooks[("click", X.POST_BUTTON)] = sent
    return d


def test_x_publishes_video_and_reads_status_link():
    d = x_driver()
    p = post()
    r = X.publish(d, X.compose(p), p)
    assert r.status == "success" and r.url == "https://x.com/demo/status/123"
    kinds = [a[0] for a in d.actions]
    assert kinds.index("upload") < kinds.index("type") < kinds.index("click")
    assert d.acts("type")[0][2] == "Hello world\n\n#ai"
    assert d.acts("goto")[0][1] == X.PUBLISH_URL


def test_x_waits_for_post_button_enabled():
    """视频还在处理、发布按钮一直是灰的：不去点，报处理超时（Review Focus 2）。"""
    d = x_driver()
    d.enabled_set.clear()
    p = post()
    with pytest.raises(base.StepFailed, match="处理超时"):
        X.publish(d, X.compose(p), p)
    assert not d.acts("click")


def test_x_media_never_attaches_is_step_failed():
    d = x_driver()
    d.hooks.pop(("upload", X.FILE_INPUT))
    p = post()
    with pytest.raises(base.StepFailed, match="视频没挂上"):
        X.publish(d, X.compose(p), p)


def test_x_no_toast_is_unknown():
    d = x_driver()
    d.hooks.pop(("click", X.POST_BUTTON))
    p = post()
    r = X.publish(d, X.compose(p), p)
    assert r.status == "unknown"
    assert d.paused >= X.POST_WAIT_S * 1000 - 1000


def test_registry_publish_contract():
    for key, m in PLATFORMS.items():
        assert callable(m.publish), key
        assert m.READY_KINDS <= m.KINDS, key
        assert m.PUBLISH_URL.startswith("https://"), key
    assert PLATFORMS["x"].READY_KINDS == {"video"}
