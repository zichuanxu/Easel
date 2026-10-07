#!/usr/bin/env python3
"""xhs_publish.py — 小红书发布（Playwright 驱动本机 Chrome，有窗口）.

流程与选择器移植自 xpzouying/xiaohongshu-mcp（Go/go-rod）。确定性 IO 固化在脚本，
文案/策略仍由上层 LLM 决定。

浏览器：默认开 **CloakBrowser**（源码级抹掉自动化痕迹的 Chromium，`~/.cloakbrowser`）的窗口，
每个账号一套固定指纹（存在登录目录 .easel-fingerprint.json，macOS 上是 macOS 身份）；没装 Cloak 再开
**本机正式版 Chrome（找不到用 Edge）**。鼠标沿曲线移过去点、按词组输入（human_input.py）。2026-10 账号因「第三方脚本 / AI 托管发文」被封 30 天：当时用的是 Playwright
自带内核的无头模式，UA 直接写着 HeadlessChrome。所以小红书这条链不再无头运行
（EASEL_XHS_HEADLESS=1 可强开，仅限没有桌面的机器，很容易被识别）。
另有发帖频率闸门（_activity_check）和「笔记含 AI 合成内容」声明（_declare_ai）。

移植的关键健壮技巧（源见各处 REF 注释）：
  - 切「上传图文/视频」tab：重试 + 遮挡检测 + 移除弹层
  - 逐图上传并等预览出现（≤60s）；视频等发布按钮可点击（≤10min = 处理完成）
  - 话题：输 # + 联想下拉点选，真绑话题
  - 发布按钮：新版 <xhs-publish-btn> + 旧版 .bg-red 双兼容
  - 发布成功校验：URL 离开 /publish/publish 才算成功（消除假成功）
  - 真人节奏：曲线移动鼠标再点、按词组输入、滚轮翻页（human_input.py）

子命令:
  check          验 playwright + chromium 内核
  login          有头扫码登录并持久化 cookie
  plan           离线打印发布步骤与选择器（不启浏览器）
  publish        图文发布（--images 逗号分隔）
  publish-video  视频发布（--video）
  selftest       离线自检（选择器字典 / 参数解析 / 标题长度算法）

真实发布需：playwright + chromium 内核 + 已扫码登录 + 外网可达（默认走项目代理）。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import login_state  # noqa: E402
import content_guard  # noqa: E402  出站内容安全闸门
import human_input  # noqa: E402  真人节奏的鼠标/键盘
import real_browser  # noqa: E402  可见真实浏览器启动器（Cloak/Chrome）

# --------------------------------------------------------------------------- #
# 选择器集中维护（小红书改版时单点更新）。REF = xiaohongshu-mcp 对应源。
# --------------------------------------------------------------------------- #
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
EXPLORE_URL = "https://www.xiaohongshu.com/explore"
CREATOR_LOGIN_URL = "https://creator.xiaohongshu.com/login"
TITLE_MAX = 20  # 小红书标题上限（全角计法，见 calc_title_length）

SELECTORS = {
    # 登录（REF login.go）
    "login_ok": ".main-container .user .link-wrapper .channel",
    "qrcode": ".login-container .qrcode-img",
    # 进页/切 tab（REF publish.go mustClickPublishTab）
    "upload_content": "div.upload-content",
    "creator_tab": "div.creator-tab",
    "pop_cover": "div.d-popover",
    # 上传（REF publish.go uploadImages / publish_video.go uploadVideo）
    "upload_input_first": ".upload-input",
    "upload_input_more": "input[type=file]",
    "img_preview": ".img-preview-area .pr",
    # 标题/正文（REF publish.go submitPublish / getContentElement）
    "title_input": "div.d-input input, input[placeholder*='标题']",
    "content_quill": "div.ql-editor",
    "content_editable": "div.editor-container [contenteditable='true'], [contenteditable='true']",
    "content_placeholder": "p[data-placeholder*='输入正文描述']",
    "title_overflow": "div.title-container div.max_suffix",
    "content_overflow": "div.edit-container div.length-error",
    # 话题（REF publish.go inputTag）
    "topic_container": "#creator-editor-topic-container",
    "topic_item": "#creator-editor-topic-container .item",
    # 发布按钮（REF publish.go findPublishButton）
    "publish_btn_new": "xhs-publish-btn",
    "publish_btn_old": ".publish-page-publish-btn button.bg-red",
}

PROFILE_NAME = "XiaohongshuProfile"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QR_OUT = PROJECT_ROOT / "outputs" / "_login" / "xhs-login-qrcode.png"

# 启动参数 / Cloak 数据目录 / 指纹文件名常量统一在 real_browser（值不变）
LAUNCH_ARGS = real_browser.LAUNCH_ARGS
IGNORE_DEFAULT_ARGS = real_browser.IGNORE_DEFAULT_ARGS
CLOAK_IGNORE_DEFAULT_ARGS = real_browser.CLOAK_IGNORE_DEFAULT_ARGS
CLOAK_DATA_DIR = real_browser.CLOAK_DATA_DIR
FINGERPRINT_FILE = real_browser.FINGERPRINT_FILE


# --------------------------------------------------------------------------- #
# 纯函数（可离线自测）
# --------------------------------------------------------------------------- #
def calc_title_length(s: str) -> int:
    """小红书标题长度：UTF-16 码元非 ASCII 计 2、ASCII 计 1，再 (n+1)//2 上取整。
    REF pkg/xhsutil/title.go CalcTitleLength。20 全角字 → 20。"""
    utf16 = s.encode("utf-16-le")
    byte_len = 0
    for i in range(0, len(utf16), 2):
        code = utf16[i] | (utf16[i + 1] << 8)
        byte_len += 2 if code > 127 else 1
    return (byte_len + 1) // 2


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _abspaths(csv: str | None) -> list[str]:
    """逗号分隔路径 → 绝对路径列表，校验存在。"""
    if not csv:
        return []
    out = []
    for raw in csv.split(","):
        raw = raw.strip()
        if not raw:
            continue
        p = Path(raw).expanduser().resolve()
        if not p.is_file():
            _die(f"文件不存在：{p}")
        out.append(str(p))
    return out


def _profile_dir(base: str | None) -> Path:
    root = Path(base).expanduser() if base else Path.home() / ".easel-browser-profiles"
    return root / PROFILE_NAME


def _cloak_executable() -> Path | None:
    """本机已装的 CloakBrowser 内核（逻辑在 real_browser.cloak_executable）。

    无头 Playwright Chromium 会被小红书 300012；同一出口下 Cloak 无头已实测能出码。
    """
    return real_browser.cloak_executable()


def _host_fingerprint_platform() -> str:
    """Cloak 指纹的平台身份（逻辑在 real_browser）。"""
    return real_browser.host_fingerprint_platform()


def _read_fingerprint(path: Path) -> dict | None:
    return real_browser.read_fingerprint(path)


def _account_fingerprint(base: str | None) -> dict:
    """这个账号固定用的 Cloak 指纹，存在 XiaohongshuProfile/.easel-fingerprint.json；第一次用时生成，
    之后永不重新生成（平台身份与本机不符除外）。实现见 real_browser.account_fingerprint。"""
    return real_browser.account_fingerprint(
        _profile_dir(base), fingerprint_file=FINGERPRINT_FILE, platform_label="小红书",
        host_fn=_host_fingerprint_platform)


def browser_engine() -> tuple[str, str]:
    """小红书实际会用哪个浏览器：("cloak", 可执行文件) / ("chrome"|"msedge", "") / ("bundled", "")。"""
    return real_browser.resolve_engine("EASEL_XHS_BROWSER", cloak_fn=_cloak_executable,
                                       channel_fn=_browser_channel)


def _browser_choice() -> str:
    """EASEL_XHS_BROWSER=chrome 跳过 Cloak 直接用本机 Chrome；默认 auto（Cloak 优先）。"""
    return (os.environ.get("EASEL_XHS_BROWSER") or "auto").strip().lower()


class _ProfileLock:
    """同一份 XiaohongshuProfile 不能同时开两个 Cloak：账号页 whoami 和登录会把内核打成 exit 21。"""

    def __init__(self, profile: Path):
        self.path = profile / ".easel.lock"
        self.fd: int | None = None

    def acquire(self, timeout_s: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + timeout_s
        last: OSError | None = None
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                os.lseek(self.fd, 0, os.SEEK_SET)
                os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
                return
            except OSError as e:
                last = e
                if self.fd is not None:
                    try:
                        os.close(self.fd)
                    except OSError:
                        pass
                    self.fd = None
                if time.time() >= deadline:
                    raise TimeoutError(f"登录目录正被占用：{self.path}") from last
                time.sleep(0.4)

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


def _clear_stale_chrome_locks(profile: Path) -> None:
    real_browser.clear_stale_chrome_locks(profile)


def _browser_channel() -> str | None:
    """本机装的正式版浏览器：Chrome 优先，其次 Edge；都没有返回 None。"""
    return real_browser.browser_channel()


def _risk_blocked(page) -> bool:
    try:
        url = page.url or ""
        title = page.title() or ""
        return ("website-login/error" in url or "error_code=300012" in url
                or "安全限制" in title)
    except Exception:
        return False


def _is_logged_in(page) -> bool:
    try:
        if page.query_selector(SELECTORS["login_ok"]) is not None:
            return True
    except Exception:
        pass
    try:
        url = (page.url or "").split("?", 1)[0]
        if "creator.xiaohongshu.com" in url and "/login" not in url:
            return True
    except Exception:
        pass
    return False


def _proxy(explicit: str | None, disable: bool) -> str | None:
    """外网代理：--no-proxy 关；--proxy 显式；否则取 env（小红书是外网，默认需代理）。"""
    if disable:
        return None
    if explicit:
        return explicit
    return os.environ.get("https_proxy") or os.environ.get("http_proxy") \
        or os.environ.get("EASEL_PROXY")


# --------------------------------------------------------------------------- #
# 浏览器动作（移植自 xiaohongshu-mcp，需 playwright）
# --------------------------------------------------------------------------- #
def _human_type(page, locator, text: str) -> None:
    """鼠标点进输入框，再按真人节奏输入（human_input.type_text）。"""
    human_input.click(page, locator)
    human_input.pause(page, 200, 600)
    human_input.type_text(page, text)


def _click_publish_tab(page, tabname: str) -> None:
    """点「上传图文/上传视频」tab：重试 15s + 遮挡检测 + 移弹层。REF mustClickPublishTab。"""
    page.wait_for_selector(SELECTORS["upload_content"], timeout=15000)
    deadline = time.time() + 15
    while time.time() < deadline:
        tabs = page.query_selector_all(SELECTORS["creator_tab"])
        for tab in tabs:
            try:
                if not tab.is_visible():
                    continue
                if (tab.inner_text() or "").strip() != tabname:
                    continue
            except Exception:
                continue
            # 遮挡检测（REF isElementBlocked：elementFromPoint 命中的是不是自己）
            blocked = tab.evaluate(
                """(el) => { const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) return true;
                    const t = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                    return !(t === el || el.contains(t)); }""")
            if blocked:
                cover = page.query_selector(SELECTORS["pop_cover"])
                if cover:
                    cover.evaluate("el => el.remove()")
                page.wait_for_timeout(200)
                continue
            human_input.click(page, tab)
            return
        page.wait_for_timeout(200)
    _die(f"未找到发布 TAB：{tabname}（页面结构可能已变，检查 SELECTORS.creator_tab）")


def _upload_images(page, paths: list[str]) -> None:
    """逐张上传并等预览出现（≤60s/张）。REF uploadImages/waitForUploadComplete。"""
    for i, path in enumerate(paths):
        sel = SELECTORS["upload_input_first"] if i == 0 else SELECTORS["upload_input_more"]
        page.set_input_files(sel, path)
        print(f"  上传图片 {i+1}/{len(paths)}: {path}", file=sys.stderr)
        deadline = time.time() + 60
        while time.time() < deadline:
            if len(page.query_selector_all(SELECTORS["img_preview"])) >= i + 1:
                break
            page.wait_for_timeout(500)
        else:
            _die(f"第 {i+1} 张图片上传超时（60s）")
        page.wait_for_timeout(1000)


def _upload_video(page, path: str) -> None:
    """上传视频，等发布按钮可点击（≤10min = 处理完成）。REF publish_video.go uploadVideo。"""
    sel = SELECTORS["upload_input_first"]
    if not page.query_selector(sel):
        sel = SELECTORS["upload_input_more"]
    page.set_input_files(sel, path)
    print(f"  上传视频：{path}（等待处理，最长 10min）", file=sys.stderr)
    _wait_publish_clickable(page, timeout_s=600)


def _content_element(page):
    """正文输入框：先 ql-editor（旧版），再 contenteditable（新版），最后退回 placeholder 定位。
    REF getContentElement。小红书已把正文编辑器从 Quill 换成 contenteditable。"""
    el = page.query_selector(SELECTORS["content_quill"])
    if el:
        return el
    el = page.query_selector(SELECTORS["content_editable"])
    if el:
        return el
    ph = page.query_selector(SELECTORS["content_placeholder"])
    if ph:
        cur = ph
        for _ in range(5):
            parent = cur.evaluate_handle("el => el.parentElement").as_element()
            if not parent:
                break
            role = parent.get_attribute("role") or ""
            if role == "textbox" or parent.get_attribute("contenteditable") == "true":
                return parent
            cur = parent
    return None


def _check_overflow(page) -> None:
    """标题/正文超限：读平台自身的溢出提示元素。REF checkTitleMaxLength/checkContentMaxLength。"""
    for key, name in (("title_overflow", "标题"), ("content_overflow", "正文")):
        el = page.query_selector(SELECTORS[key])
        if el and el.is_visible():
            _die(f"{name}超出平台长度限制：{(el.inner_text() or '').strip()}")


def _input_tags(page, content_el, tags: list[str]) -> None:
    """话题：正文末尾输 # + 联想下拉点第一项，真绑话题。REF inputTag。

    注意：必须把 # 与话题名**连续输入**、中途不能再 click 正文——否则光标会被挪走，
    # 和话题名被拆开，小红书识别不到连续的 #话题 token，联想不出、绑不上话题。
    """
    if not tags:
        return
    human_input.click(page, content_el)
    # 光标移到正文末尾，避免 # 插到正文中间。Control+End 在 macOS 上不是「到文末」，直接设选区
    content_el.evaluate("""(el) => { const r = document.createRange(); r.selectNodeContents(el);
        r.collapse(false); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }""")
    page.wait_for_timeout(400)
    for tag in tags:
        tag = tag.lstrip("#").strip()
        if not tag:
            continue
        page.keyboard.type(" ")          # 与正文/上一话题分隔，确保 # 起一个新 token
        page.keyboard.type("#")
        page.wait_for_timeout(300)
        for ch in tag:                   # 逐字输入话题名——不再 click（避免移光标拆开 #话题）
            page.keyboard.type(ch)
            page.wait_for_timeout(random.randint(30, 110))
        page.wait_for_timeout(1000)
        item = page.query_selector(SELECTORS["topic_item"])
        if item:
            human_input.click(page, item)   # 点联想第一项 = 真正绑定话题
        else:
            page.keyboard.type(" ")      # 无联想则退化为空格分隔（至少保留 #文字）
        page.wait_for_timeout(500)


def _wait_publish_clickable(page, timeout_s: int = 15):
    """等发布按钮可点击（新旧兼容）。REF findPublishButton/waitForPublishButtonClickable。"""
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        for w in page.query_selector_all(SELECTORS["publish_btn_new"]):
            if not w.is_visible():
                continue
            if (w.get_attribute("is-publish") or "") == "false":
                continue
            if (w.get_attribute("submit-disabled") or "") == "true":
                last = "新版发布按钮不可点击"
                continue
            return ("new", w)
        for b in page.query_selector_all(SELECTORS["publish_btn_old"]):
            if not b.is_visible():
                continue
            if b.get_attribute("disabled") is not None:
                last = "旧版发布按钮 disabled"
                continue
            if (b.get_attribute("aria-disabled") or "") == "true":
                last = "旧版发布按钮 aria-disabled"
                continue
            return ("old", b)
        page.wait_for_timeout(1000)
    _die(f"等待发布按钮可点击超时{('：' + last) if last else ''}")


def _diag_after_publish(page) -> str:
    """点发布后失败时，抓屏幕上可见的弹框/报错/toast 文案，供排错。
    截图默认不存（正常使用不截图）；排错时设 EASEL_PUBLISH_DEBUG=1 才会存失败截图。"""
    bits = []
    for sel in (".d-modal", "[role=dialog]", "[class*=modal]", "[class*=dialog]",
                ".d-message", ".d-toast", "[class*=toast]", "[class*=error]", "[class*=tip]"):
        try:
            for el in page.query_selector_all(sel):
                if el.is_visible():
                    t = (el.inner_text() or "").strip().replace("\n", " / ")
                    if t and t not in " ".join(bits):
                        bits.append(f"[{sel}] {t[:120]}")
        except Exception:
            pass
    shot = ""
    if os.environ.get("EASEL_PUBLISH_DEBUG"):
        try:
            out = PROJECT_ROOT / "outputs" / "_login" / "xhs-publish-fail.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out))
            shot = f"（调试截图见 {out}）"
        except Exception:
            pass
    return ("屏幕可见元素：" + " | ".join(bits[:6]) if bits else "屏幕无可识别弹框/报错") + shot


def _confirm_publish_dialog(page) -> None:
    """点发布后若弹二次确认框，点其确认按钮（保守：仅当可见且文案匹配）。"""
    deadline = time.time() + 5
    while time.time() < deadline:
        for b in page.query_selector_all("button, .d-button, [role=button]"):
            try:
                if not b.is_visible():
                    continue
                tx = (b.inner_text() or "").strip()
                if tx in ("确认发布", "确定发布", "继续发布", "立即发布", "确认", "确定"):
                    human_input.click(page, b)
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                pass
        page.wait_for_timeout(500)


def _wait_publish_success(page, timeout_s: int = 40) -> None:
    """发布成功校验：小红书发布成功后**原地清空表单回到上传页**（不换 URL）。
    成功信号任一：跳离 /publish/publish、出现「成功」toast、或编辑表单已重置（标题框+图片预览消失）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if "/publish/publish" not in page.url:
            print(f"✅ 发布成功，已跳转：{page.url}")
            return
        for sel in (".d-message", ".d-toast", "[class*=toast]", "[class*=message]"):
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and "成功" in (el.inner_text() or ""):
                    print("✅ 发布成功（检测到成功提示）")
                    return
            except Exception:
                pass
        # 表单已重置：填过的标题框 + 上传的图片预览都消失 = 已提交回到空上传页
        try:
            if (not page.query_selector(SELECTORS["title_input"])
                    and not page.query_selector(SELECTORS["img_preview"])):
                print("✅ 发布成功（编辑表单已清空复位）")
                return
        except Exception:
            pass
        page.wait_for_timeout(500)
    _die("发布未确认成功：点击发布后未跳离发布页/未见成功提示。" + _diag_after_publish(page))


def _normalize_content(text: str) -> str:
    """小红书编辑器「不支持连续空行输入」——把 2+ 连续空行压成单个空行，行尾空白清掉。"""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)      # 行尾空白
    text = re.sub(r"\n{3,}", "\n\n", text)       # 连续空行（3+ 换行）→ 一个空行
    return text.strip("\n")


# 「笔记含 AI 合成内容」声明。小红书要求 AI 生成/合成的内容主动声明；入口在发布页下方的
# 「内容类型声明」下拉里（有的版本收在「更多设置」后面）。按文字定位，改版时改这里。
AI_DECLARE_ENTRY_TEXTS = ("添加内容类型声明", "内容类型声明")
AI_DECLARE_MORE_TEXTS = ("更多设置",)
AI_DECLARE_OPTION_TEXT = "笔记含AI合成内容"
AI_DECLARE_FAILED_MSG = ("没能勾上「笔记含AI合成内容」声明，已停在发布前、没有发出去（页面可能改版）。"
                         "可以在打开的窗口里手动勾选后自己点发布；确认内容不是 AI 生成的，加 --no-ai-declare 再发。")


def _visible_text(page, text: str):
    """页面上文字恰好是 text 的第一个可见元素（Locator），没有返回 None。"""
    loc = page.get_by_text(text, exact=True)
    try:
        for i in range(min(loc.count(), 6)):
            el = loc.nth(i)
            if el.is_visible():
                return el
    except Exception:
        return None
    return None


# 「笔记含AI合成内容」这几个字出现在表单上（不在还开着的下拉/选项列表里）= 已经选上。
_AI_DECLARED_JS = """(text) => {
    const pop = "[role=listbox],[role=option],[role=menu],[class*=dropdown],[class*=popover],"
        + "[class*=option],[class*=menu]";
    return Array.from(document.querySelectorAll('body *')).some(e =>
        e.children.length === 0 && (e.textContent || '').trim() === text
        && e.offsetParent !== null && !e.closest(pop));
}"""


def _ai_declared(page) -> bool:
    try:
        return bool(page.evaluate(_AI_DECLARED_JS, AI_DECLARE_OPTION_TEXT))
    except Exception:
        return False


def _declare_ai(page) -> bool:
    """勾上「笔记含AI合成内容」。只有确认表单上显示了选中值（不是下拉里的选项）才返回 True；
    判断不了一律当没勾上——宁可停下不发，也不能没声明就发出去。
    选择器按文字猜的，还没在真机上校准过；改版或首次跑不通就停在发布前（退出码 6）。"""
    if _ai_declared(page):
        return True
    entry = None
    for _ in range(2):
        for t in AI_DECLARE_ENTRY_TEXTS:
            entry = _visible_text(page, t)
            if entry:
                break
        if entry:
            break
        more = None
        for t in AI_DECLARE_MORE_TEXTS:
            more = _visible_text(page, t)
            if more:
                break
        if not more:
            human_input.scroll(page, 600)
            continue
        human_input.click(page, more)
        human_input.pause(page, 500, 1000)
    if not entry:
        return False
    human_input.click(page, entry)
    human_input.pause(page, 500, 1000)
    option = _visible_text(page, AI_DECLARE_OPTION_TEXT)
    if not option:
        return False
    human_input.click(page, option)
    human_input.pause(page, 600, 1200)
    return _ai_declared(page)


def _fill_and_submit(page, title, content, tags, declare_ai: bool = True, on_click=None):
    """标题→正文→话题→AI 声明→长度校验→发布→成功校验。
    on_click：点下发布按钮后立刻调用（记频率闸门）——之后等成功提示超时，帖子也可能已经发出去了。"""
    content = _normalize_content(content)         # 修连续空行导致的发布失败
    title_el = page.query_selector(SELECTORS["title_input"])
    if not title_el:
        _die("未找到标题输入框（检查 SELECTORS.title_input）")
    _human_type(page, title_el, title)
    human_input.pause(page, 400, 1200)

    content_el = _content_element(page)
    if not content_el:
        _die("未找到正文输入框（检查 SELECTORS.content_*）")
    _human_type(page, content_el, content)
    human_input.pause(page, 500, 1500)
    human_input.click(page, title_el)  # REF waitAndClickTitleInput：回点标题增强稳定性
    _input_tags(page, content_el, tags)

    if declare_ai and not _declare_ai(page):
        _die(AI_DECLARE_FAILED_MSG, 6)

    _check_overflow(page)

    kind, btn = _wait_publish_clickable(page, 15)
    human_input.pause(page, 1500, 4000)   # 发之前回看一眼
    if kind == "new":
        # xhs-publish-btn 是宽横条(闭合 Shadow DOM)，内含[暂存离开][发布]两个按钮；
        # 点 host 中心会落在两按钮间隙→无效。发布按钮在右侧约 62% 处（实测像素为品牌红）。
        human_input.click(page, btn, x_frac=0.62)
    else:
        human_input.click(page, btn)
    if on_click:
        on_click()
    page.wait_for_timeout(1000)
    _confirm_publish_dialog(page)   # 若弹二次确认框，点确认
    _wait_publish_success(page, 40)


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def _allow_headless() -> bool:
    """EASEL_XHS_HEADLESS=1：允许无头（只给没有桌面的机器用，很容易被小红书识别成脚本）。"""
    return real_browser.allow_headless("EASEL_XHS_HEADLESS")


def _launch(p, headed: bool, base: str | None, proxy: str | None):
    """开小红书用的浏览器（实现见 real_browser.launch）。默认一律开窗口；
    内核优先 CloakBrowser（账号固定指纹、数据在登录目录的 cloak-browser/ 子目录），
    其次本机正式版 Chrome / Edge，最后才是 Playwright 自带的 Chromium。"""
    return real_browser.launch(
        p, profile_dir=_profile_dir(base), headed=headed, proxy=proxy,
        fingerprint_file=FINGERPRINT_FILE, platform_label="小红书",
        headless_env="EASEL_XHS_HEADLESS", browser_env="EASEL_XHS_BROWSER",
        engine=browser_engine(), fingerprint_fn=lambda: _account_fingerprint(base),
        chrome_hint="xhs_publish.py login 或 Web 账号页「登录」")


def browser_report(base: str | None = None) -> tuple[bool, list[str]]:
    """check 用：小红书会用哪个浏览器、能不能用。Cloak / 本机 Chrome 能用时不要求 Playwright 自带内核。"""
    lines: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
        lines.append("✅ playwright 已安装")
    except Exception as e:
        return False, [f"❌ playwright 不可用：{e}"]
    engine, exe = browser_engine()
    fp_path = _profile_dir(base) / FINGERPRINT_FILE
    if engine == "cloak":
        lines.append(f"✅ CloakBrowser：{exe}（小红书操作都开它的窗口）")
        lines.append(f"   固定指纹：{'已生成 ' + str(fp_path) if fp_path.is_file() else '第一次打开时生成，存到 ' + str(fp_path)}")
        lines.append(f"   浏览器数据：{_profile_dir(base) / CLOAK_DATA_DIR}（与 Chrome 的登录态分开，换浏览器要重新扫码）")
        return True, lines
    if engine in ("chrome", "msedge"):
        why = "EASEL_XHS_BROWSER=chrome" if _browser_choice() == "chrome" else "没装 CloakBrowser"
        lines.append(f"✅ 本机浏览器：{'Google Chrome' if engine == 'chrome' else 'Microsoft Edge'}"
                     f"（{why}，小红书操作都开它的窗口）")
        return True, lines
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
        ok = bool(path and Path(path).exists())
    except Exception:
        ok = False
    lines.append("⚠️ 没找到 CloakBrowser 和本机 Chrome / Edge：会用 Playwright 自带的 Chromium，更容易被小红书识别成脚本"
                 if ok else "❌ 没有可用的浏览器：装 CloakBrowser（pip install cloakbrowser && python -m cloakbrowser install）或 Google Chrome")
    return ok, lines


def cmd_check(_a) -> int:
    ok, lines = browser_report()
    for ln in lines:
        print(ln)
    if _allow_headless():
        print("⚠️ EASEL_XHS_HEADLESS=1：允许无头运行，很容易被小红书识别成脚本")
    print(f"登录态目录：{_profile_dir(None)}")
    return 0 if ok else 3


def _wait_sel(page, selector: str, timeout_ms: int = 15000, what: str = "元素") -> object:
    """等待选择器出现，容忍登录页导航竞态。

    小红书登录页会多次跳转（探索页 → 登录引导），Playwright 在导航瞬间
    查询旧 DOM 会抛 "Execution context was destroyed"——这不是选择器错误，
    是页面在跳。重试直到 deadline 而非一次失败就报错。
    """
    deadline = time.time() + timeout_ms / 1000
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            el = page.wait_for_selector(selector, timeout=2500)
            if el is not None:
                return el
        except Exception as e:  # navigation / context destroyed / timeout
            last_err = e
        page.wait_for_timeout(800)
    if last_err is not None and "Timeout" not in type(last_err).__name__:
        raise last_err
    raise TimeoutError(f"等待 {what} 超时（{timeout_ms}ms）：{selector}")


def _query_safe(page, selector: str):
    """query_selector 的容错版：导航瞬间 context 被销毁会抛异常，这里吞掉返回
    None。裸 query_selector 在页面跳转期会崩，用它做一次性登录态探测更稳。"""
    try:
        return page.query_selector(selector)
    except Exception:
        return None


# 登录完成后，到底有没有真的落下登录态：
# 本机实测过「扫码后页面已是登录态 → 立刻关浏览器」，重开 profile 里却没有 web_session、创作平台
# 退回 /login —— 脚本还打印了「登录成功，cookie 已持久化」。所以先等登录 cookie 出现再关，
# 关完再用同一份 profile 重开一次亲眼确认，确认过了才报成功。
LOGIN_COOKIE = "web_session"      # 小红书的登录凭证 cookie（.xiaohongshu.com，持久化，约一年有效）
LOGIN_COOKIE_WAIT_S = 10
CREATOR_SETTLE_S = 3              # 创作平台登录那条路径不认得它的 cookie 名，只能多留几秒让它落盘
# 重开确认时最多等多久看到发布页真渲染出来。只在「确认不了」时才等满（正常 1~3 秒就看到了），
# 所以给慢网留足余量：等太短会把已保存的登录误报成没保存。
VERIFY_SETTLE_S = 15
WEB_LOGIN_PLATFORM = "xiaohongshu"   # = web/app.py LOGIN_RUNNERS 的键，Web 账号页读 outputs/_login/<键>.json

RISK_BLOCKED_MSG = ("小红书判定当前网络为风险 IP（安全限制 300012「IP存在风险，请切换可靠网络环境」）——"
                    "二维码在此环境无法弹出。解决：①去掉 EASEL_XHS_HEADLESS，在有桌面的本机开窗口登录"
                    "（或加 `--headed-fallback`，被拦时自动改开窗口）；"
                    "②用干净/家宽 IP 的代理 `--proxy socks5://...`；"
                    "③在正常网络的机器上 login 拿到登录态，再把持久化目录 {profile} 整个拷到本机复用。")
HEADED_FALLBACK_MSG = "小红书拦截了无头浏览器，已弹出浏览器窗口，请在窗口里扫码登录，不要关掉它。"
NOT_SAVED_MSG = "登录看似成功但登录态没能保存，请重试"
VERIFY_FAILED_MSG = ("登录已完成，但确认登录态时浏览器/网络出错：{err}。"
                     "可稍后在账号页刷新重新校验（或跑 whoami）；仍显示未登录就再登录一次（已保存会直接通过）")
LOGIN_CRASH_PREFIX = "登录窗口被关闭或浏览器异常："
WINDOW_CLOSED_MSG = (LOGIN_CRASH_PREFIX + "登录窗口已关闭，登录没有完成。请重新登录"
                     "（刚才若已扫码成功，重新登录会直接显示已登录）")


class _HeadlessBlocked(Exception):
    """无头模式被 300012 风控拦截，且调用方允许改开有头窗口重来（--headed-fallback）。"""


class _WindowClosed(Exception):
    """登录窗口被用户关掉了（或浏览器崩了），页面已不可用。"""


_NEEDS_VERIFY = object()   # _login_attempt 的返回值：页面已是登录态，要关浏览器后重开确认


def _short_err(e: BaseException, limit: int = 160) -> str:
    text = " ".join(str(e).split())
    text = f"{type(e).__name__}: {text}" if text else type(e).__name__
    return text if len(text) <= limit else text[:limit] + "…"


def _login_crash_msg(e: BaseException) -> str:
    """登录中途的意外异常 → 给 Web / 终端的一句话。窗口被关单独说清楚，其余带上异常摘要。"""
    if isinstance(e, _WindowClosed) or "TargetClosed" in type(e).__name__ \
            or "has been closed" in str(e):
        return WINDOW_CLOSED_MSG
    return LOGIN_CRASH_PREFIX + _short_err(e)


def _ensure_window_open(page) -> None:
    """窗口被关后 Playwright 的查询会被 _is_logged_in 等吞掉、只有等待才抛异常；先主动查一下，
    把「窗口被关」明确报出来，而不是一直当成「还没扫码」空等到超时。"""
    try:
        closed = page.is_closed()
    except Exception:
        closed = False
    if closed:
        raise _WindowClosed()


def _close_quietly(ctx) -> None:
    """关浏览器。窗口已被用户关掉 / 浏览器已崩时 close 也可能抛，不能让它盖掉真正的结果或异常。"""
    try:
        ctx.close()
    except Exception as e:  # noqa: BLE001
        print(f"关闭浏览器时出错（忽略）：{_short_err(e)}", file=sys.stderr)


def _has_login_cookie(cookies) -> bool:
    """cookies（Playwright context.cookies() 的列表）里有没有小红书的登录凭证。纯函数，便于单测。"""
    for c in cookies or ():
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain") or "").lstrip(".")
        if (c.get("name") == LOGIN_COOKIE and c.get("value")
                and (domain == "xiaohongshu.com" or domain.endswith(".xiaohongshu.com"))):
            return True
    return False


def _settle_login_cookies(ctx, page) -> bool:
    """页面刚变成登录态：等登录 cookie 真出现再放行关浏览器。返回是否等到了。
    这期间窗口被关 → _WindowClosed / TargetClosedError 往上抛，由 cmd_login 落 error 终态。"""
    deadline = time.time() + LOGIN_COOKIE_WAIT_S
    while time.time() < deadline:
        _ensure_window_open(page)
        try:
            has_cookie = _has_login_cookie(ctx.cookies())
        except Exception:
            has_cookie = False
        if has_cookie:
            page.wait_for_timeout(1000)   # 出现后再留一口气，让 Chromium 把它写进 profile
            return True
        page.wait_for_timeout(500)
    try:
        on_creator = "creator.xiaohongshu.com" in (page.url or "")
    except Exception:
        on_creator = False
    if on_creator:
        page.wait_for_timeout(CREATOR_SETTLE_S * 1000)
    return False


def _publish_page_ready(page) -> bool:
    """创作平台发布页以登录态真渲染出来了：发布流程第一步就要等的上传区 / 发布 tab 在页面上。"""
    url = (page.url or "").split("?", 1)[0]
    if "creator.xiaohongshu.com" not in url or "/login" in url:
        return False
    return any(_query_safe(page, SELECTORS[k]) is not None for k in ("upload_content", "creator_tab"))


def _verify_saved_login(p, base: str | None, proxy: str | None) -> bool:
    """用同一份 profile 重开创作平台发布页，看到发布页真渲染出来（正向信号）才算登录态已保存。

    不能只看「URL 没带 /login」：未登录时是前端等接口 401 才跳 /login，慢网下能拖好几秒，
    URL 在跳走前一直是发布页 —— 那样会把没存上的登录报成成功。"""
    ctx = _launch(p, headed=False, base=base, proxy=proxy)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=45000)
        deadline = time.time() + VERIFY_SETTLE_S
        seen = 0
        while time.time() < deadline:
            page.wait_for_timeout(1000)
            if "/login" in (page.url or ""):
                return False            # 被踢回登录页：登录态没存上
            seen = seen + 1 if _publish_page_ready(page) else 0
            if seen >= 2:               # 连着两次都在，不是跳走前的一闪
                return True
        return False                    # 等满也没看到发布页：确认不了就不报成功
    finally:
        _close_quietly(ctx)


def _web_login_marker_path(a) -> Path | None:
    """CLI 直跑登录（没有 --status-file、用默认登录目录）时，也要让 Web 账号页知道已登录。"""
    if getattr(a, "status_file", None) or getattr(a, "profile_base", None):
        return None   # Web 发起的登录自己写这个文件；别的登录目录不是 Web 账号页看的那份
    try:
        import output_paths
        return output_paths.validate_output_path(
            output_paths.OUTPUTS_DIR / "_login" / f"{WEB_LOGIN_PLATFORM}.json", allow_system=True)
    except Exception:
        return None


def _report_login_success(a, sf: str | None, message: str, line: str = "") -> None:
    """先落终态（状态文件 + Web 登录标记），最后才打印 line：打印出错（如 Windows 控制台编码
    装不下 emoji）也不能让状态停在 verifying、更不能被当成登录异常改写成 error。"""
    login_state.write_status(sf, "success", message)
    marker = _web_login_marker_path(a)
    if marker is not None:
        try:
            login_state.write_status(str(marker), "success", message)
        except OSError:
            pass
    if line:
        try:
            print(line)
        except (UnicodeError, OSError):
            pass


def _login_attempt(p, a, *, headed: bool, sf: str | None, qr_out: Path, timeout_s: int,
                   window_msg: str) -> object:
    """跑一轮登录：返回退出码，或 _NEEDS_VERIFY（页面已是登录态，交给调用方关浏览器后确认）。
    无头被风控拦、且允许改开窗口时抛 _HeadlessBlocked（finally 先把这个浏览器关掉）。"""
    fallback = bool(getattr(a, "headed_fallback", False)) and not headed
    try:
        ctx = _launch(p, headed=headed, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy))
    except Exception as e:
        login_state.write_status(sf, "error", "浏览器没能打开。请关闭弹窗，等 10 秒再点登录，不要连点。")
        _die(f"启动浏览器失败：{e}", 1)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def risk_blocked_headless() -> None:
        if fallback:
            raise _HeadlessBlocked()
        login_state.write_status(sf, "error", "IP 存在风险，需干净网络/代理")
        _die(RISK_BLOCKED_MSG.format(profile=_profile_dir(a.profile_base)), 4)

    try:
        if headed:
            login_state.write_status(sf, "window_login", window_msg)
        try:
            page.goto(EXPLORE_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            login_state.write_status(sf, "error", f"打不开小红书页面（{type(e).__name__}）")
            _die(f"打开 {EXPLORE_URL} 失败：{e}", 1)

        # 等待页面稳定并完成可能的跳转（登录引导 / 风险拦截 / 已登录态）
        for _ in range(10):
            page.wait_for_timeout(800)
            if _risk_blocked(page):
                if headed:
                    try:
                        page.goto(CREATOR_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
                    except Exception as e:
                        login_state.write_status(sf, "error", f"打不开小红书创作平台（{type(e).__name__}）")
                        _die(f"打开 {CREATOR_LOGIN_URL} 失败：{e}", 1)
                    login_state.write_status(
                        sf, "window_login",
                        "首页被风控拦截了，已改开创作平台。请在弹出的浏览器窗口里扫码或短信登录。")
                    break
                risk_blocked_headless()
            try:
                if _is_logged_in(page):
                    break
            except Exception:
                pass

        if _is_logged_in(page):
            _report_login_success(a, sf, "已登录", line="✅ 已登录（登录态已在持久化目录），无需扫码")
            return 0

        # 抠二维码存 PNG（元素截图，不依赖 src 格式，最稳）
        qr = None
        try:
            qr = _wait_sel(page, SELECTORS["qrcode"], 20000, "登录二维码")
        except Exception:
            if _risk_blocked(page) and not headed:
                risk_blocked_headless()
            if not headed:
                login_state.write_status(sf, "error", "未找到登录二维码")
                _die("未找到登录二维码（页面结构可能已变，检查 SELECTORS.qrcode），"
                     "或已弹别的登录方式——可加 --headed 观察")
            login_state.write_status(
                sf, "window_login",
                "请在弹出的浏览器窗口里完成登录（扫码或短信），不要关掉那个窗口。")
        if qr:
            qr_out.parent.mkdir(parents=True, exist_ok=True)
            qr.screenshot(path=str(qr_out))
            if headed:
                login_state.write_status(
                    sf, "window_login",
                    "请在弹出的浏览器窗口里扫码，不要关掉那个窗口。也可以扫下面这张图。",
                    qr=str(qr_out))
            else:
                login_state.write_status(sf, "qr_ready", "二维码已就绪，请扫码", qr=str(qr_out))
            print(f"📱 二维码已保存：{qr_out}")
            print("   用小红书 App 扫码登录。若走 Easel Web UI，可在 outputs 里查看这张图。")
            print("   （二维码有时效，约几分钟；过期请重跑 login）")
        print(f"⏳ 等待扫码确认（最长 {timeout_s}s）...", file=sys.stderr)

        # 轮询登录成功（扫码成功瞬间页面会跳转，_is_logged_in 自己吞掉查询异常、重试继续等）。
        # 窗口被关：_ensure_window_open 或等待本身抛异常，由 cmd_login 统一落 error 终态。
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            _ensure_window_open(page)
            if _is_logged_in(page):
                # 这里还不能报成功：先等登录 cookie 落下，关浏览器后再重开确认（见 _verify_saved_login）
                if not _settle_login_cookies(ctx, page):
                    print(f"⚠️ 页面已是登录态，但没等到 {LOGIN_COOKIE} cookie；关掉浏览器后重开确认…",
                          file=sys.stderr)
                return _NEEDS_VERIFY
            page.wait_for_timeout(2000)
        login_state.write_status(sf, "expired", "二维码超时未扫")
        print(f"⏱️ {timeout_s}s 内未检测到登录成功（二维码可能已过期）。请重跑 login 再扫。",
              file=sys.stderr)
        return 1
    finally:
        _close_quietly(ctx)


def _login_flow(p, a, sf: str | None, qr_out: Path, timeout_s: int) -> int:
    try:
        result = _login_attempt(p, a, headed=bool(a.headed) or not _allow_headless(), sf=sf, qr_out=qr_out,
                                timeout_s=timeout_s,
                                window_msg="请在弹出的浏览器窗口里扫码，不要关掉那个窗口。")
    except _HeadlessBlocked:
        # 只在 EASEL_XHS_HEADLESS=1 时走到这里：小红书拦「未登录 + 无头」，有头窗口不拦。
        # 所以被拦时不必放弃，改开窗口让用户在窗口里扫一次，登录态落进同一份 profile。
        login_state.write_status(sf, "window_login", HEADED_FALLBACK_MSG)
        print(f"⚠️ {HEADED_FALLBACK_MSG}", file=sys.stderr)
        result = _login_attempt(p, a, headed=True, sf=sf, qr_out=qr_out, timeout_s=timeout_s,
                                window_msg=HEADED_FALLBACK_MSG)
    if result is not _NEEDS_VERIFY:
        return result
    login_state.write_status(sf, "verifying", "登录成功，正在确认登录态已保存…")
    try:
        saved = _verify_saved_login(p, a.profile_base, _proxy(a.proxy, a.no_proxy))
    except Exception as e:   # noqa: BLE001
        # 重开浏览器 / 打开发布页本身出错：说明不了登录态没存上，别报 NOT_SAVED 吓人重扫；
        # 也不报成功（没确认过）。给出可操作的下一步。
        msg = VERIFY_FAILED_MSG.format(err=_short_err(e))
        login_state.write_status(sf, "error", msg)
        print(f"⚠️ {msg}", file=sys.stderr)
        return 1
    if not saved:
        login_state.write_status(sf, "error", NOT_SAVED_MSG)
        print(f"❌ {NOT_SAVED_MSG}（重开浏览器后创作平台发布页仍打不开，要求登录）", file=sys.stderr)
        return 1
    try:
        qr_out.unlink()  # 登录成功清掉二维码图，避免误扫过期码
    except OSError:
        pass
    _report_login_success(a, sf, "登录成功", line="✅ 登录成功，已重开浏览器确认登录态已保存，下次免登")
    return 0


def cmd_login(a) -> int:
    """开 Chrome 窗口登录（二维码也抠成 PNG 供 Web 显示），登录成功并确认登录态已落盘后才报成功。
    REF login.go FetchQrcodeImage/WaitForLogin。远程无桌面环境靠图片扫码，非有头窗口；
    --headed-fallback：仅 EASEL_XHS_HEADLESS=1 时有用，无头被风控拦就改开窗口。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _die(f"需要 playwright：{e}", 3)

    qr_out = Path(a.qr_out).expanduser() if a.qr_out else DEFAULT_QR_OUT
    timeout_s = a.timeout or 180
    sf = getattr(a, "status_file", None)
    login_state.write_status(sf, "starting", "正在启动…")
    # 整个流程（含改开窗口、关浏览器后的重开确认）都持有这把锁，别让 whoami 插进来开同一份 profile
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(90)
    except TimeoutError:
        login_state.write_status(sf, "error", "账号页正在校验小红书，登录目录被占用。请关闭弹窗，等 10 秒再点登录。")
        _die("小红书登录目录正被占用（多半是后台 whoami）", 1)

    rc: int | None = None
    try:
        with sync_playwright() as p:
            rc = _login_flow(p, a, sf, qr_out, timeout_s)
        return rc
    except Exception as e:  # noqa: BLE001
        if rc is not None:
            # 流程已经落了终态，只是收尾停 Playwright 时出错：不改结论
            print(f"停止 Playwright 时出错（忽略）：{_short_err(e)}", file=sys.stderr)
            return rc
        # 窗口被用户关掉（TargetClosedError）、浏览器崩溃等意外：必须落 error 终态再退出，
        # 否则状态停在 window_login / verifying，Web 弹窗会一直转圈。（_die 抛的 SystemExit 不经过这里）
        msg = _login_crash_msg(e)
        login_state.write_status(sf, "error", msg)
        print(f"❌ {msg}", file=sys.stderr)
        return 1
    finally:
        lock.release()


def _plan_lines(kind: str, title: str, content: str, media: list[str], tags: list[str]) -> list[str]:
    tab = "上传图文" if kind == "image" else "上传视频"
    tl = calc_title_length(title) if title else 0
    lines = [
        f"发布类型：{kind}    发布页：{PUBLISH_URL}",
        f"标题：{title}（长度 {tl}/{TITLE_MAX}{'  ⚠️超限' if tl > TITLE_MAX else ''}）",
        f"正文：{content[:40]}{'...' if len(content) > 40 else ''}",
        f"媒体：{media}",
        f"话题：{tags}",
        "步骤：",
        f"  1. goto {PUBLISH_URL} → WaitLoad+DOMStable",
        f"  2. 点 tab「{tab}」（重试+遮挡检测）",
        f"  3. {'逐图上传等预览(≤60s/张)' if kind == 'image' else '上传视频等处理(≤10min)'}",
        "  4. 输标题/正文（鼠标点进去，按词组输入）+ 话题联想点选",
        "  5. 勾「笔记含AI合成内容」声明（--no-ai-declare 跳过；勾不上就停，不发）",
        "  6. 平台 DOM 长度校验",
        "  7. 等发布按钮可点击（新版<xhs-publish-btn>/旧版.bg-red）→ 鼠标移过去点",
        "  8. 成功校验：URL 离开 /publish/publish",
    ]
    return lines


# --------------------------------------------------------------------------- #
# 频率闸门：同一个账号发得太密就是「托管」特征。记录在登录目录里（按账号算），只记成功的。
# --------------------------------------------------------------------------- #
ACTIVITY_FILE = ".easel-activity.json"
DAY_S = 24 * 3600
# 种类 → (两次之间至少隔几分钟的环境变量, 默认, 24 小时内最多几次的环境变量, 默认)
ACTIVITY_LIMITS = {
    "publish": ("EASEL_XHS_MIN_GAP_MIN", 60, "EASEL_XHS_DAILY_MAX", 3),
    "reply": ("EASEL_XHS_REPLY_GAP_MIN", 0, "EASEL_XHS_REPLY_DAILY_MAX", 30),
    "comment": ("EASEL_XHS_COMMENT_GAP_MIN", 10, "EASEL_XHS_COMMENT_DAILY_MAX", 5),
}
ACTIVITY_NAMES = {"publish": "发笔记", "reply": "回复评论", "comment": "去别人笔记下评论"}


def _env_int(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name) or "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


def _activity_path(base: str | None) -> Path:
    return _profile_dir(base) / ACTIVITY_FILE


def _load_activity(base: str | None) -> dict:
    try:
        d = json.loads(_activity_path(base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def activity_budget(base: str | None, kind: str, now: float | None = None) -> tuple[int, str]:
    """现在还能做几次 kind（0 = 不能做），以及不能做时的原因。"""
    now = time.time() if now is None else now
    gap_env, gap_def, max_env, max_def = ACTIVITY_LIMITS[kind]
    gap_s = _env_int(gap_env, gap_def) * 60
    day_max = _env_int(max_env, max_def)
    stamps = [t for t in _load_activity(base).get(kind, []) if isinstance(t, (int, float)) and now - t < DAY_S]
    name = ACTIVITY_NAMES[kind]
    if len(stamps) >= day_max:
        wait = int((min(stamps) + DAY_S - now) // 60) + 1
        return 0, (f"24 小时内已经{name} {len(stamps)} 次（上限 {day_max}，{max_env} 可调），"
                   f"约 {wait} 分钟后再来")
    if stamps and gap_s and now - max(stamps) < gap_s:
        wait = int((max(stamps) + gap_s - now) // 60) + 1
        return 0, f"距上次{name}不到 {gap_s // 60} 分钟（{gap_env} 可调），约 {wait} 分钟后再来"
    return day_max - len(stamps), ""


def record_activity(base: str | None, kind: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    d = _load_activity(base)
    d[kind] = [t for t in d.get(kind, []) if isinstance(t, (int, float)) and now - t < DAY_S] + [now]
    path = _activity_path(base)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        print(f"⚠️ 没能记下这次操作的时间（频率闸门会少算一次）：{e}", file=sys.stderr)


def cmd_plan(a) -> int:
    kind = "video" if a.video else "image"
    media = [str(Path(a.video).expanduser())] if a.video else (
        [s.strip() for s in (a.images or "").split(",") if s.strip()])
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    for ln in _plan_lines(kind, a.title or "<title>", a.content or "<content>", media, tags):
        print(ln)
    return 0


def _publish(a, kind: str) -> int:
    if not a.title:
        _die("--title 必填")
    if calc_title_length(a.title) > TITLE_MAX:
        _die(f"标题过长（{calc_title_length(a.title)}/{TITLE_MAX}），请精简")
    if kind == "image":
        media = _abspaths(a.images)
        if not media:
            _die("--images 至少一张图片")
    else:
        if not a.video:
            _die("--video 必填")
        media = [_abspaths(a.video)[0]]
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]

    # 出站内容安全闸门：真发前扫描标题/正文/话题，检出 API key/内部 URL/代理 IP/模型名/
    # "由 AI 生成" 等内部设置泄露即阻止发布（dry-run 只告警）。--allow-unsafe 手动放行。
    content_guard.guard_or_die([a.title, a.content, " ".join(tags)],
                               exec_mode=bool(a.exec),
                               allow_unsafe=getattr(a, "allow_unsafe", False),
                               label="小红书发布内容")

    left, why = activity_budget(a.profile_base, "publish")
    declare_ai = not getattr(a, "no_ai_declare", False)
    if not a.exec:
        print("dry-run（加 --exec 真正发布）：\n")
        for ln in _plan_lines(kind, a.title, a.content or "", media, tags):
            print(ln)
        print(f"AI 合成声明：{'会勾选「笔记含AI合成内容」' if declare_ai else '不勾（--no-ai-declare）'}")
        if not left:
            print(f"⚠️ 现在 --exec 会被频率闸门拦下：{why}")
        return 0
    if not left:
        _die(f"小红书发得太密，这次不发：{why}", 5)

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        _die(f"需要 playwright：{e}", 3)
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(90)
    except TimeoutError:
        _die("小红书登录目录正被占用，请稍后再发")
    try:
        with sync_playwright() as p:
            ctx = _launch(p, headed=a.headed, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(300000)
            try:
                page.goto(PUBLISH_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                # 登录态探测容忍导航竞态：发布页也可能仍在跳转，跳转瞬间裸 query 会抛
                # context-destroyed；重试几次再据 url 判定「未登录」，避免误报。
                logged = False
                for _ in range(4):
                    if _query_safe(page, SELECTORS["login_ok"]) is not None:
                        logged = True
                        break
                    page.wait_for_timeout(500)
                if not logged and "login" in page.url.lower():
                    _die("未登录，请先 `login` 扫码")
                human_input.pause(page, 1500, 3500)   # 页面打开先看一眼
                if kind == "image":
                    _click_publish_tab(page, "上传图文")
                    human_input.pause(page, 800, 2000)
                    _upload_images(page, media)
                else:
                    _click_publish_tab(page, "上传视频")
                    human_input.pause(page, 800, 2000)
                    _upload_video(page, media[0])
                human_input.pause(page, 1000, 3000)
                _fill_and_submit(page, a.title, a.content or "", tags, declare_ai=declare_ai,
                                 on_click=lambda: record_activity(a.profile_base, "publish"))
            except PWTimeout as e:
                _die(f"步骤超时（选择器可能已失效，检查 SELECTORS）：{e}")
            finally:
                if not a.keep_open:
                    ctx.close()
    finally:
        lock.release()
    # 发布成功 → 落统一内容日历（对话页自动记录；发布页由 web 设 AUTORECORD=0 跳过防重复）
    try:
        import calendar_ops
        calendar_ops.record_publish("xiaohongshu", a.title,
                                    ptype="视频" if kind == "video" else "图文",
                                    tags=(a.tags or ""), note=(a.content or ""), source="chat")
    except Exception:
        pass
    return 0


def cmd_publish(a) -> int:
    return _publish(a, "image")


def cmd_publish_video(a) -> int:
    return _publish(a, "video")


def _marker_logged_in() -> bool:
    """本地登录记录（outputs/_login/xiaohongshu.json，Web 账号页看的那份）是不是「已登录」。"""
    path = _web_login_marker_path(argparse.Namespace(status_file=None, profile_base=None))
    try:
        return bool(path) and json.loads(path.read_text(encoding="utf-8")).get("state") == "success"
    except (OSError, ValueError):
        return False


def cmd_whoami(a) -> int:
    """读登录态 + 昵称/头像，输出单行 JSON（供 Web 后端 / agent 解析）。

    默认**不开浏览器**，只读本地登录记录：每次校验都开一个小红书窗口，既打扰人、又是一次自动化
    登录访问。2026-10 合并后没重启的旧 Web 后端还在定时调本命令，结果隔一会儿就弹一个窗口。
    --live 才真开浏览器校验（用户明确要求时用）。xhs 须直连（--no-proxy），走代理会被判风险。"""
    if not getattr(a, "live", False):
        print(json.dumps({"loggedIn": _marker_logged_in(), "name": "", "avatar": "", "passive": True},
                         ensure_ascii=False))
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(json.dumps({"loggedIn": False, "name": "", "avatar": "", "error": f"playwright:{e}"}))
        return 0
    result = {"loggedIn": False, "name": "", "avatar": ""}
    lock = _ProfileLock(_profile_dir(a.profile_base))
    try:
        lock.acquire(4)
    except TimeoutError:
        result["error"] = "profile-busy"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    try:
        with sync_playwright() as p:
            ctx = _launch(p, headed=False, base=a.profile_base, proxy=_proxy(a.proxy, a.no_proxy))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(EXPLORE_URL, wait_until="domcontentloaded")
                try:  # 等登录态元素出现（已登录会很快命中；未登录则短等后判定）
                    page.wait_for_selector(SELECTORS["login_ok"], timeout=4000)
                except Exception:
                    pass
                logged = _is_logged_in(page)
                if not logged and _risk_blocked(page):
                    page.goto(CREATOR_LOGIN_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    logged = _is_logged_in(page)
                result["loggedIn"] = logged
                if logged:
                    img = page.query_selector('.main-container .user img.reds-img')
                    if img:
                        result["avatar"] = img.get_attribute("src") or ""
                    a_el = page.query_selector('.main-container .user a[href^="/user/profile/"]')
                    href = a_el.get_attribute("href") if a_el else None
                    if href:  # 昵称在个人主页，explore 页只有头像
                        try:
                            page.goto("https://www.xiaohongshu.com" + href,
                                      wait_until="domcontentloaded")
                            try:
                                page.wait_for_selector(".user-name", timeout=4000)
                            except Exception:
                                pass
                            for sel in (".user-name", ".user-nickname",
                                        'div[class*="nickname"]', ".info .name"):
                                el = page.query_selector(sel)
                                if el:
                                    t = (el.inner_text() or "").strip()
                                    if t:
                                        result["name"] = t.splitlines()[0][:40]
                                        break
                        except Exception:
                            pass
            finally:
                ctx.close()
    except Exception as e:  # noqa: BLE001 — whoami 永远输出 JSON，异常视作未登录
        result["error"] = str(e)
    finally:
        lock.release()
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_selftest(_a) -> int:
    print("xhs_publish 自检（离线）...", file=sys.stderr)
    # 标题长度算法（REF title.go）
    assert calc_title_length("") == 0
    assert calc_title_length("abcd") == 2, "4 ASCII → (4+1)//2 = 2"
    assert calc_title_length("你好") == 2, "2 全角 → 4 字节 → 2"
    assert calc_title_length("你" * 20) == 20, "20 全角 → 20（上限）"
    assert calc_title_length("a") == 1
    # 选择器字典完整
    need = ["login_ok", "qrcode", "creator_tab", "upload_input_first", "img_preview",
            "title_input", "content_quill", "topic_item", "publish_btn_new", "publish_btn_old"]
    for k in need:
        assert k in SELECTORS and SELECTORS[k], f"缺选择器 {k}"
    # 路径解析
    try:
        _abspaths("/no/such/file_xyz.jpg")
        raise AssertionError("不存在文件未报错")
    except SystemExit:
        pass
    # profile 目录路由
    assert _profile_dir(None).name == PROFILE_NAME
    assert "cloak-research-profile" not in str(_profile_dir(None))
    cloak = _cloak_executable()
    assert cloak is None or cloak.is_file()
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="easel-xhs-lock-"))
    try:
        held = _ProfileLock(tmp)
        held.acquire(1)
        blocked = _ProfileLock(tmp)
        try:
            blocked.acquire(0.3)
            raise AssertionError("第二把锁应失败")
        except TimeoutError:
            pass
        finally:
            blocked.release()
        held.release()
        held.acquire(1)
        held.release()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # 代理逻辑
    assert _proxy(None, True) is None, "--no-proxy 应禁用"
    assert _proxy("http://x:1", False) == "http://x:1", "显式代理优先"
    # plan 渲染
    lines = _plan_lines("image", "标题", "正文", ["/a.jpg"], ["#tag"])
    assert any("上传图文" in ln for ln in lines) and any("成功校验" in ln for ln in lines)
    lines_v = _plan_lines("video", "t", "c", ["/a.mp4"], [])
    assert any("上传视频" in ln for ln in lines_v)
    print("✅ selftest 通过（标题算法 + 选择器字典 + 路径/代理/路由 + plan 渲染）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="小红书发布（Playwright 驱动本机 Chrome 窗口；流程移植自 xiaohongshu-mcp）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    def add_common(p):
        p.add_argument("--profile-base", help="登录态根目录（默认 ~/.easel-browser-profiles）")
        p.add_argument("--proxy", help="外网代理（默认取 env，小红书是外网需代理）")
        p.add_argument("--no-proxy", action="store_true", help="禁用代理")

    def add_content(p):
        p.add_argument("--title", help="标题（≤20 全角）")
        p.add_argument("--content", help="正文")
        p.add_argument("--images", help="图片路径，逗号分隔（图文发布）")
        p.add_argument("--video", help="视频路径（视频发布）")
        p.add_argument("--tags", help="话题，逗号分隔（如 'AI,教程'）")
        p.add_argument("--exec", action="store_true", help="真正发布（默认 dry-run）")
        p.add_argument("--allow-unsafe", action="store_true",
                       help="放行内容安全闸门（检出内部设置泄露也照发，谨慎）")
        p.add_argument("--headed", action="store_true",
                       help="开窗口（默认就开；仅 EASEL_XHS_HEADLESS=1 时才可能无头）")
        p.add_argument("--keep-open", action="store_true", help="发布后不关浏览器")
        p.add_argument("--no-ai-declare", action="store_true",
                       help="不勾「笔记含AI合成内容」（仅当内容确实不是 AI 生成/合成的）")

    sub.add_parser("check", help="检查 playwright/内核").set_defaults(func=cmd_check)

    p = sub.add_parser("login", help="扫码登录并持久化（开 Chrome 窗口，二维码也抠成图片）")
    add_common(p)
    p.add_argument("--qr-out", help=f"二维码图片输出路径（默认 {DEFAULT_QR_OUT}）")
    p.add_argument("--status-file", help="登录状态 JSON 输出路径（供 Web 后端轮询）")
    p.add_argument("--timeout", type=int, help="等待扫码超时秒数（默认 180）")
    p.add_argument("--headed", action="store_true", help="开窗口（默认就开；仅 EASEL_XHS_HEADLESS=1 时有区别）")
    p.add_argument("--headed-fallback", action="store_true",
                   help="EASEL_XHS_HEADLESS=1 时：无头被风控拦截（300012）就改开窗口登录")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("plan", help="发布步骤预览（离线）")
    add_content(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("publish", help="图文发布")
    add_common(p); add_content(p)
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("publish-video", help="视频发布")
    add_common(p); add_content(p)
    p.set_defaults(func=cmd_publish_video)

    p = sub.add_parser("whoami", help="读登录态（输出 JSON）；默认只读本地登录记录，不开浏览器")
    add_common(p)
    p.add_argument("--live", action="store_true",
                   help="真开浏览器窗口校验 + 读昵称/头像（只在用户明确要求时用）")
    p.set_defaults(func=cmd_whoami)

    sub.add_parser("selftest", help="离线自检").set_defaults(func=cmd_selftest)

    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
