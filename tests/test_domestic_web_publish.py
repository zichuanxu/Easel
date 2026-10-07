"""web_publisher（视频号/快手/知乎文章）与 zhihu_answer 的闸门 + 半自动回归。全程用假 page/假 Playwright，
不开真实浏览器、不连任何平台。"""
from __future__ import annotations

import contextlib
import json
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import publish_guard  # noqa: E402
import real_browser  # noqa: E402
import semi_auto  # noqa: E402
import web_publisher as wp  # noqa: E402
import zhihu_answer as za  # noqa: E402


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_guard, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(publish_guard, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(publish_guard, "PUBLISH_LOG_PATH", tmp_path / "publish-log.json")
    monkeypatch.setattr("calendar_ops.record_publish", lambda *a, **k: None)   # 不写真实内容日历 / publish-log
    monkeypatch.delenv(semi_auto.AUTO_PUBLISH_ENV, raising=False)
    monkeypatch.setattr(wp, "_LOGIN_DUMP_DIR", tmp_path / "_login_dump")   # 失败截图不许写进仓库 outputs/


# ── 假浏览器 ────────────────────────────────────────────────────────────


class FakeEl:
    def __init__(self, page, name):
        self.page, self.name = page, name

    def is_visible(self):
        return True

    def evaluate(self, *_a, **_k):
        return False

    def scroll_into_view_if_needed(self):
        pass


class FakePage:
    def __init__(self, url="https://zhuanlan.zhihu.com/write"):
        self.url = url
        self.clicks: list[str] = []
        self.keyboard = types.SimpleNamespace(press=lambda *_a: None, type=lambda *_a, **_k: None,
                                              insert_text=lambda *_a: None)

    def goto(self, *_a, **_k):
        pass

    def wait_for_timeout(self, _ms):
        pass

    def query_selector(self, sel):
        return FakeEl(self, sel)

    def inner_text(self, *_a):
        return ""

    def screenshot(self, **_k):
        pass


class FakeCtx:
    def __init__(self, page):
        self.pages = [page]
        self.closed = False

    def new_page(self):
        return self.pages[0]

    def close(self):
        self.closed = True


def _fake_playwright(monkeypatch, ctx):
    @contextlib.contextmanager
    def sync_playwright():
        yield types.SimpleNamespace()

    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = sync_playwright
    mod.TimeoutError = type("TimeoutError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    monkeypatch.setattr(wp, "_launch", lambda *_a, **_k: ctx)
    monkeypatch.setattr(wp, "_settle_login", lambda *_a, **_k: None)
    monkeypatch.setattr(wp, "_is_logged_in", lambda *_a, **_k: True)
    monkeypatch.setattr(wp.human_pace, "pause_before_commit", lambda *_a, **_k: None)


def _args(tmp_path, **kw):
    media = tmp_path / "v.mp4"
    media.write_bytes(b"video")
    d = dict(platform="zhihu", media=str(media), title="一篇文章", desc="正文", tags="", cover=None,
             profile_base=str(tmp_path / "prof"), exec=True, allow_unsafe=False, headed=True, keep_open=False,
             allow_repost=False, handoff_timeout=5, status_file=None, ai_declare=True)
    d.update(kw)
    return types.SimpleNamespace(**d)


@pytest.fixture
def two_step_zhihu(monkeypatch):
    """把知乎文章流程缩成「等一下 → 提交(commit)」两步，便于断言有没有点提交。"""
    monkeypatch.setitem(wp.PLATFORMS["zhihu"], "steps", [
        {"action": "wait", "value": "1"},
        {"action": "click", "selector": "button:text-is('发布')", "commit": True},
    ])


# ── 闸门 ────────────────────────────────────────────────────────────────


def test_cmd_publish_duplicate_blocked_before_browser(tmp_path, monkeypatch):
    a = _args(tmp_path)
    publish_guard.record_publish("zhihu", [a.media], a.title)
    monkeypatch.setattr(wp, "_run_browser", lambda *_a, **_k: pytest.fail("重复发布不许起浏览器"))
    with pytest.raises(SystemExit) as e:
        wp.cmd_publish(a)
    assert e.value.code == publish_guard.EXIT_DUPLICATE


def test_cmd_publish_allow_repost_passes_duplicate_but_not_cooldown(tmp_path, monkeypatch):
    a = _args(tmp_path, allow_repost=True)
    publish_guard.record_publish("zhihu", [a.media], a.title)
    monkeypatch.setattr(wp, "_run_browser", lambda *_a, **_k: 0)
    assert wp.cmd_publish(a) == 0
    publish_guard.set_cooldown("zhihu", "测试")
    with pytest.raises(SystemExit) as e:
        wp.cmd_publish(a)
    assert e.value.code == publish_guard.EXIT_COOLDOWN


def test_cmd_publish_dry_run_skips_guard(tmp_path, monkeypatch):
    a = _args(tmp_path, exec=False)
    publish_guard.set_cooldown("zhihu", "测试")
    monkeypatch.setattr(wp, "cmd_plan", lambda _a: 0)
    assert wp.cmd_publish(a) == 0


# ── 浏览器引擎 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("platform,prefix,profile", [
    ("weixin-channels", "CHANNELS", "ChannelsProfile"),
    ("kuaishou", "KUAISHOU", "KuaishouProfile"),
    ("zhihu", "ZHIHU", "ZhihuProfile"),
])
def test_launch_uses_real_browser_with_platform_env_and_profile(tmp_path, monkeypatch, platform, prefix, profile):
    seen = {}
    monkeypatch.setattr(real_browser, "launch", lambda p, **kw: seen.update(kw) or "ctx")
    assert wp._launch(object(), platform, str(tmp_path)) == "ctx"
    assert seen["browser_env"] == f"EASEL_{prefix}_BROWSER"
    assert seen["headless_env"] == f"EASEL_{prefix}_HEADLESS"
    assert seen["profile_dir"] == tmp_path / profile
    assert seen["headed"] is True


def test_zhihu_answer_launch_shares_zhihu_profile(monkeypatch):
    seen = {}
    monkeypatch.setattr(real_browser, "launch", lambda p, **kw: seen.update(kw) or "ctx")
    assert za._launch(object()) == "ctx"
    assert seen["profile_dir"].name == "ZhihuProfile"
    assert seen["browser_env"] == "EASEL_ZHIHU_BROWSER" and seen["headless_env"] == "EASEL_ZHIHU_HEADLESS"


# ── 半自动：web_publisher ───────────────────────────────────────────────


def test_semi_mode_never_clicks_commit_and_records_on_publish(tmp_path, monkeypatch, two_step_zhihu):
    page = FakePage()
    ctx = FakeCtx(page)
    _fake_playwright(monkeypatch, ctx)
    clicked = []
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: clicked.append(1))
    seen = {}

    def fake_await(pg, **kw):
        seen.update(kw)
        pg.url = "https://zhuanlan.zhihu.com/p/12345"   # 用户点了发布 → 跳文章页
        assert kw["is_published"](pg)
        return "published"

    monkeypatch.setattr(semi_auto, "await_human_publish", fake_await)
    a = _args(tmp_path)
    assert wp._run_browser(a, headed=True, do_publish=True) == 0
    assert clicked == []                       # 脚本一次都没点提交
    assert seen["platform"] == "zhihu"
    assert publish_guard.find_duplicate("zhihu", [a.media], a.title)   # 成功后记账
    assert ctx.closed


@pytest.mark.parametrize("outcome,code", [("blocked", publish_guard.EXIT_COOLDOWN), ("closed", 1), ("timeout", 1)])
def test_semi_other_outcomes_exit_without_record(tmp_path, monkeypatch, two_step_zhihu, outcome, code):
    _fake_playwright(monkeypatch, FakeCtx(FakePage()))
    monkeypatch.setattr(semi_auto, "await_human_publish", lambda *_a, **_k: outcome)
    a = _args(tmp_path)
    with pytest.raises(SystemExit) as e:
        wp._run_browser(a, headed=True, do_publish=True)
    assert e.value.code == code
    assert publish_guard.find_duplicate("zhihu", [a.media], a.title) is None


def test_semi_ai_reminder_in_status_file(tmp_path, monkeypatch, two_step_zhihu):
    _fake_playwright(monkeypatch, FakeCtx(FakePage()))

    sf = tmp_path / "s.json"
    awaiting = {}

    def fake_await(pg, **kw):
        kw["on_status"]("awaiting_user_click", semi_auto.AWAITING_MESSAGE)
        awaiting.update(json.loads(sf.read_text(encoding="utf-8")))   # 交接时刻的状态文件
        pg.url = "https://zhuanlan.zhihu.com/p/9"
        return "published"

    monkeypatch.setattr(semi_auto, "await_human_publish", fake_await)
    wp._run_browser(_args(tmp_path, status_file=str(sf)), headed=True, do_publish=True)
    assert awaiting["state"] == "awaiting_user_click" and "AI" in awaiting["message"]


# ── 自动逃生口：只点一次 + 处罚提示 exit 9 ───────────────────────────────


def test_auto_mode_clicks_once_and_exit_9_on_block_toast(tmp_path, monkeypatch, two_step_zhihu):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    page = FakePage()
    _fake_playwright(monkeypatch, FakeCtx(page))
    clicked = []
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: clicked.append(1))
    monkeypatch.setattr(semi_auto, "_toast_texts", lambda *_a: ["你的发布功能已被限制"])
    a = _args(tmp_path)
    with pytest.raises(SystemExit) as e:
        wp._run_browser(a, headed=True, do_publish=True)
    assert e.value.code == publish_guard.EXIT_COOLDOWN
    assert clicked == [1]                      # 点了一次，没有重试
    assert publish_guard.active_cooldown("zhihu")


def test_auto_mode_success_records(tmp_path, monkeypatch, two_step_zhihu):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    page = FakePage()
    _fake_playwright(monkeypatch, FakeCtx(page))
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: setattr(page, "url", "https://zhuanlan.zhihu.com/p/1"))
    monkeypatch.setattr(semi_auto, "_toast_texts", lambda *_a: [])
    a = _args(tmp_path)
    assert wp._run_browser(a, headed=True, do_publish=True) == 0
    assert publish_guard.find_duplicate("zhihu", [a.media], a.title)


def test_commit_click_has_no_fallback_retry(monkeypatch):
    """提交按钮被挡住点不了时直接抛错，不退回原生 click 补点。"""
    page = FakePage()
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("被挡住")))
    el = types.SimpleNamespace(click=lambda *_a, **_k: pytest.fail("提交按钮不许退回原生点击"))
    with pytest.raises(RuntimeError):
        wp._human_click(page, el, strict=True)
    clicks = []
    el2 = types.SimpleNamespace(click=lambda *_a, **_k: clicks.append(1))
    wp._human_click(page, el2)   # 非提交按钮才允许退回
    assert clicks == [1]


def test_commit_steps_marked_for_every_publish_flow():
    for key in ("kuaishou", "weixin-channels", "zhihu"):
        cfg = wp.PLATFORMS[key]
        flows = [cfg["steps"]] + ([cfg["steps_image"]] if cfg.get("steps_image") else [])
        for steps in flows:
            assert any(st.get("commit") for st in steps), f"{key} 缺 commit 标记"


def test_weixin_semi_stops_before_enter(monkeypatch):
    """视频号专用流程：半自动填完描述就返回，不聚焦/按 Enter 提交。"""
    pressed = []

    class Frame:
        url = "https://channels.weixin.qq.com/micro/content/post/create"

        def evaluate(self, js, *a):
            if "Enter" in js or "focus()" in js and "发表" in js:
                pytest.fail("半自动不许聚焦发表按钮")
            return True

    class Page(FakePage):
        frames = [Frame()]
        keyboard = types.SimpleNamespace(press=lambda k: pressed.append(k))

        def wait_for_selector(self, *_a, **_k):
            pass

        def wait_for_url(self, *_a, **_k):
            pass

        def set_input_files(self, *_a, **_k):
            pass

        def locator(self, _s):
            return types.SimpleNamespace(count=lambda: 1, nth=lambda _i: FakeEl(None, "x"))

    monkeypatch.setattr(wp, "_settle_login", lambda *_a, **_k: None)
    monkeypatch.setattr(wp, "_is_logged_in", lambda *_a, **_k: True)
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: None)
    wp._publish_weixin_channels(Page(url="https://channels.weixin.qq.com/platform/post/list"),
                                {"media": "/x.mp4", "title": "t", "desc": "d", "tags": ""}, semi=True)
    assert pressed == []


# ── zhihu_answer ────────────────────────────────────────────────────────


def test_question_key_same_question_same_key():
    k = za.question_key("https://www.zhihu.com/question/123456")
    assert k == za.question_key("https://www.zhihu.com/question/123456/answer/777?x=1")
    assert k != za.question_key("https://www.zhihu.com/question/654321")


def test_zhihu_answer_published_detection():
    base = "https://www.zhihu.com/question/1"
    page = FakePage(url=base)
    assert not _zh_published(page, base, [])
    page.url = base + "/answer/99"
    assert _zh_published(page, base, [])
    page.url = base
    assert _zh_published(page, base, ["发布成功"])


def _zh_published(page, base, toasts):
    orig = semi_auto._toast_texts
    semi_auto._toast_texts = lambda *_a: toasts
    try:
        return za._answer_published(page, base)
    finally:
        semi_auto._toast_texts = orig


class ZhPage(FakePage):
    def query_selector(self, sel):
        if "SignContainer" in sel:
            return None
        return types.SimpleNamespace(inner_text=lambda: "问题标题")


def _zh_run(monkeypatch, outcome, tmp_path, **kw):
    ctx = FakeCtx(ZhPage(url="https://www.zhihu.com/question/42"))
    mod = types.ModuleType("playwright.sync_api")

    @contextlib.contextmanager
    def sync_playwright():
        yield types.SimpleNamespace()

    mod.sync_playwright = sync_playwright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    monkeypatch.setattr(za, "_launch", lambda *_a, **_k: ctx)
    monkeypatch.setattr(za, "type_into_editor", lambda *_a, **_k: True)
    monkeypatch.setattr(za, "_click_publish_btn", lambda *_a: pytest.fail("半自动不许点发布回答"))
    monkeypatch.setattr(semi_auto, "await_human_publish", lambda *_a, **_k: outcome)
    f = tmp_path / "a.md"
    f.write_text("回答正文", encoding="utf-8")
    res = za.publish_answer("https://www.zhihu.com/question/42", "回答正文", dry_run=False,
                            content_path=f, **kw)
    return res, ctx, f


def test_zhihu_answer_semi_published_records(monkeypatch, tmp_path):
    res, ctx, f = _zh_run(monkeypatch, "published", tmp_path)
    assert res["success"] and ctx.closed
    assert publish_guard.find_duplicate("zhihu", [], za.question_key("https://www.zhihu.com/question/42"))


@pytest.mark.parametrize("outcome", ["closed", "timeout"])
def test_zhihu_answer_semi_not_published(monkeypatch, tmp_path, outcome):
    res, ctx, _ = _zh_run(monkeypatch, outcome, tmp_path)
    assert not res["success"] and "未发布" in res["error"]
    assert publish_guard.find_duplicate("zhihu", [], za.question_key("https://www.zhihu.com/question/42")) is None


def test_zhihu_answer_semi_blocked_exits_9(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as e:
        _zh_run(monkeypatch, "blocked", tmp_path)
    assert e.value.code == publish_guard.EXIT_COOLDOWN


def test_zhihu_answer_main_guard_same_question_twice(monkeypatch, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("回答正文", encoding="utf-8")
    publish_guard.record_publish("zhihu", [], za.question_key("https://www.zhihu.com/question/42"))
    monkeypatch.setattr(za, "publish_answer", lambda *_a, **_k: pytest.fail("重复回答不许起浏览器"))
    monkeypatch.setattr(sys, "argv", ["zhihu_answer.py", "--question", "https://www.zhihu.com/question/42",
                                      "--content-file", str(f), "--exec"])
    with pytest.raises(SystemExit) as e:
        za.main()
    assert e.value.code == publish_guard.EXIT_DUPLICATE


# ── 审查修复：verifying 非终态 / 失败路径写 error / 未确认记账 / 冷却 ───────────


def _status(sf):
    return json.loads(Path(sf).read_text(encoding="utf-8"))


@pytest.fixture
def readback_zhihu(monkeypatch, two_step_zhihu):
    monkeypatch.setitem(wp.PLATFORMS["zhihu"], "readback", True)
    monkeypatch.setitem(wp._READBACK_VERIFIERS, "zhihu", ("platform_readback", "verify_x"))


def _semi_published(monkeypatch, tmp_path, sf):
    """半自动交接桩：像真的 await_human_publish 一样把状态文件写成 verifying 再返回 published。"""
    import login_state

    def fake(pg, **kw):
        login_state.write_status(str(sf), "verifying", semi_auto.VERIFYING_MESSAGE)
        return "published"
    monkeypatch.setattr(semi_auto, "await_human_publish", fake)


def test_semi_readback_unverified_writes_error_not_success(tmp_path, monkeypatch, readback_zhihu):
    import platform_readback
    _fake_playwright(monkeypatch, FakeCtx(FakePage()))
    sf = tmp_path / "s.json"
    _semi_published(monkeypatch, tmp_path, sf)
    monkeypatch.setattr(wp, "_readback_verify", lambda *a, **k: platform_readback.ReadbackResult(
        outcome="unverified", error="列表里没有本次内容"))
    a = _args(tmp_path, status_file=str(sf), handoff_timeout=5)
    with pytest.raises(SystemExit) as e:
        wp._run_browser(a, headed=True, do_publish=True)
    assert e.value.code == 5
    st = _status(sf)
    assert st["state"] == "error" and "读回未核实" in st["message"]    # 绝不是 success / verifying
    row = publish_guard.find_duplicate("zhihu", [a.media], a.title)
    assert row                                                      # 用户已点过发布：记 unconfirmed 防二发
    assert json.loads(publish_guard.ledger_path().read_text(encoding="utf-8").splitlines()[-1])["unconfirmed"] is True


def test_semi_readback_verified_writes_success_only_after_verify(tmp_path, monkeypatch, readback_zhihu):
    import platform_readback
    _fake_playwright(monkeypatch, FakeCtx(FakePage()))
    sf = tmp_path / "s.json"
    _semi_published(monkeypatch, tmp_path, sf)
    seen = []
    item = types.SimpleNamespace(platform_content_id="9", status="published")

    def verify(*a, **k):
        seen.append(_status(sf)["state"])
        return platform_readback.ReadbackResult(outcome="verified", matched=item, evidence={})
    monkeypatch.setattr(wp, "_readback_verify", verify)
    assert wp._run_browser(_args(tmp_path, status_file=str(sf)), headed=True, do_publish=True) == 0
    assert seen == ["verifying"]            # 核对期间是非终态
    assert _status(sf)["state"] == "success"


def test_die_writes_error_status_when_status_file_in_use(tmp_path, monkeypatch):
    sf = tmp_path / "s.json"
    monkeypatch.setattr(wp, "_ACTIVE_PUBLISH_STATUS_FILE", str(sf))
    with pytest.raises(SystemExit):
        wp._die("kuaishou 读回未确认", 5)
    assert _status(sf)["state"] == "error" and "读回未确认" in _status(sf)["message"]


def test_auto_unconfirmed_still_records_ledger(tmp_path, monkeypatch, two_step_zhihu):
    """自动逃生口：发布键点了但 URL 没变（未确认）→ 退出前记 unconfirmed 账，重复闸门挡二发。"""
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    monkeypatch.setitem(wp.PLATFORMS["zhihu"], "publish_success", {"url_contains": "/p/"})
    page = FakePage()
    _fake_playwright(monkeypatch, FakeCtx(page))
    monkeypatch.setattr(wp.human_input, "click", lambda *_a, **_k: None)
    monkeypatch.setattr(semi_auto, "_toast_texts", lambda *_a: [])
    monkeypatch.setattr(wp.time, "time", iter(range(0, 10_000, 20)).__next__)   # 让 30s 等待立刻超时
    a = _args(tmp_path)
    with pytest.raises(SystemExit) as e:
        wp._run_browser(a, headed=True, do_publish=True)
    assert e.value.code == 5
    last = json.loads(publish_guard.ledger_path().read_text(encoding="utf-8").splitlines()[-1])
    assert last["unconfirmed"] is True and last["url"] == ""
    with pytest.raises(SystemExit) as e2:
        publish_guard.guard_before_publish("zhihu", [a.media], a.title)
    assert e2.value.code == publish_guard.EXIT_DUPLICATE


def test_whoami_blocked_in_cooldown_without_browser(tmp_path, monkeypatch, capsys):
    publish_guard.set_cooldown("zhihu", "测试冷却")
    monkeypatch.setattr(wp, "_launch", lambda *_a, **_k: pytest.fail("冷却期不许起浏览器"))
    with pytest.raises(SystemExit) as e:
        wp.cmd_whoami(types.SimpleNamespace(platform="zhihu", profile_base=str(tmp_path)))
    assert e.value.code == publish_guard.EXIT_COOLDOWN
    out = capsys.readouterr()
    assert json.loads(out.out.strip().splitlines()[-1])["loggedIn"] is False and "冷却" in out.err


def test_login_in_cooldown_only_warns(tmp_path, monkeypatch, capsys):
    publish_guard.set_cooldown("zhihu", "测试冷却")
    monkeypatch.setattr(wp, "_run_browser", lambda *_a, **_k: 0)
    assert wp.cmd_login(types.SimpleNamespace(platform="zhihu")) == 0
    assert "冷却期" in capsys.readouterr().err


def test_zhihu_dry_run_never_launches_browser_and_shows_cooldown(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)           # 真去 import playwright 会 ImportError
    monkeypatch.setattr(za, "_launch", lambda *_a, **_k: pytest.fail("dry-run 不许起浏览器"))
    publish_guard.set_cooldown("zhihu", "测试冷却")
    res = za.publish_answer("https://www.zhihu.com/question/42", "回答正文", dry_run=True)
    assert res["success"] and res["dry_run"]
    err = capsys.readouterr().err
    assert "DRY-RUN" in err and "冷却期" in err


def test_zhihu_semi_success_status_after_verification(monkeypatch, tmp_path):
    sf = tmp_path / "s.json"
    import login_state
    login_state.write_status(str(sf), "verifying", semi_auto.VERIFYING_MESSAGE)
    res, _ctx, _f = _zh_run(monkeypatch, "published", tmp_path, status_file=str(sf))
    assert res["success"] and _status(sf)["state"] == "success"


def test_zhihu_main_failure_writes_error_status(monkeypatch, tmp_path):
    import login_state
    f = tmp_path / "a.md"
    f.write_text("回答正文", encoding="utf-8")
    sf = tmp_path / "s.json"
    login_state.write_status(str(sf), "verifying", semi_auto.VERIFYING_MESSAGE)
    monkeypatch.setattr(za, "publish_answer", lambda *_a, **_k: {"success": False, "error": "未确认", "url": ""})
    monkeypatch.setattr(sys, "argv", ["zhihu_answer.py", "--question", "https://www.zhihu.com/question/43",
                                      "--content-file", str(f), "--exec", "--status-file", str(sf)])
    with pytest.raises(SystemExit) as e:
        za.main()
    assert e.value.code == 1
    assert _status(sf)["state"] == "error" and "未确认" in _status(sf)["message"]


def test_zhihu_auto_unconfirmed_records_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    ctx = FakeCtx(ZhPage(url="https://www.zhihu.com/question/44"))
    mod = types.ModuleType("playwright.sync_api")

    @contextlib.contextmanager
    def sync_playwright():
        yield types.SimpleNamespace()
    mod.sync_playwright = sync_playwright
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    monkeypatch.setattr(za, "_launch", lambda *_a, **_k: ctx)
    monkeypatch.setattr(za, "type_into_editor", lambda *_a, **_k: True)
    monkeypatch.setattr(za, "_click_publish_btn", lambda *_a: True)
    monkeypatch.setattr(semi_auto, "_toast_texts", lambda *_a: [])
    f = tmp_path / "a.md"
    f.write_text("回答正文", encoding="utf-8")
    res = za.publish_answer("https://www.zhihu.com/question/44", "回答正文", dry_run=False, content_path=f)
    assert not res["success"] and "未确认" in res["error"]
    last = json.loads(publish_guard.ledger_path().read_text(encoding="utf-8").splitlines()[-1])
    assert last["unconfirmed"] is True and last["platform"] == "zhihu"
