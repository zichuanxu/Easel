#!/usr/bin/env python3
"""edge_tts_compat.py — 经兼容层运行 edge-tts 命令行（参数同 `edge-tts`）。

2026-10 起，微软旧合成地址 speech.platform.bing.com 只认 v2 版 Sec-MS-GEC 令牌；
edge-tts 7.2.8 及以前还发 v1，握手一律 403（rany2/edge-tts#490）。新版 Edge 走的
api.msedgeservices.com 仍接受旧令牌（上游 PR #491 的做法）。这里在运行 edge-tts 前
把合成地址换过去；装的 edge-tts 已不是「旧地址 + v1 令牌」时什么都不改。

tts.py 通过本入口调 edge-tts。上游发版修复后：升级 edge-tts，删掉本文件和
tts.py 里的 _edge_tts_cmd / _has_module，改回直接调 `edge-tts` 命令。
"""
from __future__ import annotations

LEGACY_HOST = "speech.platform.bing.com"
NEW_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    "?Ocp-Apim-Subscription-Key={token}"
)


def patch() -> bool:
    """旧地址 + v1 令牌时把合成地址改到新地址，返回是否改了。

    要改 edge_tts.communicate 里的 WSS_URL：它 `from .constants import WSS_URL`，
    只改 constants 不生效。
    """
    from edge_tts import communicate
    from edge_tts.constants import TRUSTED_CLIENT_TOKEN

    if LEGACY_HOST not in communicate.WSS_URL:
        return False
    if not str(getattr(communicate, "SEC_MS_GEC_VERSION", "")).startswith("1-"):
        return False
    communicate.WSS_URL = NEW_WSS_URL.format(token=TRUSTED_CLIENT_TOKEN)
    return True


def main() -> None:
    patch()
    from edge_tts.util import main as edge_tts_main

    edge_tts_main()


if __name__ == "__main__":
    main()
