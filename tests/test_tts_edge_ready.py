"""edge-tts 免 key 配音：PATH 没激活 .venv 时也要找到它，设置页配音通道要显示它的状态。不联网。"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
import tts  # noqa: E402

BIN_DIR = "Scripts" if os.name == "nt" else "bin"


def _fake_edge_tts(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("edge-tts.exe" if os.name == "nt" else "edge-tts")
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def _same(a: str | None, b: Path) -> bool:
    return a is not None and os.path.normcase(a) == os.path.normcase(str(b))


@pytest.fixture()
def no_path(tmp_path, monkeypatch):
    """PATH 里没有 edge-tts、脚本也不在仓库里（不让本机真 .venv 干扰），解释器在空目录。"""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    # 脚本位置的「项目根」（上三级）是 tmp_path/elsewhere，不能和 cwd 重合
    monkeypatch.setattr(tts, "__file__", str(tmp_path / "elsewhere" / "ws" / "shared" / "scripts" / "tts.py"))
    monkeypatch.setattr(tts.sys, "executable", str(tmp_path / "sys-python" / "python"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_finds_edge_tts_next_to_interpreter(no_path, monkeypatch):
    b = _fake_edge_tts(no_path / "venv" / BIN_DIR)
    monkeypatch.setattr(tts.sys, "executable", str(b.parent / "python"))
    assert _same(tts.find_edge_tts(), b)


def test_ignores_venv_in_current_directory(no_path):
    """cwd 可能是任意目录（下载的仓库等），不执行那里的 .venv/bin/edge-tts。"""
    if Path("/root/miniconda3/bin/edge-tts").exists():
        pytest.skip("本机有旧路径 /root/miniconda3/bin/edge-tts")
    _fake_edge_tts(no_path / ".venv" / BIN_DIR)
    assert tts.find_edge_tts() is None


def test_finds_edge_tts_in_repo_venv_via_script_location(no_path, monkeypatch):
    repo = no_path / "repo"
    b = _fake_edge_tts(repo / ".venv" / BIN_DIR)
    monkeypatch.setattr(tts, "__file__", str(repo / "skills" / "shared" / "scripts" / "tts.py"))
    assert _same(tts.find_edge_tts(), b)


def test_returns_none_when_not_installed(no_path):
    if Path("/root/miniconda3/bin/edge-tts").exists():
        pytest.skip("本机有旧路径 /root/miniconda3/bin/edge-tts")
    assert tts.find_edge_tts() is None


def _speech_rows(tmp_path, monkeypatch, env_text: str, found: bool) -> list[dict]:
    env_file = tmp_path / ".env"
    env_file.write_text(env_text, encoding="utf-8")
    monkeypatch.setattr(web, "ENV_FILE", env_file)
    monkeypatch.setattr(tts, "find_edge_tts", lambda: "/x/edge-tts" if found else None)
    return web._model_channels()["channels"]["speech"]["rows"]


def test_speech_channel_shows_edge_row_as_primary_without_cloud_voice(tmp_path, monkeypatch):
    rows = _speech_rows(tmp_path, monkeypatch, "", found=True)
    edge = [r for r in rows if r.get("type") == "edge"]
    assert len(edge) == 1
    assert edge[0]["result"] == "已就绪"
    assert edge[0]["role"] == "主"
    assert "slot" not in edge[0]   # 只读展示行：前端只保存带 slot 的行


def test_speech_edge_row_is_fallback_when_cloud_voice_set(tmp_path, monkeypatch):
    rows = _speech_rows(tmp_path, monkeypatch, "VOICE_PROVIDER=dashscope\n", found=False)
    edge = next(r for r in rows if r.get("type") == "edge")
    assert edge["role"] == "兜底"
    assert edge["result"].startswith("未装")
