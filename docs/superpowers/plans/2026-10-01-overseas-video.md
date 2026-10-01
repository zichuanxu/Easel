# 海外平台发布 PR 2：视频发布 + 发布中心 + 对话接入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户能从发布中心或对话，把视频发到 TikTok / Instagram / X / Threads（YouTube 等账号有频道、真机校准后开启）。

**Architecture:** `overseas/base.py` 新增 `PageDriver`（平台流程只通过它操作页面，离线测试换成假驱动）、`Result`、`StepFailed` / `Blocked`、失败现场保存；每个平台模块新增 `PUBLISH_URL`、`READY_KINDS`、`publish(drv, fields, post)`；`overseas_publisher.py` 新增 `publish` 命令（默认预览、`--exec` 真发、内容安全闸门、登录目录锁、被拦改有头重试、结果待确认不重发、成功记日历）。Web 发布中心走异步发布 + 轮询；对话新增 `skill-overseas-publish`，跨平台发布路由到它。

**Tech Stack:** Python 3.12、Playwright sync API、FastAPI、React 19 + TypeScript、pytest、vitest。

**Spec:** `docs/superpowers/specs/2026-10-01-overseas-publishing-design.md`（第 5 节 + 第 8 节 PR 2）

## Global Constraints

- 中文注释 / 文档 / 提交；前缀 `feat/fix/docs/chore/polish`；提交末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 测试不起真浏览器、不连平台、不碰用户 `.env`、`~/.openclaw-easel`、`~/.easel-browser-profiles`、真实 `outputs/`。
- 国内平台的登录、发布、代理行为不变（`web_publisher.py`、`xhs_publish.py`、`douyin_publish.py` 不改）。
- 本 PR 只接通**视频**：各平台 `READY_KINDS = frozenset({"video"})`；YouTube 先 `frozenset()`（账号无频道、未真机校准），Task 9 校准后才改成 `{"video"}`。图文 / 纯文字在 PR 3。
- 退出码：2 内容不合格、3 缺 Playwright、5 结果待确认、6 未登录、7 内容安全闸门拦下、1 其它失败（与 spec 第 6 节一致）。
- 结果待确认（已点发布、没等到成功信号）**绝不自动重发、不记日历**。
- 发布中心海外平台：卡片正文就是完整英文文案；非 YouTube 平台发送 `title=''`、`tags=''`（避免把中文母版标题 / 标签拼进英文文案）；YouTube 取卡片第一行为标题（≤100）、其余为描述。「一键适配」对海外平台要求输出英文、话题标签写进正文末尾。（spec 5.4 原写「发布中心不做一键改写成英文」，用户在对话中接受了这一补充。）
- 被平台拦（URL 落到验证码 / challenge / checkpoint 页）：未加 `--headed` 时改开有头窗口重试一次（spec 5.2）。
- 文件 I/O 显式 UTF-8；开发在 worktree `../Easel-wt-ov`（分支 `feat/overseas-video`），不停 / 不重启用户的 `easel web` 与网关。
- 全部任务后跑：`python -m pytest`、两个 validator、`overseas_publisher.py selftest`、`publish_dispatch.py selftest`、`cd web/frontend && npm test && npm run build && npm run lint`。

## Review Focus

1. 点了发布但一直没等到成功信号（慢网 / 平台改版）—— 必须是退出码 5「结果待确认，不要直接重发」，不重试、不记日历（Task 5 `test_unknown_result_is_exit_5_without_retry_or_calendar`）。
2. 视频还在处理、发布按钮不可点 —— 不能去点不可点的按钮，等到超时报「视频处理超时」（Task 2 `test_x_waits_for_post_button_enabled`）。
3. 发布中心把中文母版标题 / 标签拼进海外英文文案 —— 非 YouTube 平台 title、tags 必须为空，YouTube 只取卡片第一行作标题（Task 7 `overseasPayload` 用例）。
4. 未登录 / 登录态说不准时发布 —— 未登录退出码 6、说不准报「登录态没法确认」，都不去走发布流程（Task 5 `test_not_logged_in_is_exit_6` / `test_unsettled_login_is_not_published`）。
5. 文件名里带密钥一类敏感信息 —— 真发前被内容安全闸门拦下（退出码 7），预览时只告警（Task 5 `test_exec_guard_scans_media_filenames`）。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `skills/shared/scripts/overseas/base.py` | 新增 `StepFailed`、`Blocked`、`BLOCK_MARKERS`、`Result`、`PageDriver`、`save_failure` |
| `skills/shared/scripts/overseas/{x,threads,instagram,tiktok,youtube}.py` | 新增 `PUBLISH_URL`、`READY_KINDS`、页面选择器常量、`publish()` |
| `skills/shared/scripts/overseas/__init__.py` | `REQUIRED_ATTRS` 加 `PUBLISH_URL`、`READY_KINDS`、`publish` |
| `skills/shared/scripts/overseas_publisher.py` | 新增 `publish` 命令、`run_publish`、selftest 检查 `READY_KINDS` |
| `skills/shared/scripts/calendar_ops.py` | `PLATFORM_NAMES` 加 5 个平台 |
| `web/app.py` | `PublishRequest.visibility`、`MEDIA_REQUIRED` / `VIDEO_ONLY_PUBLISH` 加海外平台、`api_publish` 的 `overseas` 分支（异步） |
| `web/frontend/src/lib/overseasPublish.ts` | 海外平台元数据、可见范围选项、发送载荷、适配提示 |
| `web/frontend/src/lib/api.ts` | `publishNow` 载荷加 `visibility` |
| `web/frontend/src/components/PublishPage.tsx` | 平台分组、海外平台卡片可见范围、适配提示、海外载荷 |
| `skills/openclaw/skill-overseas-publish/` | 新技能：SKILL.md、EASEL-META.md、references/platforms.md |
| `skills/openclaw/skill-cross-platform-publish/` | 平台表 + `publish_dispatch.py` 路由 |
| `skills/openclaw/skill-my-account/SKILL.md` | 海外平台 whoami 说明 |
| `scripts/validate_skills.py` | `PUBLISH_SCRIPT_CONTRACTS` 加 `overseas_publisher.py` |
| `docs/skill-function-mapping.md`、`web/frontend/src/lib/skillDisplayNames.ts`、`web/frontend/src/lib/capabilityMenu.ts` | 登记新技能 |
| 测试 | `tests/test_overseas_driver.py`、`tests/test_overseas_flows.py`、`tests/test_overseas_publish.py`、`tests/test_overseas_web.py`（追加）、`web/frontend/src/lib/overseasPublish.test.ts`、`web/frontend/src/components/PublishPage.test.tsx` |

---

### Task 1: 页面驱动与发布结果 `overseas/base.py`

**Files:**
- Modify: `skills/shared/scripts/overseas/base.py`（文件末尾追加；顶部 import 加 `random`、`from dataclasses import dataclass`）
- Test: `tests/test_overseas_driver.py`

**Interfaces:**
- Consumes: 现有 `short_err`、`settle`
- Produces:
  - `class StepFailed(RuntimeError)`、`class Blocked(RuntimeError)`、`BLOCK_MARKERS: tuple[str, ...]`
  - `@dataclass class Result(status: str, url: str = "", message: str = "")`，`status ∈ {"success","failed","unknown"}`
  - `class PageDriver(page, *, pace=(0.25, 0.7))`，方法：`goto(url, timeout_ms=60000)`（落到 `BLOCK_MARKERS` 抛 `Blocked`）、`url() -> str`、`count(sel) -> int`、`visible(sel) -> bool`、`click(sel, timeout_ms=15000)`（失败抛 `StepFailed`）、`upload(sel, files, timeout_ms=30000)`、`type_text(sel, text, *, clear=True, timeout_ms=15000)`、`press(key)`、`wait_for(sel, timeout_ms=15000, state="visible") -> bool`、`wait_enabled(sel, timeout_ms=60000) -> bool`、`text(sel) -> str`、`attr(sel, name) -> str`、`pause(ms)`、`dismiss(selectors, rounds=2)`、`settle(mod) -> bool | None`；属性 `page`
  - `save_failure(page, key: str) -> Path | None`（写 `outputs/_login/<key>-publish-fail.png/.html`，任何异常都吞掉返回 None）

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_driver.py`：

```python
"""PageDriver（overseas/base.py）的离线测试：用最小的假 Playwright 页面，不起浏览器。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import base  # noqa: E402


class FakeKeyboard:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def press(self, key):
        self.events.append(("press", key))

    def type(self, text, delay=0):
        self.events.append(("type", text))


class FakeLocator:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    def nth(self, _i):
        return self

    def count(self):
        return 1 if self.sel in self.page.present else 0

    def is_visible(self):
        return self.sel in self.page.present

    def is_enabled(self):
        return self.sel in self.page.enabled

    def get_attribute(self, name, timeout=None):
        return self.page.attrs.get((self.sel, name))

    def inner_text(self, timeout=None):
        return self.page.texts.get(self.sel, "")

    def click(self, timeout=None):
        if self.sel not in self.page.present:
            raise RuntimeError(f"Timeout waiting for {self.sel}")
        self.page.clicks.append(self.sel)

    def set_input_files(self, files, timeout=None):
        self.page.uploads.append((self.sel, list(files)))

    def wait_for(self, state="visible", timeout=None):
        if self.sel not in self.page.present:
            raise RuntimeError("Timeout")


class FakePWPage:
    def __init__(self, url="https://example.test/home"):
        self.url = url
        self.present: set[str] = set()
        self.enabled: set[str] = set()
        self.attrs: dict = {}
        self.texts: dict = {}
        self.clicks: list[str] = []
        self.uploads: list = []
        self.waited = 0
        self.keyboard = FakeKeyboard()
        self.after_goto = None

    def locator(self, sel):
        return FakeLocator(self, sel)

    def goto(self, url, wait_until=None, timeout=None):
        self.url = self.after_goto or url

    def wait_for_timeout(self, ms):
        self.waited += ms


def drv_for(page):
    return base.PageDriver(page, pace=(0, 0))


def test_type_text_clears_then_types_lines_with_enter():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hello\n\n#ai")
    sel_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
    assert page.clicks == ["#box"]
    assert page.keyboard.events == [("press", sel_all), ("press", "Backspace"), ("type", "Hello"),
                                    ("press", "Enter"), ("press", "Enter"), ("type", "#ai")]


def test_type_text_without_clear_keeps_existing_text():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hi", clear=False)
    assert page.keyboard.events == [("type", "Hi")]


def test_click_missing_element_raises_step_failed():
    with pytest.raises(base.StepFailed, match="#nope"):
        drv_for(FakePWPage()).click("#nope", timeout_ms=10)


def test_goto_onto_challenge_page_raises_blocked():
    page = FakePWPage()
    page.after_goto = "https://www.instagram.com/challenge/?next=/"
    with pytest.raises(base.Blocked):
        drv_for(page).goto("https://www.instagram.com/")
    page.after_goto = None
    drv_for(page).goto("https://x.com/home")
    assert page.url == "https://x.com/home"


def test_wait_enabled_respects_aria_disabled():
    page = FakePWPage()
    page.present.add("#post")
    page.enabled.add("#post")
    page.attrs[("#post", "aria-disabled")] = "true"
    assert drv_for(page).wait_enabled("#post", timeout_ms=1) is False
    page.attrs[("#post", "aria-disabled")] = "false"
    assert drv_for(page).wait_enabled("#post", timeout_ms=1) is True


def test_dismiss_clicks_only_visible_popups():
    page = FakePWPage()
    page.present.add("button.notnow")
    drv_for(page).dismiss(["button.notnow", "button.absent"], rounds=1)
    assert page.clicks == ["button.notnow"]


def test_wait_for_and_text_helpers():
    page = FakePWPage()
    page.present.add("#toast")
    page.texts["#toast"] = "Your post was sent."
    drv = drv_for(page)
    assert drv.wait_for("#toast", 10) is True
    assert drv.wait_for("#missing", 10) is False
    assert drv.text("#toast") == "Your post was sent."
    assert drv.text("#missing") == ""


def test_result_defaults():
    r = base.Result("success")
    assert (r.status, r.url, r.message) == ("success", "", "")


def test_save_failure_never_raises():
    assert base.save_failure(SimpleNamespace(), "demo") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_driver.py -q`
Expected: FAIL，`AttributeError: module 'overseas.base' has no attribute 'PageDriver'`

- [ ] **Step 3: 实现**

`base.py` 顶部 import 区改为：

```python
import os
import random
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
```

文件末尾追加：

```python
# ---- 发布：页面驱动、结果、失败现场 ----------------------------------------------------------

# 落到这些页面 = 平台要人工验证（验证码 / 安全检查），无头浏览器过不去，调用方改开有头窗口
BLOCK_MARKERS = ("captcha", "/challenge", "checkpoint", "/account/access", "/suspended")


class StepFailed(RuntimeError):
    """发布流程某一步做不下去（找不到元素、超时）：多半是平台改版，调用方保存失败现场。"""


class Blocked(RuntimeError):
    """平台拦了无头浏览器（验证码 / 安全检查页）：调用方可改开有头窗口重试一次。"""


@dataclass
class Result:
    status: str          # success：确认已发出；failed：明确失败；unknown：点了发布但没等到成功信号
    url: str = ""
    message: str = ""


class PageDriver:
    """平台发布流程只通过它操作页面，离线测试里换成按剧本走的假驱动。
    pace：每个动作后随机停顿的秒数区间（像人一样操作，测试里传 (0, 0)）。"""

    def __init__(self, page, *, pace: tuple[float, float] = (0.25, 0.7)):
        self.page = page
        self.pace = pace

    def _rest(self) -> None:
        lo, hi = self.pace
        if hi > 0:
            self.page.wait_for_timeout(int(random.uniform(lo, hi) * 1000))

    def goto(self, url: str, timeout_ms: int = 60000) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        now = self.url().lower()
        if any(m in now for m in BLOCK_MARKERS):
            raise Blocked(f"被带到了验证页：{self.url()}")

    def url(self) -> str:
        try:
            return self.page.url or ""
        except Exception:  # noqa: BLE001
            return ""

    def count(self, sel: str) -> int:
        try:
            return self.page.locator(sel).count()
        except Exception:  # noqa: BLE001
            return 0

    def visible(self, sel: str) -> bool:
        try:
            loc = self.page.locator(sel)
            return any(loc.nth(i).is_visible() for i in range(min(loc.count(), 5)))
        except Exception:  # noqa: BLE001
            return False

    def click(self, sel: str, timeout_ms: int = 15000) -> None:
        try:
            self.page.locator(sel).first.click(timeout=timeout_ms)
        except Exception as e:  # noqa: BLE001
            raise StepFailed(f"点不到 {sel}：{short_err(e)}") from e
        self._rest()

    def upload(self, sel: str, files, timeout_ms: int = 30000) -> None:
        try:
            self.page.locator(sel).first.set_input_files([str(f) for f in files], timeout=timeout_ms)
        except Exception as e:  # noqa: BLE001
            raise StepFailed(f"选不了文件（{sel}）：{short_err(e)}") from e
        self._rest()

    def type_text(self, sel: str, text: str, *, clear: bool = True, timeout_ms: int = 15000) -> None:
        """点进输入框（可先全选删掉预填内容）再逐行输入、行间回车：
        富文本编辑器（DraftJS 等）只认真实的键盘事件，直接 fill 会被忽略。"""
        self.click(sel, timeout_ms)
        kb = self.page.keyboard
        if clear:
            kb.press("Meta+A" if sys.platform == "darwin" else "Control+A")
            kb.press("Backspace")
        for i, line in enumerate(text.split("\n")):
            if i:
                kb.press("Enter")
            if line:
                kb.type(line, delay=random.randint(15, 45))
        self._rest()

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def wait_for(self, sel: str, timeout_ms: int = 15000, state: str = "visible") -> bool:
        try:
            self.page.locator(sel).first.wait_for(state=state, timeout=timeout_ms)
            return True
        except Exception:  # noqa: BLE001
            return False

    def wait_enabled(self, sel: str, timeout_ms: int = 60000) -> bool:
        """等按钮真能点：is_enabled 且 aria-disabled 不是 true（视频处理完之前发布按钮是灰的）。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            try:
                loc = self.page.locator(sel).first
                if loc.count() and loc.is_enabled() and loc.get_attribute("aria-disabled") != "true":
                    return True
            except Exception:  # noqa: BLE001
                pass
            if time.monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(500)

    def text(self, sel: str) -> str:
        try:
            return self.page.locator(sel).first.inner_text(timeout=2000) or ""
        except Exception:  # noqa: BLE001
            return ""

    def attr(self, sel: str, name: str) -> str:
        try:
            return self.page.locator(sel).first.get_attribute(name, timeout=2000) or ""
        except Exception:  # noqa: BLE001
            return ""

    def pause(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)

    def dismiss(self, selectors, rounds: int = 2) -> None:
        """点掉挡路的提示（开通知、新功能引导、内容检查询问……）：可见就点，点不到不报错。"""
        for _ in range(rounds):
            hit = False
            for sel in selectors:
                if not self.visible(sel):
                    continue
                try:
                    self.page.locator(sel).first.click(timeout=3000)
                    hit = True
                    self.page.wait_for_timeout(600)
                except Exception:  # noqa: BLE001
                    pass
            if not hit:
                return

    def settle(self, mod) -> bool | None:
        return settle(self.page, mod)


def save_failure(page, key: str) -> Path | None:
    """失败现场：截图 + 页面 HTML 存到 outputs/_login/<平台>-publish-fail.png/.html，对着它改选择器。"""
    try:
        import output_paths
        png = output_paths.validate_output_path(
            output_paths.OUTPUTS_DIR / "_login" / f"{key}-publish-fail.png", allow_system=True, create_parent=True)
        page.screenshot(path=str(png), full_page=True)
        png.with_suffix(".html").write_text(page.content(), encoding="utf-8")
        return png
    except Exception:  # noqa: BLE001 — 保存现场失败不能盖掉发布本身的结果
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_driver.py tests/test_overseas_base.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add skills/shared/scripts/overseas/base.py tests/test_overseas_driver.py
git commit -m "feat(overseas): 发布用的页面驱动、发布结果与失败现场保存

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 假驱动 + X 视频发布

**Files:**
- Modify: `skills/shared/scripts/overseas/x.py`（加常量与 `publish`）
- Modify: `skills/shared/scripts/overseas/__init__.py`（`REQUIRED_ATTRS` 加 `"PUBLISH_URL", "READY_KINDS", "publish"`）
- Modify: `skills/shared/scripts/overseas/{tiktok,youtube,instagram,threads}.py`（本任务先各加 `PUBLISH_URL` 与 `READY_KINDS = frozenset()` 和一个占位 `publish` 抛 `StepFailed("未接通")`，让注册表契约成立；Task 3/4 逐个替换成真实流程）
- Test: `tests/test_overseas_flows.py`（新建，含 `FakeDriver`）

**Interfaces:**
- Consumes: Task 1 的 `Result`、`StepFailed`；`Post`、`caption_text`
- Produces:
  - 每个平台模块：`PUBLISH_URL: str`、`READY_KINDS: frozenset`、`publish(drv, fields: dict, post: Post) -> Result`
  - `x.py` 常量：`TEXTBOX`、`FILE_INPUT`、`MEDIA_READY`、`POST_BUTTON`、`TOAST`、`TOAST_LINK`；`POST_WAIT_S = 90`、`PROCESS_WAIT_MS = 300000`

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_flows.py`：

```python
"""海外平台发布流程（各平台模块的 publish）离线测试：按剧本走的假驱动，不起浏览器、不连平台。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import PLATFORMS, base  # noqa: E402
from overseas.post import Post  # noqa: E402

VIDEO = Path("/tmp/clip.mp4")


class FakeDriver:
    """记录动作；visible / enabled / text / attr 读剧本，hooks[(动作, 选择器)] 在动作后改剧本。"""

    def __init__(self, *, visible=(), enabled=(), texts=None, attrs=None, url="https://example.test/"):
        self.actions: list[tuple] = []
        self.visible_set = set(visible)
        self.enabled_set = set(enabled)
        self.texts = dict(texts or {})
        self.attrs = dict(attrs or {})
        self._url = url
        self.hooks: dict = {}
        self.paused = 0
        self.page = None

    def _do(self, act, sel, *extra):
        self.actions.append((act, sel, *extra))
        hook = self.hooks.get((act, sel))
        if hook:
            hook(self)

    def goto(self, url, timeout_ms=60000):
        self._url = url
        self._do("goto", url)

    def url(self):
        return self._url

    def count(self, sel):
        return 1 if sel in self.visible_set else 0

    def visible(self, sel):
        return sel in self.visible_set

    def click(self, sel, timeout_ms=15000):
        if sel not in self.visible_set:
            raise base.StepFailed(f"点不到 {sel}")
        self._do("click", sel)

    def upload(self, sel, files, timeout_ms=30000):
        self._do("upload", sel, tuple(str(f) for f in files))

    def type_text(self, sel, text, *, clear=True, timeout_ms=15000):
        self._do("type", sel, text)

    def press(self, key):
        self._do("press", key)

    def wait_for(self, sel, timeout_ms=15000, state="visible"):
        self._do("wait_for", sel)
        return sel in self.visible_set

    def wait_enabled(self, sel, timeout_ms=60000):
        self._do("wait_enabled", sel)
        return sel in self.enabled_set

    def text(self, sel):
        return self.texts.get(sel, "")

    def attr(self, sel, name):
        return self.attrs.get((sel, name), "")

    def pause(self, ms):
        self.paused += ms

    def dismiss(self, selectors, rounds=2):
        self._do("dismiss", tuple(selectors))

    def settle(self, mod):
        return True

    def acts(self, kind):
        return [a for a in self.actions if a[0] == kind]


def post(**kw):
    return Post(media=[VIDEO], title=kw.pop("title", ""), desc=kw.pop("desc", "Hello world"),
                tags=kw.pop("tags", "ai"), **kw)


# ---------------------------------------------------------------- X
X = PLATFORMS["x"]


def x_driver():
    d = FakeDriver(visible={X.TEXTBOX, X.POST_BUTTON}, enabled={X.POST_BUTTON})
    d.hooks[("upload", X.FILE_INPUT)] = lambda dr: dr.visible_set.add(X.MEDIA_READY)

    def sent(dr):
        dr.texts[X.TOAST] = "Your post was sent. View"
        dr.attrs[(X.TOAST_LINK, "href")] = "/demo/status/123"
    d.hooks[("click", X.POST_BUTTON)] = sent
    return d


def test_x_publishes_video_and_reads_status_link():
    d = x_driver()
    p = post()
    r = X.publish(d, X.compose(p), p)
    assert r.status == "success" and r.url == "https://x.com/demo/status/123"
    kinds = [a[0] for a in d.actions]
    assert kinds.index("upload") < kinds.index("type") < kinds.index("click")
    assert d.acts("type")[0][2] == "Hello world\n\n#ai"
    assert d.acts("goto")[0][1] == X.PUBLISH_URL


def test_x_waits_for_post_button_enabled():
    """视频还在处理、发布按钮一直是灰的：不去点，报处理超时（Review Focus 2）。"""
    d = x_driver()
    d.enabled_set.clear()
    p = post()
    with pytest.raises(base.StepFailed, match="处理超时"):
        X.publish(d, X.compose(p), p)
    assert not d.acts("click")


def test_x_media_never_attaches_is_step_failed():
    d = x_driver()
    d.hooks.pop(("upload", X.FILE_INPUT))
    p = post()
    with pytest.raises(base.StepFailed, match="视频没挂上"):
        X.publish(d, X.compose(p), p)


def test_x_no_toast_is_unknown():
    d = x_driver()
    d.hooks.pop(("click", X.POST_BUTTON))
    p = post()
    r = X.publish(d, X.compose(p), p)
    assert r.status == "unknown"
    assert d.paused >= X.POST_WAIT_S * 1000 - 1000


def test_registry_publish_contract():
    for key, m in PLATFORMS.items():
        assert callable(m.publish), key
        assert m.READY_KINDS <= m.KINDS, key
        assert m.PUBLISH_URL.startswith("https://"), key
    assert PLATFORMS["x"].READY_KINDS == {"video"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py -q`
Expected: FAIL，`AttributeError: module 'overseas.x' has no attribute 'TEXTBOX'`

- [ ] **Step 3: 实现 X 发布**

`x.py` 在 `AVATAR_SELECTORS` 之后加：

```python
PUBLISH_URL = "https://x.com/compose/post"
READY_KINDS = frozenset({"video"})       # 图文 / 纯文字在 PR 3 接通
# 发帖弹窗（首页还有一个内嵌发帖框，同样的 testid，一律限定在弹窗里）；真机校准于 2026-10-01
_DIALOG = '[role="dialog"]'
TEXTBOX = f'{_DIALOG} [data-testid="tweetTextarea_0"]'
FILE_INPUT = f'{_DIALOG} input[data-testid="fileInput"]'
MEDIA_READY = f'{_DIALOG} [aria-label="Remove media"]'     # 视频挂上后才出现
POST_BUTTON = f'{_DIALOG} [data-testid="tweetButton"]'
TOAST = '[data-testid="toast"]'
TOAST_LINK = f'{TOAST} a[href*="/status/"]'
POST_WAIT_S = 90
PROCESS_WAIT_MS = 300000
```

文件末尾加：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(TEXTBOX, 30000):
        raise base.StepFailed("没打开发帖框")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(MEDIA_READY, 120000):
        raise base.StepFailed("视频没挂上（没出现 Remove media）")
    drv.type_text(TEXTBOX, fields["caption"])
    if not drv.wait_enabled(POST_BUTTON, PROCESS_WAIT_MS):
        raise base.StepFailed("视频处理超时，发布按钮一直不能点")
    drv.click(POST_BUTTON)
    for _ in range(POST_WAIT_S):
        if "sent" in drv.text(TOAST).lower():
            href = drv.attr(TOAST_LINK, "href")
            url = f"https://x.com{href}" if href.startswith("/") else href
            return base.Result("success", url=url, message="已发布到 X")
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但没等到「已发送」提示")
```

`overseas/__init__.py` 的 `REQUIRED_ATTRS` 末尾加 `"PUBLISH_URL", "READY_KINDS", "publish",`。

`tiktok.py`、`youtube.py`、`instagram.py`、`threads.py` 各在 `AVATAR_SELECTORS` 之后加（PUBLISH_URL 按平台：tiktok `"https://www.tiktok.com/tiktokstudio/upload"`、youtube `"https://studio.youtube.com/"`、instagram / threads `HOME_URL`）：

```python
PUBLISH_URL = "https://www.tiktok.com/tiktokstudio/upload"
READY_KINDS: frozenset[str] = frozenset()
```

并在文件末尾加：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    raise base.StepFailed(f"{NAME} 发布还没接通")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py tests/test_overseas_platforms.py -q && .venv/bin/python skills/shared/scripts/overseas_publisher.py selftest`
Expected: 全部 PASS；selftest ✅

- [ ] **Step 5: 提交**

```bash
git add skills/shared/scripts/overseas/ tests/test_overseas_flows.py
git commit -m "feat(overseas): X 视频发布流程

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Threads 与 Instagram 视频发布

**Files:**
- Modify: `skills/shared/scripts/overseas/threads.py`、`skills/shared/scripts/overseas/instagram.py`（替换占位 `publish`、`READY_KINDS` 改 `{"video"}`）
- Test: `tests/test_overseas_flows.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `FakeDriver`、`post()`；Task 1 的 `Result`、`StepFailed`
- Produces:
  - `threads.py`：`OPEN_COMPOSER`、`TEXTBOX`、`FILE_INPUT`、`MEDIA_READY`、`POST_BUTTON`、`DIALOG`、`POSTED_LINK`、`POST_WAIT_S = 120`
  - `instagram.py`：`NEW_POST`、`FILE_INPUT`、`REEL_OK`、`NEXT`、`CAPTION`、`SHARE`、`DIALOG`、`POPUPS`、`heading(text) -> str`、`POST_WAIT_S = 300`

- [ ] **Step 1: 写失败的测试（追加到 `tests/test_overseas_flows.py`）**

```python
# ---------------------------------------------------------------- Threads
TH = PLATFORMS["threads"]


def threads_driver():
    d = FakeDriver(visible={TH.OPEN_COMPOSER})
    d.hooks[("click", TH.OPEN_COMPOSER)] = lambda dr: dr.visible_set.update({TH.TEXTBOX, TH.DIALOG})
    d.hooks[("upload", TH.FILE_INPUT)] = lambda dr: dr.visible_set.update({TH.MEDIA_READY, TH.POST_BUTTON})

    def posted(dr):
        dr.visible_set.discard(TH.DIALOG)
        dr.visible_set.add(TH.POSTED_LINK)
        dr.attrs[(TH.POSTED_LINK, "href")] = "/@demo/post/ABC"
    d.hooks[("click", TH.POST_BUTTON)] = posted
    return d


def test_threads_publishes_video():
    d = threads_driver()
    p = post()
    r = TH.publish(d, TH.compose(p), p)
    assert r.status == "success" and r.url == "https://www.threads.com/@demo/post/ABC"
    kinds = [a[0] + ":" + str(a[1]) for a in d.actions]
    assert kinds.index(f"click:{TH.OPEN_COMPOSER}") < kinds.index(f"upload:{TH.FILE_INPUT}")
    assert TH.READY_KINDS == {"video"}


def test_threads_dialog_stays_open_is_unknown():
    d = threads_driver()
    d.hooks.pop(("click", TH.POST_BUTTON))
    p = post()
    assert TH.publish(d, TH.compose(p), p).status == "unknown"


# ---------------------------------------------------------------- Instagram
IG = PLATFORMS["instagram"]


def ig_driver(*, reel_notice=True):
    d = FakeDriver(visible={IG.NEW_POST, IG.POPUPS[0]})

    def opened(dr):
        dr.visible_set.add(IG.FILE_INPUT)
    d.hooks[("click", IG.NEW_POST)] = opened

    def uploaded(dr):
        dr.visible_set.add(IG.heading("Crop"))
        dr.visible_set.add(IG.NEXT)
        if reel_notice:
            dr.visible_set.add(IG.REEL_OK)
    d.hooks[("upload", IG.FILE_INPUT)] = uploaded
    steps = iter(["Edit", "caption"])

    def next_page(dr):
        step = next(steps)
        if step == "Edit":
            dr.visible_set.add(IG.heading("Edit"))
        else:
            dr.visible_set.update({IG.CAPTION, IG.SHARE})
    d.hooks[("click", IG.NEXT)] = next_page
    d.hooks[("click", IG.SHARE)] = lambda dr: dr.texts.__setitem__(IG.DIALOG, "Reel shared\nYour reel has been shared.")
    return d


def test_instagram_publishes_reel_through_crop_and_edit():
    d = ig_driver()
    p = post()
    r = IG.publish(d, IG.compose(p), p)
    assert r.status == "success"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks == [IG.NEW_POST, IG.REEL_OK, IG.NEXT, IG.NEXT, IG.SHARE]
    assert d.acts("type")[0][1] == IG.CAPTION
    assert d.acts("dismiss")[0][1] == IG.POPUPS
    assert IG.READY_KINDS == {"video"}


def test_instagram_without_reel_notice_still_works():
    d = ig_driver(reel_notice=False)
    p = post()
    assert IG.publish(d, IG.compose(p), p).status == "success"


def test_instagram_error_text_is_failed():
    d = ig_driver()
    d.hooks[("click", IG.SHARE)] = lambda dr: dr.texts.__setitem__(IG.DIALOG, "Your reel couldn't be shared.")
    p = post()
    r = IG.publish(d, IG.compose(p), p)
    assert r.status == "failed" and "couldn't" in r.message


def test_instagram_no_share_confirmation_is_unknown():
    d = ig_driver()
    d.hooks.pop(("click", IG.SHARE))
    p = post()
    assert IG.publish(d, IG.compose(p), p).status == "unknown"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py -q -k "threads or instagram"`
Expected: FAIL，`AttributeError: module 'overseas.threads' has no attribute 'OPEN_COMPOSER'`

- [ ] **Step 3: 实现 Threads**

`threads.py` 把占位的 `PUBLISH_URL` / `READY_KINDS` 两行替换为：

```python
PUBLISH_URL = HOME_URL
READY_KINDS = frozenset({"video"})       # 图文 / 纯文字在 PR 3 接通
# 首页「What's new?」打开发帖弹窗；真机校准于 2026-10-01
OPEN_COMPOSER = '[aria-label^="Empty text field"]'
DIALOG = '[role="dialog"]'
TEXTBOX = f'{DIALOG} [role="textbox"]'
FILE_INPUT = f'{DIALOG} input[type="file"]'
MEDIA_READY = f'{DIALOG} video'
POST_BUTTON = f'{DIALOG} div[role="button"]:text-is("Post")'   # 精确匹配，别点成 Post Options
POSTED_LINK = 'a[href*="/post/"]:has-text("View")'
POST_WAIT_S = 120
```

把占位 `publish` 替换为：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(OPEN_COMPOSER, 30000):
        raise base.StepFailed("找不到发帖入口（What's new?）")
    drv.click(OPEN_COMPOSER)
    if not drv.wait_for(TEXTBOX, 15000):
        raise base.StepFailed("发帖弹窗没打开")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(MEDIA_READY, 120000):
        raise base.StepFailed("视频没挂上（弹窗里没出现视频预览）")
    drv.type_text(TEXTBOX, fields["caption"], clear=False)
    drv.click(POST_BUTTON)
    for _ in range(POST_WAIT_S):
        if not drv.visible(DIALOG) and drv.visible(POSTED_LINK):
            href = drv.attr(POSTED_LINK, "href")
            url = f"https://www.threads.com{href}" if href.startswith("/") else href
            return base.Result("success", url=url, message="已发布到 Threads")
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但没等到「已发布」提示")
```

- [ ] **Step 4: 实现 Instagram**

`instagram.py` 把占位的两行替换为：

```python
PUBLISH_URL = HOME_URL
READY_KINDS = frozenset({"video"})       # 图文在 PR 3 接通
# 新建帖子流程：New post → 选文件 →（Reels 提示 OK）→ Crop → Next → Edit → Next → 写说明 → Share
# 真机校准于 2026-10-01
DIALOG = '[role="dialog"]'
NEW_POST = 'svg[aria-label="New post"]'
FILE_INPUT = f'{DIALOG} input[type="file"]'
REEL_OK = f'{DIALOG} button:text-is("OK")'
NEXT = f'{DIALOG} div[role="button"]:text-is("Next")'
CAPTION = f'{DIALOG} [role="textbox"][aria-label^="Add a caption"]'
SHARE = f'{DIALOG} div[role="button"]:text-is("Share")'
POPUPS = ('button:text-is("Not Now")',)      # 首页「开启通知」弹窗
POST_WAIT_S = 300                            # Reels 要转码，最长等 5 分钟


def heading(text: str) -> str:
    return f'{DIALOG} [role="heading"]:text-is("{text}")'
```

把占位 `publish` 替换为：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    drv.dismiss(POPUPS)
    if not drv.wait_for(NEW_POST, 20000):
        raise base.StepFailed("找不到新建帖子入口（New post）")
    drv.click(NEW_POST)
    if not drv.wait_for(FILE_INPUT, 15000, state="attached"):
        raise base.StepFailed("新建帖子弹窗没打开")
    drv.upload(FILE_INPUT, post.media)
    if drv.wait_for(REEL_OK, 8000):
        drv.click(REEL_OK)
    for step in ("Crop", "Edit"):
        if not drv.wait_for(heading(step), 60000):
            raise base.StepFailed(f"没到 {step} 页")
        drv.click(NEXT)
    if not drv.wait_for(CAPTION, 30000):
        raise base.StepFailed("没到写说明那一步")
    drv.type_text(CAPTION, fields["caption"], clear=False)
    drv.click(SHARE)
    for _ in range(POST_WAIT_S):
        text = drv.text(DIALOG).lower()
        if "shared" in text and "couldn" not in text:
            return base.Result("success", message="已发布到 Instagram")
        if "couldn" in text or "try again" in text:
            return base.Result("failed", message=drv.text(DIALOG)[:120])
        drv.pause(1000)
    return base.Result("unknown", message="点了分享，但没等到「已分享」提示")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py tests/test_overseas_platforms.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add skills/shared/scripts/overseas/threads.py skills/shared/scripts/overseas/instagram.py tests/test_overseas_flows.py
git commit -m "feat(overseas): Threads 与 Instagram（Reels）视频发布流程

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: TikTok 与 YouTube 视频发布

**Files:**
- Modify: `skills/shared/scripts/overseas/tiktok.py`、`skills/shared/scripts/overseas/youtube.py`
- Test: `tests/test_overseas_flows.py`（追加）

**Interfaces:**
- Consumes: 同 Task 3
- Produces:
  - `tiktok.py`：`FILE_INPUT`、`UPLOADED`、`CAPTION`、`VISIBILITY_BUTTON`、`VISIBILITY_LABEL: dict`、`option(label) -> str`、`POST_BUTTON`、`POPUPS`、`POST_NOW`、`UPLOAD_WAIT_S = 300`、`POST_WAIT_S = 180`
  - `youtube.py`：`CREATE`、`UPLOAD_ITEM`、`FILE_INPUT`、`TITLE`、`DESCRIPTION`、`NOT_FOR_KIDS`、`NEXT`、`VISIBILITY_RADIO: dict`、`DONE`、`PUBLISHED_LINK`、`NO_CHANNEL_MARKERS`；`READY_KINDS` 仍为 `frozenset()`（Task 9 真机校准后改）

- [ ] **Step 1: 写失败的测试（追加）**

```python
# ---------------------------------------------------------------- TikTok
TT = PLATFORMS["tiktok"]


def tiktok_driver():
    d = FakeDriver(visible={TT.FILE_INPUT, TT.CAPTION, TT.VISIBILITY_BUTTON}, enabled={TT.POST_BUTTON})
    d.hooks[("upload", TT.FILE_INPUT)] = lambda dr: dr.texts.__setitem__(TT.UPLOADED, "clip.mp4 1080P Uploaded")
    d.hooks[("click", TT.VISIBILITY_BUTTON)] = lambda dr: dr.visible_set.update(
        {TT.option(v) for v in TT.VISIBILITY_LABEL.values()})
    d.visible_set.add(TT.POST_BUTTON)
    d.hooks[("click", TT.POST_BUTTON)] = lambda dr: setattr(dr, "_url", "https://www.tiktok.com/tiktokstudio/content")
    return d


def test_tiktok_publishes_with_visibility():
    d = tiktok_driver()
    p = post(visibility="only_me")
    r = TT.publish(d, TT.compose(p), p)
    assert r.status == "success"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks == [TT.VISIBILITY_BUTTON, TT.option("Only you"), TT.POST_BUTTON]
    assert d.acts("type")[0][1] == TT.CAPTION      # 清掉预填的文件名再写
    assert TT.READY_KINDS == {"video"}


def test_tiktok_upload_never_finishes_is_step_failed():
    d = tiktok_driver()
    d.hooks.pop(("upload", TT.FILE_INPUT))
    p = post()
    with pytest.raises(base.StepFailed, match="上传超时"):
        TT.publish(d, TT.compose(p), p)


def test_tiktok_confirms_post_now_when_content_check_pending():
    d = tiktok_driver()
    d.hooks[("click", TT.POST_BUTTON)] = lambda dr: dr.visible_set.add(TT.POST_NOW)
    d.hooks[("click", TT.POST_NOW)] = lambda dr: setattr(dr, "_url", "https://www.tiktok.com/tiktokstudio/content")
    p = post()
    assert TT.publish(d, TT.compose(p), p).status == "success"
    assert d.acts("click")[-1][1] == TT.POST_NOW


def test_tiktok_stays_on_upload_page_is_unknown():
    d = tiktok_driver()
    d.hooks.pop(("click", TT.POST_BUTTON))
    p = post()
    assert TT.publish(d, TT.compose(p), p).status == "unknown"


# ---------------------------------------------------------------- YouTube
YT = PLATFORMS["youtube"]


def youtube_driver():
    d = FakeDriver(visible={YT.CREATE}, url=YT.PUBLISH_URL)
    d.hooks[("click", YT.CREATE)] = lambda dr: dr.visible_set.add(YT.UPLOAD_ITEM)
    d.hooks[("click", YT.UPLOAD_ITEM)] = lambda dr: dr.visible_set.add(YT.FILE_INPUT)
    d.hooks[("upload", YT.FILE_INPUT)] = lambda dr: dr.visible_set.update(
        {YT.TITLE, YT.DESCRIPTION, YT.NOT_FOR_KIDS, YT.NEXT, *YT.VISIBILITY_RADIO.values(), YT.DONE})

    def done(dr):
        dr.visible_set.add(YT.PUBLISHED_LINK)
        dr.attrs[(YT.PUBLISHED_LINK, "href")] = "https://youtu.be/abc123"
    d.hooks[("click", YT.DONE)] = done
    return d


def test_youtube_flow_sets_title_description_visibility():
    d = youtube_driver()
    p = post(title="My Short", visibility="private")
    r = YT.publish(d, YT.compose(p), p)
    assert r.status == "success" and r.url == "https://youtu.be/abc123"
    typed = {a[1]: a[2] for a in d.acts("type")}
    assert typed[YT.TITLE] == "My Short" and typed[YT.DESCRIPTION] == "Hello world\n\n#ai"
    clicks = [a[1] for a in d.acts("click")]
    assert clicks.count(YT.NEXT) == 3
    assert YT.VISIBILITY_RADIO["private"] in clicks and clicks[-1] == YT.DONE
    assert YT.READY_KINDS == frozenset()        # 没频道、未真机校准：先不开放


def test_youtube_without_channel_says_so():
    d = youtube_driver()
    d.hooks[("goto", YT.PUBLISH_URL)] = lambda dr: setattr(dr, "_url", "https://www.youtube.com/?channel_creation_token=x")
    p = post(title="T")
    with pytest.raises(base.StepFailed, match="频道"):
        YT.publish(d, YT.compose(p), p)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py -q -k "tiktok or youtube"`
Expected: FAIL，`AttributeError: module 'overseas.tiktok' has no attribute 'FILE_INPUT'`

- [ ] **Step 3: 实现 TikTok**

`tiktok.py` 把占位的两行替换为：

```python
PUBLISH_URL = "https://www.tiktok.com/tiktokstudio/upload"
READY_KINDS = frozenset({"video"})       # 图片轮播在 PR 3 视网页版能力接通
# TikTok Studio 上传页；真机校准于 2026-10-01
FILE_INPUT = 'input[type="file"][accept^="video"]'
UPLOADED = '[data-e2e="upload_status_container"]'           # 上传完显示「Uploaded」
CAPTION = '[data-e2e="caption_container"] .public-DraftEditor-content'   # 预填了文件名，要先清空
VISIBILITY_BUTTON = '[data-e2e="video_visibility_container"] button[role="combobox"]'
VISIBILITY_LABEL = {"everyone": "Everyone", "friends": "Friends", "only_me": "Only you"}
POST_BUTTON = '[data-e2e="post_video_button"]'
# 新功能引导（react-joyride）、「开启内容检查？」等弹窗：选不开启
POPUPS = ('.react-joyride__tooltip button:has-text("Got it")',
          '.TUXModal-overlay button:has-text("Cancel")',
          '.TUXModal-overlay button:has-text("Got it")')
POST_NOW = '.TUXModal-overlay button:has-text("Post now")'  # 内容检查没跑完时的确认
UPLOAD_WAIT_S = 300
POST_WAIT_S = 180


def option(label: str) -> str:
    return f'[role="option"]:has-text("{label}")'
```

把占位 `publish` 替换为：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(FILE_INPUT, 30000, state="attached"):
        raise base.StepFailed("上传页没打开（找不到选择视频）")
    drv.upload(FILE_INPUT, post.media)
    for _ in range(UPLOAD_WAIT_S):
        if "uploaded" in drv.text(UPLOADED).lower():
            break
        drv.dismiss(POPUPS, rounds=1)
        drv.pause(1000)
    else:
        raise base.StepFailed("视频上传超时")
    drv.dismiss(POPUPS)
    drv.type_text(CAPTION, fields["caption"], clear=True)
    drv.dismiss(POPUPS)
    drv.click(VISIBILITY_BUTTON)
    drv.click(option(VISIBILITY_LABEL[fields["visibility"]]))
    if not drv.wait_enabled(POST_BUTTON, 120000):
        raise base.StepFailed("发布按钮一直不能点")
    drv.click(POST_BUTTON)
    for _ in range(POST_WAIT_S):
        if "/tiktokstudio/content" in drv.url():
            return base.Result("success", message="已发布到 TikTok")
        if drv.visible(POST_NOW):
            drv.click(POST_NOW)
        drv.pause(1000)
    return base.Result("unknown", message="点了发布，但页面没跳到作品管理")
```

- [ ] **Step 4: 实现 YouTube（先不开放）**

`youtube.py` 把占位的两行替换为：

```python
PUBLISH_URL = "https://studio.youtube.com/"
# 账号还没有频道、选择器未经真机校准：先不开放（PR 2 计划 Task 9 有频道后校准再改成 {"video"}）
READY_KINDS: frozenset[str] = frozenset()
NO_CHANNEL_MARKERS = ("channel_creation_token", "/create_channel")
CREATE = "#create-icon"
UPLOAD_ITEM = "tp-yt-paper-item#text-item-0"
FILE_INPUT = 'input[type="file"]'
TITLE = "#title-textarea #textbox"
DESCRIPTION = "#description-textarea #textbox"
NOT_FOR_KIDS = 'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
NEXT = "#next-button"
VISIBILITY_RADIO = {
    "public": 'tp-yt-paper-radio-button[name="PUBLIC"]',
    "unlisted": 'tp-yt-paper-radio-button[name="UNLISTED"]',
    "private": 'tp-yt-paper-radio-button[name="PRIVATE"]',
}
DONE = "#done-button"
PUBLISHED_LINK = 'a[href*="youtu.be/"], a[href*="/shorts/"], a[href*="watch?v="]'
POST_WAIT_S = 600       # 上传 + 处理
```

把占位 `publish` 替换为：

```python
def publish(drv, fields: dict, post: Post) -> base.Result:
    drv.goto(PUBLISH_URL)
    if any(m in drv.url() for m in NO_CHANNEL_MARKERS):
        raise base.StepFailed("这个 Google 账号还没有 YouTube 频道：先在 youtube.com →「设置」→「账号」创建频道")
    if not drv.wait_for(CREATE, 30000):
        raise base.StepFailed("YouTube Studio 没打开（找不到「创建」）")
    drv.click(CREATE)
    drv.click(UPLOAD_ITEM)
    if not drv.wait_for(FILE_INPUT, 15000, state="attached"):
        raise base.StepFailed("上传窗口没打开")
    drv.upload(FILE_INPUT, post.media)
    if not drv.wait_for(TITLE, 120000):
        raise base.StepFailed("上传后没出现标题框")
    drv.type_text(TITLE, fields["title"], clear=True)
    drv.type_text(DESCRIPTION, fields["description"], clear=True)
    drv.click(NOT_FOR_KIDS)
    for _ in range(3):
        drv.click(NEXT)
    drv.click(VISIBILITY_RADIO[fields["visibility"]])
    drv.click(DONE)
    for _ in range(POST_WAIT_S):
        if drv.visible(PUBLISHED_LINK):
            return base.Result("success", url=drv.attr(PUBLISHED_LINK, "href"), message="已发布到 YouTube")
        drv.pause(1000)
    return base.Result("unknown", message="点了完成，但没等到视频链接")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py tests/test_overseas_platforms.py -q && .venv/bin/python skills/shared/scripts/overseas_publisher.py selftest`
Expected: 全部 PASS；selftest ✅

- [ ] **Step 6: 提交**

```bash
git add skills/shared/scripts/overseas/tiktok.py skills/shared/scripts/overseas/youtube.py tests/test_overseas_flows.py
git commit -m "feat(overseas): TikTok 视频发布流程；YouTube 流程（未校准，先不开放）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `overseas_publisher.py publish` 命令

**Files:**
- Modify: `skills/shared/scripts/overseas_publisher.py`
- Modify: `skills/shared/scripts/calendar_ops.py`（`PLATFORM_NAMES` 加 5 个平台）
- Test: `tests/test_overseas_publish.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `PageDriver`、`Result`、`StepFailed`、`Blocked`、`save_failure`；各平台 `compose` / `publish` / `READY_KINDS`；`post.validate`、`PostError`；`content_guard.guard_or_die(parts, *, exec_mode, allow_unsafe=False, label=...)`；`calendar_ops.record_publish(platform, title, url="", ptype="", tags="", note="", source="chat")`；`login_state.write_status(path, state, message)`
- Produces:
  - 常量：`EXIT_INVALID = 2`、`EXIT_PLAYWRIGHT = 3`、`EXIT_UNKNOWN = 5`、`EXIT_NOT_LOGGED_IN = 6`、`PUBLISH_LOCK_WAIT_S = 60`
  - `build_post(a) -> Post`、`check_publishable(mod, post) -> None`（不合格抛 `PostError`）
  - `run_publish(mod, post, fields, *, headed=False, status_file=None, launch=base.launch, driver_cls=base.PageDriver, profile_root=None, record=None) -> int`
  - 命令：`publish --platform P --media M [--media M2] --title --desc --tags --visibility --status-file --headed --allow-unsafe --exec`
  - 状态文件状态：`starting` → `publishing` → `success` / `error`（消息给发布中心看）

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_publish.py`：

```python
"""overseas_publisher publish 命令的离线测试：假平台、假浏览器、假驱动，不连平台。"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import overseas_publisher as op  # noqa: E402
from overseas import base  # noqa: E402
from overseas.post import Limits, Post, caption_text  # noqa: E402


class FakeDrv:
    def __init__(self, page):
        self.page = page
        self.world = page.world

    def goto(self, url, timeout_ms=60000):
        if self.world.blocked_headless and not self.page.headed:
            raise base.Blocked("captcha")

    def settle(self, mod):
        return self.world.logged


class World:
    def __init__(self, *, logged=True, result=None, raises=None, blocked_headless=False):
        self.logged, self.result, self.raises = logged, result, raises
        self.blocked_headless = blocked_headless
        self.launches: list[bool] = []
        self.published = 0

    @contextmanager
    def launch(self, profile, *, headed):
        self.launches.append(headed)
        page = SimpleNamespace(headed=headed, world=self)
        yield SimpleNamespace(pages=[page], new_page=lambda: page)


def make_mod(world):
    def publish(drv, fields, post):
        world.published += 1
        if world.raises:
            raise world.raises
        return world.result or base.Result("success", url="https://demo.test/p/1")
    return SimpleNamespace(
        KEY="demo", NAME="Demo", PROFILE="DemoProfile", HOME_URL="https://demo.test/",
        KINDS=frozenset({"video", "text"}), READY_KINDS=frozenset({"video"}),
        LIMITS=Limits(caption=100), VISIBILITY=(), compose=lambda p: {"caption": caption_text(p)},
        publish=publish)


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 16)
    monkeypatch.setattr(base, "save_failure", lambda page, key: None)
    return tmp_path, video


def run(world, tmp_path, video, *, headed=False):
    recorded: list[tuple] = []
    mod = make_mod(world)
    p = Post(media=[video], desc="Hello", tags="ai")
    sf = tmp_path / "status.json"
    rc = op.run_publish(mod, p, mod.compose(p), headed=headed, status_file=str(sf), launch=world.launch,
                        driver_cls=FakeDrv, profile_root=tmp_path / "profiles",
                        record=lambda *a, **k: recorded.append((a, k)))
    status = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    return rc, status, recorded


def test_success_records_calendar_and_status(env):
    tmp_path, video = env
    rc, status, recorded = run(World(), tmp_path, video)
    assert rc == 0 and status["state"] == "success"
    assert "https://demo.test/p/1" in status["message"]
    assert len(recorded) == 1 and recorded[0][0][0].url == "https://demo.test/p/1"


def test_unknown_result_is_exit_5_without_retry_or_calendar(env):
    """点了发布没等到成功信号：退出码 5、提示别重发、不重试、不记日历（Review Focus 1）。"""
    tmp_path, video = env
    world = World(result=base.Result("unknown", message="没等到提示"))
    rc, status, recorded = run(world, tmp_path, video)
    assert rc == op.EXIT_UNKNOWN == 5
    assert status["state"] == "error" and "不要直接重发" in status["message"]
    assert world.published == 1 and recorded == []


def test_step_failed_is_exit_1_with_hint(env):
    tmp_path, video = env
    rc, status, _ = run(World(raises=base.StepFailed("找不到发布按钮")), tmp_path, video)
    assert rc == 1 and "找不到发布按钮" in status["message"] and "改版" in status["message"]


def test_failed_result_is_exit_1(env):
    tmp_path, video = env
    rc, status, recorded = run(World(result=base.Result("failed", message="平台拒绝")), tmp_path, video)
    assert rc == 1 and "平台拒绝" in status["message"] and recorded == []


def test_not_logged_in_is_exit_6(env):
    """未登录：退出码 6，不走发布流程（Review Focus 4）。"""
    tmp_path, video = env
    world = World(logged=False)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == op.EXIT_NOT_LOGGED_IN == 6 and "未登录" in status["message"]
    assert world.published == 0


def test_unsettled_login_is_not_published(env):
    tmp_path, video = env
    world = World(logged=None)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 1 and "没法确认" in status["message"] and world.published == 0


def test_missing_profile_is_exit_6_without_browser(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    world = World()
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 6 and world.launches == []


def test_blocked_headless_retries_headed_once(env):
    tmp_path, video = env
    world = World(blocked_headless=True)
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 0 and world.launches == [False, True]


def test_blocked_even_when_headed_is_error(env):
    tmp_path, video = env
    world = World(blocked_headless=True)

    @contextmanager
    def always_blocked(profile, *, headed):
        world.launches.append(headed)
        page = SimpleNamespace(headed=False, world=world)   # 有头也被拦
        yield SimpleNamespace(pages=[page], new_page=lambda: page)

    world.launch = always_blocked
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 1 and "验证" in status["message"] and world.launches == [False, True]


def test_playwright_missing_is_exit_3(env):
    tmp_path, video = env
    world = World()

    @contextmanager
    def no_pw(profile, *, headed):
        raise base.PlaywrightMissing("需要 playwright")
        yield  # pragma: no cover

    world.launch = no_pw
    rc, status, _ = run(world, tmp_path, video)
    assert rc == 3


# ---------------------------------------------------------------- 命令行：校验 / 预览 / 闸门
def cli(monkeypatch, *argv):
    monkeypatch.setattr(op, "run_publish", lambda *a, **k: pytest.fail("不该走到真发布"))
    try:
        return op.main(["publish", *argv])
    except SystemExit as e:
        return e.code


def test_dry_run_prints_fields_and_never_launches(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "Hello", "--tags", "ai")
    out = capsys.readouterr().out
    assert rc == 0 and '"caption": "Hello\\n\\n#ai"' in out and "--exec" in out


def test_invalid_content_is_exit_2(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "中" * 200, "--exec")
    assert rc == op.EXIT_INVALID == 2


def test_kind_not_ready_yet_is_exit_2(monkeypatch, capsys):
    rc = cli(monkeypatch, "--platform", "x", "--desc", "just text", "--exec")
    assert rc == 2 and "还没接通" in capsys.readouterr().err


def test_youtube_not_open_until_calibrated(monkeypatch, capsys, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "youtube", "--media", str(video), "--title", "T", "--exec")
    assert rc == 2 and "YouTube" in capsys.readouterr().err


def test_exec_guard_scans_media_filenames(monkeypatch, capsys, tmp_path):
    """文件名带密钥：真发前被内容安全闸门拦下，退出码 7（Review Focus 5）。"""
    video = tmp_path / "sk-ABCDefgh12345678ijkl.mp4"
    video.write_bytes(b"\x00")
    rc = cli(monkeypatch, "--platform", "x", "--media", str(video), "--desc", "Hello", "--exec")
    assert rc == 7


def test_exec_hands_post_to_run_publish(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00")
    seen = {}

    def fake_run(mod, post, fields, **kw):
        seen.update(key=mod.KEY, caption=fields["caption"], headed=kw["headed"], sf=kw["status_file"])
        return 0

    monkeypatch.setattr(op, "run_publish", fake_run)
    rc = op.main(["publish", "--platform", "x", "--media", str(video), "--desc", "Hi", "--status-file",
                  str(tmp_path / "s.json"), "--exec"])
    assert rc == 0 and seen == {"key": "x", "caption": "Hi", "headed": False, "sf": str(tmp_path / "s.json")}


def test_selftest_checks_ready_kinds(capsys):
    assert op.main(["selftest"]) == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_publish.py -q`
Expected: FAIL，`AttributeError: module 'overseas_publisher' has no attribute 'run_publish'`

- [ ] **Step 3: 实现**

`overseas_publisher.py`：

3a. 文档字符串第一行改为「海外平台（TikTok / YouTube / Instagram / X / Threads）登录、登录态校验与发布。」，用法里加一行：

```
  python skills/shared/scripts/overseas_publisher.py publish --platform x --media out.mp4 --desc "..." [--exec]
```

3b. import 区改为：

```python
import argparse
import json
import sys
import time
from pathlib import Path

import calendar_ops
import content_guard
import login_state
from overseas import PLATFORMS, REQUIRED_ATTRS, base, get
from overseas.post import KIND_LABEL, Post, PostError, validate, x_weighted_length
```

3c. 常量区加：

```python
EXIT_INVALID = 2
EXIT_PLAYWRIGHT = 3
EXIT_UNKNOWN = 5
EXIT_NOT_LOGGED_IN = 6
PUBLISH_LOCK_WAIT_S = 60
UNKNOWN_MSG = "{name}：{detail}。结果待确认，请先到 {name} 上看一眼，不要直接重发"
STEP_FAILED_MSG = "{name} 发布失败：{err}（页面可能改版了，现场截图在 outputs/_login/{key}-publish-fail.png）"
```

3d. 在 `_print_platforms` 之前加：

```python
def build_post(a) -> Post:
    return Post(media=[Path(m).expanduser() for m in a.media or []], title=a.title or "", desc=a.desc or "",
                tags=a.tags or "", visibility=a.visibility or "")


def check_publishable(mod, post: Post) -> None:
    validate(post, name=mod.NAME, kinds=mod.KINDS, limits=mod.LIMITS, visibility=mod.VISIBILITY)
    if post.kind not in mod.READY_KINDS:
        if not mod.READY_KINDS:
            raise PostError(f"{mod.NAME} 发布还没接通（YouTube 需要账号先有频道并完成真机校准）")
        raise PostError(f"{mod.NAME} 的{KIND_LABEL[post.kind]}发布还没接通，目前只能发视频")


def _pub_fail(sf, msg: str, rc: int) -> int:
    login_state.write_status(sf, "error", msg)
    print(f"❌ {msg}", file=sys.stderr)
    return rc


def _record(mod, post: Post, fields: dict, result) -> None:
    title = post.title or (fields.get("caption") or fields.get("description") or "").split("\n")[0][:60]
    calendar_ops.record_publish(mod.KEY, title, url=result.url, ptype=KIND_LABEL[post.kind], tags=post.tags)


def run_publish(mod, post: Post, fields: dict, *, headed: bool = False, status_file=None, launch=base.launch,
                driver_cls=base.PageDriver, profile_root=None, record=None) -> int:
    """真发布：确认登录 → 平台流程 → 按结果落状态。被拦（验证页）且没开窗口时改开有头窗口重试一次。
    结果待确认（unknown）绝不重试、不记日历。record(result) 成功后记日历（测试注入）。"""
    sf = status_file
    if record is None:
        def record(result):
            _record(mod, post, fields, result)
    profile = base.profile_dir(mod, profile_root)
    if not profile.is_dir():
        return _pub_fail(sf, f"{mod.NAME} 未登录：请先在账号页登录", EXIT_NOT_LOGGED_IN)
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(PUBLISH_LOCK_WAIT_S)
    except TimeoutError:
        return _pub_fail(sf, f"{mod.NAME} 的登录目录正被占用（可能在登录或校验），请稍后再发", 1)
    try:
        attempts = [True] if headed else [False, True]
        for i, use_headed in enumerate(attempts):
            try:
                return _publish_once(mod, post, fields, use_headed, sf, launch, driver_cls, profile, record)
            except base.Blocked as e:
                if i + 1 < len(attempts):
                    login_state.write_status(sf, "publishing", f"{mod.NAME} 要人工验证，已弹出浏览器窗口，请在窗口里完成验证")
                    print(f"⚠️ {mod.NAME} 拦了无头浏览器（{e}），改开窗口重试", file=sys.stderr)
                    continue
                return _pub_fail(sf, f"{mod.NAME} 要求人工验证，没能通过：{e}", 1)
        return 1
    except base.PlaywrightMissing as e:
        return _pub_fail(sf, str(e), EXIT_PLAYWRIGHT)
    finally:
        lock.release()


def _publish_once(mod, post, fields, headed, sf, launch, driver_cls, profile, record) -> int:
    with launch(profile, headed=headed) as ctx:
        drv = driver_cls(base.first_page(ctx))
        login_state.write_status(sf, "publishing", f"正在打开 {mod.NAME}…")
        drv.goto(mod.HOME_URL)
        state = drv.settle(mod)
        if state is None:
            return _pub_fail(sf, f"{mod.NAME} 登录态没法确认（页面一直没稳定），请稍后再试", 1)
        if not state:
            return _pub_fail(sf, f"{mod.NAME} 未登录：请先在账号页登录", EXIT_NOT_LOGGED_IN)
        login_state.write_status(sf, "publishing", f"正在发布到 {mod.NAME}（上传和处理视频可能要几分钟）…")
        try:
            result = mod.publish(drv, fields, post)
        except base.StepFailed as e:
            base.save_failure(drv.page, mod.KEY)
            return _pub_fail(sf, STEP_FAILED_MSG.format(name=mod.NAME, err=e, key=mod.KEY), 1)
        if result.status == "success":
            msg = result.message or f"已发布到 {mod.NAME}"
            if result.url:
                msg += f"：{result.url}"
            login_state.write_status(sf, "success", msg)
            print(f"✅ {msg}")
            try:
                record(result)
            except Exception as e:  # noqa: BLE001 — 记日历失败不影响发布结果
                print(f"记日历失败（忽略）：{base.short_err(e)}", file=sys.stderr)
            return 0
        base.save_failure(drv.page, mod.KEY)
        if result.status == "unknown":
            return _pub_fail(sf, UNKNOWN_MSG.format(name=mod.NAME, detail=result.message), EXIT_UNKNOWN)
        return _pub_fail(sf, f"{mod.NAME} 发布失败：{result.message}", 1)


def cmd_publish(a) -> int:
    mod = get(a.platform)
    post = build_post(a)
    sf = a.status_file
    try:
        check_publishable(mod, post)
    except PostError as e:
        return _pub_fail(sf, str(e), EXIT_INVALID)
    fields = mod.compose(post)
    parts = [post.title, post.desc, post.tags, *(m.name for m in post.media)]   # 文件名也会发出去
    label = f"{mod.NAME} 发布内容"
    if not a.exec:
        content_guard.guard_or_die(parts, exec_mode=False, allow_unsafe=a.allow_unsafe, label=label)
        print(json.dumps({"platform": mod.KEY, "kind": post.kind, "media": [str(m) for m in post.media],
                          "fields": fields}, ensure_ascii=False, indent=2))
        print("dry-run：只预览，加 --exec 才会真正发布")
        return 0
    content_guard.guard_or_die(parts, exec_mode=True, allow_unsafe=a.allow_unsafe, label=label)
    login_state.write_status(sf, "starting", f"准备发布到 {mod.NAME}…")
    return run_publish(mod, post, fields, headed=a.headed, status_file=sf)
```

3e. `_selftest` 循环体末尾（`LOGIN_MARKERS` 检查之后）加：

```python
        if not set(m.READY_KINDS) <= set(m.KINDS):
            problems.append(f"{key} 的 READY_KINDS 超出了 KINDS")
```

3f. `main()` 里 `sub.add_parser("selftest", ...)` 之前加：

```python
    p = sub.add_parser("publish", help="发布（默认只预览；--exec 才真发）")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    p.add_argument("--media", action="append", help="视频或图片路径（可重复）；不传即纯文字")
    p.add_argument("--title", help="标题（YouTube 必填，≤100）")
    p.add_argument("--desc", help="正文 / 说明")
    p.add_argument("--tags", help="话题标签，逗号或空格分隔")
    p.add_argument("--visibility", help="可见范围：YouTube public/unlisted/private；TikTok everyone/friends/only_me")
    p.add_argument("--status-file", help="发布状态 JSON（Web 发布中心轮询它）")
    p.add_argument("--headed", action="store_true", help="开窗口发布（平台要人工验证时用）")
    p.add_argument("--allow-unsafe", action="store_true", help="放行内容安全闸门（检出敏感信息也照发，谨慎）")
    p.add_argument("--exec", action="store_true", help="真正发布（默认只预览）")
```

并在 `if a.cmd == "login":` 之前加：

```python
    if a.cmd == "publish":
        return cmd_publish(a)
```

3g. `calendar_ops.py` 的 `PLATFORM_NAMES` 改为：

```python
PLATFORM_NAMES = {
    "xiaohongshu": "小红书", "douyin": "抖音", "kuaishou": "快手",
    "weixin-channels": "微信视频号", "zhihu": "知乎", "bilibili": "B站",
    "tiktok": "TikTok", "youtube": "YouTube", "instagram": "Instagram", "x": "X", "threads": "Threads",
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_publish.py tests/test_overseas_login.py -q && .venv/bin/python skills/shared/scripts/overseas_publisher.py selftest`
Expected: 全部 PASS；selftest ✅

- [ ] **Step 5: 提交**

```bash
git add skills/shared/scripts/overseas_publisher.py skills/shared/scripts/calendar_ops.py tests/test_overseas_publish.py
git commit -m "feat(overseas): publish 命令——预览 / 真发、内容安全闸门、被拦改窗口重试、结果待确认不重发

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Web 发布接口接入海外平台

**Files:**
- Modify: `web/app.py`（`MEDIA_REQUIRED`、`VIDEO_ONLY_PUBLISH`、`PublishRequest`、`api_publish`）
- Test: `tests/test_overseas_web.py`（追加）

**Interfaces:**
- Consumes: Task 5 的命令行 `publish --platform --title --desc --tags --status-file --exec --media ... [--visibility]`；现有 `_start_async_publish(platform, cmd, title, body, cfg, status_file, code_file)`
- Produces: `PublishRequest.visibility: str = ''`；`OVERSEAS_PUBLISH: set[str]`；海外平台 `POST /api/publish/{p}` 返回 `{'async': True, 'pending': True, ...}`

- [ ] **Step 1: 写失败的测试（追加到 `tests/test_overseas_web.py`）**

先确认 `_safe_output_path` 用的根目录：`grep -n "def _safe_output_path" -A8 web/app.py`。下面的测试假设它基于 `OUTPUTS_DIR`；若是别的变量，测试里一并 monkeypatch。

```python
def _outputs_with(tmp_path, monkeypatch, name, data):
    outputs = tmp_path / "outputs"
    (outputs / "proj").mkdir(parents=True)
    (outputs / "proj" / name).write_bytes(data)
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    monkeypatch.setattr(web, "PUBLISH_DIR", outputs / "_publish")
    return outputs


def test_publish_overseas_runs_async_with_exact_title(monkeypatch, tmp_path):
    """海外平台走异步发布；title 原样传（发布中心对非 YouTube 平台传空，不能被拿正文前 20 字顶上）。"""
    _outputs_with(tmp_path, monkeypatch, "clip.mp4", b"\x00")
    started = {}

    def fake_start(platform, cmd, title, body, cfg, status_file, code_file):
        started.update(platform=platform, cmd=list(cmd), title=title)
        return {"async": True, "pending": True}

    monkeypatch.setattr(web, "_start_async_publish", fake_start)
    req = web.PublishRequest(title="", body="Hello world #ai", media=["proj/clip.mp4"], tags="", visibility="only_me")
    res = asyncio.run(web.api_publish("tiktok", req))
    assert res["async"] is True
    cmd = started["cmd"]
    assert cmd[1].endswith("overseas_publisher.py") and cmd[2] == "publish"
    assert cmd[cmd.index("--platform") + 1] == "tiktok"
    assert cmd[cmd.index("--title") + 1] == ""
    assert cmd[cmd.index("--desc") + 1] == "Hello world #ai"
    assert cmd[cmd.index("--visibility") + 1] == "only_me"
    assert cmd[cmd.index("--media") + 1].endswith("clip.mp4")
    assert "--exec" in cmd and "--status-file" in cmd


def test_publish_overseas_requires_video_for_now(monkeypatch, tmp_path):
    _outputs_with(tmp_path, monkeypatch, "a.png", b"\x89PNG")
    for platform in OVERSEAS:
        with pytest.raises(web.HTTPException) as ei:
            asyncio.run(web.api_publish(platform, web.PublishRequest(body="hi", media=["proj/a.png"])))
        assert ei.value.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_web.py -q -k publish`
Expected: FAIL（`PublishRequest` 没有 `visibility`；海外平台落到 `web_publisher` 分支报 `KeyError: 'wp'`）

- [ ] **Step 3: 实现**

`MEDIA_REQUIRED` / `VIDEO_ONLY_PUBLISH` 改为：

```python
OVERSEAS_PUBLISH = {"tiktok", "youtube", "instagram", "x", "threads"}
MEDIA_REQUIRED = {"xiaohongshu", "douyin", "kuaishou", "weixin-channels", "bilibili"} | OVERSEAS_PUBLISH
# 只能发视频的平台；海外平台的图文 / 纯文字在下一期接通，现在也只收视频
VIDEO_ONLY_PUBLISH = {"douyin", "weixin-channels", "bilibili"} | OVERSEAS_PUBLISH
```

`PublishRequest` 加字段：

```python
    visibility: str = ''   # 海外平台可见范围：YouTube public/unlisted/private，TikTok everyone/friends/only_me
```

`api_publish` 里 `elif platform == 'wechat-oa':` 之前加分支：

```python
    elif backend == 'overseas':
        # 海外平台：上传 + 平台处理视频要几分钟，异步跑、前端轮询。
        # 标题原样传：发布中心对非 YouTube 平台故意传空（英文文案全在正文里），不能用正文前 20 字顶上。
        PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
        status_file = PUBLISH_DIR / f'{platform}.json'
        code_file = PUBLISH_DIR / f'{platform}.code'
        cmd = [py, str(SHARED_SCRIPTS / 'overseas_publisher.py'), 'publish', '--platform', cfg['op'],
               '--title', req.title.strip(), '--desc', req.body, '--tags', tags,
               '--status-file', str(status_file), '--exec']
        for m in vids or imgs:
            cmd += ['--media', m]
        if req.visibility:
            cmd += ['--visibility', req.visibility]
        return _start_async_publish(platform, cmd, title, req.body, cfg, status_file, code_file)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_web.py tests/test_web_security.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add web/app.py tests/test_overseas_web.py
git commit -m "feat(publish): 发布接口接入海外平台（异步发布、可见范围）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 发布中心前端

**Files:**
- Create: `web/frontend/src/lib/overseasPublish.ts`
- Test: `web/frontend/src/lib/overseasPublish.test.ts`、`web/frontend/src/components/PublishPage.test.tsx`（新建）
- Modify: `web/frontend/src/lib/api.ts`（`publishNow` 载荷）、`web/frontend/src/components/PublishPage.tsx`、发布页样式文件

**Interfaces:**
- Consumes: Task 6 的 `PublishRequest.visibility`
- Produces（`overseasPublish.ts`）：
  - `OVERSEAS_PLATFORMS: { key; label; titleLimit?; bodyLimit; hint; region: 'overseas' }[]`
  - `VISIBILITY_OPTIONS: Record<string, { value: string; label: string }[]>`（youtube、tiktok）
  - `isOverseas(key: string): boolean`
  - `overseasPayload(key: string, text: string): { title: string; body: string; tags: string }`
  - `overseasAdaptRule(keys: string[]): string`

- [ ] **Step 1: 写失败的测试**

`web/frontend/src/lib/overseasPublish.test.ts`：

```ts
import { describe, it, expect } from 'vitest';
import { OVERSEAS_PLATFORMS, VISIBILITY_OPTIONS, isOverseas, overseasPayload, overseasAdaptRule } from './overseasPublish';

describe('overseasPublish', () => {
  it('五个海外平台，限额与后端一致', () => {
    expect(OVERSEAS_PLATFORMS.map((p) => p.key)).toEqual(['tiktok', 'youtube', 'instagram', 'x', 'threads']);
    const yt = OVERSEAS_PLATFORMS.find((p) => p.key === 'youtube')!;
    expect(yt.titleLimit).toBe(100);
    expect(OVERSEAS_PLATFORMS.find((p) => p.key === 'x')!.bodyLimit).toBe(280);
    expect(isOverseas('x')).toBe(true);
    expect(isOverseas('douyin')).toBe(false);
  });

  it('非 YouTube 平台：整段卡片文字作正文，标题和母版标签留空（Review Focus 3）', () => {
    expect(overseasPayload('tiktok', 'Hello world #ai')).toEqual({ title: '', body: 'Hello world #ai', tags: '' });
  });

  it('YouTube：第一行作标题，其余作描述', () => {
    expect(overseasPayload('youtube', 'My Short\n\nAbout this video #ai')).toEqual(
      { title: 'My Short', body: 'About this video #ai', tags: '' });
    expect(overseasPayload('youtube', 'Only title')).toEqual({ title: 'Only title', body: '', tags: '' });
  });

  it('可见范围选项只给 YouTube 和 TikTok', () => {
    expect(Object.keys(VISIBILITY_OPTIONS).sort()).toEqual(['tiktok', 'youtube']);
    expect(VISIBILITY_OPTIONS.tiktok.map((o) => o.value)).toEqual(['everyone', 'friends', 'only_me']);
  });

  it('适配提示：选了海外平台才要求英文', () => {
    expect(overseasAdaptRule(['xiaohongshu'])).toBe('');
    const rule = overseasAdaptRule(['xiaohongshu', 'x', 'youtube']);
    expect(rule).toContain('YouTube、X');
    expect(rule).toContain('英文');
    expect(rule).toContain('第一行');
  });
});
```

`web/frontend/src/components/PublishPage.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  createSchedule: vi.fn(), executeSkill: vi.fn(), runAgent: vi.fn(), streamChat: vi.fn(),
  fetchAccounts: vi.fn(() => Promise.resolve([])), publishNow: vi.fn(), publishStatus: vi.fn(),
  submitPublishSms: vi.fn(), fetchOutputs: vi.fn(() => Promise.resolve([])), mediaUrl: (p: string) => p,
}));

import PublishPage from './PublishPage';

describe('PublishPage 海外平台', () => {
  it('平台分国内、海外两组', () => {
    render(<PublishPage persona="" />);
    const overseas = screen.getByRole('group', { name: '海外平台' });
    expect(within(overseas).getByRole('button', { name: 'TikTok' })).toBeTruthy();
    const domestic = screen.getByRole('group', { name: '国内平台' });
    expect(within(domestic).getByRole('button', { name: '小红书' })).toBeTruthy();
  });

  it('选了 TikTok：卡片里有可见范围选择', () => {
    render(<PublishPage persona="" />);
    fireEvent.click(screen.getByRole('button', { name: 'TikTok' }));
    const select = screen.getByRole('combobox', { name: 'TikTok 可见范围' }) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['', 'everyone', 'friends', 'only_me']);
  });
});
```

注意：`PublishPage` 的草稿存在 localStorage（`loadPublishDraft`），第二个用例开始前若 TikTok 已被前一个用例选中会影响结果——两个用例之间 `localStorage.clear()`（在 `describe` 里加 `beforeEach(() => localStorage.clear())`，并从 vitest 导入 `beforeEach`）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd web/frontend && npx vitest run src/lib/overseasPublish.test.ts src/components/PublishPage.test.tsx`
Expected: FAIL（`overseasPublish` 模块不存在；找不到 role="group" name="海外平台"）

- [ ] **Step 3: 写 `lib/overseasPublish.ts`**

```ts
// 发布中心的海外平台（与 skills/shared/scripts/overseas/<平台>.py 的 LIMITS / VISIBILITY 对齐）。
// 海外平台的卡片正文就是完整英文文案（话题标签写在正文里），所以发送时不再拼中文母版的标题和标签。

export interface OverseasPlatform {
  key: string;
  label: string;
  titleLimit?: number;
  bodyLimit: number;
  hint: string;
  region: 'overseas';
}

export const OVERSEAS_PLATFORMS: OverseasPlatform[] = [
  { key: 'tiktok', label: 'TikTok', bodyLimit: 2200, hint: '英文说明≤2200，需附视频', region: 'overseas' },
  { key: 'youtube', label: 'YouTube', titleLimit: 100, bodyLimit: 5000,
    hint: '第一行是英文标题（≤100），空一行后写描述；需附视频；账号要先有频道', region: 'overseas' },
  { key: 'instagram', label: 'Instagram', bodyLimit: 2200, hint: '英文说明≤2200、话题≤30，视频发成 Reels', region: 'overseas' },
  { key: 'x', label: 'X', bodyLimit: 280, hint: '英文≤280（中日韩文字算 2），需附视频', region: 'overseas' },
  { key: 'threads', label: 'Threads', bodyLimit: 500, hint: '英文≤500，话题只能 1 个，需附视频', region: 'overseas' },
];

const KEYS = new Set(OVERSEAS_PLATFORMS.map((p) => p.key));

export const VISIBILITY_OPTIONS: Record<string, { value: string; label: string }[]> = {
  youtube: [
    { value: 'public', label: '公开' },
    { value: 'unlisted', label: '不公开（有链接可看）' },
    { value: 'private', label: '私享' },
  ],
  tiktok: [
    { value: 'everyone', label: '所有人' },
    { value: 'friends', label: '好友' },
    { value: 'only_me', label: '仅自己' },
  ],
};

export function isOverseas(key: string): boolean {
  return KEYS.has(key);
}

/** 发给 /api/publish 的标题 / 正文 / 标签：YouTube 第一行是标题，其余平台整段都是正文。 */
export function overseasPayload(key: string, text: string): { title: string; body: string; tags: string } {
  if (key !== 'youtube') return { title: '', body: text.trim(), tags: '' };
  const [first, ...rest] = text.trim().split('\n');
  return { title: first.trim(), body: rest.join('\n').trim(), tags: '' };
}

/** 一键适配的附加要求：选了海外平台时，这些平台的版本要写英文。 */
export function overseasAdaptRule(keys: string[]): string {
  const labels = OVERSEAS_PLATFORMS.filter((p) => keys.includes(p.key)).map((p) => p.label);
  if (labels.length === 0) return '';
  return `【海外平台】${labels.join('、')} 的版本一律用英文，话题标签用英文写在正文末尾（如 #AI #productivity），` +
    `遵守各平台字数上限；YouTube 版本第一行写英文标题（≤100 字符），空一行后写描述。\n`;
}
```

- [ ] **Step 4: 改 `lib/api.ts` 的 `publishNow`**

载荷类型改为：

```ts
  payload: { title: string; body: string; media: string[]; tags?: string; visibility?: string },
```

- [ ] **Step 5: 改 `PublishPage.tsx`**

5a. import 加：

```tsx
import { OVERSEAS_PLATFORMS, VISIBILITY_OPTIONS, isOverseas, overseasPayload, overseasAdaptRule } from '../lib/overseasPublish';
```

5b. 把原 `const PLATFORMS: { key: string; label: string; titleLimit?: number; bodyLimit: number; hint: string }[] = [ ... ];`
改为（数组内容——原有 7 条国内平台——原样搬进 `DOMESTIC_PLATFORMS`）：

```tsx
type PlatformMeta = { key: string; label: string; titleLimit?: number; bodyLimit: number; hint: string; region?: 'overseas' };

// 平台列表须与后端 LOGIN_RUNNERS 对齐（有登录/发布链路的才列）
const DOMESTIC_PLATFORMS: PlatformMeta[] = [
  { key: 'xiaohongshu', label: '小红书', titleLimit: 20, bodyLimit: 1000, hint: '标题≤20，正文≤1000，重情绪+话题标签' },
  { key: 'douyin', label: '抖音', titleLimit: 55, bodyLimit: 55, hint: '文案≤55，前几字是钩子' },
  { key: 'kuaishou', label: '快手', titleLimit: 30, bodyLimit: 1000, hint: '视频或图片(图文)，标题≤30，需附媒体' },
  { key: 'weixin-channels', label: '视频号', bodyLimit: 1000, hint: '需附视频，短描述+话题标签，微信扫码登录' },
  { key: 'zhihu', label: '知乎', bodyLimit: 5000, hint: '长文/回答，讲清逻辑' },
  { key: 'bilibili', label: 'B站', titleLimit: 80, bodyLimit: 2000, hint: '需附视频，标题≤80、简介≤2000，默认投「知识」分区' },
  { key: 'wechat-oa', label: '公众号', titleLimit: 64, bodyLimit: 20000, hint: '图文文章，正文用 Markdown，首图作封面，发到草稿箱；需先在账号页「登录公众号后台」扫码' },
];
const PLATFORMS: PlatformMeta[] = [...DOMESTIC_PLATFORMS, ...OVERSEAS_PLATFORMS];
```

5c. `PUBLISHABLE`、`MEDIA_REQUIRED`、`VIDEO_ONLY` 三个集合改为：

```tsx
const OVERSEAS_KEYS = OVERSEAS_PLATFORMS.map((p) => p.key);
// 能一键发布的平台（有后端 publisher）
const PUBLISHABLE = new Set(['xiaohongshu', 'douyin', 'kuaishou', 'weixin-channels', 'zhihu', 'bilibili', 'wechat-oa', ...OVERSEAS_KEYS]);
// 必须附带媒体的平台（无媒体发不了）——公众号需要一张封面图，也计入
const MEDIA_REQUIRED = new Set(['xiaohongshu', 'douyin', 'kuaishou', 'weixin-channels', 'bilibili', 'wechat-oa', ...OVERSEAS_KEYS]);
// 只能发视频的平台（抖音/视频号/B站必须视频；海外平台的图文 / 纯文字在下一期接通，现在也只收视频）
const VIDEO_ONLY = new Set(['douyin', 'weixin-channels', 'bilibili', ...OVERSEAS_KEYS]);
```

5d. 组件状态（`const [pubSmsBusy, ...]` 之后）加：

```tsx
  // 海外平台可见范围（YouTube / TikTok）；空 = 用平台默认（公开 / 所有人）
  const [visibility, setVisibility] = useState<Record<string, string>>({});
```

5e. `adapt()` 的 prompt：在 `` `小红书可用 emoji 和 #话题标签，按平台习惯自然分行即可。\n` + `` 之后插入一行：

```tsx
      overseasAdaptRule(sel.map((p) => p.key)) +
```

5f. `publishAll()` 里把 `const res = await publishNow(t.key, { title, body: effective(t.key), media: selectedMedia, tags });` 改为：

```tsx
        const payload = isOverseas(t.key)
          ? { ...overseasPayload(t.key, effective(t.key)), media: selectedMedia, visibility: visibility[t.key] || '' }
          : { title, body: effective(t.key), media: selectedMedia, tags };
        const res = await publishNow(t.key, payload);
```

5g. 平台选择区（`<label className="field-label">发布平台</label>` 之后整个 `<div className="publish-platforms">…</div>`）改为：

```tsx
        {[
          { name: '国内平台', items: PLATFORMS.filter((p) => !p.region) },
          { name: '海外平台', items: PLATFORMS.filter((p) => p.region === 'overseas') },
        ].map((g) => (
          <div key={g.name} className="publish-platforms" role="group" aria-label={g.name}>
            <span className="publish-group-label">{g.name.replace('平台', '')}</span>
            {g.items.map((p) => (
              <button key={p.key} type="button" className={`chip ${platforms.includes(p.key) ? 'active' : ''}`}
                aria-pressed={platforms.includes(p.key)}
                onClick={() => toggle(p.key)}>{p.label}</button>
            ))}
          </div>
        ))}
```

5h. 卡片 `pv-foot` 里 `<span className="pv-hint">…</span>` 之后加：

```tsx
                {VISIBILITY_OPTIONS[p.key] && (
                  <select className="pv-visibility" aria-label={`${p.label} 可见范围`}
                    value={visibility[p.key] || ''}
                    onChange={(e) => setVisibility((v) => ({ ...v, [p.key]: e.target.value }))}>
                    <option value="">默认（公开）</option>
                    {VISIBILITY_OPTIONS[p.key].map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                )}
```

5i. 媒体附件说明改为：`（小红书/抖音/快手/微信视频号/B站/海外平台必需，从内容库选；抖音、视频号、B站、海外平台须为视频）`

5j. 样式：在发布页样式文件（`grep -rln "publish-platforms" web/frontend/src/styles`）里加：

```css
.publish-group-label { font-size: var(--fs-12); color: var(--c-ink-3); margin-right: var(--sp-1); align-self: center; }
.pv-visibility { font-size: var(--fs-12); border: 1px solid var(--c-rule); border-radius: var(--r-control); background: var(--c-surface); padding: 2px 6px; }
```

- [ ] **Step 6: 跑前端测试、构建、lint**

Run: `cd web/frontend && npm test && npm run build && npm run lint`
Expected: 测试全过；构建成功；lint 无 error（warning 与 main 相同）

- [ ] **Step 7: 提交**

```bash
git add web/frontend/src
git commit -m "feat(publish): 发布中心接入海外平台——分组、英文适配、可见范围、海外载荷

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 对话技能、跨平台路由与登记

**Files:**
- Create: `skills/openclaw/skill-overseas-publish/SKILL.md`、`EASEL-META.md`、`references/platforms.md`
- Modify: `skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py`、`skills/openclaw/skill-cross-platform-publish/SKILL.md`
- Modify: `skills/openclaw/skill-my-account/SKILL.md`
- Modify: `scripts/validate_skills.py`、`docs/skill-function-mapping.md`、`web/frontend/src/lib/skillDisplayNames.ts`、`web/frontend/src/lib/capabilityMenu.ts`

**Interfaces:**
- Consumes: Task 5 命令行（SKILL.md 里的命令必须能过 `validate_skill_commands.py`）
- Produces: 技能 `skill-overseas-publish`；`publish_dispatch.PLATFORMS` 五个海外平台 → `skill-overseas-publish`

- [ ] **Step 1: 写失败的检查**

`publish_dispatch.py` 的 `cmd_selftest` 里，在 `assert PLATFORMS["xiaohongshu"]["publisher"] == "skill-xhs-publisher"` 之后加：

```python
    for k in ("tiktok", "youtube", "instagram", "x", "threads"):
        assert PLATFORMS[k]["publisher"] == "skill-overseas-publish", f"{k} 应路由到 skill-overseas-publish"
    assert PLATFORMS["youtube"]["title"] == 100 and PLATFORMS["x"]["body"] == 280
```

Run: `.venv/bin/python skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py selftest`
Expected: FAIL，`KeyError: 'tiktok'`

- [ ] **Step 2: 加路由**

`publish_dispatch.py` 的 `PLATFORMS` 末尾（`"zhihu"` 之后）加：

```python
    # 海外平台：浏览器自动化发到自己的账号（skill-overseas-publish）；文案由 LLM 改写成英文
    "tiktok": {"publisher": "skill-overseas-publish", "types": ["video"],
               "title": 0, "body": 2200, "tags": 0, "aspect": "9:16",
               "note": "英文说明≤2200；竖版；可见范围 everyone/friends/only_me"},
    "youtube": {"publisher": "skill-overseas-publish", "types": ["video"],
                "title": 100, "body": 5000, "tags": 0, "aspect": "9:16/16:9",
                "note": "英文标题≤100、描述≤5000；竖版≤3 分钟自动成 Shorts；账号要先有频道"},
    "instagram": {"publisher": "skill-overseas-publish", "types": ["video"],
                  "title": 0, "body": 2200, "tags": 30, "aspect": "9:16",
                  "note": "视频发成 Reels；英文说明≤2200、话题≤30"},
    "x": {"publisher": "skill-overseas-publish", "types": ["video"],
          "title": 0, "body": 280, "tags": 0, "aspect": "16:9/9:16",
          "note": "英文≤280（中日韩文字算 2、链接算 23）"},
    "threads": {"publisher": "skill-overseas-publish", "types": ["video"],
                "title": 0, "body": 500, "tags": 1, "aspect": "9:16",
                "note": "英文≤500；话题只能 1 个"},
```

Run 同上，Expected: `✅ selftest 通过`

- [ ] **Step 3: 写技能**

`skills/openclaw/skill-overseas-publish/SKILL.md`：

````markdown
---
name: skill-overseas-publish
description: >-
  海外平台发布：把视频发到 TikTok、YouTube、Instagram（Reels）、X、Threads 上自己的账号。
  当用户说"发 TikTok""发 YouTube / Shorts""发 Instagram / Reels""发推 / 发 X""发 Threads""发海外平台"
  "出海发布"时使用。本机浏览器自动化（登录态在账号页窗口登录），不经第三方服务。国内平台用各自的发布 SKILL。
layer: publish
---

# 海外平台发布

> 走 `skills/shared/scripts/overseas_publisher.py`（CWD=项目根）。登录在 Web「账号」页「海外」分组点「登录」，
> 本机弹 Chrome 窗口亲手登录。目前只接通**视频**；图文 / 纯文字在下一期。YouTube 要账号先有频道。

## 流程

1. **改写英文文案**（你来做）：按 `references/platforms.md` 的各平台上限写英文版本；话题标签用英文。
   不确定的事实不编；画像里的人设、语气照样遵守。
2. **先预览**（不加 `--exec`，不开浏览器、不联网）：把输出的 `fields` 原样给用户看。
3. **用户确认后再真发**：同一条命令加 `--exec`。
4. **看退出码**：
   - `0` 成功（输出里有帖子链接时一并告诉用户）；
   - `2` 内容不合格（按提示改文案 / 换视频）；`6` 未登录（让用户去账号页登录）；`7` 内容安全闸门拦下；
   - `5` **结果待确认**：只让用户去平台核对，**绝不重跑 `--exec`**（可能已经发出去了）；
   - `1` 其它失败：页面可能改版，现场截图在 `outputs/_login/<平台>-publish-fail.png`。

## 命令

```bash
python skills/shared/scripts/overseas_publisher.py platforms
python skills/shared/scripts/overseas_publisher.py whoami --platform tiktok
python skills/shared/scripts/overseas_publisher.py publish --platform tiktok --media outputs/项目/成片.mp4 --desc "English caption" --tags "ai,productivity" --visibility only_me
python skills/shared/scripts/overseas_publisher.py publish --platform youtube --media outputs/项目/成片.mp4 --title "English title" --desc "Description" --visibility private --exec
```

平台码：`tiktok` / `youtube` / `instagram` / `x` / `threads`。`--visibility` 只有 YouTube（public / unlisted / private）
和 TikTok（everyone / friends / only_me）有；不传用平台默认（公开 / 所有人）。

## 规则

1. 只发用户自己的作品；每次真发前都要用户明确确认。
2. 一次一个平台；多平台用 skill-cross-platform-publish 编排，逐个调用本技能。
3. 退出码 5 不重发；连续失败不要反复重试，停下来告诉用户。
4. 账号被要求人工验证时，脚本会弹出浏览器窗口，提醒用户在窗口里完成。
````

`skills/openclaw/skill-overseas-publish/references/platforms.md`：

```markdown
# 海外平台规格（与 overseas/<平台>.py 的 LIMITS 一致）

| 平台 | 已接通 | 文案字段 | 上限 | 可见范围 | 备注 |
|---|---|---|---|---|---|
| TikTok | 视频 | `--desc`（+ `--tags`） | 说明 ≤2200 | everyone / friends / only_me | 竖版 9:16 |
| YouTube | 待频道校准 | `--title` + `--desc` | 标题 ≤100，描述 ≤5000 | public / unlisted / private | 竖版 ≤3 分钟自动成 Shorts |
| Instagram | 视频（Reels） | `--desc` | 说明 ≤2200，话题 ≤30 | — | 竖版 9:16 |
| X | 视频 | `--desc` | 加权 ≤280（中日韩文字算 2，链接算 23） | — | 免费账号视频 ≤2 分 20 秒 |
| Threads | 视频 | `--desc` | ≤500，话题 1 个 | — | |

英文改写要点：开头一句就是钩子；口语、短句；话题标签 3–5 个（Threads 1 个），放在末尾；不要中文。

真机校准记录：2026-10-01 校准 X / Threads / Instagram / TikTok 发布页元素（只读，未发布）；
真发测试结果见 PR 2 的 PR 描述。页面改版时对照 `outputs/_login/<平台>-publish-fail.*` 更新模块里的选择器。
```

`skills/openclaw/skill-overseas-publish/EASEL-META.md`：

```markdown
# Easel SKILL 元数据

| 字段 | 值 |
|------|-----|
| **SKILL 名称** | skill-overseas-publish |
| **所属层** | publish |
| **来源类型** | 自研（工具封装） |
| **原始来源** | Easel 自研。海外平台发布，走 `skills/shared/scripts/overseas_publisher.py`（Playwright 浏览器自动化 + 本机 Chrome + 登录态持久化） |
| **参考项目** | Playwright（https://playwright.dev/） |
| **许可** | 随 Easel 项目许可 |

> 整理时间: 2026-10-01
> 用途: 来源溯源与致谢
```

- [ ] **Step 4: 跨平台发布 SKILL 与我的账号 SKILL**

`skill-cross-platform-publish/SKILL.md`：
- frontmatter description 第一行的平台列表 `（小红书/抖音/B站/公众号/快手/视频号/知乎）` 改为 `（小红书/抖音/B站/公众号/快手/视频号/知乎/TikTok/YouTube/Instagram/X/Threads）`；
- 「支持平台」表末尾加一行：`| tiktok / youtube / instagram / x / threads（海外）| skill-overseas-publish ✅（目前只发视频；文案改写成英文）|`。

`skill-my-account/SKILL.md` 的「支持平台」节 `whoami：` 那一行之后加：

```markdown
海外平台（TikTok / YouTube / Instagram / X / Threads）的登录身份：`python skills/shared/scripts/overseas_publisher.py whoami --platform <平台码>`。
```

- [ ] **Step 5: 登记**

- `scripts/validate_skills.py` 的 `PUBLISH_SCRIPT_CONTRACTS` 加：

```python
    "skills/shared/scripts/overseas_publisher.py": (
        "content_guard.guard_or_die", 'add_argument("--exec"',
    ),
```

- `docs/skill-function-mapping.md`：第 4 行「当前共 **114 个 Skill**」改为「**115 个 Skill**」；发布层表格里 `skill-kuaishou-upload` 那一行之后加：

```markdown
| `skill-overseas-publish` | 海外平台发布：把视频发到 TikTok、YouTube、Instagram（Reels）、X、Threads 上自己的账号（本机浏览器自动化，不经第三方服务）。 |
```

- `web/frontend/src/lib/skillDisplayNames.ts`：在 `'skill-kuaishou-upload': '快手',` 之后加 `'skill-overseas-publish': '海外平台',`。
- `web/frontend/src/lib/capabilityMenu.ts`：在 `skill-channels-upload` 条目之后加：

```ts
      {
       "skill": "skill-overseas-publish",
       "label": "海外平台",
       "desc": "海外平台发布：把视频发到 TikTok、YouTube、Instagram（Reels）、X、Threads 上自己的账号。本机浏览器自动化，不经第三方服务。",
       "status": "ready"
      },
```

- [ ] **Step 6: 跑校验**

Run:
```bash
.venv/bin/python scripts/validate_skills.py
.venv/bin/python scripts/validate_skill_commands.py
.venv/bin/python skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py selftest
cd web/frontend && npm test && npm run build
```
Expected: `OK: 115 skills ...`；命令校验 OK；selftest ✅；前端通过

- [ ] **Step 7: 提交**

```bash
git add skills/openclaw/skill-overseas-publish skills/openclaw/skill-cross-platform-publish skills/openclaw/skill-my-account scripts/validate_skills.py docs/skill-function-mapping.md web/frontend/src/lib/skillDisplayNames.ts web/frontend/src/lib/capabilityMenu.ts
git commit -m "feat(publish): 对话技能 skill-overseas-publish，跨平台发布路由到海外平台

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 真机测试发布（需用户在场，逐平台先征得同意）

**Files:**
- Modify（按结果）：各平台模块的选择器 / 成功信号常量、模块文档字符串校准日期、`references/platforms.md` 的校准记录；YouTube 有频道时 `READY_KINDS` 改 `{"video"}` 并补测试
- 测试视频：会话 scratchpad 里的 `easel-test.mp4`（4 秒 1080×1920，ffmpeg testsrc2 生成）

**Interfaces:**
- Consumes: Task 5 命令行
- Produces: 各平台真发一次的结论（成功信号是否命中、帖子链接）

每个平台**单独问用户**是否同意真发一条测试帖，并说明可见范围：TikTok 用 `--visibility only_me`；YouTube（若已有频道）用 `--visibility private`；X / Instagram / Threads 没有私密发布，测试帖公开可见，问用户是发完手动删、还是先跳过。文案用 `Easel test post — please ignore`。

- [ ] **Step 1: 逐平台预览**

```bash
.venv/bin/python skills/shared/scripts/overseas_publisher.py publish --platform tiktok --media <scratchpad>/easel-test.mp4 --desc "Easel test post — please ignore" --visibility only_me
```
Expected: 打印 fields、提示 dry-run，退出码 0。

- [ ] **Step 2: 用户同意后逐平台真发**

同一命令加 `--exec`。Expected：`✅ 已发布到 <平台>`，退出码 0。

结果不符时：
- 退出码 5（没等到成功信号）：让用户到平台确认帖子是否已发出；**不要重跑**。已发出 → 用只读探针打印发布后的页面（URL、toast / 对话框文字），把成功信号常量改成真实的，补一条离线测试；没发出 → 看 `outputs/_login/<平台>-publish-fail.png`。
- 退出码 1：看失败现场截图，修正对应选择器，补测试后重试（重试前再次征得用户同意）。

- [ ] **Step 3: YouTube**

问用户是否已建频道。已建：跑一次只读探针确认 Studio 上传弹窗元素，校准 `youtube.py` 选择器 → `READY_KINDS = frozenset({"video"})`、把 `test_youtube_flow_sets_title_description_visibility` 里 `READY_KINDS == frozenset()` 的断言改成 `{"video"}`、删除 `test_youtube_not_open_until_calibrated` → 私享测试发布。未建：保持关闭，在 PR 描述里写明。

- [ ] **Step 4: 记录并提交**

更新各模块文档字符串校准日期与 `references/platforms.md` 的真发结果。

Run: `.venv/bin/python -m pytest tests/test_overseas_flows.py tests/test_overseas_publish.py -q && .venv/bin/python skills/shared/scripts/overseas_publisher.py selftest`
Expected: 全部 PASS

```bash
git add skills/shared/scripts/overseas/ skills/openclaw/skill-overseas-publish/references/platforms.md tests/
git commit -m "fix(overseas): 真机测试发布校准成功信号

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 全量验证、整体审查与合并

- [ ] **Step 1: 全量检查**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_skills.py
.venv/bin/python scripts/validate_skill_commands.py
.venv/bin/python skills/shared/scripts/overseas_publisher.py selftest
.venv/bin/python skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py selftest
cd web/frontend && npm test && npm run build && npm run lint
```
Expected：全部通过；lint 无 error。

- [ ] **Step 2: 整体代码审查**

派独立审查（Sonnet），输入整条分支 diff，重点：国内平台零改动、发布结果三态与退出码、unknown 不重发、闸门覆盖、锁与登录 / whoami 的互斥、Blocked 重试只一次、Web 异步发布与前端载荷、YouTube 关闭状态。修掉确认的问题（每条先写失败测试）。

- [ ] **Step 3: 推送、开 PR、合并、清理**

```bash
git push -u origin feat/overseas-video
gh pr create --base main --title "feat(overseas): 海外平台视频发布（TikTok / Instagram / X / Threads），接入发布中心与对话" --body "<变更、验证、真机测试结果，结尾 🤖 Generated with [Claude Code](https://claude.com/claude-code)>"
gh pr merge --merge
```

合并后：删 worktree 软链 → `git worktree remove ../Easel-wt-ov` → 主目录 `git pull --ff-only` → 删本地与远端分支 → 重建前端 → 提醒用户：后端有改动，任务结束后重启 `easel web`；新技能要 `bash openclaw/sync.sh` 同步给智能体（会写 OpenClaw 工作区，由用户执行）。
