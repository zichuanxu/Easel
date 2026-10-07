"""semi_auto：半自动交接。用假 page，不开真实浏览器。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"))

import json

import pytest

import publish_guard as pg
import semi_auto


class FakePage:
    def __init__(self, toasts=None, published_after=None, closed_after=None, raise_on_locator=None):
        self.toasts = toasts or {}
        self.published_after = published_after
        self.closed_after = closed_after
        self.polls = 0
        self.closed = False
        self.raise_on_locator = raise_on_locator
        self.clicked = []

    def is_closed(self):
        if self.closed_after is not None and self.polls >= self.closed_after:
            self.closed = True
        return self.closed

    def locator(self, sel):
        page = self

        class L:
            def all_inner_texts(self_inner):
                page.polls += 1
                if page.raise_on_locator:
                    raise page.raise_on_locator
                return page.toasts.get(sel, []) if page.polls >= 2 else []

            def click(self_inner, *a, **k):
                page.clicked.append(sel)
        return L()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER_PATH", tmp_path / "l.jsonl")
    monkeypatch.setattr(pg, "COOLDOWN_PATH", tmp_path / "cd.json")
    monkeypatch.setattr(pg, "PUBLISH_LOG_PATH", tmp_path / "pl.json")
    clock = {"t": 0.0}
    monkeypatch.setattr(semi_auto, "_monotonic", lambda: clock["t"])
    monkeypatch.setattr(semi_auto, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.delenv(semi_auto.AUTO_PUBLISH_ENV, raising=False)


def test_auto_click_default_off(monkeypatch):
    assert semi_auto.auto_click_allowed("douyin") is False
    for v in ("0", "true", "yes", ""):
        monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, v)
        assert semi_auto.auto_click_allowed("douyin") is False
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    assert semi_auto.auto_click_allowed("douyin") is True


def test_published(tmp_path):
    page = FakePage()
    sf = tmp_path / "s.json"
    states = []
    out = semi_auto.await_human_publish(
        page, platform="douyin", is_published=lambda p: p.polls >= 3,
        toast_selectors=(".toast",), status_file=str(sf), on_status=lambda s, m: states.append(s))
    assert out == "published"
    assert states == ["awaiting_user_click", "verifying"]   # 非终态：核对由调用方做，本函数从不写 success
    d = json.loads(sf.read_text(encoding="utf-8"))
    assert d["state"] == "verifying" and "ts" in d and "正在核对" in d["message"]
    import login_state
    assert "verifying" in login_state.STATES
    assert page.clicked == []   # 绝不点击


def test_status_file_awaiting_shape(tmp_path):
    sf = tmp_path / "s.json"
    seen = {}

    def pub(p):
        seen.update(json.loads(sf.read_text(encoding="utf-8")))
        return True
    semi_auto.await_human_publish(FakePage(), platform="douyin", is_published=pub,
                                  toast_selectors=(), status_file=str(sf))
    assert seen["state"] == "awaiting_user_click" and "亲自点击" in seen["message"]


def test_blocked_sets_cooldown(tmp_path):
    page = FakePage(toasts={".toast": ["视频投稿功能已封禁，详情见【消息-系统通知】"]})
    out = semi_auto.await_human_publish(page, platform="douyin", is_published=lambda p: False,
                                        toast_selectors=(".toast",), status_file=str(tmp_path / "s.json"))
    assert out == "blocked"
    assert pg.active_cooldown("douyin")
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["state"] == "error"


def test_ordinary_toast_does_not_block():
    page = FakePage(toasts={".toast": ["请勿发布违规内容"]})
    out = semi_auto.await_human_publish(page, platform="douyin", is_published=lambda p: p.polls >= 4,
                                        toast_selectors=(".toast",))
    assert out == "published" and pg.active_cooldown("douyin") is None


def test_closed():
    page = FakePage(closed_after=3)
    out = semi_auto.await_human_publish(page, platform="douyin", is_published=lambda p: False,
                                        toast_selectors=(".toast",))
    assert out == "closed"


def test_closed_via_exception():
    page = FakePage(raise_on_locator=RuntimeError("Target page, context or browser has been closed"))
    out = semi_auto.await_human_publish(page, platform="douyin", is_published=lambda p: False,
                                        toast_selectors=(".toast",))
    assert out == "closed"


def test_timeout(tmp_path):
    out = semi_auto.await_human_publish(FakePage(), platform="douyin", is_published=lambda p: False,
                                        toast_selectors=(".toast",), timeout_s=10, poll_s=2.0,
                                        status_file=str(tmp_path / "s.json"))
    assert out == "timeout"
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["state"] == "error"


def test_transient_errors_are_ignored():
    calls = {"n": 0}

    def pub(p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Execution context was destroyed, most likely because of a navigation")
        return True
    out = semi_auto.await_human_publish(FakePage(), platform="douyin", is_published=pub, toast_selectors=())
    assert out == "published" and calls["n"] == 2


def test_exit_net_turns_pending_status_into_error(tmp_path):
    """进程退出时状态文件仍停在 verifying / awaiting_user_click → 补写 error；已终态的不动。"""
    import login_state
    sf = tmp_path / "s.json"
    login_state.write_status(str(sf), "verifying", "已检测到发布，正在核对…")
    semi_auto.note_exit_reason("读回未见本次内容")
    assert semi_auto.mark_error_if_pending(str(sf)) is True
    d = json.loads(sf.read_text(encoding="utf-8"))
    assert d["state"] == "error" and "读回" in d["message"]
    login_state.write_status(str(sf), "success", "ok")
    assert semi_auto.mark_error_if_pending(str(sf)) is False
    assert json.loads(sf.read_text(encoding="utf-8"))["state"] == "success"


def test_default_toast_selectors_are_toast_only():
    sels = " ".join(semi_auto.DEFAULT_TOAST_SELECTORS)
    for broad in ("notice", "tips", "message-box", "Modal", "dialog"):
        assert broad not in sels
    assert "[role=alert]" in semi_auto.DEFAULT_TOAST_SELECTORS


def test_platform_toast_selectors_not_broad():
    import douyin_publish, web_publisher, xhs_publish, zhihu_answer
    allsel = (list(douyin_publish.TOAST_SELECTORS) + list(web_publisher._TOAST_SELECTORS)
              + list(xhs_publish.XHS_TOAST_SELECTORS) + list(zhihu_answer.ZHIHU_TOAST_SELECTORS))
    for sel in allsel:
        for broad in ("Modal", "dialog", "tips", "[class*=message]", "notice", "message-box"):
            assert broad not in sel, sel
