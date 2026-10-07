"""account_stats fetch：平台处于发布冷却期时拒绝抓取（不起浏览器），退出码 = publish_guard.EXIT_COOLDOWN。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"))

import account_stats  # noqa: E402
import publish_guard  # noqa: E402


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_guard, "COOLDOWN_PATH", tmp_path / "cooldown.json")
    monkeypatch.setattr(account_stats, "_scrape", lambda *a, **k: pytest.fail("冷却期不该起浏览器"))


@pytest.mark.parametrize("pf", ["douyin", "kuaishou", "zhihu", "weixin-channels", "xiaohongshu"])
def test_fetch_refused_in_cooldown(pf, capsys, monkeypatch):
    publish_guard.set_cooldown(pf, "平台提示处罚")
    monkeypatch.setattr(sys, "argv", ["account_stats.py", "fetch", "--platform", pf, "--manual"])
    assert account_stats.main() == publish_guard.EXIT_COOLDOWN
    cap = capsys.readouterr()
    assert "冷却期" in cap.err
    out = json.loads(cap.out.strip().splitlines()[-1])
    assert out["cooldown"] is True and out["loggedIn"] is False


def test_cooldown_is_per_platform(monkeypatch, capsys):
    """别的平台冷却不影响本平台（走到 playwright 检查/抓取分支即说明没被冷却拦）。"""
    publish_guard.set_cooldown("douyin", "x")
    monkeypatch.setattr(account_stats, "_scrape", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("reached")))
    monkeypatch.setattr(sys, "argv", ["account_stats.py", "fetch", "--platform", "kuaishou"])
    with pytest.raises((RuntimeError, SystemExit)):
        account_stats.main()
    assert "冷却期" not in capsys.readouterr().err
