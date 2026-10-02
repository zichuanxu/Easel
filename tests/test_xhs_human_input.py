"""小红书「像人一样操作」与频率闸门的回归测试（不起真浏览器、不连小红书）。

2026-10 账号被判「第三方脚本 / AI 托管发文」封 30 天。改法：本机 Chrome 窗口 + 曲线移动鼠标点击、
按词组输入（human_input.py）+ 发帖/回复/评论频率闸门 + 勾「笔记含AI合成内容」声明（勾不上不发）。
"""
from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import human_input  # noqa: E402
import xhs_comment  # noqa: E402
import xhs_publish as xhs  # noqa: E402


class FakeMouse:
    def __init__(self, log):
        self.log = log

    def move(self, x, y):
        self.log.append(("move", x, y))

    def down(self):
        self.log.append(("down",))

    def up(self):
        self.log.append(("up",))

    def wheel(self, dx, dy):
        self.log.append(("wheel", dy))


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def type(self, s):
        self.log.append(("type", s))

    def insert_text(self, s):
        self.log.append(("insert", s))

    def press(self, k):
        self.log.append(("press", k))


class FakePage:
    def __init__(self, w=1200, h=800):
        self.log: list = []
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)
        self.viewport_size = None
        self.size = (w, h)
        self.waited = []

    def evaluate(self, _js, *_a):
        return list(self.size)

    def wait_for_timeout(self, ms):
        self.waited.append(ms)


class FakeEl:
    """一个元素；页面被滚轮往下滚时，它在窗口里的 y 跟着往上走。"""

    def __init__(self, page, x, y, w=100, h=30, scrolls=True, covered_below=None):
        self.page, self.x, self.y, self.w, self.h, self.scrolls = page, x, y, w, h, scrolls
        self.covered_below = covered_below   # 窗口里这个 y 以下被吸底栏盖住
        self.probes: list = []

    def evaluate(self, _js, point):
        self.probes.append(point)
        return self.covered_below is None or point[1] < self.covered_below

    def bounding_box(self):
        dy = sum(e[1] for e in self.page.log if e[0] == "wheel") if self.scrolls else 0
        return {"x": self.x, "y": self.y - dy, "width": self.w, "height": self.h}

    def scroll_into_view_if_needed(self):
        self.page.log.append(("scroll_into_view",))
        if not self.scrolls:
            self.y = 300            # 内层滚动区被 JS 滚到了窗口里


@pytest.fixture(autouse=True)
def seeded():
    human_input.rng.seed(7)


# ── 鼠标轨迹 / 输入节奏 ─────────────────────────────────────────────────


@pytest.mark.parametrize("dst", [(10, 10), (900, 650), (400.5, 300.25), (101, 100)])
def test_curve_ends_exactly_on_target(dst):
    pts = human_input.curve(100, 100, *dst)
    assert pts[-1] == dst
    assert 1 <= len(pts) <= 45
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in pts)


def test_curve_bends_off_the_straight_line():
    pts = human_input.curve(0, 0, 1000, 0)
    assert max(abs(y) for _x, y in pts) > 20       # 不是直线瞬移


def test_click_moves_along_path_then_presses_inside_box():
    page = FakePage()
    el = FakeEl(page, 300, 200)
    human_input.click(page, el)
    kinds = [e[0] for e in page.log]
    assert kinds.count("move") >= 8
    assert kinds[-2:] == ["down", "up"]
    _, x, y = [e for e in page.log if e[0] == "move"][-1]
    assert 300 <= x <= 400 and 200 <= y <= 230


def test_click_x_frac_targets_right_side_of_wide_bar():
    page = FakePage()
    human_input.click(page, FakeEl(page, 0, 300, w=1000, h=40), x_frac=0.62)
    _, x, _y = [e for e in page.log if e[0] == "move"][-1]
    assert 600 <= x <= 640


def test_offscreen_element_is_scrolled_in_with_the_wheel():
    page = FakePage(h=800)
    el = FakeEl(page, 100, 2500)
    human_input.click(page, el)
    assert any(e[0] == "wheel" for e in page.log)
    assert not any(e[0] == "scroll_into_view" for e in page.log)
    box = el.bounding_box()
    assert 0 <= box["y"] <= 800


def test_tall_element_click_lands_in_visible_part_and_not_on_sticky_bar():
    """正文框比窗口还高、底部被吸底发布栏盖住：点击要落在露出来且没被盖住的那段里。"""
    page = FakePage(h=800)
    el = FakeEl(page, 100, 300, w=600, h=2000, covered_below=720)
    for _ in range(20):
        human_input.click(page, el)
        _, x, y = [e for e in page.log if e[0] == "move"][-1]
        assert 8 <= y < 720


def test_fully_covered_element_is_not_clicked():
    page = FakePage(h=800)
    el = FakeEl(page, 100, 300, covered_below=0)
    with pytest.raises(RuntimeError):
        human_input.click(page, el)
    assert ("down",) not in page.log


def test_zero_size_element_is_not_clicked():
    page = FakePage()
    el = FakeEl(page, 100, 300, w=0, h=0)
    with pytest.raises(RuntimeError):
        human_input.click(page, el)
    assert ("down",) not in page.log


def test_element_in_inner_scroller_falls_back_to_scroll_into_view():
    page = FakePage(h=800)
    human_input.click(page, FakeEl(page, 100, 2500, scrolls=False))
    assert ("scroll_into_view",) in page.log
    assert page.log[-1] == ("up",)


def test_element_that_stays_offscreen_is_not_clicked():
    page = FakePage(h=800)
    el = FakeEl(page, 100, 2500, scrolls=False)
    el.scroll_into_view_if_needed = lambda: None
    with pytest.raises(RuntimeError):
        human_input.click(page, el)
    assert ("down",) not in page.log


@pytest.mark.parametrize("text", ["", "abc 123", "你好世界，今天去露营。\n第二行\n\nEnd!", "混合Mix中文ABC😀"])
def test_chunks_roundtrip(text):
    parts = human_input.chunks(text)
    assert "".join(parts) == text
    for p in parts:
        if p == "\n" or ord(p[0]) < 128:
            assert len(p) == 1
        else:
            assert 1 <= len(p) <= 4 and "\n" not in p


def test_type_text_uses_enter_for_newlines_and_insert_for_cjk():
    page = FakePage()
    human_input.type_text(page, "露营攻略\nok")
    typed = "".join(e[1] if e[0] in ("type", "insert") else "\n" for e in page.log
                    if e[0] in ("type", "insert", "press"))
    assert typed == "露营攻略\nok"
    assert ("press", "Enter") in page.log
    assert all(len(e[1]) == 1 for e in page.log if e[0] == "type")


# ── 频率闸门 ────────────────────────────────────────────────────────


@pytest.fixture
def base(tmp_path, monkeypatch):
    for k in ("EASEL_XHS_MIN_GAP_MIN", "EASEL_XHS_DAILY_MAX", "EASEL_XHS_REPLY_DAILY_MAX",
              "EASEL_XHS_COMMENT_GAP_MIN", "EASEL_XHS_COMMENT_DAILY_MAX"):
        monkeypatch.delenv(k, raising=False)
    return str(tmp_path / "profiles")


def test_publish_gap_and_daily_cap(base):
    t0 = 1_000_000.0
    assert xhs.activity_budget(base, "publish", now=t0)[0] == 3
    xhs.record_activity(base, "publish", now=t0)
    left, why = xhs.activity_budget(base, "publish", now=t0 + 30 * 60)
    assert left == 0 and "60 分钟" in why
    assert xhs.activity_budget(base, "publish", now=t0 + 61 * 60)[0] == 2
    xhs.record_activity(base, "publish", now=t0 + 2 * 3600)
    xhs.record_activity(base, "publish", now=t0 + 4 * 3600)
    left, why = xhs.activity_budget(base, "publish", now=t0 + 6 * 3600)
    assert left == 0 and "上限 3" in why
    assert xhs.activity_budget(base, "publish", now=t0 + 24 * 3600 + 1)[0] == 1   # 第一条滚出 24 小时


def test_activity_env_override_and_bad_values(base, monkeypatch):
    monkeypatch.setenv("EASEL_XHS_MIN_GAP_MIN", "0")
    monkeypatch.setenv("EASEL_XHS_DAILY_MAX", "abc")          # 写错了按默认
    xhs.record_activity(base, "publish", now=100.0)
    assert xhs.activity_budget(base, "publish", now=101.0)[0] == 2


def test_activity_file_is_per_account_and_pruned(base):
    xhs.record_activity(base, "reply", now=0.0)
    xhs.record_activity(base, "reply", now=2 * xhs.DAY_S)
    d = json.loads((Path(base) / xhs.PROFILE_NAME / xhs.ACTIVITY_FILE).read_text(encoding="utf-8"))
    assert d == {"reply": [2 * xhs.DAY_S]}


def test_corrupt_activity_file_counts_as_empty(base):
    path = Path(base) / xhs.PROFILE_NAME / xhs.ACTIVITY_FILE
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    assert xhs.activity_budget(base, "comment")[0] == 5


def _pub_args(tmp_path, **kw):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    d = dict(title="周末露营", content="正文", images=str(img), video=None, tags="", exec=True,
             allow_unsafe=False, headed=False, keep_open=False, no_ai_declare=False,
             profile_base=str(tmp_path / "profiles"), proxy=None, no_proxy=True)
    d.update(kw)
    return types.SimpleNamespace(**d)


def test_publish_blocked_by_rate_before_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(xhs, "activity_budget", lambda *_a: (0, "太密"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)   # 真走到起浏览器会 ImportError
    with pytest.raises(SystemExit) as e:
        xhs.cmd_publish(_pub_args(tmp_path))
    assert e.value.code == 5


def test_publish_dry_run_reports_rate_and_ai_declare(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(xhs, "activity_budget", lambda *_a: (0, "太密"))
    assert xhs.cmd_publish(_pub_args(tmp_path, exec=False)) == 0
    out = capsys.readouterr().out
    assert "笔记含AI合成内容" in out and "频率闸门" in out


def test_ai_declare_failure_stops_before_publish_click(monkeypatch):
    page = types.SimpleNamespace(query_selector=lambda _s: object(), wait_for_timeout=lambda _ms: None)
    monkeypatch.setattr(xhs, "_human_type", lambda *_a: None)
    monkeypatch.setattr(xhs, "_content_element", lambda _p: object())
    monkeypatch.setattr(xhs, "_input_tags", lambda *_a: None)
    monkeypatch.setattr(xhs.human_input, "click", lambda *_a, **_k: None)
    monkeypatch.setattr(xhs.human_input, "pause", lambda *_a: None)
    monkeypatch.setattr(xhs, "_declare_ai", lambda _p: False)

    def no_publish(*_a, **_k):
        raise AssertionError("AI 声明没勾上，不许去点发布")

    monkeypatch.setattr(xhs, "_wait_publish_clickable", no_publish)
    with pytest.raises(SystemExit) as e:
        xhs._fill_and_submit(page, "标题", "正文", [], declare_ai=True)
    assert e.value.code == 6


# ── 评论：间隔下限 + 闸门 ────────────────────────────────────────────


@pytest.mark.parametrize("gap,lo", [(0, 20.0), (4, 20.0), (60, 60.0)])
def test_comment_gap_has_floor_and_jitter(gap, lo):
    page = FakePage()
    xhs_comment._gap_wait(page, gap)
    assert lo * 1000 <= page.waited[-1] <= lo * 2000


def _reply_args(**kw):
    d = dict(replies_json=json.dumps([{"id": f"c{i}", "nickname": f"n{i}", "reply": "谢谢"} for i in range(3)]),
             replied_file=None, exec=False, allow_unsafe=False, profile_base=None, url=None,
             note_id="n", xsec_token="t", proxy=None, no_proxy=True, headed=False, scroll=1, gap=20.0)
    d.update(kw)
    return types.SimpleNamespace(**d)


def test_reply_dry_run_warns_when_over_budget(monkeypatch, capsys):
    monkeypatch.setattr(xhs_comment.xhs_publish, "activity_budget", lambda *_a: (1, ""))
    assert xhs_comment.cmd_reply(_reply_args()) == 0
    assert "最多回 1 条" in capsys.readouterr().out


def test_reply_exec_blocked_before_browser(monkeypatch):
    monkeypatch.setattr(xhs_comment.xhs_publish, "activity_budget", lambda *_a: (0, "满了"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(SystemExit) as e:
        xhs_comment.cmd_reply(_reply_args(exec=True))
    assert e.value.code == 5


def test_comment_launch_shares_publish_browser(monkeypatch):
    seen = []
    monkeypatch.setattr(xhs, "_launch", lambda *a: seen.append(a) or "ctx")
    assert xhs_comment._launch("p", False, None, None) == "ctx"
    assert seen == [("p", False, None, None)]


def test_ai_declared_check_fails_closed():
    def boom(*_a):
        raise RuntimeError("page gone")
    assert xhs._ai_declared(types.SimpleNamespace(evaluate=boom)) is False


def test_one_bad_reply_does_not_abort_batch(capsys):
    def bad(*_a):
        raise RuntimeError("元素被别的东西挡住了")
    assert xhs_comment._safe(bad, "page", "n", "r") is False
    assert "跳过" in capsys.readouterr().err
