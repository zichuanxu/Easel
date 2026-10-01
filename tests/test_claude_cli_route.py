"""Claude CLI 路线的纯逻辑（easel/claude_cli_route.py）：规则与 setup.sh 的 EASEL_AGENT_RUNTIME=claude-cli 分支一致。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from easel import claude_cli_route as ccr  # noqa: E402

HOME = "/home/u"


@pytest.mark.parametrize("raw,expected", [
    ("", "anthropic/claude-opus-5"),                      # 空 = 默认（setup.sh 的 CLAUDE_CLI_DEFAULT_MODEL）
    ("anthropic/claude-sonnet-4-6", "anthropic/claude-sonnet-4-6"),
    ("claude-cli/claude-opus-5-5", "anthropic/claude-opus-5-5"),   # 老写法改成新写法
    ("claude-sonnet-4-6", "anthropic/claude-sonnet-4-6"),          # 裸模型名补 provider
    ("openai/gpt-4o", None),                              # 别家 provider
    ("claude-", None),
    ("gpt-4o", None),
    ("anthropic/", None),
])
def test_normalize_model_matches_setup_sh(raw, expected):
    assert ccr.normalize_model(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("", os.path.join(HOME, ".claude-easel")),            # 默认隔离目录
    ("shared", ""),                                       # 不隔离：个人 ~/.claude
    ("~/agents/claude/", os.path.join(HOME, "agents/claude")),
    ("/opt/claude-easel//", "/opt/claude-easel"),
])
def test_resolve_config_dir(raw, expected):
    assert ccr.resolve_config_dir(raw, HOME) == (expected, "")


@pytest.mark.parametrize("raw", ["relative/dir", "~", "~bob/x", HOME, HOME + "/"])
def test_resolve_config_dir_rejects_relative_or_home(raw):
    d, err = ccr.resolve_config_dir(raw, HOME)
    assert d == "" and "绝对路径" in err


def _cfg():
    return {
        "models": {"providers": {"openai": {"baseUrl": "https://x/v1", "apiKey": "k"}}},
        "agents": {"defaults": {"model": {"primary": "openai/m"},
                                "models": {"openai/m": {"alias": "m"}}}},
        "env": {"vars": {"OTHER": "1"}},
    }


def test_apply_route_writes_runtime_primary_and_config_dir():
    cfg = _cfg()
    changed = ccr.apply_route(cfg, "anthropic/claude-opus-5", "/home/u/.claude-easel")
    d = cfg["agents"]["defaults"]
    assert d["model"]["primary"] == "anthropic/claude-opus-5"
    assert d["models"]["anthropic/claude-opus-5"]["agentRuntime"] == {"id": "claude-cli"}
    assert d["models"]["openai/m"] == {"alias": "m"}                 # 别的模型条目不动
    assert "anthropic" not in cfg["models"]["providers"]             # 这条路线不写 provider
    assert cfg["env"]["vars"] == {"OTHER": "1", "CLAUDE_CONFIG_DIR": "/home/u/.claude-easel"}
    assert changed is True
    assert ccr.apply_route(cfg, "anthropic/claude-opus-5", "/home/u/.claude-easel") is False


def test_apply_route_shared_removes_config_dir():
    cfg = _cfg()
    cfg["env"]["vars"]["CLAUDE_CONFIG_DIR"] = "/home/u/.claude-easel/"   # 末尾 / 不算改目录
    assert ccr.apply_route(cfg, "anthropic/claude-opus-5", "/home/u/.claude-easel") is False
    assert ccr.apply_route(cfg, "anthropic/claude-opus-5", "") is True
    assert "CLAUDE_CONFIG_DIR" not in cfg["env"]["vars"]


def test_apply_route_shared_without_env_block_adds_nothing():
    cfg = {"agents": {"defaults": {"model": {"primary": "openai/m"}}}}
    assert ccr.apply_route(cfg, "anthropic/claude-opus-5", "") is False
    assert "env" not in cfg
