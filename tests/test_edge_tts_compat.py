"""edge-tts 2026-10 起合成 403 的兼容层：只在装的 edge-tts 仍用旧地址 + v1 令牌时改走新地址；
tts.py 经兼容入口调 edge-tts。用假 edge_tts 包，不联网、不依赖本机是否装了 edge-tts。"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import edge_tts_compat  # noqa: E402
import tts  # noqa: E402

LEGACY = "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken=TOK"
BIN_DIR = "Scripts" if os.name == "nt" else "bin"


@pytest.fixture()
def fake_edge_tts(monkeypatch):
    """装一个假 edge_tts 包到 sys.modules：communicate 按名字持有 WSS_URL / SEC_MS_GEC_VERSION（同真包）。"""
    pkg = types.ModuleType("edge_tts")
    constants = types.ModuleType("edge_tts.constants")
    constants.TRUSTED_CLIENT_TOKEN = "TOK"
    communicate = types.ModuleType("edge_tts.communicate")
    communicate.WSS_URL = LEGACY
    communicate.SEC_MS_GEC_VERSION = "1-143.0.3650.75"
    pkg.constants, pkg.communicate = constants, communicate
    monkeypatch.setitem(sys.modules, "edge_tts", pkg)
    monkeypatch.setitem(sys.modules, "edge_tts.constants", constants)
    monkeypatch.setitem(sys.modules, "edge_tts.communicate", communicate)
    return communicate


def test_patch_moves_legacy_v1_synthesis_to_new_host(fake_edge_tts):
    assert edge_tts_compat.patch() is True
    assert fake_edge_tts.WSS_URL == (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
        "?Ocp-Apim-Subscription-Key=TOK"
    )


def test_patch_leaves_upstream_new_host_alone(fake_edge_tts):
    """上游发版已改地址：不动。"""
    fake_edge_tts.WSS_URL = "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key=X"
    before = fake_edge_tts.WSS_URL
    assert edge_tts_compat.patch() is False
    assert fake_edge_tts.WSS_URL == before


def test_patch_leaves_upstream_v2_token_alone(fake_edge_tts):
    """上游改发 v2 令牌、继续用旧地址：旧地址认 v2，不能再改道。"""
    fake_edge_tts.SEC_MS_GEC_VERSION = "2-155.0.4283.45"
    assert edge_tts_compat.patch() is False
    assert fake_edge_tts.WSS_URL == LEGACY


def _exe(d: Path, name: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / (f"{name}.exe" if os.name == "nt" else name)
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_cmd_uses_current_interpreter_when_it_has_edge_tts(monkeypatch):
    monkeypatch.setattr(tts, "_has_module", lambda py, mod: py == sys.executable)
    cmd = tts._edge_tts_cmd("/somewhere/edge-tts")
    assert cmd == [sys.executable, str(Path(tts.__file__).resolve().parent / "edge_tts_compat.py")]


def test_cmd_uses_python_next_to_edge_tts(tmp_path, monkeypatch):
    """gateway 起脚本的 python 可能不是装了 edge-tts 的那个：用 edge-tts 同目录（venv）的解释器。"""
    b = _exe(tmp_path / "venv" / BIN_DIR, "edge-tts")
    py = _exe(b.parent, "python")
    monkeypatch.setattr(tts, "_has_module", lambda p, mod: os.path.normcase(p) == os.path.normcase(str(py)))
    cmd = tts._edge_tts_cmd(str(b))
    assert os.path.normcase(cmd[0]) == os.path.normcase(str(py))
    assert cmd[1].endswith("edge_tts_compat.py")


def test_cmd_falls_back_to_plain_cli_without_usable_interpreter(tmp_path, monkeypatch):
    b = _exe(tmp_path / "pipx" / BIN_DIR, "edge-tts")
    monkeypatch.setattr(tts, "_has_module", lambda p, mod: False)
    assert tts._edge_tts_cmd(str(b)) == [str(b)]


def test_speak_runs_edge_tts_through_compat_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "find_edge_tts", lambda: "/x/edge-tts")
    monkeypatch.setattr(tts, "_has_module", lambda py, mod: py == sys.executable)
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        Path(cmd[cmd.index("--write-media") + 1]).write_bytes(b"ID3")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    out = tmp_path / "vo.mp3"
    tts._run_edge_tts("测试", out, voice="zh-CN-YunyangNeural", rate="+12%",
                      volume=None, pitch=None, subtitle=None, proxy=None)
    assert seen[0][:2] == [sys.executable, str(Path(tts.__file__).resolve().parent / "edge_tts_compat.py")]
    assert "--voice" in seen[0] and "zh-CN-YunyangNeural" in seen[0]
    assert out.read_bytes() == b"ID3"


def test_handshake_403_gets_auth_hint_not_proxy_hint(tmp_path, monkeypatch, capsys):
    """403 的 URL 里有 ConnectionId=，曾误中「connection」关键字给出代理提示，把人引去查代理。"""
    monkeypatch.setattr(tts, "find_edge_tts", lambda: "/x/edge-tts")
    monkeypatch.setattr(tts, "_has_module", lambda py, mod: False)
    err = ("aiohttp.client_exceptions.WSServerHandshakeError: 403, message='Invalid response status', "
           "url='wss://speech.platform.bing.com/...&ConnectionId=abc&Sec-MS-GEC=X'")
    monkeypatch.setattr(tts.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", err))
    with pytest.raises(SystemExit):
        tts._run_edge_tts("测试", tmp_path / "vo.mp3", voice="zh-CN-YunyangNeural", rate=None,
                          volume=None, pitch=None, subtitle=None, proxy=None)
    msg = capsys.readouterr().err
    assert "rany2/edge-tts#490" in msg
    assert "外网代理" not in msg
