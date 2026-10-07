"""bili_upload 的发布闸门：重复拦截 / 冷却 / --allow-repost / 读回成功后记账（假 biliup、假读回，不连 B站）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "shared" / "scripts"))

import publish_guard  # noqa: E402
import platform_readback  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "bili_upload", ROOT / "skills" / "openclaw" / "skill-bilibili-upload" / "scripts" / "bili_upload.py")
bu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bu)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_guard, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(publish_guard, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(publish_guard, "PUBLISH_LOG_PATH", tmp_path / "publish-log.json")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x01\x02\x03")
    cookie = tmp_path / "cookies.json"
    cookie.write_text("{}", encoding="utf-8")
    sent = []
    monkeypatch.setattr(bu, "_has_biliup", lambda: True)
    monkeypatch.setattr(bu.subprocess, "call", lambda cmd, **kw: sent.append(cmd) or 0)
    monkeypatch.setattr(platform_readback, "capture_bilibili_snapshot", lambda c: set())
    item = SimpleNamespace(platform_content_id="BV1xx", status="开放浏览")
    monkeypatch.setattr(platform_readback, "verify_bilibili_publish", lambda *a, **k: SimpleNamespace(
        outcome="verified", matched=item, evidence={"account": {"name": "me"}}, error=""))
    monkeypatch.setattr("calendar_ops.record_publish", lambda *a, **k: None)
    return video, cookie, sent


def run(video, cookie, *extra):
    argv = ["bili_upload.py", "upload", "--video", str(video), "--title", "测试标题", "--cookie", str(cookie),
            "--exec", *extra]
    monkeypatch_argv = sys.argv
    sys.argv = argv
    try:
        return bu.main()
    except SystemExit as e:
        return e.code
    finally:
        sys.argv = monkeypatch_argv


def test_success_records_ledger_then_duplicate_blocked(env):
    video, cookie, sent = env
    assert run(video, cookie) == 0 and len(sent) == 1
    assert publish_guard.find_duplicate("bilibili", [str(video)], "测试标题")["url"].endswith("BV1xx")
    assert run(video, cookie) == publish_guard.EXIT_DUPLICATE and len(sent) == 1   # 没再发


def test_allow_repost_passes_duplicate(env):
    video, cookie, sent = env
    run(video, cookie)
    assert run(video, cookie, "--allow-repost") == 0 and len(sent) == 2


def test_cooldown_blocks_even_with_allow_repost(env):
    video, cookie, sent = env
    publish_guard.set_cooldown("bilibili", "测试冷却")
    assert run(video, cookie, "--allow-repost") == publish_guard.EXIT_COOLDOWN and sent == []


def test_unverified_readback_does_not_record(env, monkeypatch):
    video, cookie, sent = env
    monkeypatch.setattr(platform_readback, "verify_bilibili_publish", lambda *a, **k: SimpleNamespace(
        outcome="unverified", matched=None, evidence={}, error=""))
    assert run(video, cookie) == 4
    assert publish_guard.find_duplicate("bilibili", [str(video)], "测试标题") is None


def test_dry_run_skips_guard(env, tmp_path):
    video, cookie, sent = env
    publish_guard.set_cooldown("bilibili", "测试冷却")
    sys.argv = ["bili_upload.py", "upload", "--video", str(video), "--title", "x"]
    assert bu.main() == 0 and sent == []
