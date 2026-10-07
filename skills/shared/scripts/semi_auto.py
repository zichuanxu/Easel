#!/usr/bin/env python3
"""semi_auto.py — 国内浏览器平台的「半自动」交接：脚本填好表单，停在发布按钮前，由人亲自点发布。

背景：小红书因 AI 托管/第三方脚本被封号、抖音投稿功能被封。国内平台（抖音/小红书/视频号/快手/知乎）
一律改为半自动：Easel 在可见的真实浏览器里把所有内容填好 → 本模块接管 → 提示用户检查并亲自点击「发布」
→ 脚本只被动观察结果（发布成功 / 平台处罚提示 / 窗口被关 / 超时），**不替用户点发布**。

用法（发布脚本在表单填完后调用）::

    import semi_auto
    outcome = semi_auto.await_human_publish(
        page, platform="douyin",
        is_published=lambda pg: "/manage" in pg.url,      # 发布成功的判定（各平台自己写）
        status_file=args.status_file,
    )
    # outcome: "published" | "blocked" | "closed" | "timeout"
    # blocked 时 publish_guard 已把该平台设为冷却；调用方应 sys.exit(publish_guard.EXIT_COOLDOWN)，不得重试。

逃生口：环境变量 EASEL_DOMESTIC_AUTO_PUBLISH=1 才允许脚本自动点击发布（auto_click_allowed）。
这个开关**只能由用户自己**在 .env / 终端里设置；agent 永远不得设置它，也不得建议用户设置它来「省事」。

纯 stdlib（page 由调用方传入，只用 Playwright 同步 API 的 locator / is_closed / wait_for_timeout 子集）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import login_state  # noqa: E402
import publish_guard  # noqa: E402

AUTO_PUBLISH_ENV = "EASEL_DOMESTIC_AUTO_PUBLISH"
AWAITING_MESSAGE = "已在窗口里填好，请检查后亲自点击『发布』（脚本不会替你点）。"

# 常见 toast / 通知容器（各平台不全，调用方可按平台传自己的）。只取这些元素的文本去判处罚，不看整页。
DEFAULT_TOAST_SELECTORS = (
    ".semi-toast", ".semi-toast-content", ".semi-notification",
    ".ant-message", ".ant-notification", ".el-message", ".el-notification",
    "[role=alert]", "[class*=toast]", "[class*=Toast]", "[class*=notice]", "[class*=message-box]",
)

# 内部定时/时钟入口（测试可替换）
_sleep = time.sleep
_monotonic = time.monotonic


def auto_click_allowed(platform: str = "") -> bool:
    """是否允许脚本自动点击「发布」：仅当环境变量 EASEL_DOMESTIC_AUTO_PUBLISH == "1"（默认关）。
    这是用户自己掌控的逃生口，agent 不得设置。platform 目前不影响判定，保留给将来按平台细分。"""
    import os
    return (os.environ.get(AUTO_PUBLISH_ENV) or "").strip() == "1"


def _write_status(status_file, on_status, state: str, message: str) -> None:
    """写状态文件（沿用 login_state.write_status 的 JSON 形状：state/message/ts…）并回调 on_status。"""
    try:
        login_state.write_status(status_file, state, message)
    except OSError:
        pass
    if on_status:
        try:
            on_status(state, message)
        except Exception:
            pass


def _page_closed(page) -> bool:
    try:
        return bool(page.is_closed())
    except Exception:
        return True  # 连 is_closed 都抛，说明浏览器/连接已没了


def _looks_closed(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in ("target closed", "targetclosed", "has been closed", "browser has been closed",
                                   "connection closed", "page closed", "context or browser"))


def _toast_texts(page, selectors) -> list[str]:
    texts: list[str] = []
    for sel in selectors:
        try:
            for t in page.locator(sel).all_inner_texts():
                if t and t.strip():
                    texts.append(t.strip())
        except Exception as e:
            if _looks_closed(e):
                raise
            continue
    return texts


def await_human_publish(page, *, platform: str, is_published: Callable[[object], bool],
                        toast_selectors=DEFAULT_TOAST_SELECTORS, timeout_s: float = 3600,
                        poll_s: float = 2.0, status_file: str | None = None,
                        on_status: Callable[[str, str], None] | None = None) -> str:
    """表单已填好后调用：提示用户亲自点发布，并被动等待结果。返回 "published"|"blocked"|"closed"|"timeout"。

    每轮轮询顺序：页面是否已关 → toast 里有没有平台处罚提示（命中则 publish_guard.on_block_detected 设冷却，
    返回 "blocked"）→ is_published(page)（成功返回 "published"）。本函数从不点击任何按钮。
    状态文件写 login_state 同款 JSON：awaiting_user_click（等用户点）→ success（已发布）/ error（其余）。"""
    name = publish_guard.platform_display(platform)
    print(f"✋ {name}：{AWAITING_MESSAGE}", flush=True)
    _write_status(status_file, on_status, "awaiting_user_click", AWAITING_MESSAGE)
    deadline = _monotonic() + timeout_s
    while True:
        if _page_closed(page):
            _write_status(status_file, on_status, "error", "浏览器窗口已关闭，未确认发布结果；请到平台后台自行核对，不要自动重试。")
            return "closed"
        try:
            for text in _toast_texts(page, toast_selectors):
                if publish_guard.classify_block_text(text):
                    publish_guard.on_block_detected(platform, text)
                    _write_status(status_file, on_status, "error",
                                  f"{name} 提示处罚/限制：{text[:120]}。已设为冷却，请勿重试，先向用户汇报。")
                    return "blocked"
            if is_published(page):
                _write_status(status_file, on_status, "success", "检测到已发布。")
                return "published"
        except Exception as e:
            if _looks_closed(e) or _page_closed(page):
                _write_status(status_file, on_status, "error", "浏览器窗口已关闭，未确认发布结果；请到平台后台自行核对，不要自动重试。")
                return "closed"
            # 导航瞬间选择器/上下文失效等瞬时错误：忽略，下一轮再看
        if _monotonic() >= deadline:
            _write_status(status_file, on_status, "error", "等待用户点击发布超时，未确认发布结果；请向用户确认，不要自动重试。")
            return "timeout"
        _sleep(poll_s)
