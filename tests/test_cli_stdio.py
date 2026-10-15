"""easel CLI 的标准输出编码。

Windows 上 stdout 被管道接走时按 locale 编码（cp1252 / cp936），输出里的中文、emoji 编码不出来
就 UnicodeEncodeError，CLI 一个字没打就崩 —— CI 的 Real install 里 easel doctor 就是这么挂的。
用 PYTHONIOENCODING=cp1252 在任何平台上模拟。不联网、不碰 OpenClaw。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_output_survives_non_utf8_pipe():
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "PYTHONPATH": str(PROJECT_ROOT)}
    r = subprocess.run([sys.executable, "-m", "easel.cli", "--help"], cwd=PROJECT_ROOT,
                       capture_output=True, timeout=120, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "社媒内容工作流".encode("utf-8") in r.stdout
