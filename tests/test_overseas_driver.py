"""PageDriver（overseas/base.py）的离线测试：用最小的假 Playwright 页面，不起浏览器。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import base  # noqa: E402


class FakeKeyboard:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def press(self, key):
        self.events.append(("press", key))

    def type(self, text, delay=0):
        self.events.append(("type", text))


class FakeLocator:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    def nth(self, _i):
        return self

    def count(self):
        return self.page.counts.get(self.sel, 1 if self.sel in self.page.present else 0)

    def is_visible(self):
        return self.sel in self.page.present

    def is_enabled(self):
        return self.sel in self.page.enabled

    def get_attribute(self, name, timeout=None):
        return self.page.attrs.get((self.sel, name))

    def inner_text(self, timeout=None):
        return self.page.texts.get(self.sel, "")

    def click(self, timeout=None):
        if self.sel not in self.page.present:
            raise RuntimeError(f"Timeout waiting for {self.sel}")
        self.page.clicks.append(self.sel)

    def set_input_files(self, files, timeout=None):
        self.page.uploads.append((self.sel, list(files)))

    def wait_for(self, state="visible", timeout=None):
        if self.sel not in self.page.present:
            raise RuntimeError("Timeout")


class FakePWPage:
    def __init__(self, url="https://example.test/home"):
        self.url = url
        self.present: set[str] = set()
        self.counts: dict = {}
        self.enabled: set[str] = set()
        self.attrs: dict = {}
        self.texts: dict = {}
        self.clicks: list[str] = []
        self.uploads: list = []
        self.waited = 0
        self.keyboard = FakeKeyboard()
        self.after_goto = None

    def locator(self, sel):
        return FakeLocator(self, sel)

    def goto(self, url, wait_until=None, timeout=None):
        self.url = self.after_goto or url

    def wait_for_timeout(self, ms):
        self.waited += ms


def drv_for(page):
    return base.PageDriver(page, pace=(0, 0))


def test_type_text_clears_then_types_lines_with_enter():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hello\n\n#ai")
    sel_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
    assert page.clicks == ["#box"]
    assert page.keyboard.events == [("press", sel_all), ("press", "Backspace"), ("type", "Hello"),
                                    ("press", "Enter"), ("press", "Enter"), ("type", "#ai"), ("type", " ")]


def test_type_text_closes_tag_suggestions_before_next_line():
    """以话题结尾的行：先补空格（X / Instagram / TikTok 的联想框就收了），联想框还开着（Threads）再按 Esc，然后才回车（Review Focus 1）。"""
    page = FakePWPage()
    page.present.update({"#box", '[role="listbox"]'})
    drv_for(page).type_text("#box", "Hi #ai\nBye", clear=False)
    assert page.keyboard.events == [("type", "Hi #ai"), ("type", " "), ("press", "Escape"),
                                    ("press", "Enter"), ("type", "Bye"), ("press", "Escape")]


def test_type_text_never_presses_escape_without_suggestions():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hi #ai", clear=False)
    assert page.keyboard.events == [("type", "Hi #ai"), ("type", " ")]


def test_wait_count_waits_for_n_matches():
    page = FakePWPage()
    page.counts = {"img.preview": 1}
    assert drv_for(page).wait_count("img.preview", 2, timeout_ms=1500) is False
    page.counts["img.preview"] = 2
    assert drv_for(page).wait_count("img.preview", 2, timeout_ms=1500) is True


def test_type_text_without_clear_keeps_existing_text():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hi", clear=False)
    assert page.keyboard.events == [("type", "Hi")]


def test_click_missing_element_raises_step_failed():
    with pytest.raises(base.StepFailed, match="#nope"):
        drv_for(FakePWPage()).click("#nope", timeout_ms=10)


def test_goto_onto_challenge_page_raises_blocked():
    page = FakePWPage()
    page.after_goto = "https://www.instagram.com/challenge/?next=/"
    with pytest.raises(base.Blocked):
        drv_for(page).goto("https://www.instagram.com/")
    page.after_goto = None
    drv_for(page).goto("https://x.com/home")
    assert page.url == "https://x.com/home"


def _challenge_cleared_after(page, ms):
    """模拟用户在窗口里过验证：等够 ms 后页面离开验证页，之后再打开目标页也不再被拦。"""
    gotos: list[str] = []
    real_goto = page.goto

    def goto(url, wait_until=None, timeout=None):
        gotos.append(url)
        real_goto(url, wait_until, timeout)

    def wait(n):
        page.waited += n
        if page.waited >= ms:
            page.url = "https://www.instagram.com/"
            page.after_goto = None

    page.goto, page.wait_for_timeout = goto, wait
    return gotos


def test_goto_headed_waits_for_user_to_clear_challenge_then_reopens_target():
    """有头窗口落到验证页：等用户在窗口里过验证，过了再重开目标页，不是一看到验证页就关窗口（Final review 1）。"""
    page = FakePWPage()
    page.after_goto = "https://www.instagram.com/challenge/?next=/"
    gotos = _challenge_cleared_after(page, 6000)
    base.PageDriver(page, pace=(0, 0), block_wait_ms=60000).goto("https://www.instagram.com/create/")
    assert gotos == ["https://www.instagram.com/create/", "https://www.instagram.com/create/"]
    assert page.url == "https://www.instagram.com/create/"


def test_goto_headed_gives_up_when_challenge_never_cleared():
    page = FakePWPage()
    page.after_goto = "https://www.instagram.com/challenge/?next=/"
    _challenge_cleared_after(page, 10 ** 9)
    with pytest.raises(base.Blocked):
        base.PageDriver(page, pace=(0, 0), block_wait_ms=8000).goto("https://www.instagram.com/")
    assert 8000 <= page.waited < 12000


def test_commit_marks_committed_before_clicking():
    """点最终发布按钮前就记下 committed：点击本身报错也可能已经发出去了（Final review 2）。"""
    page = FakePWPage()
    drv = drv_for(page)
    assert drv.committed is False
    with pytest.raises(base.StepFailed):
        drv.commit("#post", timeout_ms=10)
    assert drv.committed is True
    page.present.add("#post")
    drv.commit("#post")
    assert page.clicks == ["#post"]


def test_wait_enabled_respects_aria_disabled():
    page = FakePWPage()
    page.present.add("#post")
    page.enabled.add("#post")
    page.attrs[("#post", "aria-disabled")] = "true"
    assert drv_for(page).wait_enabled("#post", timeout_ms=1) is False
    page.attrs[("#post", "aria-disabled")] = "false"
    assert drv_for(page).wait_enabled("#post", timeout_ms=1) is True


def test_dismiss_clicks_only_visible_popups():
    page = FakePWPage()
    page.present.add("button.notnow")
    drv_for(page).dismiss(["button.notnow", "button.absent"], rounds=1)
    assert page.clicks == ["button.notnow"]


def test_wait_for_and_text_helpers():
    page = FakePWPage()
    page.present.add("#toast")
    page.texts["#toast"] = "Your post was sent."
    drv = drv_for(page)
    assert drv.wait_for("#toast", 10) is True
    assert drv.wait_for("#missing", 10) is False
    assert drv.text("#toast") == "Your post was sent."
    assert drv.text("#missing") == ""


def test_result_defaults():
    r = base.Result("success")
    assert (r.status, r.url, r.message) == ("success", "", "")


def test_save_failure_never_raises():
    assert base.save_failure(SimpleNamespace(), "demo") is None
