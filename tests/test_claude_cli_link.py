"""Claude CLI 续聊兜底软链：目录名与 OpenClaw 算法一致、幂等、只挪不覆盖、不碰别人的软链。

全在 tmp_path 里做（home 显式传临时目录），不碰真实的 ~/.claude 和 ~/.claude-easel。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from easel import claude_cli_link as link
from easel.commands import doctor

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Claude CLI 路线只支持 Linux/macOS（软链）")


@pytest.fixture()
def env(tmp_path):
    home = tmp_path / "home"
    ws = home / ".openclaw-easel" / "workspace"
    ws.mkdir(parents=True)
    cfg = home / ".claude-easel"
    return home, ws, cfg


def test_project_key_matches_openclaw_sanitizer(tmp_path):
    ws = tmp_path / "a.b" / "workspace"
    ws.mkdir(parents=True)
    key = link.project_key(ws)
    assert key == "".join(c if c.isascii() and c.isalnum() else "-" for c in os.path.realpath(ws))


def test_astral_characters_count_as_two_utf16_units():
    # JS: "/a/🙂b".replace(/[^a-zA-Z0-9]/g, "-") === "-a---b"（emoji 占两个 UTF-16 码元）
    assert link.project_key("/a/🙂b").endswith("-a---b")
    assert link.project_key("/测试").endswith("---")


def test_home_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    probe, _ = link.link_paths("/x/.claude-easel", "/ws")
    assert probe == tmp_path / ".claude" / "projects" / "-ws"


def test_long_workspace_key_gets_openclaw_hash():
    # 期望值来自 OpenClaw 的 JS 实现：hash = hash * 31 + charCodeAt >>> 0，toString(36)
    assert link._hash36("/Users/a/" + "x" * 250) == "ons97o"
    assert link._hash36("/Users/测试/𝒳🙂/" + "y" * 230) == "1oqbikd"   # BMP 外字符按两个 UTF-16 码元算
    key = link.project_key("/" + "x" * 300)
    assert len(key) > 200 and key[:200] == ("-" + "x" * 300)[:200]


def test_creates_link_and_is_idempotent(env):
    home, ws, cfg = env
    ok, msg = link.ensure_link(str(cfg), ws, home=home)
    assert ok, msg
    probe, target = link.link_paths(cfg, ws, home)
    assert probe.is_symlink() and os.path.realpath(probe) == os.path.realpath(target)
    (target / "s1.jsonl").write_text("{}", encoding="utf-8")
    assert (probe / "s1.jsonl").is_file()          # OpenClaw 从 ~/.claude 那边能看到会话文件
    assert link.ensure_link(str(cfg), ws, home=home)[0]
    assert link.check_link(str(cfg), ws, home=home)[0]


def test_existing_dir_contents_are_moved_not_overwritten(env):
    home, ws, cfg = env
    probe, target = link.link_paths(cfg, ws, home)
    (probe / "memory").mkdir(parents=True)
    (probe / "old.jsonl").write_text("old", encoding="utf-8")
    (target / "memory").mkdir(parents=True)
    (target / "new.jsonl").write_text("new", encoding="utf-8")
    ok, msg = link.ensure_link(str(cfg), ws, home=home)
    assert ok, msg
    assert probe.is_symlink()
    assert (target / "old.jsonl").read_text(encoding="utf-8") == "old"
    assert (target / "new.jsonl").read_text(encoding="utf-8") == "new"


def test_name_clash_stops_without_touching_anything(env):
    home, ws, cfg = env
    probe, target = link.link_paths(cfg, ws, home)
    probe.mkdir(parents=True)
    target.mkdir(parents=True)
    (probe / "same.jsonl").write_text("A", encoding="utf-8")
    (target / "same.jsonl").write_text("B", encoding="utf-8")
    ok, msg = link.ensure_link(str(cfg), ws, home=home)
    assert not ok and "同名" in msg
    assert not probe.is_symlink()
    assert (probe / "same.jsonl").read_text(encoding="utf-8") == "A"
    assert (target / "same.jsonl").read_text(encoding="utf-8") == "B"


def test_foreign_symlink_is_left_alone(env, tmp_path):
    home, ws, cfg = env
    probe, _ = link.link_paths(cfg, ws, home)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    probe.parent.mkdir(parents=True)
    probe.symlink_to(elsewhere, target_is_directory=True)
    ok, msg = link.ensure_link(str(cfg), ws, home=home)
    assert not ok and os.path.realpath(probe) == os.path.realpath(elsewhere)
    assert not link.check_link(str(cfg), ws, home=home)[0]


@pytest.mark.parametrize("config_dir", ["", "  ", None])
def test_shared_claude_dir_needs_no_link(env, config_dir):
    home, ws, _ = env
    assert link.ensure_link(config_dir, ws, home=home) == (True, "共用个人 ~/.claude，不需要软链")
    assert not (home / ".claude" / "projects").exists()


def test_config_dir_equal_to_personal_claude_or_relative_is_skipped(env):
    home, ws, _ = env
    assert link.ensure_link(str(home / ".claude"), ws, home=home)[0]
    ok, msg = link.ensure_link("relative/dir", ws, home=home)
    assert ok and "不是绝对路径" in msg
    assert not (home / ".claude" / "projects").exists()


def test_check_reports_missing_link_with_fix(env):
    home, ws, cfg = env
    ok, msg = link.check_link(str(cfg), ws, home=home)
    assert not ok and "python -m easel.claude_cli_link" in msg


def test_main_with_explicit_paths(env, monkeypatch, capsys):
    home, ws, cfg = env
    monkeypatch.setenv("HOME", str(home))
    assert link.main(["--check", "--config-dir", str(cfg), "--workspace", str(ws)]) == 1
    assert link.main(["--config-dir", str(cfg), "--workspace", str(ws)]) == 0
    assert "已建软链" in capsys.readouterr().out
    assert link.main(["--check", "--config-dir", str(cfg), "--workspace", str(ws)]) == 0


def test_main_without_claude_cli_route_is_noop(monkeypatch, capsys):
    monkeypatch.setattr(link, "from_openclaw", lambda: (False, None))
    assert link.main([]) == 0
    assert "没走 Claude CLI" in capsys.readouterr().out


def test_doctor_check_uses_openclaw_config_dir(env, monkeypatch):
    home, ws, cfg = env
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(link, "from_openclaw", lambda: (True, str(cfg)))
    monkeypatch.setattr("easel.openclaw_workspace.workspace_dir", lambda: ws)
    ok, detail = doctor._claude_cli_resume_ready()
    assert not ok and "丢上下文" in detail
    link.ensure_link(str(cfg), ws, home=home)
    assert doctor._claude_cli_resume_ready()[0]


def test_from_openclaw_reads_runtime_and_config_dir(tmp_path, monkeypatch):
    import json
    cfg_file = tmp_path / "openclaw.json"
    monkeypatch.setattr("easel.openclaw_workspace.config_path", lambda: cfg_file)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert link.from_openclaw() == (False, None)                       # 没有配置文件
    cfg_file.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "anthropic/claude-sonnet-5-5"},
                                "models": {"anthropic/claude-sonnet-5-5": {"agentRuntime": {"id": "claude-cli"}}}}},
        "env": {"vars": {"CLAUDE_CONFIG_DIR": "/Users/x/.claude-easel"}},
    }), encoding="utf-8")
    assert link.from_openclaw() == (True, "/Users/x/.claude-easel")
