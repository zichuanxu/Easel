"""douyin_publish：半自动发布的回归测试（假 playwright / 假 page，绝不碰真实抖音）。

钉住的契约：
- 浏览器走 real_browser.launch（EASEL_DOUYIN_BROWSER / EASEL_DOUYIN_HEADLESS），发布一律开窗口；
- 真发前过 publish_guard（冷却 → 9，重复 → 8），dry-run 只展示闸门状态；
- 默认半自动：脚本不点发布，await_human_publish 交接；published → 读回 → 记台账；blocked → 9；closed/timeout → 5；
- 自动点击逃生口（EASEL_DOMESTIC_AUTO_PUBLISH=1）：只点一次；AI 声明勾不上 → 6；toast 命中处罚 → 冷却 + 9。
"""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"))

import douyin_publish as dy
import platform_readback
import publish_guard as pg
import real_browser
import semi_auto


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER_PATH", tmp_path / "_publish" / "ledger.jsonl")
    monkeypatch.setattr(pg, "COOLDOWN_PATH", tmp_path / "_publish" / "cooldown.json")
    monkeypatch.setattr(pg, "PUBLISH_LOG_PATH", tmp_path / "_analytics" / "publish-log.json")
    monkeypatch.setattr("calendar_ops.record_publish", lambda *a, **k: None)   # 不写真实内容日历 / publish-log
    monkeypatch.delenv(semi_auto.AUTO_PUBLISH_ENV, raising=False)
    monkeypatch.setattr(dy, "DEFAULT_QR_OUT", tmp_path / "_login" / "douyin.png")   # 失败现场 dump 不写进仓库 outputs/
    return tmp_path


# ---------------- 假浏览器 ----------------
class FakePage:
    def __init__(self, toasts=None):
        self.url = "https://creator.douyin.com/creator-micro/content/post/video"
        self.toasts = toasts or []

    def set_default_timeout(self, *_a):
        pass

    def goto(self, *_a, **_k):
        pass

    def wait_for_timeout(self, *_a):
        pass

    def is_closed(self):
        return False

    def locator(self, sel):
        page = self

        class L:
            def all_inner_texts(self_inner):
                return list(page.toasts) if sel == ".semi-toast" else []
        return L()


class FakeCtx:
    def __init__(self, page):
        self.pages = [page]
        self.closed = False

    def close(self):
        self.closed = True


class _PW:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把 _publish 里所有真浏览器步骤换成桩，返回记录调用的 dict。"""
    rec = {"clicks": 0, "launch": [], "page": FakePage()}
    fake_sync = types.ModuleType("playwright.sync_api")
    fake_sync.sync_playwright = lambda: _PW()
    fake_sync.TimeoutError = type("PWTimeout", (Exception,), {})
    fake_sync.Error = type("PWError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync)

    def fake_launch(p, headed, base, proxy):
        rec["launch"].append(headed)
        rec["ctx"] = FakeCtx(rec["page"])
        return rec["ctx"]

    monkeypatch.setattr(dy, "_launch", fake_launch)
    monkeypatch.setattr(dy, "_wait_ready", lambda page: None)
    monkeypatch.setattr(dy, "_logged_in", lambda page: True)
    monkeypatch.setattr(dy, "_go_upload", lambda page: None)
    monkeypatch.setattr(dy, "_switch_tab", lambda page, kind: None)
    monkeypatch.setattr(dy, "_upload_files", lambda page, paths: None)
    monkeypatch.setattr(dy, "_wait_video_processed", lambda page: None)
    monkeypatch.setattr(dy, "_select_ai_cover", lambda page: None)
    monkeypatch.setattr(dy, "_set_dual_cover", lambda page: None)
    monkeypatch.setattr(dy, "_fill_title_desc", lambda page, t, d, tags: None)
    monkeypatch.setattr(dy.human_pace, "pace", lambda *a, **k: None)
    monkeypatch.setattr(dy, "_verify_wall", lambda page: False)
    monkeypatch.setattr(dy, "_wait_toast", lambda page, timeout_s=20: None)
    monkeypatch.setattr(platform_readback, "capture_douyin_snapshot", lambda page: set())
    item = types.SimpleNamespace(platform_content_id="777", status="published")
    monkeypatch.setattr(platform_readback, "verify_douyin_publish",
                        lambda page, **k: platform_readback.ReadbackResult(
                            outcome="verified", matched=item, evidence={}))
    monkeypatch.setattr(dy, "_declare_ai", lambda page: True)

    def fake_click(page, n=0):
        rec["clicks"] += 1
    monkeypatch.setattr(dy, "_click_publish", fake_click)
    return rec


def _args(tmp_path, **over):
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"video-bytes")
    ns = dict(title="周末露营攻略", content="简介", video=str(vid), images=None, tags="露营",
              exec=True, allow_unsafe=False, headed=False, keep_open=False, sms_code_file=None,
              status_file=str(tmp_path / "st.json"), allow_repost=False, ai_declare=True,
              handoff_timeout=5, profile_base=str(tmp_path / "prof"), proxy=None, no_proxy=True)
    ns.update(over)
    return types.SimpleNamespace(**ns)


def _run(a):
    with pytest.raises(SystemExit) as e:
        dy._publish(a, "video")
    return e.value.code


# ---------------- 浏览器引擎 ----------------
def test_launch_uses_real_browser_with_env_names(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(real_browser, "launch", lambda p, **kw: seen.update(kw) or "ctx")
    assert dy._launch(object(), True, str(tmp_path), None) == "ctx"
    assert seen["headless_env"] == "EASEL_DOUYIN_HEADLESS" and seen["browser_env"] == "EASEL_DOUYIN_BROWSER"
    assert seen["profile_dir"] == tmp_path / "DouyinProfile" and seen["platform_label"] == "抖音"


def test_allow_headless_env(monkeypatch):
    monkeypatch.delenv("EASEL_DOUYIN_HEADLESS", raising=False)
    assert dy._allow_headless() is False
    monkeypatch.setenv("EASEL_DOUYIN_HEADLESS", "1")
    assert dy._allow_headless() is True


# ---------------- 闸门 ----------------
def test_dry_run_shows_guard_status_without_exit(tmp_path, env, capsys):
    pg.set_cooldown("douyin", "测试冷却")
    assert dy._publish(_args(tmp_path, exec=False), "video") == 0
    out = capsys.readouterr().out
    assert "冷却" in out and env["launch"] == []


def test_cooldown_blocks_before_browser(tmp_path, env):
    pg.set_cooldown("douyin", "测试冷却")
    assert _run(_args(tmp_path)) == pg.EXIT_COOLDOWN
    assert env["launch"] == []


def test_duplicate_blocks_unless_allow_repost(tmp_path, env):
    a = _args(tmp_path)
    pg.record_publish("douyin", [a.video], a.title)
    assert _run(a) == pg.EXIT_DUPLICATE and env["launch"] == []
    # 带 --allow-repost 放行 → 进入半自动交接
    env["handoff"] = None
    import semi_auto as sa
    sa_orig = sa.await_human_publish
    try:
        sa.await_human_publish = lambda page, **k: "published"
        assert dy._publish(_args(tmp_path, allow_repost=True), "video") == 0
    finally:
        sa.await_human_publish = sa_orig


# ---------------- 半自动交接 ----------------
def _stub_handoff(monkeypatch, outcome, calls=None):
    def fake(page, **kw):
        if calls is not None:
            calls.append(kw)
        return outcome
    monkeypatch.setattr(semi_auto, "await_human_publish", fake)


def test_semi_auto_published_records_ledger_and_never_clicks(tmp_path, env, monkeypatch):
    calls = []
    _stub_handoff(monkeypatch, "published", calls)
    a = _args(tmp_path)
    assert dy._publish(a, "video") == 0
    assert env["clicks"] == 0 and env["launch"] == [True]       # 窗口 + 不点发布
    assert calls[0]["platform"] == "douyin" and calls[0]["timeout_s"] == 5
    assert calls[0]["is_published"] is dy._is_published
    assert pg.find_duplicate("douyin", [a.video], a.title)       # 已记台账
    assert env["ctx"].closed


@pytest.mark.parametrize("outcome,code", [("blocked", 9), ("closed", 5), ("timeout", 5)])
def test_semi_auto_failures_exit_nonzero_no_retry(tmp_path, env, monkeypatch, outcome, code):
    _stub_handoff(monkeypatch, outcome)
    called = []
    monkeypatch.setattr(platform_readback, "verify_douyin_publish", lambda *a, **k: called.append(1))
    a = _args(tmp_path)
    assert _run(a) == code
    assert env["clicks"] == 0 and not called
    assert not pg.find_duplicate("douyin", [a.video], a.title)   # 没发布 → 不记台账


def test_semi_auto_ai_declare_failure_goes_into_handoff_message(tmp_path, env, monkeypatch):
    monkeypatch.setattr(dy, "_declare_ai", lambda page: False)
    seen = []

    def fake(page, **kw):
        kw["on_status"]("awaiting_user_click", semi_auto.AWAITING_MESSAGE)
        seen.append(json.loads(Path(kw["status_file"]).read_text(encoding="utf-8")))
        return "published"
    monkeypatch.setattr(semi_auto, "await_human_publish", fake)
    a = _args(tmp_path)
    assert dy._publish(a, "video") == 0                          # 半自动勾不上不报错
    assert seen[0]["state"] == "awaiting_user_click"
    assert "自主声明" in seen[0]["message"] and "内容由AI生成" in seen[0]["message"]


def test_no_ai_declare_skips_declaration(tmp_path, env, monkeypatch):
    monkeypatch.setattr(dy, "_declare_ai", lambda page: pytest.fail("不该尝试声明"))
    _stub_handoff(monkeypatch, "published")
    assert dy._publish(_args(tmp_path, ai_declare=False), "video") == 0


def test_is_published_by_redirect_or_toast():
    p = FakePage()
    assert dy._is_published(p) is False
    p.url = "https://creator.douyin.com/creator-micro/content/manage?enter_from=pub"
    assert dy._is_published(p) is True
    q = FakePage(toasts=["发布成功"])
    assert dy._is_published(q) is True


def test_toast_ban_before_publish_sets_cooldown(tmp_path, env, monkeypatch):
    env["page"] = FakePage(toasts=["抖音投稿功能已被封禁"])
    _stub_handoff(monkeypatch, "published")
    assert _run(_args(tmp_path)) == pg.EXIT_COOLDOWN
    assert pg.active_cooldown("douyin")


# ---------------- 自动点击逃生口 ----------------
def test_auto_mode_clicks_exactly_once(tmp_path, env, monkeypatch):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    monkeypatch.setattr(semi_auto, "await_human_publish", lambda *a, **k: pytest.fail("自动模式不应交接"))
    assert dy._publish(_args(tmp_path), "video") == 0
    assert env["clicks"] == 1


def test_auto_mode_ai_declare_failure_exits_6_before_click(tmp_path, env, monkeypatch):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    monkeypatch.setattr(dy, "_declare_ai", lambda page: False)
    assert _run(_args(tmp_path)) == 6
    assert env["clicks"] == 0


def test_auto_mode_block_toast_after_click_exits_9(tmp_path, env, monkeypatch):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    page = env["page"]

    def click_then_ban(p, n=0):
        env["clicks"] += 1
        page.toasts = ["抖音投稿功能已被封禁"]
    monkeypatch.setattr(dy, "_click_publish", click_then_ban)
    assert _run(_args(tmp_path)) == pg.EXIT_COOLDOWN
    assert env["clicks"] == 1 and pg.active_cooldown("douyin")


# ---------------- AI 声明 ----------------
class DeclPage:
    """_declare_ai 用的假页：get_by_text 找不到任何入口。"""
    def __init__(self, declared=False):
        self.declared = declared
        self.mouse = types.SimpleNamespace(wheel=lambda *a: None)

    def evaluate(self, js, text):
        return self.declared

    def get_by_text(self, text, exact=True):
        return types.SimpleNamespace(count=lambda: 0)

    def wait_for_timeout(self, *_a):
        pass

    @property
    def viewport_size(self):
        return {"width": 1000, "height": 800}


def test_declare_ai_already_declared_and_not_found(monkeypatch):
    monkeypatch.setattr(dy.human_input, "scroll", lambda *a: None)
    assert dy._declare_ai(DeclPage(declared=True)) is True
    assert dy._declare_ai(DeclPage(declared=False)) is False      # 找不到入口 → False，不抛


# ---------------- 命令行兼容 ----------------
def test_cli_flags_present(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["douyin_publish.py", "publish-video", "--help"])
    with pytest.raises(SystemExit):
        dy.main()
    out = capsys.readouterr().out
    for flag in ("--allow-repost", "--ai-declare", "--no-ai-declare", "--handoff-timeout",
                 "--headed", "--status-file", "--keep-open", "--exec"):
        assert flag in out


# ---------------- 审查修复：verifying 非终态 / 失败写 error / 未确认记账 / 冷却 ----------------
def _verifying_handoff(monkeypatch):
    import login_state

    def fake(page, **kw):
        login_state.write_status(kw["status_file"], "verifying", semi_auto.VERIFYING_MESSAGE)
        return "published"
    monkeypatch.setattr(semi_auto, "await_human_publish", fake)


def test_semi_success_written_only_after_readback_verified(tmp_path, env, monkeypatch):
    _verifying_handoff(monkeypatch)
    a = _args(tmp_path)
    seen = []
    item = types.SimpleNamespace(platform_content_id="777", status="published")

    def verify(page, **k):
        seen.append(json.loads(Path(a.status_file).read_text(encoding="utf-8"))["state"])
        return platform_readback.ReadbackResult(outcome="verified", matched=item, evidence={})
    monkeypatch.setattr(platform_readback, "verify_douyin_publish", verify)
    assert dy._publish(a, "video") == 0
    assert seen == ["verifying"]
    assert json.loads(Path(a.status_file).read_text(encoding="utf-8"))["state"] == "success"


def test_semi_unverified_readback_ends_in_error_never_success(tmp_path, env, monkeypatch):
    _verifying_handoff(monkeypatch)
    monkeypatch.setattr(platform_readback, "verify_douyin_publish",
                        lambda page, **k: platform_readback.ReadbackResult(outcome="unverified"))
    a = _args(tmp_path)
    assert _run(a) == 5
    st = json.loads(Path(a.status_file).read_text(encoding="utf-8"))
    assert st["state"] == "error" and "未确认" in st["message"]


def test_auto_unconfirmed_records_ledger_with_flag(tmp_path, env, monkeypatch):
    monkeypatch.setenv(semi_auto.AUTO_PUBLISH_ENV, "1")
    pw_timeout = sys.modules["playwright.sync_api"].TimeoutError
    monkeypatch.setattr(dy, "_wait_toast", lambda page, timeout_s=20: (_ for _ in ()).throw(pw_timeout("x")))
    monkeypatch.setattr(platform_readback, "verify_douyin_publish",
                        lambda page, **k: platform_readback.ReadbackResult(outcome="unverified"))
    a = _args(tmp_path)
    assert _run(a) == 5 and env["clicks"] == 1
    last = json.loads(pg.ledger_path().read_text(encoding="utf-8").splitlines()[-1])
    assert last["unconfirmed"] is True and last["url"] == ""
    assert pg.find_duplicate("douyin", [a.video], a.title)   # 重复闸门能挡住二发


def test_whoami_blocked_in_cooldown_without_browser(tmp_path, env, capsys):
    pg.set_cooldown("douyin", "测试冷却")
    with pytest.raises(SystemExit) as e:
        dy.cmd_whoami(types.SimpleNamespace(profile_base=None, proxy=None, no_proxy=True))
    assert e.value.code == pg.EXIT_COOLDOWN and env["launch"] == []
    assert "冷却" in capsys.readouterr().err
