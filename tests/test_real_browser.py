"""real_browser：通用启动器（假 playwright，不开真实浏览器）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"))

import real_browser as rb


class FakeChromium:
    def __init__(self):
        self.calls = []

    def launch_persistent_context(self, profile, **kw):
        self.calls.append((profile, kw))
        return "ctx"


class FakeP:
    def __init__(self):
        self.chromium = FakeChromium()


def test_fingerprint_stable_and_per_profile(tmp_path):
    a = rb.account_fingerprint(tmp_path / "A", platform_label="抖音")
    assert rb.account_fingerprint(tmp_path / "A")["seed"] == a["seed"]
    assert (tmp_path / "A" / rb.FINGERPRINT_FILE).is_file()
    assert not (tmp_path / "B").exists()
    assert json.loads((tmp_path / "A" / rb.FINGERPRINT_FILE).read_text(encoding="utf-8"))["seed"] == a["seed"]


def test_launch_cloak_uses_cloak_dir_and_fingerprint(tmp_path):
    p = FakeP()
    ctx = rb.launch(p, profile_dir=tmp_path / "DouyinProfile", headed=True,
                    engine=("cloak", "/x/Chromium"))
    assert ctx == "ctx"
    profile, kw = p.chromium.calls[0]
    assert profile == str(tmp_path / "DouyinProfile" / rb.CLOAK_DATA_DIR)
    assert kw["executable_path"] == "/x/Chromium" and kw["headless"] is False and kw["no_viewport"] is True
    assert any(a.startswith("--fingerprint=") for a in kw["args"])
    assert "--no-proxy-server" in kw["args"]


def test_launch_headless_requires_env(tmp_path, monkeypatch):
    monkeypatch.delenv("EASEL_X_HEADLESS", raising=False)
    p = FakeP()
    rb.launch(p, profile_dir=tmp_path / "P", headed=False, headless_env="EASEL_X_HEADLESS", engine=("chrome", ""))
    assert p.chromium.calls[0][1]["headless"] is False
    assert p.chromium.calls[0][1]["channel"] == "chrome"
    monkeypatch.setenv("EASEL_X_HEADLESS", "1")
    rb.launch(p, profile_dir=tmp_path / "P", headed=False, headless_env="EASEL_X_HEADLESS", engine=("chrome", ""))
    assert p.chromium.calls[1][1]["headless"] is True


def test_resolve_engine_order(monkeypatch):
    monkeypatch.setenv("E_BR", "chrome")
    assert rb.resolve_engine("E_BR", cloak_fn=lambda: Path("/c"), channel_fn=lambda: "chrome") == ("chrome", "")
    monkeypatch.setenv("E_BR", "auto")
    assert rb.resolve_engine("E_BR", cloak_fn=lambda: Path("/c"), channel_fn=lambda: "chrome") == ("cloak", "/c")
    assert rb.resolve_engine("E_BR", cloak_fn=lambda: None, channel_fn=lambda: None) == ("bundled", "")
