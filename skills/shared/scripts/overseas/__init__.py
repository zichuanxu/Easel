"""海外平台（TikTok / YouTube / Instagram / X / Threads）发布的共用包。

PLATFORMS：平台码 → 平台模块。每个模块都要有 REQUIRED_ATTRS 里的成员（overseas_publisher selftest 会查）。
"""
from __future__ import annotations

from . import instagram, threads, tiktok, x, youtube

PLATFORMS = {m.KEY: m for m in (tiktok, youtube, instagram, x, threads)}

REQUIRED_ATTRS = (
    "KEY", "NAME", "PROFILE", "HOME_URL", "LOGIN_URL", "COOKIE_URL", "AUTH_COOKIES", "LOGIN_MARKERS",
    "KINDS", "LIMITS", "VISIBILITY", "VISIBILITY_DEFAULT", "NAME_SELECTORS", "AVATAR_SELECTORS",
    "compose", "is_logged_in", "read_identity",
)


def get(key: str):
    try:
        return PLATFORMS[key]
    except KeyError:
        raise KeyError(f"不支持的海外平台：{key}（可选：{', '.join(PLATFORMS)}）") from None
