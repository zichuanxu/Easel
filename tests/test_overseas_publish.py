"""overseas_publisher publish 命令的离线测试：假平台、假浏览器、假驱动，不连平台。"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import overseas_publisher as op  # noqa: E402
from overseas import base  # noqa: E402
from overseas.post import Limits, Post, caption_text  # noqa: E402


class FakeDrv:
    def __init__(self, page, *, block_wait_ms=0):
        self.page = page
        self.world = page.world
        self.committed = False
        self.world.block_waits.append(block_wait_ms)

    def goto(self, url, timeout_ms=60000):
        if self.world.blocked_headless and not self.page.headed:
            raise base.Blocked("captcha")

    def settle(self, mod):
        return self.world.logged


class World:
    def __init__(self, *, logged=True, result=None, raises=None, blocked_headless=False, commit_first=False):
        self.logged, self.result, self.raises = logged, result, raises
        self.blocked_headless = blocked_headless
        self.commit_first = commit_first         # 先点了最终发布按钮再出错
        self.launches: list[bool] = []
        self.block_waits: list[int] = []
        self.published = 0

    @contextmanager
    def launch(self, profile, *, headed):
        self.launches.append(headed)
        page = SimpleNamespace(headed=headed, world=self)
        yield SimpleNamespace(pages=[page], new_page=lambda: page)


def make_mod(world):
    def publish(drv, fields, post):
        world.published += 1
        if world.commit_first:
            drv.committed = True
        if world.raises:
            raise world.raises
        return world.result or base.Result("success", url="https://demo.test/p/1")
    return SimpleNamespace(
        KEY="demo", NAME="Demo", PROFILE="DemoProfile", HOME_URL="https://demo.test/",
        KINDS=frozenset({"video", "text"}), READY_KINDS=frozenset({"video"}),
        LIMITS=Limits(caption=100), VISIBILITY=(), compose=lambda p: {"caption": caption_text(p)},
        publish=publish)


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 16)
    monkeypatch.setattr(base, "save_failure", lambda page, key: None)
    return tmp_path, video


def run(world, tmp_path, video, *, headed=False):
    recorded: list[tuple] = []
    mod = make_mod(world)
    p = Post(media=[video], desc="Hello", tags="ai")
    sf = tmp_path / "status.json"
    rc = op.run_publish(mod, p, mod.compose(p), headed=headed, status_file=str(sf), launch=world.launch,
                        driver_cls=FakeDrv, profile_root=tmp_path / "profiles",
                        record=lambda *a, **k: recorded.append((a, k)))
    status = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    return rc, status, recorded


def test_success_records_calendar_and_status(env):
    tmp_path, video = env
    rc, status, recorded = run(World(), tmp_path, video)
    assert rc == 0 and status["state"] == "success"
    assert "https://demo.test/p/1" in status["message"]
    assert len(recorded) == 1 and recorded[0][0][0].url == "https://demo.test/p/1"


def test_unknown_result_is_exit_5_without_retry_or_calendar(env):
    """点了发布没等到成功信号：退出码 5、提示别重发、不重试、不记日历（Review Focus 1）。"""
    tmp_path, video = env
    world = World(result=base.Result("unknown", message="没等到提示"))
    rc, status, recorded = run(world, tmp_path, video)
    assert rc == op.EXIT_UNKNOWN == 5
    assert status["state"] == "error" and "不要直接重发" in status["message"]
    assert world.published == 1 and recorded == []


def test_step_failed_is_exit_1_with_hint(env):
    tmp_path, video = env
    rc, status, _ = run(World(raises=base.StepFailed("找不到发布按钮")), tmp_path, video)
    assert rc == 1 and "找不到发布按钮" in status["message"] and "改版" in status["message"]


@pytest.mark.parametrize("err", [base.StepFailed("点不到 Post now"),
                                 RuntimeError("Target page, context or browser has been closed")])
def test_error_after_post_click_is_unknown_exit_5(env, err):
    """点了最终发布按钮之后出任何错：可能已经发出去了，只能报待确认、退出码 5，不重试不记日历（Final review 2）。"""
    tmp_path, video = env
    world = World(raises=err, commit_first=True)
    rc, status, recorded = run(world, tmp_path, video)
    assert rc == op.EXIT_UNKNOWN
    assert status["state"] == "error" and "不要直接重发" in status["message"]
    assert world.published == 1 and recorded == [] and world.launches == [False]


def test_failed_result_is_exit_1(env):
    tmp_path, video = env
    rc, status, recorded = run(World(result=base.Result("failed", message="平台拒绝")), tmp_path, video)
    assert rc == 1 and "平台拒绝" in status["message"] and recorded == []


def test_not_logged_in_is_exit_6(env):
    """未登录：退出码 6，不走发布流程（Review Focus 4）。"""
    tmp_path, video = env
    world = World(logged=False)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == op.EXIT_NOT_LOGGED_IN == 6 and "未登录" in status["message"]
    assert world.published == 0


def test_unsettled_login_is_not_published(env):
    tmp_path, video = env
    world = World(logged=None)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 1 and "没法确认" in status["message"] and world.published == 0


def test_missing_profile_is_exit_6_without_browser(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    world = World()
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 6 and world.launches == []


def test_blocked_headless_retries_headed_once(env):
    tmp_path, video = env
    world = World(blocked_headless=True)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 0 and world.launches == [False, True]


def test_headed_retry_gives_user_time_to_verify(env):
    """无头被拦改开窗口：窗口里的驱动要等用户过验证，无头那次不等（Final review 1）。"""
    tmp_path, video = env
    world = World(blocked_headless=True)
    rc, _, _ = run(world, tmp_path, video)
    assert rc == 0 and world.block_waits == [0, op.VERIFY_WAIT_MS] and op.VERIFY_WAIT_MS >= 120000


def test_blocked_even_when_headed_is_error(env):
    tmp_path, video = env
    world = World(blocked_headless=True)

    @contextmanager
    def always_blocked(profile, *, headed):
        world.launches.append(headed)
        page = SimpleNamespace(headed=False, world=world)   # 有头也被拦
        yield SimpleNamespace(pages=[page], new_page=lambda: page)

    world.launch = always_blocked
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 1 and "验证" in status["message"] and world.launches == [False, True]


def test_playwright_missing_is_exit_3(env):
    tmp_path, video = env
    world = World()

    @contextmanager
    def no_pw(profile, *, headed):
        raise base.PlaywrightMissing("需要 playwright")
        yield  # pragma: no cover

    world.launch = no_pw
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 3


# ---------------------------------------------------------------- 命令行：校验 / 预览 / 闸门
def cli(monkeypatch, *argv):
    monkeypatch.setattr(op, "run_publish", lambda *a, **k: pytest.fail("不该走到真发布"))
    try:
        return op.main(["publish", *argv])
    except SystemExit as e:
        return e.code


def test_dry_run_prints_fields_and_never_launches(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "Hello", "--tags", "ai")
    out = capsys.readouterr().out
    assert rc == 0 and '"caption": "Hello\\n\\n#ai"' in out and "--exec" in out


def test_invalid_content_is_exit_2(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "中" * 200, "--exec")
    assert rc == op.EXIT_INVALID == 2


def test_kind_not_ready_yet_is_exit_2(monkeypatch, capsys):
    rc = cli(monkeypatch, "--platform", "x", "--desc", "just text", "--exec")
    assert rc == 2 and "还没接通" in capsys.readouterr().err


def test_youtube_not_open_until_calibrated(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "youtube", "--media", str(video), "--title", "T", "--exec")
    assert rc == 2 and "YouTube" in capsys.readouterr().err


def test_exec_guard_scans_media_filenames(monkeypatch, capsys, tmp_path):
    """文件名带密钥：真发前被内容安全闸门拦下，退出码 7（Review Focus 5）。"""
    video = tmp_path / "sk-ABCDefgh12345678ijkl.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "Hello", "--exec")
    assert rc == 7


def test_exec_hands_post_to_run_publish(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    seen = {}

    def fake_run(mod, post, fields, **kw):
        seen.update(key=mod.KEY, caption=fields["caption"], headed=kw["headed"], sf=kw["status_file"])
        return 0

    monkeypatch.setattr(op, "run_publish", fake_run)
    rc = op.main(["publish", "--platform", "x", "--media", str(video), "--desc", "Hi", "--status-file",
                  str(tmp_path / "s.json"), "--exec"])
    assert rc == 0 and seen == {"key": "x", "caption": "Hi", "headed": False, "sf": str(tmp_path / "s.json")}


def test_selftest_checks_ready_kinds(capsys):
    assert op.main(["selftest"]) == 0
