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

    def __init__(self, *, visible=(), enabled=(), texts=None, attrs=None, counts=None, url="https://example.test/"):
        self.actions: list[tuple] = []
        self.visible_set = set(visible)
        self.enabled_set = set(enabled)
        self.texts = dict(texts or {})
        self.attrs = dict(attrs or {})
        self.counts = dict(counts or {})
        self._url = url
        self.hooks: dict = {}
        self.paused = 0
        self.page = None
        self.committed = False

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
        return self.counts.get(sel, 1 if sel in self.visible_set else 0)

    def wait_count(self, sel, n, timeout_ms=120000):
        self._do("wait_count", sel, n)
        return self.count(sel) >= n

    def visible(self, sel):
        return sel in self.visible_set

    def click(self, sel, timeout_ms=15000):
        if sel not in self.visible_set:
            raise base.StepFailed(f"点不到 {sel}")
        self._do("click", sel)

    def commit(self, sel, timeout_ms=15000):
        self.committed = True
        self.actions.append(("commit", sel))
        self.click(sel, timeout_ms)

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


# ---------------------------------------------------------------- Threads
TH = PLATFORMS["threads"]


def threads_driver():
    d = FakeDriver(visible={TH.OPEN_COMPOSER}, enabled={TH.POST_BUTTON})
    d.hooks[("click", TH.OPEN_COMPOSER)] = lambda dr: dr.visible_set.update({TH.TEXTBOX, TH.DIALOG})
    d.hooks[("upload", TH.FILE_INPUT)] = lambda dr: dr.visible_set.update({TH.MEDIA_READY, TH.POST_BUTTON})

    def posted(dr):
        dr.visible_set.discard(TH.DIALOG)
        dr.visible_set.add(TH.POSTED_LINK)
        dr.attrs[(TH.POSTED_LINK, "href")] = "/@demo/post/ABC"
    d.hooks[("click", TH.POST_BUTTON)] = posted
    return d


def test_threads_publishes_video():
    d = threads_driver()
    p = post()
    r = TH.publish(d, TH.compose(p), p)
    assert r.status == "success" and r.url == "https://www.threads.com/@demo/post/ABC"
    kinds = [a[0] + ":" + str(a[1]) for a in d.actions]
    assert kinds.index(f"click:{TH.OPEN_COMPOSER}") < kinds.index(f"upload:{TH.FILE_INPUT}")
    assert TH.READY_KINDS == {"video"}


def test_threads_waits_for_post_button_enabled():
    """视频还没传完、Post 是灰的：等它能点，等不到报处理超时，不去点（Final review 4）。"""
    d = threads_driver()
    d.enabled_set.clear()
    p = post()
    with pytest.raises(base.StepFailed, match="处理超时"):
        TH.publish(d, TH.compose(p), p)
    assert TH.POST_BUTTON not in [a[1] for a in d.acts("click")] and not d.committed


def test_threads_dialog_stays_open_is_unknown():
    d = threads_driver()
    d.hooks.pop(("click", TH.POST_BUTTON))
    p = post()
    assert TH.publish(d, TH.compose(p), p).status == "unknown"


# ---------------------------------------------------------------- Instagram
IG = PLATFORMS["instagram"]


def ig_driver(*, reel_notice=True):
    d = FakeDriver(visible={IG.NEW_POST, IG.POPUPS[0]}, enabled={IG.SHARE})

    def opened(dr):
        dr.visible_set.add(IG.FILE_INPUT)
    d.hooks[("click", IG.NEW_POST)] = opened

    def uploaded(dr):
        dr.visible_set.add(IG.heading("Crop"))
        dr.visible_set.add(IG.NEXT)
        if reel_notice:
            dr.visible_set.add(IG.REEL_OK)
    d.hooks[("upload", IG.FILE_INPUT)] = uploaded
    steps = iter(["Edit", "caption"])

    def next_page(dr):
        step = next(steps)
        if step == "Edit":
            dr.visible_set.add(IG.heading("Edit"))
        else:
            dr.visible_set.update({IG.CAPTION, IG.SHARE})
    d.hooks[("click", IG.NEXT)] = next_page
    d.hooks[("click", IG.SHARE)] = lambda dr: dr.texts.__setitem__(IG.DIALOG, "Reel shared\nYour reel has been shared.")
    return d


def test_instagram_publishes_reel_through_crop_and_edit():
    d = ig_driver()
    p = post()
    r = IG.publish(d, IG.compose(p), p)
    assert r.status == "success"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks == [IG.NEW_POST, IG.REEL_OK, IG.NEXT, IG.NEXT, IG.SHARE]
    assert d.acts("type")[0][1] == IG.CAPTION
    assert d.acts("dismiss")[0][1] == IG.POPUPS
    assert IG.READY_KINDS == {"video"}


def test_instagram_without_reel_notice_still_works():
    d = ig_driver(reel_notice=False)
    p = post()
    assert IG.publish(d, IG.compose(p), p).status == "success"


def test_instagram_error_text_is_failed():
    d = ig_driver()
    d.hooks[("click", IG.SHARE)] = lambda dr: dr.texts.__setitem__(IG.DIALOG, "Your reel couldn't be shared.")
    p = post()
    r = IG.publish(d, IG.compose(p), p)
    assert r.status == "failed" and "couldn't" in r.message


def test_instagram_waits_for_share_enabled():
    """Share 是灰的：等它能点，等不到就报错，不去点（Final review 4）。"""
    d = ig_driver()
    d.enabled_set.clear()
    p = post()
    with pytest.raises(base.StepFailed, match="分享按钮"):
        IG.publish(d, IG.compose(p), p)
    assert IG.SHARE not in [a[1] for a in d.acts("click")] and not d.committed


def test_instagram_caption_words_never_count_as_result():
    """说明里写了 shared / couldn't / try again：弹窗文字里这段是用户自己写的，不能当成平台给的结果（Final review 7）。"""
    caption = "We shared it — couldn't wait, try again tomorrow"
    d = ig_driver()

    def typed(dr):
        dr.texts[IG.CAPTION] = caption
        dr.texts[IG.DIALOG] = "Create new reel\n" + caption + "\nAdd location"
    d.hooks[("type", IG.CAPTION)] = typed
    d.hooks.pop(("click", IG.SHARE))      # 点了 Share，页面还停在写说明那一步
    p = post()
    assert IG.publish(d, IG.compose(p), p).status == "unknown"


def test_instagram_no_share_confirmation_is_unknown():
    d = ig_driver()
    d.hooks.pop(("click", IG.SHARE))
    p = post()
    assert IG.publish(d, IG.compose(p), p).status == "unknown"


# ---------------------------------------------------------------- TikTok
TT = PLATFORMS["tiktok"]


def tiktok_driver():
    d = FakeDriver(visible={TT.FILE_INPUT, TT.CAPTION, TT.VISIBILITY_BUTTON}, enabled={TT.POST_BUTTON})
    d.hooks[("upload", TT.FILE_INPUT)] = lambda dr: dr.texts.__setitem__(TT.UPLOADED, "clip.mp4 1080P Uploaded")
    d.hooks[("click", TT.VISIBILITY_BUTTON)] = lambda dr: dr.visible_set.update(
        {TT.option(v) for v in TT.VISIBILITY_LABEL.values()})
    d.visible_set.add(TT.POST_BUTTON)
    d.hooks[("click", TT.POST_BUTTON)] = lambda dr: setattr(dr, "_url", "https://www.tiktok.com/tiktokstudio/content")
    return d


def test_tiktok_publishes_with_visibility():
    d = tiktok_driver()
    p = post(visibility="only_me")
    r = TT.publish(d, TT.compose(p), p)
    assert r.status == "success"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks == [TT.VISIBILITY_BUTTON, TT.option("Only you"), TT.POST_BUTTON]
    assert d.acts("type")[0][1] == TT.CAPTION      # 清掉预填的文件名再写
    assert TT.READY_KINDS == {"video"}


def test_tiktok_upload_never_finishes_is_step_failed():
    d = tiktok_driver()
    d.hooks.pop(("upload", TT.FILE_INPUT))
    p = post()
    with pytest.raises(base.StepFailed, match="上传超时"):
        TT.publish(d, TT.compose(p), p)


def test_tiktok_confirms_post_now_when_content_check_pending():
    d = tiktok_driver()
    d.hooks[("click", TT.POST_BUTTON)] = lambda dr: dr.visible_set.add(TT.POST_NOW)
    d.hooks[("click", TT.POST_NOW)] = lambda dr: setattr(dr, "_url", "https://www.tiktok.com/tiktokstudio/content")
    p = post()
    assert TT.publish(d, TT.compose(p), p).status == "success"
    assert d.acts("click")[-1][1] == TT.POST_NOW


def test_tiktok_post_now_vanishing_keeps_waiting():
    """「Post now」确认框在点下去之前自己消失（内容检查刚好跑完）：不算失败，接着等跳转（Final review 2）。"""
    d = tiktok_driver()
    d.hooks[("click", TT.POST_BUTTON)] = lambda dr: dr.visible_set.add(TT.POST_NOW)
    real_click = d.click

    def click(sel, timeout_ms=15000):
        if sel == TT.POST_NOW:
            d.visible_set.discard(TT.POST_NOW)
            d._url = "https://www.tiktok.com/tiktokstudio/content"
            raise base.StepFailed("点不到 Post now")
        real_click(sel, timeout_ms)
    d.click = click
    p = post()
    assert TT.publish(d, TT.compose(p), p).status == "success"


def test_tiktok_stays_on_upload_page_is_unknown():
    d = tiktok_driver()
    d.hooks.pop(("click", TT.POST_BUTTON))
    p = post()
    assert TT.publish(d, TT.compose(p), p).status == "unknown"


# ---------------------------------------------------------------- YouTube
YT = PLATFORMS["youtube"]


def youtube_driver():
    d = FakeDriver(visible={YT.CREATE}, url=YT.PUBLISH_URL)
    d.hooks[("click", YT.CREATE)] = lambda dr: dr.visible_set.add(YT.UPLOAD_ITEM)
    d.hooks[("click", YT.UPLOAD_ITEM)] = lambda dr: dr.visible_set.add(YT.FILE_INPUT)
    d.hooks[("upload", YT.FILE_INPUT)] = lambda dr: dr.visible_set.update(
        {YT.TITLE, YT.DESCRIPTION, YT.NOT_FOR_KIDS, YT.NEXT, *YT.VISIBILITY_RADIO.values(), YT.DONE})

    def done(dr):
        dr.visible_set.add(YT.PUBLISHED_LINK)
        dr.attrs[(YT.PUBLISHED_LINK, "href")] = "https://youtu.be/abc123"
    d.hooks[("click", YT.DONE)] = done
    return d


def test_youtube_flow_sets_title_description_visibility():
    d = youtube_driver()
    p = post(title="My Short", visibility="private")
    r = YT.publish(d, YT.compose(p), p)
    assert r.status == "success" and r.url == "https://youtu.be/abc123"
    typed = {a[1]: a[2] for a in d.acts("type")}
    assert typed[YT.TITLE] == "My Short" and typed[YT.DESCRIPTION] == "Hello world\n\n#ai"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks.count(YT.NEXT) == 3
    assert YT.VISIBILITY_RADIO["private"] in clicks and clicks[-1] == YT.DONE
    assert YT.READY_KINDS == frozenset()        # 没频道、未真机校准：先不开放


def test_youtube_without_channel_says_so():
    d = youtube_driver()
    d.hooks[("goto", YT.PUBLISH_URL)] = lambda dr: setattr(dr, "_url", "https://www.youtube.com/?channel_creation_token=x")
    p = post(title="T")
    with pytest.raises(base.StepFailed, match="频道"):
        YT.publish(d, YT.compose(p), p)


def test_threads_post_button_matches_nested_label():
    """真机：Threads 的「Post」按钮是 div[role=button] > div > 文字，Playwright 的 :text-is 只匹配直接装着文字的
    最小元素，外层按钮匹配不上（2026-10-01 真发时点不到）。要用 :has(:text-is("Post"))，且不能误中「Post Options」。"""
    assert TH.POST_BUTTON == '[role="dialog"] div[role="button"]:has(:text-is("Post"))'


@pytest.mark.parametrize("mod,make,button", [
    (X, x_driver, X.POST_BUTTON), (TH, threads_driver, TH.POST_BUTTON), (IG, ig_driver, IG.SHARE),
    (TT, tiktok_driver, TT.POST_BUTTON), (YT, youtube_driver, YT.DONE)])
def test_final_button_is_clicked_through_commit(mod, make, button):
    """最终的发布 / 分享按钮一律走 commit：点下去之后出任何错都只能报待确认（Final review 2）。"""
    d = make()
    p = post(title="My Short")
    assert mod.publish(d, mod.compose(p), p).status == "success"
    assert d.acts("commit") == [("commit", button)] and d.committed
