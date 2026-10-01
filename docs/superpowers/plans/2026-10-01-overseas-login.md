# 海外平台发布 PR 1：底座与登录 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TikTok / YouTube / Instagram / X / Threads 五个海外平台都能在 Web 账号页弹出本机 Chrome 窗口亲手登录、校验登录态、退出。

**Architecture:** 新建 `skills/shared/scripts/overseas/` 包（`post.py` 内容模型、`base.py` 浏览器底座、每平台一个模块）和命令行入口 `overseas_publisher.py`（login / whoami / platforms / selftest）。`web/app.py` 新增 `overseas` 后端分支，账号页按「国内 / 海外」分组。国内平台的登录、发布、代理代码一律不动。

**Tech Stack:** Python 3.12、Playwright sync API（`channel="chrome"`）、FastAPI、React 19 + Vite + TypeScript、pytest、vitest。

**Spec:** `docs/superpowers/specs/2026-10-01-overseas-publishing-design.md`（本计划只覆盖第 8 节的 PR 1；PR 2/3 的页面元素要等本 PR 真机登录后校准，届时另写计划）

## Global Constraints

- 代码注释、文档、提交信息用中文；提交前缀只用 `feat/fix/docs/chore/polish`；提交信息末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 测试不起真浏览器、不连任何平台、不碰用户 `.env`、`~/.openclaw-easel`、`~/.easel-browser-profiles`、真实 `outputs/`；一律用 `tmp_path` / `monkeypatch`。
- 不改国内平台行为：`web_publisher.py`、`xhs_publish.py`、`douyin_publish.py`、`bili_login.py` 不改；`_xhs_headed_fallback_available` 抽出公共函数后行为必须与原来逐项一致（原有参数化测试不改、全过）。
- 平台码 / 显示名 / 登录目录名固定为：`tiktok`/TikTok/`TikTokProfile`、`youtube`/YouTube/`YouTubeProfile`、`instagram`/Instagram/`InstagramProfile`、`x`/X/`XProfile`、`threads`/Threads/`ThreadsProfile`。
- 海外登录超时 `OVERSEAS_LOGIN_TIMEOUT = 600`（秒），与 `LOGIN_TIMEOUT` 放在一起；退出码：缺 Playwright = 3，其余失败 = 1。
- 文件读写显式 `encoding="utf-8"`；Python 代码里不写只在 POSIX 上成立的假设（锁要兼容 Windows）。
- 开发在 worktree `../Easel-wt-os`（分支 `feat/overseas-login`）里做；不停、不重启用户正在跑的 `easel web` 和网关。
- 每个任务结束前跑该任务的测试；全部任务结束后跑：`python -m pytest`（仓库根目录）、`python scripts/validate_skills.py`、`python scripts/validate_skill_commands.py`、`cd web/frontend && npm test && npm run build && npm run lint`。

## Review Focus

1. 会话已过期但登录 cookie 还在：页面过几秒才跳回登录页 —— whoami / 登录确认不能报「已登录」（Task 2 `test_settle_catches_late_redirect_to_login`）。
2. 点「登录」时其实已经是登录态（登录目录有效）—— 应立即进入确认并成功，不能干等到超时（Task 4 `test_already_logged_in_succeeds_without_waiting`）。
3. 本机没装 Google Chrome —— 退回自带 Chromium 并提示，不能崩（Task 2 `test_open_context_falls_back_when_chrome_missing`）。
4. 没有桌面的环境（Linux 服务器）—— 账号页海外按钮置灰并说明原因，登录接口 400，不能弹不出窗口还空等 10 分钟（Task 5 `test_overseas_unavailable_without_desktop`、Task 6 置灰测试）。
5. 登录窗口还开着时有人调 whoami（CLI / 智能体）—— whoami 拿不到登录目录锁就返回带 `error` 的「校验失败」，不能再开第二个浏览器、也不能被当成可信的「未登录」（Task 4 `test_whoami_busy_profile_is_unconfident`）。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `skills/shared/scripts/overseas/__init__.py` | 平台注册表 `PLATFORMS`、`get()`、平台模块必备成员 `REQUIRED_ATTRS` |
| `skills/shared/scripts/overseas/post.py` | `Post`、`Limits`、形式推断、话题标签、文案拼接、X 加权计数、媒体与上限校验（纯函数） |
| `skills/shared/scripts/overseas/base.py` | 启动本机 Chrome（退回 Chromium）、启动参数与代理、登录目录、cookie / 登录页判定、等待落定、读身份、窗口关闭判定、登录目录锁 |
| `skills/shared/scripts/overseas/{tiktok,youtube,instagram,x,threads}.py` | 各平台常量、形式与上限、`compose` / `is_logged_in` / `read_identity` |
| `skills/shared/scripts/overseas_publisher.py` | 命令行：`platforms` / `login` / `whoami` / `selftest`；`run_login`、`run_whoami` |
| `web/app.py` | `LOGIN_RUNNERS` 加 `region` 与 5 个海外条目、`OVERSEAS_LOGIN_TIMEOUT`、`_can_open_window`、`/api/accounts` 的 `region` 与不可用原因、登录 / whoami 的 `overseas` 分支 |
| `web/frontend/src/lib/api.ts` | `AccountItem.region` |
| `web/frontend/src/components/AccountsPage.tsx` | 国内 / 海外分组、海外按钮叫「登录」、不可用状态、页头说明 |
| `web/frontend/src/styles/pages/accounts.css` | 分组标题样式 |
| `docs/known-issues.md`、`docs/known-issues_EN.md` | 海外登录需要桌面与本机 Chrome 的说明 |
| 测试 | `tests/test_overseas_post.py`、`tests/test_overseas_base.py`、`tests/test_overseas_platforms.py`、`tests/test_overseas_login.py`、`tests/test_overseas_web.py`、`web/frontend/src/components/AccountsPage.test.tsx` |

---

### Task 1: 内容模型 `overseas/post.py`

**Files:**
- Create: `skills/shared/scripts/overseas/__init__.py`（本任务只放文档字符串，Task 3 填注册表）
- Create: `skills/shared/scripts/overseas/post.py`
- Test: `tests/test_overseas_post.py`

**Interfaces:**
- Produces:
  - `class PostError(ValueError)`
  - `@dataclass(frozen=True) class Limits(caption: int, title: int = 0, hashtags: int = 0, images: int = 0, weighted: bool = False)`
  - `@dataclass class Post(media: list[Path] = [], title: str = "", desc: str = "", tags: str = "", visibility: str = "")`，属性 `kind -> str`
  - `VIDEO_EXTS`、`IMAGE_EXTS`（frozenset）、`KIND_LABEL: dict[str, str]`
  - `infer_kind(media) -> str`、`parse_tags(raw: str) -> list[str]`、`caption_text(post, *, with_title=True) -> str`、`x_weighted_length(text: str) -> int`、`check_media(media) -> None`、`validate(post, *, name, kinds, limits, visibility=()) -> None`

- [ ] **Step 1: 建包占位**

`skills/shared/scripts/overseas/__init__.py`：

```python
"""海外平台（TikTok / YouTube / Instagram / X / Threads）发布的共用包。"""
```

- [ ] **Step 2: 写失败的测试**

`tests/test_overseas_post.py`：

```python
"""海外发布内容模型（overseas/post.py）的离线测试：形式推断、话题标签、文案拼接、字数、媒体校验。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import post as P  # noqa: E402

LIM = P.Limits(caption=20, images=2, hashtags=2)


def _media(tmp_path, *names):
    out = []
    for n in names:
        f = tmp_path / n
        f.write_bytes(b"x")
        out.append(f)
    return out


def test_infer_kind():
    assert P.infer_kind([]) == "text"
    assert P.infer_kind([Path("a.MP4")]) == "video"
    assert P.infer_kind([Path("a.jpg"), Path("b.webp")]) == "image"


@pytest.mark.parametrize("media", [
    [Path("a.mp4"), Path("b.mp4")],
    [Path("a.mp4"), Path("b.jpg")],
    [Path("a.gif")],
    [Path("a.txt")],
])
def test_infer_kind_rejects_bad_mixes(media):
    with pytest.raises(P.PostError):
        P.infer_kind(media)


def test_parse_tags_prefixes_and_dedupes_case_insensitively():
    assert P.parse_tags("#Easel, easel  AI，shorts #ai") == ["#Easel", "#AI", "#shorts"]
    assert P.parse_tags("") == []


def test_caption_text_joins_nonempty_parts():
    post = P.Post(title="Title", desc="Body", tags="a b")
    assert P.caption_text(post) == "Title\n\nBody\n\n#a #b"
    assert P.caption_text(post, with_title=False) == "Body\n\n#a #b"
    assert P.caption_text(P.Post(title="Only")) == "Only"


@pytest.mark.parametrize("text,expected", [
    ("a" * 280, 280),
    ("中" * 140, 280),
    ("日本語", 6),
    ("see https://example.com/a/very/long/path?x=1 ok", 4 + 23 + 3),
    ("😀", 2),
])
def test_x_weighted_length(text, expected):
    assert P.x_weighted_length(text) == expected


def test_validate_ok(tmp_path):
    P.validate(P.Post(media=_media(tmp_path, "a.jpg"), title="hi", tags="a"),
               name="Demo", kinds={"image"}, limits=LIM)


def test_validate_kind_not_supported(tmp_path):
    with pytest.raises(P.PostError, match="Demo 不支持发视频"):
        P.validate(P.Post(media=_media(tmp_path, "a.mp4"), title="hi"),
                   name="Demo", kinds={"image"}, limits=LIM)


def test_validate_too_many_images(tmp_path):
    with pytest.raises(P.PostError, match="最多 2 张"):
        P.validate(P.Post(media=_media(tmp_path, "a.jpg", "b.jpg", "c.jpg")),
                   name="Demo", kinds={"image"}, limits=LIM)


def test_validate_caption_too_long():
    with pytest.raises(P.PostError, match="最多 20"):
        P.validate(P.Post(title="x" * 21), name="Demo", kinds={"text"}, limits=LIM)


def test_validate_weighted_caption():
    lim = P.Limits(caption=10, weighted=True)
    P.validate(P.Post(title="中" * 5), name="X", kinds={"text"}, limits=lim)
    with pytest.raises(P.PostError, match="加权"):
        P.validate(P.Post(title="中" * 6), name="X", kinds={"text"}, limits=lim)


def test_validate_hashtag_limit():
    with pytest.raises(P.PostError, match="话题标签最多 2 个"):
        P.validate(P.Post(title="t", tags="a b c"), name="Demo", kinds={"text"}, limits=LIM)


def test_validate_title_rules():
    lim = P.Limits(caption=50, title=5)
    with pytest.raises(P.PostError, match="需要标题"):
        P.validate(P.Post(desc="d"), name="YT", kinds={"text"}, limits=lim)
    with pytest.raises(P.PostError, match="标题最多 5"):
        P.validate(P.Post(title="123456"), name="YT", kinds={"text"}, limits=lim)


def test_validate_empty_text_post():
    with pytest.raises(P.PostError, match="不能为空"):
        P.validate(P.Post(), name="X", kinds={"text"}, limits=LIM)


def test_validate_visibility():
    P.validate(P.Post(title="t", visibility="private"), name="YT", kinds={"text"}, limits=LIM,
               visibility=("public", "private"))
    with pytest.raises(P.PostError, match="只能是"):
        P.validate(P.Post(title="t", visibility="secret"), name="YT", kinds={"text"}, limits=LIM,
                   visibility=("public",))
    with pytest.raises(P.PostError, match="没有可见范围"):
        P.validate(P.Post(title="t", visibility="public"), name="IG", kinds={"text"}, limits=LIM)


def test_check_media_missing_file(tmp_path):
    with pytest.raises(P.PostError, match="不存在"):
        P.check_media([tmp_path / "nope.mp4"])


def test_check_media_symlink_to_non_media(tmp_path):
    secret = tmp_path / "secrets.env"
    secret.write_text("TOKEN=abc", encoding="utf-8")
    link = tmp_path / "x.png"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("本机不允许建符号链接（Windows 非开发者模式）")
    with pytest.raises(P.PostError, match="不是图片或视频"):
        P.check_media([link])
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_post.py -q`
Expected: FAIL，`ImportError: cannot import name 'post' from 'overseas'`

- [ ] **Step 4: 实现 `overseas/post.py`**

```python
"""海外平台发布的内容模型：Post、平台上限、文案拼接与校验。

纯函数、不碰浏览器：overseas_publisher 在开浏览器之前就用它把不合格的内容挡掉。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTS = frozenset({".mp4", ".mov", ".m4v", ".webm"})
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
KIND_LABEL = {"video": "视频", "image": "图文", "text": "纯文字"}

# X 的加权计数（twitter-text v3）：这些码位区间算 1，其余（中日韩文字、emoji 等）算 2；URL 一律算 23
_X_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
_X_URL_WEIGHT = 23
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


class PostError(ValueError):
    """内容不合格（开浏览器之前就退出）。"""


@dataclass(frozen=True)
class Limits:
    caption: int              # 主文案上限（YouTube 是描述）
    title: int = 0            # 独立标题上限；0 = 平台没有独立标题，标题并进主文案
    hashtags: int = 0         # 话题标签个数上限；0 = 不限
    images: int = 0           # 图文最多几张；0 = 不支持图文
    weighted: bool = False    # True = 按 X 的加权规则计数


@dataclass
class Post:
    media: list[Path] = field(default_factory=list)
    title: str = ""
    desc: str = ""
    tags: str = ""
    visibility: str = ""

    @property
    def kind(self) -> str:
        return infer_kind(self.media)


def infer_kind(media) -> str:
    """无媒体 = 纯文字；1 个视频 = 视频；1～N 张图 = 图文；其它组合报错。"""
    if not media:
        return "text"
    exts = {Path(m).suffix.lower() for m in media}
    if exts <= VIDEO_EXTS:
        if len(media) != 1:
            raise PostError("视频一次只能发 1 个")
        return "video"
    if exts <= IMAGE_EXTS:
        return "image"
    raise PostError("媒体只能是 1 个视频（mp4/mov/m4v/webm），或 1～N 张图片（jpg/png/webp），不能混用")


def parse_tags(raw: str) -> list[str]:
    """逗号 / 空格分隔的话题标签 → 加 # 并去重（不分大小写，保留第一次出现的写法和顺序）。"""
    out: list[str] = []
    seen: set[str] = set()
    for t in re.split(r"[,，\s]+", raw or ""):
        t = t.strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(f"#{t}")
    return out


def caption_text(post: Post, *, with_title: bool = True) -> str:
    """标题 + 正文 + 话题标签，空的部分跳过，段落之间空一行。"""
    parts = [post.title.strip() if with_title else "", post.desc.strip(), " ".join(parse_tags(post.tags))]
    return "\n\n".join(p for p in parts if p)


def _x_char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _X_LIGHT_RANGES) else 2


def x_weighted_length(text: str) -> int:
    n, pos = 0, 0
    for m in _URL_RE.finditer(text):
        n += sum(_x_char_weight(c) for c in text[pos:m.start()]) + _X_URL_WEIGHT
        pos = m.end()
    return n + sum(_x_char_weight(c) for c in text[pos:])


def check_media(media) -> None:
    """文件要存在，且按真实路径（解开符号链接）看是图片或视频：x.png 链到 .env 一类文件时拒绝上传。"""
    for m in media:
        p = Path(m).expanduser()
        if not p.is_file():
            raise PostError(f"媒体文件不存在：{m}")
        real = p.resolve()
        if real.suffix.lower() not in VIDEO_EXTS | IMAGE_EXTS:
            raise PostError(f"媒体文件实际指向 {real.name}，不是图片或视频")


def validate(post: Post, *, name: str, kinds, limits: Limits, visibility: tuple[str, ...] = ()) -> None:
    """按平台的形式、上限和可见范围选项校验；不合格抛 PostError，消息直接给用户看。"""
    kind = post.kind
    if kind not in kinds:
        raise PostError(f"{name} 不支持发{KIND_LABEL[kind]}")
    check_media(post.media)
    if kind == "image" and len(post.media) > limits.images:
        raise PostError(f"{name} 图文最多 {limits.images} 张，当前 {len(post.media)} 张")
    if limits.title:
        title = post.title.strip()
        if not title:
            raise PostError(f"{name} 需要标题")
        if len(title) > limits.title:
            raise PostError(f"{name} 标题最多 {limits.title} 个字符，当前 {len(title)}")
        body = caption_text(post, with_title=False)
    else:
        body = caption_text(post)
    if kind == "text" and not body:
        raise PostError("纯文字帖子不能为空")
    n = x_weighted_length(body) if limits.weighted else len(body)
    if n > limits.caption:
        unit = "（加权，中日韩文字算 2）" if limits.weighted else ""
        raise PostError(f"{name} 文案最多 {limits.caption} 个字符{unit}，当前 {n}")
    tags = parse_tags(post.tags)
    if limits.hashtags and len(tags) > limits.hashtags:
        raise PostError(f"{name} 话题标签最多 {limits.hashtags} 个，当前 {len(tags)} 个")
    if post.visibility:
        if not visibility:
            raise PostError(f"{name} 没有可见范围选项，不要传 --visibility")
        if post.visibility not in visibility:
            raise PostError(f"{name} 的可见范围只能是：{', '.join(visibility)}")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_post.py -q`
Expected: 全部 PASS（符号链接用例在不允许建链接的系统上 SKIP）

- [ ] **Step 6: 提交**

```bash
git add skills/shared/scripts/overseas/__init__.py skills/shared/scripts/overseas/post.py tests/test_overseas_post.py
git commit -m "feat(overseas): 海外发布内容模型——形式推断、话题标签、文案拼接与上限校验

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 浏览器底座 `overseas/base.py`

**Files:**
- Create: `skills/shared/scripts/overseas/base.py`
- Test: `tests/test_overseas_base.py`

**Interfaces:**
- Consumes: 无（不依赖 Task 1）
- Produces:
  - 常量 `PROFILE_ROOT: Path`、`LAUNCH_ARGS: tuple[str, ...]`、`CHROME_MISSING_HINT: str`
  - 异常 `PlaywrightMissing(RuntimeError)`、`WindowClosed(RuntimeError)`
  - `short_err(e, limit=160) -> str`、`profile_dir(mod, root=None) -> Path`（用 `mod.PROFILE`）
  - `launch_options(headed: bool, env=None) -> dict`、`open_context(p, profile: Path, *, headed: bool, env=None)`、`close_quietly(ctx)`
  - `launch(profile: Path, *, headed: bool)`：上下文管理器，产出 Playwright persistent context
  - `first_page(ctx)`、`has_auth_cookie(page, url, names) -> bool`、`on_login_page(page, markers) -> bool`
  - `settle(page, mod, *, rounds=12, step_ms=800, stable=3) -> bool`（用 `mod.LOGIN_MARKERS`、`mod.is_logged_in`）
  - `read_identity(page, name_selectors: str, avatar_selectors: str) -> dict`（`{"name", "avatar"}`）
  - `ensure_window_open(page)`、`is_window_closed_error(e) -> bool`
  - `class ProfileLock(profile: Path)`：`acquire(timeout_s: float)`（超时抛 `TimeoutError`）、`release()`

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_base.py`：

```python
"""海外发布浏览器底座（overseas/base.py）的离线测试：不起真浏览器。"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import base  # noqa: E402


class FakeContext:
    def __init__(self, cookies=()):
        self._cookies = list(cookies)
        self.asked: list = []

    def cookies(self, urls=None):
        self.asked.append(urls)
        return list(self._cookies)


class FakePage:
    """urls：每次 wait_for_timeout 之后依次切到的地址（模拟客户端跳转）。"""

    def __init__(self, url="https://example.com/home", cookies=(), urls=None):
        self.context = FakeContext(cookies)
        self._urls = list(urls or [])
        self.url = url
        self.waits = 0
        self.closed = False

    def wait_for_timeout(self, _ms):
        self.waits += 1
        if self._urls:
            self.url = self._urls.pop(0)

    def is_closed(self):
        return self.closed


MOD = SimpleNamespace(COOKIE_URL="https://example.com", AUTH_COOKIES=("sid",), LOGIN_MARKERS=("/login",))
MOD.is_logged_in = lambda page: (base.has_auth_cookie(page, MOD.COOKIE_URL, MOD.AUTH_COOKIES)
                                 and not base.on_login_page(page, MOD.LOGIN_MARKERS))
SID = [{"name": "sid", "value": "v"}]


def test_has_auth_cookie_needs_named_nonempty_cookie():
    assert base.has_auth_cookie(FakePage(cookies=SID), MOD.COOKIE_URL, ("sid",))
    assert not base.has_auth_cookie(FakePage(cookies=[{"name": "sid", "value": ""}]), MOD.COOKIE_URL, ("sid",))
    assert not base.has_auth_cookie(FakePage(cookies=[{"name": "other", "value": "v"}]), MOD.COOKIE_URL, ("sid",))
    page = FakePage(cookies=SID)
    base.has_auth_cookie(page, MOD.COOKIE_URL, ("sid",))
    assert page.context.asked == [["https://example.com"]]


def test_has_auth_cookie_swallows_errors():
    class Boom:
        def cookies(self, urls=None):
            raise RuntimeError("closed")

    page = FakePage()
    page.context = Boom()
    assert base.has_auth_cookie(page, MOD.COOKIE_URL, ("sid",)) is False


def test_on_login_page_is_case_insensitive():
    assert base.on_login_page(FakePage(url="https://x.com/i/flow/LOGIN"), ("/i/flow/login",))
    assert not base.on_login_page(FakePage(url="https://x.com/home"), ("/i/flow/login",))


def test_settle_needs_a_stable_logged_in_streak():
    page = FakePage(cookies=SID)
    assert base.settle(page, MOD, rounds=5, step_ms=1, stable=3) is True
    assert page.waits == 3


def test_settle_catches_late_redirect_to_login():
    """会话过期但 cookie 还在：几秒后客户端跳回登录页，不能算已登录（Review Focus 1）。"""
    page = FakePage(cookies=SID, urls=["https://example.com/home", "https://example.com/login"])
    assert base.settle(page, MOD, rounds=6, step_ms=1, stable=3) is False


def test_settle_times_out_without_cookie():
    page = FakePage()
    assert base.settle(page, MOD, rounds=4, step_ms=1, stable=2) is False
    assert page.waits == 4


def test_launch_options_use_real_chrome_flags_and_proxy():
    opts = base.launch_options(headed=True, env={"EASEL_PROXY": "http://127.0.0.1:7890"})
    assert opts["headless"] is False
    assert "--disable-blink-features=AutomationControlled" in opts["args"]
    assert "--no-proxy-server" not in opts["args"]          # 海外不强制直连（国内照旧）
    assert opts["ignore_default_args"] == ["--enable-automation"]
    assert opts["proxy"] == {"server": "http://127.0.0.1:7890"}
    assert "proxy" not in base.launch_options(headed=False, env={})
    assert base.launch_options(headed=False, env={})["headless"] is True


class FakeChromium:
    def __init__(self, fail_chrome: Exception | None):
        self.fail_chrome = fail_chrome
        self.calls: list[dict] = []

    def launch_persistent_context(self, user_data_dir, **kw):
        self.calls.append(kw)
        if kw.get("channel") == "chrome" and self.fail_chrome:
            raise self.fail_chrome
        return SimpleNamespace(pages=[], kw=kw)


def test_open_context_prefers_installed_chrome(tmp_path):
    ctx = base.open_context(SimpleNamespace(chromium=FakeChromium(None)), tmp_path / "Prof", headed=False, env={})
    assert ctx.kw["channel"] == "chrome"
    assert (tmp_path / "Prof").is_dir()


def test_open_context_falls_back_when_chrome_missing(tmp_path, capsys):
    """本机没装 Chrome：退回自带 Chromium 并提示，不崩（Review Focus 3）。"""
    err = RuntimeError("Chromium distribution 'chrome' is not found at /Applications/Google Chrome.app")
    chromium = FakeChromium(err)
    ctx = base.open_context(SimpleNamespace(chromium=chromium), tmp_path / "Prof", headed=True, env={})
    assert "channel" not in ctx.kw
    assert len(chromium.calls) == 2
    assert "Chrome" in capsys.readouterr().err


def test_open_context_reraises_other_errors(tmp_path):
    chromium = FakeChromium(RuntimeError("Target page, context or browser has been closed"))
    with pytest.raises(RuntimeError, match="closed"):
        base.open_context(SimpleNamespace(chromium=chromium), tmp_path / "Prof", headed=True, env={})


def test_profile_dir_uses_module_profile(tmp_path):
    assert base.profile_dir(SimpleNamespace(PROFILE="XProfile"), tmp_path) == tmp_path / "XProfile"
    assert base.profile_dir(SimpleNamespace(PROFILE="XProfile")) == base.PROFILE_ROOT / "XProfile"


def test_profile_lock_is_exclusive(tmp_path):
    a = base.ProfileLock(tmp_path / "Prof")
    b = base.ProfileLock(tmp_path / "Prof")
    a.acquire(1)
    try:
        with pytest.raises(TimeoutError):
            b.acquire(0.3)
    finally:
        a.release()
    b.acquire(1)
    b.release()


def test_ensure_window_open_raises_when_closed():
    page = FakePage()
    page.closed = True
    with pytest.raises(base.WindowClosed):
        base.ensure_window_open(page)


@pytest.mark.parametrize("exc,expected", [
    (base.WindowClosed(), True),
    (type("TargetClosedError", (Exception,), {})("Target closed"), True),
    (RuntimeError("Target page, context or browser has been closed"), True),
    (RuntimeError("net::ERR_NAME_NOT_RESOLVED"), False),
])
def test_is_window_closed_error(exc, expected):
    assert base.is_window_closed_error(exc) is expected


def test_read_identity_best_effort():
    class El:
        def __init__(self, text="", src=""):
            self.text, self.src = text, src

        def inner_text(self):
            return self.text

        def get_attribute(self, _name):
            return self.src

    class Page:
        def query_selector(self, sel):
            return {"#name": El(text="Alice\n@alice"), "img.av": El(src="https://cdn/a.jpg"),
                    "img.data": El(src="data:image/png;base64,xx")}.get(sel)

    assert base.read_identity(Page(), "#missing, #name", "img.data, img.av") == {
        "name": "Alice", "avatar": "https://cdn/a.jpg"}
    assert base.read_identity(Page(), "#missing", "") == {"name": "", "avatar": ""}


def test_short_err_truncates():
    assert base.short_err(RuntimeError("x" * 500)).endswith("…")
    assert base.short_err(RuntimeError("")) == "RuntimeError"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_base.py -q`
Expected: FAIL，`ImportError: cannot import name 'base' from 'overseas'`

- [ ] **Step 3: 实现 `overseas/base.py`**

```python
"""海外平台发布的浏览器底座：启动本机 Chrome、登录目录、代理、等待落定、读身份、登录目录锁。

与国内平台（web_publisher.py / xhs_publish.py）互不影响：国内一律直连（--no-proxy-server），
这里不加；配了 EASEL_PROXY 才走代理，否则用系统网络设置。
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PROFILE_ROOT = Path.home() / ".easel-browser-profiles"
# 不加 --no-sandbox / --disable-gpu：真 Chrome 会为这些参数弹「不受支持的命令行标记」提示条
LAUNCH_ARGS = ("--disable-blink-features=AutomationControlled", "--no-first-run",
               "--no-default-browser-check")
CHROME_MISSING_HINT = ("没找到本机 Google Chrome，改用 Playwright 自带的 Chromium；"
                       "YouTube（Google）登录可能会被拦，建议先安装 Chrome")


class PlaywrightMissing(RuntimeError):
    """没装 Playwright。"""


class WindowClosed(RuntimeError):
    """用户把登录窗口关掉了。"""


def short_err(e: BaseException, limit: int = 160) -> str:
    text = " ".join(str(e).split())
    text = f"{type(e).__name__}: {text}" if text else type(e).__name__
    return text if len(text) <= limit else text[:limit] + "…"


def profile_dir(mod, root: str | Path | None = None) -> Path:
    return (Path(root).expanduser() if root else PROFILE_ROOT) / mod.PROFILE


def launch_options(headed: bool, env=None) -> dict:
    env = os.environ if env is None else env
    opts = {
        "headless": not headed,
        "args": list(LAUNCH_ARGS),
        # 去掉「Chrome 正受到自动测试软件的控制」提示条和 navigator.webdriver 标记（Google 登录会看它）
        "ignore_default_args": ["--enable-automation"],
        "viewport": {"width": 1280, "height": 860},
        "locale": "en-US",
    }
    proxy = (env.get("EASEL_PROXY") or "").strip()
    if proxy:
        opts["proxy"] = {"server": proxy}
    return opts


def _chrome_missing(e: BaseException) -> bool:
    s = str(e).lower()
    return "chrome" in s and ("not found" in s or "doesn't exist" in s or "no such file" in s)


def open_context(p, profile: Path, *, headed: bool, env=None):
    """优先用本机 Google Chrome（Google 登录只认真 Chrome），没装就退回自带 Chromium 并提示。"""
    profile.mkdir(parents=True, exist_ok=True)
    opts = launch_options(headed, env)
    try:
        return p.chromium.launch_persistent_context(str(profile), channel="chrome", **opts)
    except Exception as e:  # noqa: BLE001
        if not _chrome_missing(e):
            raise
        print(f"⚠️ {CHROME_MISSING_HINT}", file=sys.stderr)
        return p.chromium.launch_persistent_context(str(profile), **opts)


def close_quietly(ctx) -> None:
    try:
        ctx.close()
    except Exception as e:  # noqa: BLE001 — 窗口已被关 / 浏览器已崩时 close 也会抛，不能盖掉真正的结果
        print(f"关闭浏览器时出错（忽略）：{short_err(e)}", file=sys.stderr)


@contextmanager
def launch(profile: Path, *, headed: bool):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise PlaywrightMissing(f"需要 playwright：{e}") from e
    with sync_playwright() as p:
        ctx = open_context(p, profile, headed=headed)
        try:
            yield ctx
        finally:
            close_quietly(ctx)


def first_page(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def has_auth_cookie(page, url: str, names) -> bool:
    try:
        cookies = page.context.cookies([url])
    except Exception:  # noqa: BLE001
        return False
    return any(c.get("name") in names and c.get("value") for c in cookies or ())


def on_login_page(page, markers) -> bool:
    try:
        url = (page.url or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(m.lower() in url for m in markers)


def settle(page, mod, *, rounds: int = 12, step_ms: int = 800, stable: int = 3) -> bool:
    """等客户端跳转落定再下结论：连续 stable 轮都是登录态才算已登录；落到登录页、或等满都没稳定，算未登录。
    会话过期时登录 cookie 往往还在，页面要过几秒才跳回登录页——只看第一眼会误判成已登录。"""
    streak = 0
    for _ in range(rounds):
        page.wait_for_timeout(step_ms)
        try:
            if on_login_page(page, mod.LOGIN_MARKERS):
                return False
            streak = streak + 1 if mod.is_logged_in(page) else 0
        except Exception:  # noqa: BLE001
            streak = 0
        if streak >= stable:
            return True
    return False


def _split(selectors: str) -> list[str]:
    return [s.strip() for s in (selectors or "").split(",") if s.strip()]


def read_identity(page, name_selectors: str, avatar_selectors: str) -> dict:
    """尽力读昵称和头像：逐个选择器试，读不到就留空，不抛错。选择器内部不要含逗号（逗号用来分隔候选）。"""
    out = {"name": "", "avatar": ""}
    for sel in _split(name_selectors):
        try:
            el = page.query_selector(sel)
            text = (el.inner_text() or "").strip() if el else ""
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            out["name"] = text.splitlines()[0].strip()[:40]
            break
    for sel in _split(avatar_selectors):
        try:
            el = page.query_selector(sel)
            src = (el.get_attribute("src") or "") if el else ""
        except Exception:  # noqa: BLE001
            src = ""
        if src.startswith("http"):
            out["avatar"] = src
            break
    return out


def ensure_window_open(page) -> None:
    """窗口被关后，Playwright 的查询会被吞掉、只有等待才抛异常：先主动查一下，明确报「窗口被关」。"""
    try:
        closed = page.is_closed()
    except Exception:  # noqa: BLE001
        closed = False
    if closed:
        raise WindowClosed()


def is_window_closed_error(e: BaseException) -> bool:
    if isinstance(e, WindowClosed) or "TargetClosed" in type(e).__name__:
        return True
    return "has been closed" in str(e)


class ProfileLock:
    """同一个登录目录同时只能有一个浏览器：登录窗口开着时，whoami / 发布等着或放弃，别再开第二个。
    （与 xhs_publish._ProfileLock 同一做法；海外这份独立，不改国内代码。）"""

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
                    raise TimeoutError(f"登录目录正被占用：{self.path.parent}") from last
                time.sleep(0.2)

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
        finally:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_base.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add skills/shared/scripts/overseas/base.py tests/test_overseas_base.py
git commit -m "feat(overseas): 海外发布浏览器底座——本机 Chrome、代理、等待落定、登录目录锁

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 五个平台模块与注册表

**Files:**
- Modify: `skills/shared/scripts/overseas/__init__.py`（整文件替换）
- Create: `skills/shared/scripts/overseas/tiktok.py`、`youtube.py`、`instagram.py`、`x.py`、`threads.py`
- Test: `tests/test_overseas_platforms.py`

**Interfaces:**
- Consumes: Task 1 的 `Limits`、`Post`、`caption_text`；Task 2 的 `base.has_auth_cookie`、`base.on_login_page`、`base.read_identity`
- Produces:
  - `overseas.PLATFORMS: dict[str, module]`（顺序：tiktok、youtube、instagram、x、threads）、`overseas.get(key) -> module`（未知平台抛 `KeyError`）、`overseas.REQUIRED_ATTRS: tuple[str, ...]`
  - 每个平台模块：`KEY`、`NAME`、`PROFILE`、`HOME_URL`、`LOGIN_URL`、`COOKIE_URL`、`AUTH_COOKIES`、`LOGIN_MARKERS`、`KINDS: frozenset`、`LIMITS: Limits`、`VISIBILITY: tuple`、`VISIBILITY_DEFAULT: str`、`NAME_SELECTORS: str`、`AVATAR_SELECTORS: str`、`compose(post) -> dict`、`is_logged_in(page) -> bool`、`read_identity(page) -> dict`

说明：登录 cookie 名、登录页标记来自各平台公开行为；身份选择器（昵称 / 头像）只有 X 有把握，其余先留空字符串（`read_identity` 返回空，登录成功消息退回「已登录」）。Task 7 真机登录后统一校准。

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_platforms.py`：

```python
"""五个海外平台模块的契约测试：注册表、形式与上限、文案拼接、登录判定（假页面，不起浏览器）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import PLATFORMS, REQUIRED_ATTRS, get  # noqa: E402
from overseas.post import Post  # noqa: E402


class FakeContext:
    def __init__(self, cookies):
        self._cookies = cookies

    def cookies(self, urls=None):
        return list(self._cookies)


class FakePage:
    def __init__(self, url, cookies=()):
        self.url = url
        self.context = FakeContext(list(cookies))


def test_registry_has_five_platforms_with_unique_profiles():
    assert list(PLATFORMS) == ["tiktok", "youtube", "instagram", "x", "threads"]
    assert len({m.PROFILE for m in PLATFORMS.values()}) == 5
    for key, m in PLATFORMS.items():
        assert m.KEY == key
        for attr in REQUIRED_ATTRS:
            assert hasattr(m, attr), f"{key} 缺 {attr}"
        assert ("image" in m.KINDS) == (m.LIMITS.images > 0)
        if m.VISIBILITY:
            assert m.VISIBILITY_DEFAULT in m.VISIBILITY
        else:
            assert m.VISIBILITY_DEFAULT == ""


def test_names_and_profiles_match_spec():
    assert {k: (m.NAME, m.PROFILE) for k, m in PLATFORMS.items()} == {
        "tiktok": ("TikTok", "TikTokProfile"),
        "youtube": ("YouTube", "YouTubeProfile"),
        "instagram": ("Instagram", "InstagramProfile"),
        "x": ("X", "XProfile"),
        "threads": ("Threads", "ThreadsProfile"),
    }


def test_get_unknown_platform():
    with pytest.raises(KeyError, match="不支持的海外平台"):
        get("weibo")


@pytest.mark.parametrize("key,kinds", [
    ("tiktok", {"video", "image"}),
    ("youtube", {"video"}),
    ("instagram", {"video", "image"}),
    ("x", {"video", "image", "text"}),
    ("threads", {"video", "image", "text"}),
])
def test_kinds_match_spec(key, kinds):
    assert PLATFORMS[key].KINDS == kinds


def test_limits_match_spec():
    yt, tt, ig, x, th = (PLATFORMS[k].LIMITS for k in ("youtube", "tiktok", "instagram", "x", "threads"))
    assert (yt.title, yt.caption) == (100, 5000)
    assert tt.caption == 2200
    assert (ig.caption, ig.hashtags, ig.images) == (2200, 30, 10)
    assert (x.caption, x.images, x.weighted) == (280, 4, True)
    assert (th.caption, th.images) == (500, 10)


def test_youtube_compose_splits_title_and_description():
    f = PLATFORMS["youtube"].compose(Post(title="My Short", desc="Body", tags="ai, easel"))
    assert f == {"title": "My Short", "description": "Body\n\n#ai #easel", "visibility": "public"}


def test_tiktok_compose_caption_and_visibility():
    f = PLATFORMS["tiktok"].compose(Post(title="T", desc="D", tags="x", visibility="only_me"))
    assert f == {"caption": "T\n\nD\n\n#x", "visibility": "only_me"}
    assert PLATFORMS["tiktok"].compose(Post(title="T"))["visibility"] == "everyone"


@pytest.mark.parametrize("key", ["instagram", "x", "threads"])
def test_caption_only_platforms(key):
    assert PLATFORMS[key].compose(Post(title="T", tags="a")) == {"caption": "T\n\n#a"}


@pytest.mark.parametrize("key", ["tiktok", "youtube", "instagram", "x", "threads"])
def test_is_logged_in_needs_auth_cookie_and_not_login_page(key):
    m = PLATFORMS[key]
    good = [{"name": m.AUTH_COOKIES[0], "value": "v"}]
    assert m.is_logged_in(FakePage(m.HOME_URL, good))
    assert not m.is_logged_in(FakePage(m.HOME_URL, []))
    assert not m.is_logged_in(FakePage(m.LOGIN_URL, good))


@pytest.mark.parametrize("key", ["tiktok", "youtube", "instagram", "x", "threads"])
def test_read_identity_never_raises(key):
    class Empty:
        def query_selector(self, _sel):
            return None

    assert PLATFORMS[key].read_identity(Empty()) == {"name": "", "avatar": ""}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_platforms.py -q`
Expected: FAIL，`ImportError: cannot import name 'PLATFORMS' from 'overseas'`

- [ ] **Step 3: 写五个平台模块**

`skills/shared/scripts/overseas/tiktok.py`：

```python
"""TikTok：TikTok Studio 网页版（www.tiktok.com/tiktokstudio）。

登录判定：sessionid 登录 cookie + 不在登录页。昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "tiktok"
NAME = "TikTok"
PROFILE = "TikTokProfile"
HOME_URL = "https://www.tiktok.com/tiktokstudio"
LOGIN_URL = "https://www.tiktok.com/login"
COOKIE_URL = "https://www.tiktok.com"
AUTH_COOKIES = ("sessionid", "sessionid_ss")
LOGIN_MARKERS = ("/login",)
KINDS = frozenset({"video", "image"})
LIMITS = Limits(caption=2200, images=35)
VISIBILITY = ("everyone", "friends", "only_me")
VISIBILITY_DEFAULT = "everyone"
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post), "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
```

`skills/shared/scripts/overseas/youtube.py`：

```python
"""YouTube：YouTube Studio（studio.youtube.com），Google 账号登录（只认本机真 Chrome）。

登录判定：youtube.com 上的登录 cookie + 不在 Google 登录页。昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "youtube"
NAME = "YouTube"
PROFILE = "YouTubeProfile"
HOME_URL = "https://studio.youtube.com/"
LOGIN_URL = ("https://accounts.google.com/ServiceLogin?service=youtube"
             "&continue=https%3A%2F%2Fstudio.youtube.com%2F")
COOKIE_URL = "https://www.youtube.com"
AUTH_COOKIES = ("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID")
LOGIN_MARKERS = ("accounts.google.com", "servicelogin")
KINDS = frozenset({"video"})
LIMITS = Limits(caption=5000, title=100)
VISIBILITY = ("public", "unlisted", "private")
VISIBILITY_DEFAULT = "public"
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"title": post.title.strip(), "description": caption_text(post, with_title=False),
            "visibility": post.visibility or VISIBILITY_DEFAULT}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
```

`skills/shared/scripts/overseas/instagram.py`：

```python
"""Instagram：instagram.com 网页版（桌面版支持发帖和 Reels）。

登录判定：sessionid 登录 cookie + 不在登录 / 安全验证页。昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "instagram"
NAME = "Instagram"
PROFILE = "InstagramProfile"
HOME_URL = "https://www.instagram.com/"
LOGIN_URL = "https://www.instagram.com/accounts/login/"
COOKIE_URL = "https://www.instagram.com"
AUTH_COOKIES = ("sessionid",)
LOGIN_MARKERS = ("/accounts/login", "/challenge")
KINDS = frozenset({"video", "image"})
LIMITS = Limits(caption=2200, hashtags=30, images=10)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
```

`skills/shared/scripts/overseas/x.py`：

```python
"""X（Twitter）：x.com 网页版。

登录判定：auth_token 登录 cookie + 不在登录流程页。身份读左侧栏的账号切换按钮（首行是显示名）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "x"
NAME = "X"
PROFILE = "XProfile"
HOME_URL = "https://x.com/home"
LOGIN_URL = "https://x.com/i/flow/login"
COOKIE_URL = "https://x.com"
AUTH_COOKIES = ("auth_token",)
LOGIN_MARKERS = ("/i/flow/login", "/logout", "/login")
KINDS = frozenset({"video", "image", "text"})
LIMITS = Limits(caption=280, images=4, weighted=True)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = '[data-testid="SideNav_AccountSwitcher_Button"]'
AVATAR_SELECTORS = '[data-testid="SideNav_AccountSwitcher_Button"] img'


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
```

`skills/shared/scripts/overseas/threads.py`：

```python
"""Threads：threads.com 网页版（可用 Instagram 账号登录）。

登录判定：sessionid 登录 cookie + 不在登录页。Threads 每帖只能加 1 个话题标签（2024 起），真机校准时确认。
昵称 / 头像选择器待真机校准（PR 1 计划 Task 7）。
"""
from __future__ import annotations

from . import base
from .post import Limits, Post, caption_text

KEY = "threads"
NAME = "Threads"
PROFILE = "ThreadsProfile"
HOME_URL = "https://www.threads.com/"
LOGIN_URL = "https://www.threads.com/login"
COOKIE_URL = "https://www.threads.com"
AUTH_COOKIES = ("sessionid",)
LOGIN_MARKERS = ("/login",)
KINDS = frozenset({"video", "image", "text"})
LIMITS = Limits(caption=500, hashtags=1, images=10)
VISIBILITY: tuple[str, ...] = ()
VISIBILITY_DEFAULT = ""
NAME_SELECTORS = ""
AVATAR_SELECTORS = ""


def compose(post: Post) -> dict:
    return {"caption": caption_text(post)}


def is_logged_in(page) -> bool:
    return base.has_auth_cookie(page, COOKIE_URL, AUTH_COOKIES) and not base.on_login_page(page, LOGIN_MARKERS)


def read_identity(page) -> dict:
    return base.read_identity(page, NAME_SELECTORS, AVATAR_SELECTORS)
```

- [ ] **Step 4: 写注册表**

`skills/shared/scripts/overseas/__init__.py`（整文件替换）：

```python
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
```

- [ ] **Step 5: 跑测试确认通过（含前两个任务）**

Run: `.venv/bin/python -m pytest tests/test_overseas_platforms.py tests/test_overseas_post.py tests/test_overseas_base.py -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add skills/shared/scripts/overseas/ tests/test_overseas_platforms.py
git commit -m "feat(overseas): TikTok / YouTube / Instagram / X / Threads 平台模块与注册表

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 命令行 `overseas_publisher.py`（login / whoami / platforms / selftest）

**Files:**
- Create: `skills/shared/scripts/overseas_publisher.py`
- Test: `tests/test_overseas_login.py`

**Interfaces:**
- Consumes: Task 2 的 `base.launch`、`base.first_page`、`base.profile_dir`、`base.ProfileLock`、`base.settle`、`base.ensure_window_open`、`base.is_window_closed_error`、`base.short_err`、`base.PlaywrightMissing`；Task 3 的 `PLATFORMS`、`REQUIRED_ATTRS`、`get`；Task 1 的 `KIND_LABEL`、`x_weighted_length`；共享脚本 `login_state.write_status(path, state, message="", qr="")`
- Produces:
  - `run_login(mod, status_file: str | None, timeout_s: int, *, launch=base.launch, clock=time.monotonic, profile_root=None) -> int`（0 成功 / 1 失败 / 3 缺 Playwright）
  - `run_whoami(mod, *, launch=base.launch, profile_root=None) -> dict`（`{"loggedIn", "name", "avatar"}`，校验本身失败时带 `"error"`）
  - `main(argv=None) -> int`
  - 常量：`DEFAULT_LOGIN_TIMEOUT = 600`、`LOGIN_POLL_MS = 2000`、`COOKIE_SETTLE_MS = 3000`、`LOGIN_LOCK_WAIT_S = 30`、`WHOAMI_LOCK_WAIT_S = 20`；消息常量 `WINDOW_MSG`、`NOT_SAVED_MSG`、`VERIFY_FAILED_MSG`、`WINDOW_CLOSED_MSG`、`EXPIRED_MSG`、`BUSY_MSG`
  - 命令：`platforms`、`login --platform P [--status-file F] [--timeout N]`、`whoami --platform P`、`selftest`

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_login.py`：

```python
"""overseas_publisher 登录 / whoami 状态机的离线测试：按剧本走的假浏览器，不起真 Chrome、不连平台。"""
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


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakePage:
    def __init__(self, world, headed):
        self.world, self.headed = world, headed
        self.url = ""
        self.closed = False

    def goto(self, url, **_kw):
        if self.world.goto_error:
            raise self.world.goto_error
        self.url = url

    def wait_for_timeout(self, ms):
        self.world.clock.t += ms / 1000
        if self.headed:
            self.world.waits += 1
            if self.world.close_window_after is not None and self.world.waits >= self.world.close_window_after:
                self.closed = True

    def is_closed(self):
        return self.closed


class FakeCtx:
    def __init__(self, page):
        self.pages = [page]

    def new_page(self):
        return self.pages[0]


class World:
    """logged_after：有头窗口里等了几次之后登录成功（None = 一直不登录）；already：一打开就是登录态；
    saved：关掉窗口、无头重开后是否还是登录态。"""

    def __init__(self, logged_after=None, saved=True, already=False):
        self.clock = Clock()
        self.logged_after, self.saved, self.already = logged_after, saved, already
        self.waits = 0
        self.launches: list[bool] = []
        self.goto_error: Exception | None = None
        self.verify_error: Exception | None = None
        self.close_window_after: int | None = None

    def logged(self, page) -> bool:
        if page.headed:
            return self.already or (self.logged_after is not None and self.waits >= self.logged_after)
        return self.saved

    @contextmanager
    def launch(self, profile, *, headed):
        self.launches.append(headed)
        if not headed and self.verify_error:
            raise self.verify_error
        yield FakeCtx(FakePage(self, headed))


def make_mod(world):
    return SimpleNamespace(
        KEY="demo", NAME="Demo", PROFILE="DemoProfile",
        HOME_URL="https://demo.test/home", LOGIN_URL="https://demo.test/login", LOGIN_MARKERS=("/login",),
        is_logged_in=world.logged,
        read_identity=lambda page: {"name": "Alice", "avatar": "https://cdn/a.jpg"},
    )


@pytest.fixture
def states(monkeypatch):
    seen: list[tuple[str, str]] = []
    real = op.login_state.write_status

    def record(path, state, message="", qr=""):
        seen.append((state, message))
        real(path, state, message, qr)

    monkeypatch.setattr(op.login_state, "write_status", record)
    return seen


def run(world, tmp_path, timeout=60):
    sf = tmp_path / "demo.json"
    rc = op.run_login(make_mod(world), str(sf), timeout, launch=world.launch, clock=world.clock,
                      profile_root=tmp_path / "profiles")
    return rc, json.loads(sf.read_text(encoding="utf-8"))


def test_login_success_verifies_saved_profile(tmp_path, states):
    world = World(logged_after=3)
    rc, final = run(world, tmp_path)
    assert rc == 0
    assert [s for s, _ in states] == ["starting", "window_login", "verifying", "success"]
    assert "Demo" in states[1][1]
    assert final["message"] == "Alice"
    assert world.launches == [True, False]      # 有头窗口登录 → 无头重开确认


def test_already_logged_in_succeeds_without_waiting(tmp_path, states):
    """点「登录」时其实已经登录：直接进入确认，不干等（Review Focus 2）。"""
    world = World(already=True)
    rc, final = run(world, tmp_path)
    assert rc == 0 and final["state"] == "success"
    assert world.waits == 1                     # 只有等 cookie 落盘那一次


def test_not_saved_is_error(tmp_path, states):
    rc, final = run(World(logged_after=1, saved=False), tmp_path)
    assert rc == 1
    assert (final["state"], final["message"]) == ("error", op.NOT_SAVED_MSG)


def test_timeout_is_expired(tmp_path, states):
    rc, final = run(World(), tmp_path, timeout=10)
    assert rc == 1
    assert final["state"] == "expired" and "分钟" in final["message"]


def test_window_closed_is_error(tmp_path, states):
    world = World()
    world.close_window_after = 2
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert (final["state"], final["message"]) == ("error", op.WINDOW_CLOSED_MSG)


def test_verify_crash_is_error_with_next_step(tmp_path, states):
    world = World(logged_after=1)
    world.verify_error = RuntimeError("net::ERR_INTERNET_DISCONNECTED")
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert final["state"] == "error" and final["message"].startswith("登录已完成，但确认登录态时")


def test_goto_failure_is_error(tmp_path, states):
    world = World()
    world.goto_error = RuntimeError("net::ERR_CONNECTION_REFUSED")
    rc, final = run(world, tmp_path)
    assert rc == 1
    assert final["state"] == "error" and "ERR_CONNECTION_REFUSED" in final["message"]


def test_playwright_missing_exits_3(tmp_path, states):
    @contextmanager
    def no_playwright(profile, *, headed):
        raise base.PlaywrightMissing("需要 playwright：No module named 'playwright'")
        yield  # pragma: no cover

    rc = op.run_login(make_mod(World()), str(tmp_path / "demo.json"), 60, launch=no_playwright,
                      profile_root=tmp_path / "profiles")
    assert rc == 3
    assert states[-1][0] == "error" and "playwright" in states[-1][1]


def test_profile_busy_is_error(tmp_path, states, monkeypatch):
    monkeypatch.setattr(op, "LOGIN_LOCK_WAIT_S", 0.2)
    world = World(already=True)
    lock = base.ProfileLock(tmp_path / "profiles" / "DemoProfile")
    lock.acquire(1)
    try:
        rc, final = run(world, tmp_path)
    finally:
        lock.release()
    assert rc == 1 and final["state"] == "error" and "占用" in final["message"]
    assert world.launches == []


def _whoami(world, tmp_path):
    return op.run_whoami(make_mod(world), launch=world.launch, profile_root=tmp_path / "profiles")


def test_whoami_without_profile_skips_browser(tmp_path):
    world = World()
    assert _whoami(world, tmp_path) == {"loggedIn": False, "name": "", "avatar": ""}
    assert world.launches == []


def test_whoami_logged_in_reads_identity(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    world = World(saved=True)
    assert _whoami(world, tmp_path) == {"loggedIn": True, "name": "Alice", "avatar": "https://cdn/a.jpg"}
    assert world.launches == [False]


def test_whoami_logged_out(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    assert _whoami(World(saved=False), tmp_path) == {"loggedIn": False, "name": "", "avatar": ""}


def test_whoami_busy_profile_is_unconfident(tmp_path, monkeypatch):
    """登录窗口开着时校验：拿不到锁就报校验失败（带 error），不开第二个浏览器（Review Focus 5）。"""
    monkeypatch.setattr(op, "WHOAMI_LOCK_WAIT_S", 0.2)
    world = World(saved=True)
    lock = base.ProfileLock(tmp_path / "profiles" / "DemoProfile")
    lock.acquire(1)
    try:
        res = _whoami(world, tmp_path)
    finally:
        lock.release()
    assert res["loggedIn"] is False and res.get("error")
    assert world.launches == []


def test_whoami_browser_error_is_unconfident(tmp_path):
    (tmp_path / "profiles" / "DemoProfile").mkdir(parents=True)
    world = World()
    world.verify_error = RuntimeError("browser crashed")
    res = _whoami(world, tmp_path)
    assert res["loggedIn"] is False and "browser crashed" in res["error"]


def test_cli_whoami_prints_single_json_line(monkeypatch, capsys):
    monkeypatch.setattr(op, "run_whoami", lambda mod: {"loggedIn": True, "name": mod.NAME, "avatar": ""})
    assert op.main(["whoami", "--platform", "x"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads(lines[-1]) == {"loggedIn": True, "name": "X", "avatar": ""}


def test_cli_login_passes_platform_and_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(op, "run_login", lambda mod, sf, timeout: seen.update(key=mod.KEY, sf=sf, t=timeout) or 0)
    assert op.main(["login", "--platform", "youtube", "--status-file", "s.json", "--timeout", "90"]) == 0
    assert seen == {"key": "youtube", "sf": "s.json", "t": 90}
    assert op.main(["login", "--platform", "threads"]) == 0
    assert seen["t"] == op.DEFAULT_LOGIN_TIMEOUT == 600


def test_cli_rejects_unknown_platform():
    with pytest.raises(SystemExit) as ei:
        op.main(["whoami", "--platform", "weibo"])
    assert ei.value.code == 2


def test_cli_platforms_lists_all(capsys):
    assert op.main(["platforms"]) == 0
    out = capsys.readouterr().out
    for name in ("TikTok", "YouTube", "Instagram", "X", "Threads"):
        assert name in out
    assert "加权" in out and "标题≤100" in out


def test_selftest_passes(capsys):
    assert op.main(["selftest"]) == 0
    assert "✅" in capsys.readouterr().out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_login.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'overseas_publisher'`

- [ ] **Step 3: 实现 `overseas_publisher.py`**

```python
#!/usr/bin/env python3
"""海外平台（TikTok / YouTube / Instagram / X / Threads）登录与登录态校验。发布在后续 PR 加入。

用法（项目根目录）：
  python skills/shared/scripts/overseas_publisher.py platforms
  python skills/shared/scripts/overseas_publisher.py login --platform youtube [--status-file F] [--timeout 600]
  python skills/shared/scripts/overseas_publisher.py whoami --platform x
  python skills/shared/scripts/overseas_publisher.py selftest

login 在本机弹出 Chrome 窗口，由用户亲手登录（含两步验证）；登录态保存在
~/.easel-browser-profiles/<平台>Profile。--status-file 写 login_state JSON，Web 账号页轮询它。
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import login_state
from overseas import PLATFORMS, REQUIRED_ATTRS, base, get
from overseas.post import KIND_LABEL, x_weighted_length

DEFAULT_LOGIN_TIMEOUT = 600
LOGIN_POLL_MS = 2000
COOKIE_SETTLE_MS = 3000       # 看到登录态后再等一会儿，让登录 cookie 落盘再关浏览器
LOGIN_LOCK_WAIT_S = 30
WHOAMI_LOCK_WAIT_S = 20
NAV_TIMEOUT_MS = 60000

STARTING_MSG = "正在启动 Chrome…"
WINDOW_MSG = "已弹出 Chrome 窗口，请在窗口里登录 {name}，不要关掉它（可以做两步验证，最长 {minutes} 分钟）"
VERIFYING_MSG = "登录成功，正在确认登录态已保存…"
NOT_SAVED_MSG = "登录看似成功但登录态没能保存，请重试"
VERIFY_FAILED_MSG = ("登录已完成，但确认登录态时浏览器或网络出错：{err}。"
                     "可以稍后在账号页点「校验」；仍显示未登录就再登录一次")
WINDOW_CLOSED_MSG = "登录窗口被关掉了，登录没有完成。请重新点登录"
EXPIRED_MSG = "{minutes} 分钟内没有完成登录，请重新点登录"
BUSY_MSG = "{name} 的登录目录正被占用（可能在校验登录状态），请等 10 秒再点登录"


def run_login(mod, status_file, timeout_s, *, launch=base.launch, clock=time.monotonic, profile_root=None) -> int:
    """弹出有头窗口让用户登录 → 关窗口 → 无头重开确认登录态已保存，才写 success。每条路都落终态。"""
    sf = status_file
    login_state.write_status(sf, "starting", STARTING_MSG)
    profile = base.profile_dir(mod, profile_root)
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(LOGIN_LOCK_WAIT_S)
    except TimeoutError:
        return _fail(sf, "error", BUSY_MSG.format(name=mod.NAME))
    try:
        return _login_locked(mod, sf, timeout_s, profile, launch, clock)
    finally:
        lock.release()


def _fail(sf, state: str, msg: str, rc: int = 1) -> int:
    login_state.write_status(sf, state, msg)
    print(f"❌ {msg}", file=sys.stderr)
    return rc


def _login_locked(mod, sf, timeout_s, profile, launch, clock) -> int:
    minutes = max(1, timeout_s // 60)
    try:
        with launch(profile, headed=True) as ctx:
            page = base.first_page(ctx)
            login_state.write_status(sf, "window_login", WINDOW_MSG.format(name=mod.NAME, minutes=minutes))
            page.goto(mod.LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            deadline = clock() + timeout_s
            while True:
                base.ensure_window_open(page)
                if mod.is_logged_in(page):
                    page.wait_for_timeout(COOKIE_SETTLE_MS)
                    break
                if clock() >= deadline:
                    return _fail(sf, "expired", EXPIRED_MSG.format(minutes=minutes))
                page.wait_for_timeout(LOGIN_POLL_MS)
    except base.PlaywrightMissing as e:
        return _fail(sf, "error", str(e), rc=3)
    except Exception as e:  # noqa: BLE001 — 任何意外都要落 error 终态，否则账号页弹窗会一直转圈
        msg = WINDOW_CLOSED_MSG if base.is_window_closed_error(e) else f"登录出错：{base.short_err(e)}"
        return _fail(sf, "error", msg)

    login_state.write_status(sf, "verifying", VERIFYING_MSG)
    try:
        ident = _verify_saved(mod, profile, launch)
    except Exception as e:  # noqa: BLE001 — 重开浏览器 / 网络出错说明不了没存上，别吓人重登
        return _fail(sf, "error", VERIFY_FAILED_MSG.format(err=base.short_err(e)))
    if ident is None:
        return _fail(sf, "error", NOT_SAVED_MSG)
    login_state.write_status(sf, "success", ident.get("name") or "已登录")
    print(f"✅ {mod.NAME} 登录成功，已重开浏览器确认登录态已保存")
    return 0


def _verify_saved(mod, profile, launch) -> dict | None:
    with launch(profile, headed=False) as ctx:
        page = base.first_page(ctx)
        page.goto(mod.HOME_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        if not base.settle(page, mod):
            return None
        return mod.read_identity(page)


def run_whoami(mod, *, launch=base.launch, profile_root=None) -> dict:
    """无头打开首页看登录态。没登录过（没有登录目录）直接返回未登录，不起浏览器；
    校验本身失败（目录被占用、浏览器 / 网络出错）带 error 字段，Web 后端据此不删登录标记。"""
    result = {"loggedIn": False, "name": "", "avatar": ""}
    profile = base.profile_dir(mod, profile_root)
    if not profile.is_dir():
        return result
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(WHOAMI_LOCK_WAIT_S)
    except TimeoutError:
        result["error"] = "登录目录正被占用（登录窗口可能还开着）"
        return result
    try:
        with launch(profile, headed=False) as ctx:
            page = base.first_page(ctx)
            page.goto(mod.HOME_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if base.settle(page, mod):
                result["loggedIn"] = True
                result.update(mod.read_identity(page))
    except Exception as e:  # noqa: BLE001 — whoami 永远输出 JSON
        result["error"] = base.short_err(e)
    finally:
        lock.release()
    return result


def _print_platforms() -> int:
    for m in PLATFORMS.values():
        kinds = "、".join(KIND_LABEL[k] for k in ("video", "image", "text") if k in m.KINDS)
        lim = m.LIMITS
        parts = [f"文案≤{lim.caption}{'（加权）' if lim.weighted else ''}"]
        if lim.title:
            parts.append(f"标题≤{lim.title}")
        if lim.images:
            parts.append(f"图片≤{lim.images}张")
        if lim.hashtags:
            parts.append(f"标签≤{lim.hashtags}个")
        if m.VISIBILITY:
            parts.append(f"可见范围：{'/'.join(m.VISIBILITY)}")
        print(f"{m.KEY:<10} {m.NAME:<10} {kinds}  {'，'.join(parts)}")
    return 0


def _selftest() -> int:
    problems: list[str] = []
    for key, m in PLATFORMS.items():
        missing = [a for a in REQUIRED_ATTRS if not hasattr(m, a)]
        if missing:
            problems.append(f"{key} 缺 {', '.join(missing)}")
            continue
        if m.KEY != key:
            problems.append(f"{key} 的 KEY 写成了 {m.KEY}")
        if not m.KINDS or not set(m.KINDS) <= set(KIND_LABEL):
            problems.append(f"{key} 的 KINDS 不合法：{sorted(m.KINDS)}")
        if ("image" in m.KINDS) != (m.LIMITS.images > 0):
            problems.append(f"{key} 的图文能力和图片张数上限对不上")
        if m.VISIBILITY and m.VISIBILITY_DEFAULT not in m.VISIBILITY:
            problems.append(f"{key} 的默认可见范围不在选项里")
        if not any(mk.lower() in m.LOGIN_URL.lower() for mk in m.LOGIN_MARKERS):
            problems.append(f"{key} 的登录页地址没被 LOGIN_MARKERS 识别")
    if len({m.PROFILE for m in PLATFORMS.values()}) != len(PLATFORMS):
        problems.append("登录目录名有重复")
    for text, n in (("a" * 280, 280), ("中" * 140, 280), ("https://example.com/x", 23)):
        if x_weighted_length(text) != n:
            problems.append(f"X 加权计数错误：{text[:12]}…")
    if problems:
        for p in problems:
            print(f"❌ {p}")
        return 1
    print(f"✅ selftest 通过（{len(PLATFORMS)} 个平台：{', '.join(PLATFORMS)}）")
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows GBK 控制台打印 ✅ / ❌ 会崩
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="海外平台（TikTok / YouTube / Instagram / X / Threads）登录与登录态校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("platforms", help="列出平台、支持的形式和上限")
    p = sub.add_parser("login", help="弹出 Chrome 窗口，亲手登录")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    p.add_argument("--status-file", help="登录状态 JSON（Web 账号页轮询它）")
    p.add_argument("--timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT, help="最长等多少秒（默认 600）")
    p = sub.add_parser("whoami", help="校验登录态，输出单行 JSON")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    sub.add_parser("selftest", help="离线自检")
    a = ap.parse_args(argv)
    if a.cmd == "platforms":
        return _print_platforms()
    if a.cmd == "selftest":
        return _selftest()
    if a.cmd == "login":
        return run_login(get(a.platform), a.status_file, a.timeout)
    print(json.dumps(run_whoami(get(a.platform)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_login.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 跑命令行冒烟（离线）**

Run: `.venv/bin/python skills/shared/scripts/overseas_publisher.py selftest && .venv/bin/python skills/shared/scripts/overseas_publisher.py platforms`
Expected: `✅ selftest 通过（5 个平台：tiktok, youtube, instagram, x, threads）`，随后 5 行平台说明。

- [ ] **Step 6: 提交**

```bash
git add skills/shared/scripts/overseas_publisher.py tests/test_overseas_login.py
git commit -m "feat(overseas): 海外平台窗口登录与登录态校验命令（login / whoami / platforms / selftest）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Web 后端接入 + 已知问题文档

**Files:**
- Modify: `web/app.py`：`LOGIN_TIMEOUT` 附近（约 217 行）、`LOGIN_RUNNERS`（约 229 行）、`/api/accounts`（约 3102 行）、`_xhs_headed_fallback_available`（约 3116 行）、`api_login_start`（约 3138 行）、`_account_whoami` 的命令拼装（约 3434 行）
- Modify: `docs/known-issues.md`、`docs/known-issues_EN.md`（文末追加一节）
- Test: `tests/test_overseas_web.py`

**Interfaces:**
- Consumes: Task 4 的命令行：`overseas_publisher.py login --platform P --status-file F --timeout N`、`overseas_publisher.py whoami --platform P`（单行 JSON）；Task 3 的 `PLATFORMS[k].NAME/.PROFILE`（测试里对齐）
- Produces:
  - `LOGIN_RUNNERS[k]["region"]`（`"domestic"` / `"overseas"`）；海外条目 `{"name", "backend": "overseas", "op", "profile", "region": "overseas"}`
  - `OVERSEAS_LOGIN_TIMEOUT = 600`、`OVERSEAS_NO_DESKTOP_NOTE: str`
  - `_can_open_window(platform=None, env=None, os_name=None) -> bool`、`_runner_available(cfg) -> tuple[bool, str]`
  - `/api/accounts` 每行多 `region`；海外平台在没桌面时 `supported: false`、`note` 为原因

- [ ] **Step 1: 写失败的测试**

`tests/test_overseas_web.py`：

```python
"""Web 账号页接入海外平台：LOGIN_RUNNERS、/api/accounts 的 region 与不可用原因、登录 / whoami 命令拼装、退出。
不起浏览器、不连平台。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
from overseas import PLATFORMS  # noqa: E402

OVERSEAS = ["tiktok", "youtube", "instagram", "x", "threads"]


def test_login_runners_register_overseas_platforms():
    for key in OVERSEAS:
        cfg = web.LOGIN_RUNNERS[key]
        assert cfg["backend"] == "overseas" and cfg["region"] == "overseas"
        assert cfg["op"] == key
        assert cfg["profile"] == PLATFORMS[key].PROFILE
        assert cfg["name"] == PLATFORMS[key].NAME
    for key, cfg in web.LOGIN_RUNNERS.items():
        if key not in OVERSEAS:
            assert cfg["region"] == "domestic", key
    assert web.OVERSEAS_LOGIN_TIMEOUT == 600


@pytest.fixture
def login_dir(monkeypatch, tmp_path):
    d = tmp_path / "_login"
    d.mkdir()
    monkeypatch.setattr(web, "LOGIN_DIR", d)
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    monkeypatch.setattr(web, "_account_logged_in", lambda *_a: False)   # 不读真机的公众号 / B 站配置
    return d


def test_accounts_api_reports_region(login_dir, monkeypatch):
    monkeypatch.setattr(web, "_can_open_window", lambda: True)
    rows = {r["platform"]: r for r in asyncio.run(web.api_accounts())}
    assert rows["youtube"]["region"] == "overseas" and rows["youtube"]["supported"] is True
    assert rows["xiaohongshu"]["region"] == "domestic"


def test_overseas_unavailable_without_desktop(login_dir, monkeypatch):
    """没桌面（Linux 服务器）：海外登录不可用并说明原因，接口直接 400（Review Focus 4）。"""
    monkeypatch.setattr(web, "_can_open_window", lambda: False)
    rows = {r["platform"]: r for r in asyncio.run(web.api_accounts())}
    assert rows["x"]["supported"] is False
    assert "桌面" in rows["x"]["note"]
    assert rows["xiaohongshu"]["supported"] is True
    with pytest.raises(web.HTTPException) as ei:
        asyncio.run(web.api_login_start("x"))
    assert ei.value.status_code == 400


def test_login_start_runs_overseas_window_login(login_dir, monkeypatch):
    monkeypatch.setattr(web, "_can_open_window", lambda: True)
    captured: dict[str, list[str]] = {}

    class FakePopen:
        def __init__(self, cmd, **_kw):
            captured["cmd"] = list(cmd)
            status = cmd[cmd.index("--status-file") + 1]
            Path(status).write_text(json.dumps({"state": "window_login", "message": "已弹出 Chrome 窗口"}),
                                    encoding="utf-8")

        def poll(self):
            return None

    monkeypatch.setattr(web.subprocess, "Popen", FakePopen)
    res = asyncio.run(web.api_login_start("youtube"))
    assert res["state"] == "window_login"
    cmd = captured["cmd"]
    assert cmd[1].endswith("overseas_publisher.py") and cmd[2] == "login"
    assert cmd[cmd.index("--platform") + 1] == "youtube"
    assert cmd[cmd.index("--timeout") + 1] == "600"


def test_whoami_runs_overseas_script(login_dir, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"loggedIn": True, "name": "Alice", "avatar": ""}), stderr="")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    res = asyncio.run(web.api_account_whoami("threads"))
    assert res["loggedIn"] is True and res["name"] == "Alice"
    assert calls[0][1].endswith("overseas_publisher.py")
    assert calls[0][2:] == ["whoami", "--platform", "threads"]
    marker = json.loads((login_dir / "threads.json").read_text(encoding="utf-8"))
    assert marker["state"] == "success"


def test_logout_removes_overseas_profile(login_dir, monkeypatch, tmp_path):
    profiles = tmp_path / "profiles"
    (profiles / "XProfile").mkdir(parents=True)
    monkeypatch.setattr(web, "BROWSER_PROFILES", profiles)
    (login_dir / "x.json").write_text("{}", encoding="utf-8")
    res = asyncio.run(web.api_logout("x"))
    assert "XProfile" in res["deleted"]
    assert not (profiles / "XProfile").exists()
    assert not (login_dir / "x.json").exists()


@pytest.mark.parametrize("platform,os_name,env,expected", [
    ("darwin", "posix", {}, True),
    ("win32", "nt", {}, True),
    ("linux", "posix", {}, False),
    ("linux", "posix", {"DISPLAY": ":0"}, True),
    ("linux", "posix", {"WAYLAND_DISPLAY": "wayland-0"}, True),
])
def test_can_open_window(platform, os_name, env, expected):
    assert web._can_open_window(platform=platform, env=env, os_name=os_name) is expected
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_web.py -q`
Expected: FAIL（`KeyError: 'tiktok'`、`AttributeError: ... has no attribute '_can_open_window'` 等）

- [ ] **Step 3: 改 `web/app.py` —— 常量与 `LOGIN_RUNNERS`**

在 `LOGIN_TIMEOUT = 240` 下面加：

```python
# 海外平台在本机弹出的 Chrome 窗口里亲手登录（输密码、两步验证），比扫码慢
OVERSEAS_LOGIN_TIMEOUT = 600
OVERSEAS_NO_DESKTOP_NOTE = '需要在有桌面的本机登录（会弹出 Chrome 窗口）'
```

把 `LOGIN_RUNNERS` 整体替换为：

```python
LOGIN_RUNNERS: dict[str, dict] = {
    "xiaohongshu": {"name": "小红书", "backend": "xhs", "profile": "XiaohongshuProfile", "region": "domestic"},
    "kuaishou": {"name": "快手", "backend": "web", "wp": "kuaishou", "profile": "KuaishouProfile", "region": "domestic"},
    "weixin-channels": {"name": "微信视频号", "backend": "web", "wp": "weixin-channels", "profile": "ChannelsProfile",
                        "region": "domestic"},
    "zhihu": {"name": "知乎", "backend": "web", "wp": "zhihu", "profile": "ZhihuProfile", "region": "domestic"},
    "bilibili": {"name": "B站", "backend": "biliup", "region": "domestic"},
    "douyin": {"name": "抖音", "backend": "douyin", "profile": "DouyinProfile", "region": "domestic"},
    # 微信公众号：扫码登录后台会话（发布+数据都走它），backend=='wechat-oa' 在各处单独分支处理。
    "wechat-oa": {"name": "微信公众号", "backend": "wechat-oa", "region": "domestic"},
    # 海外平台：本机弹 Chrome 窗口亲手登录。op = overseas_publisher.py 的平台码，
    # profile 必须与 skills/shared/scripts/overseas/<平台>.py 的 PROFILE 一致（退出时按它删登录目录）。
    "tiktok": {"name": "TikTok", "backend": "overseas", "op": "tiktok", "profile": "TikTokProfile",
               "region": "overseas"},
    "youtube": {"name": "YouTube", "backend": "overseas", "op": "youtube", "profile": "YouTubeProfile",
                "region": "overseas"},
    "instagram": {"name": "Instagram", "backend": "overseas", "op": "instagram", "profile": "InstagramProfile",
                  "region": "overseas"},
    "x": {"name": "X", "backend": "overseas", "op": "x", "profile": "XProfile", "region": "overseas"},
    "threads": {"name": "Threads", "backend": "overseas", "op": "threads", "profile": "ThreadsProfile",
                "region": "overseas"},
}
```

- [ ] **Step 4: 改 `web/app.py` —— 能否弹窗口、`/api/accounts`**

把 `_xhs_headed_fallback_available` 整个函数替换为下面两个函数（行为与原来逐项一致）：

```python
def _can_open_window(platform: str | None = None, env: dict | None = None,
                     os_name: str | None = None) -> bool:
    """本机能不能弹出浏览器窗口：macOS / Windows 能；Linux 要有 DISPLAY 或 WAYLAND_DISPLAY。
    参数只为测试注入，默认取真实环境。"""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    os_name = os.name if os_name is None else os_name
    if platform == "darwin" or os_name == "nt":
        return True
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def _xhs_headed_fallback_available(platform: str | None = None, env: dict | None = None,
                                   os_name: str | None = None) -> bool:
    """小红书登录能不能「无头被拦就改开有头窗口」：本机得有桌面能弹窗口。

    实测小红书只拦「未登录 + 无头」（300012），有头窗口不拦 —— 所以本机有桌面时给 runner 加
    --headed-fallback，被拦就弹窗口让用户扫；没桌面（服务器 / 无 DISPLAY 的 Linux）加了也弹不出来。
    EASEL_XHS_HEADED_FALLBACK=0/1 强制关/开（例如 Web 是远程访问、窗口会弹在别人看不到的屏幕上）。
    参数只为测试注入，默认取真实环境。"""
    env = os.environ if env is None else env
    override = (env.get("EASEL_XHS_HEADED_FALLBACK") or "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False
    return _can_open_window(platform, env, os_name)
```

在 `@app.get("/api/accounts")` 上方加：

```python
def _runner_available(cfg: dict) -> tuple[bool, str]:
    """(账号页能不能登录这个平台, 给用户看的说明)。海外平台要弹 Chrome 窗口，没桌面就不可用。"""
    if cfg['backend'] == 'unsupported':
        return False, cfg.get('note', '')
    if cfg['backend'] == 'overseas' and not _can_open_window():
        return False, OVERSEAS_NO_DESKTOP_NOTE
    return True, cfg.get('note', '')
```

把 `api_accounts` 替换为：

```python
@app.get("/api/accounts")
async def api_accounts():
    rows = []
    for pf, cfg in LOGIN_RUNNERS.items():
        ok, note = _runner_available(cfg)
        rows.append({
            'platform': pf, 'name': cfg['name'], 'backend': cfg['backend'],
            'region': cfg.get('region', 'domestic'),   # 账号页按国内 / 海外分组
            'supported': ok,
            'loggedIn': _account_logged_in(pf, cfg),
            # 登录标记指纹：前端 whoami 缓存记着校验那一刻的值，不相等 = 之后有人登录/退出过
            # （CLI 直跑 login 等），缓存作废重新校验——否则缓存的「未登录」要顶满 10 分钟 TTL。
            'loginTs': _login_marker_ts(pf),
            'note': note,
        })
    return rows
```

- [ ] **Step 5: 改 `web/app.py` —— 登录与 whoami 的 `overseas` 分支**

`api_login_start` 里，在 `if backend == 'unsupported':` 那段之后加：

```python
    if backend == 'overseas' and not _can_open_window():
        raise HTTPException(400, f"{cfg['name']}：{OVERSEAS_NO_DESKTOP_NOTE}")
```

同一函数的命令拼装里，在 `elif backend == 'douyin':` 分支之后、`else:` 之前加：

```python
    elif backend == 'overseas':
        # 海外平台：本机弹出 Chrome 窗口，用户亲手登录（含两步验证），比扫码慢，给 10 分钟
        cmd = [sys.executable, str(SHARED_SCRIPTS / 'overseas_publisher.py'), 'login',
               '--platform', cfg['op'], '--status-file', str(status),
               '--timeout', str(OVERSEAS_LOGIN_TIMEOUT)]
```

`_account_whoami` 的命令拼装里，在 `elif backend == 'douyin':` 分支之后、`else:` 之前加：

```python
    elif backend == 'overseas':
        cmd = [sys.executable, str(SHARED_SCRIPTS / 'overseas_publisher.py'), 'whoami',
               '--platform', cfg['op']]
```

- [ ] **Step 6: 跑测试确认通过，并回归小红书 / 视频号相关测试**

Run: `.venv/bin/python -m pytest tests/test_overseas_web.py tests/test_xhs_login.py tests/test_login_whoami_race.py tests/test_web_analytics.py tests/test_mp_login.py -q`
Expected: 全部 PASS（`test_xhs_headed_fallback_available` 的参数化用例不改、全过）

- [ ] **Step 7: 写已知问题文档**

`docs/known-issues.md` 文末追加：

```markdown
## 海外平台登录：要在有桌面的本机，最好装 Google Chrome

- **影响范围**：账号页的 TikTok / YouTube / Instagram / X / Threads。
- **表现**：点「登录」会在运行 Easel 的这台电脑上弹出 Chrome 窗口，需要在窗口里亲手登录（含两步验证），最长 10 分钟。没有桌面的环境（Linux 服务器、无 `DISPLAY`）弹不出窗口，账号页的登录按钮会置灰。
- **Google 登录**：Google 会拦截自动化用的 Chromium（「此浏览器或应用可能不安全」）。Easel 优先用本机安装的 Google Chrome；没装时退回 Playwright 自带的 Chromium，YouTube 登录大概率失败。解决：安装 Google Chrome 后重新点登录。
- **网络**：海外平台不强制直连。配了 `EASEL_PROXY` 就走该代理，否则用系统网络设置。国内平台照旧直连。
- **登录目录**：`~/.easel-browser-profiles/<平台>Profile`（如 `YouTubeProfile`）。账号页「退出」会删掉它。
```

`docs/known-issues_EN.md` 文末追加：

```markdown
## Overseas platform login needs a local desktop, ideally with Google Chrome

- **Affects**: TikTok / YouTube / Instagram / X / Threads on the Accounts page.
- **Behavior**: "登录" opens a Chrome window on the machine running Easel; you sign in there yourself (2FA included), within 10 minutes. Machines without a desktop (Linux servers, no `DISPLAY`) cannot show the window, so the button is disabled.
- **Google sign-in**: Google blocks automation Chromium ("This browser or app may not be secure"). Easel prefers the locally installed Google Chrome and falls back to Playwright's bundled Chromium, where YouTube sign-in will likely fail. Fix: install Google Chrome and sign in again.
- **Network**: overseas platforms are not forced to connect directly. `EASEL_PROXY` is used when set; otherwise the system network settings apply. Domestic platforms still connect directly.
- **Profiles**: `~/.easel-browser-profiles/<Platform>Profile` (e.g. `YouTubeProfile`). "退出" on the Accounts page deletes it.
```

- [ ] **Step 8: 提交**

```bash
git add web/app.py tests/test_overseas_web.py docs/known-issues.md docs/known-issues_EN.md
git commit -m "feat(accounts): 账号页接入五个海外平台的窗口登录、校验与退出

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 账号页前端分组

**Files:**
- Modify: `web/frontend/src/lib/api.ts`（`AccountItem`，约 370 行）
- Modify: `web/frontend/src/components/AccountsPage.tsx`（`status`、页头说明、列表渲染，约 284–357 行）
- Modify: `web/frontend/src/styles/pages/accounts.css`
- Test: `web/frontend/src/components/AccountsPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 的 `/api/accounts` 字段 `region: 'domestic' | 'overseas'`、`supported`、`note`
- Produces: 账号页 `<section className="accounts-group" aria-label="国内|海外">`（多于一组时才带标题 `<h2 className="accounts-group-title">`）

- [ ] **Step 1: 写失败的测试**

在 `web/frontend/src/components/AccountsPage.test.tsx` 的 `describe('AccountsPage', ...)` 里追加：

```tsx
  it('国内、海外分两组；海外平台的登录按钮叫「登录」', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', region: 'domestic', supported: true, loggedIn: false, note: '' },
      { platform: 'youtube', name: 'YouTube', backend: 'overseas', region: 'overseas', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    const overseas = await screen.findByRole('region', { name: '海外' });
    const domestic = screen.getByRole('region', { name: '国内' });
    expect(within(overseas).getByText('YouTube')).toBeTruthy();
    expect(within(domestic).getByText('知乎')).toBeTruthy();
    expect(within(overseas).getByRole('heading', { level: 2, name: '海外' })).toBeTruthy();
    expect(within(overseas).getByRole('button', { name: '登录' })).toBeTruthy();
    expect(within(domestic).getByRole('button', { name: '扫码登录' })).toBeTruthy();
  });

  it('只有国内平台时不显示分组标题', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    await screen.findByText('知乎');
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });

  it('没桌面时海外平台显示「不可用」和原因，登录按钮置灰', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', region: 'domestic', supported: true, loggedIn: false, note: '' },
      { platform: 'x', name: 'X', backend: 'overseas', region: 'overseas', supported: false, loggedIn: false,
        note: '需要在有桌面的本机登录（会弹出 Chrome 窗口）' },
    ]);
    render(<AccountsPage />);
    const row = (await screen.findByText('X')).closest('.account-row') as HTMLElement;
    expect(within(row).getByText('不可用')).toBeTruthy();
    expect(within(row).getByText(/有桌面的本机/)).toBeTruthy();
    expect((within(row).getByRole('button', { name: '登录' }) as HTMLButtonElement).disabled).toBe(true);
  });
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd web/frontend && npx vitest run src/components/AccountsPage.test.tsx`
Expected: FAIL（找不到 role="region" name="海外"；`region` 不在 `AccountItem` 上的类型错误由 Step 6 的 build 检查）

- [ ] **Step 3: 改 `lib/api.ts`**

把 `AccountItem` 替换为：

```ts
export interface AccountItem {
  platform: string;
  name: string;
  backend: string;      // xhs | web | biliup | douyin | wechat-oa | overseas | unsupported
  /** 账号页分组：国内平台扫码登录；海外平台在本机弹出的 Chrome 窗口里登录。旧后端没有这个字段，按国内处理。 */
  region?: 'domestic' | 'overseas';
  supported: boolean;
  loggedIn: boolean;
  /** 登录标记指纹（outputs/_login/<平台>.json 的 mtime 秒，无标记为 null）。只用来比相等：
   *  跟 whoami 缓存里记的不一样 = 之后有人登录/退出过（CLI 直跑 login 等），缓存作废。 */
  loginTs?: number | null;
  note: string;
}
```

- [ ] **Step 4: 改 `AccountsPage.tsx`**

4a. `status` 函数第一行改为：

```tsx
    if (!a.supported) return <StatusDot tone="idle">{a.region === 'overseas' ? '不可用' : '待重写'}</StatusDot>;
```

4b. 在 `const busyFor = ...` 下面加：

```tsx
  // 海外平台不是扫码，是在本机弹出的 Chrome 窗口里登录
  const loginLabel = (a: AccountItem) => (a.region === 'overseas' ? '登录' : '扫码登录');
```

4c. 页头说明改为：

```tsx
        description="国内平台用手机 App 扫码登录，海外平台在本机弹出的 Chrome 窗口里登录。登录状态保存在本机，之后发布不用再登。"
```

4d. 在 `return (` 之前定义 `renderRow` 与 `groups`（行内 JSX 原样搬自现有 `accounts.map` 块，只有登录按钮文字改用 `loginLabel(a)`）：

```tsx
  const renderRow = (a: AccountItem) => {
    const w = whoami[a.platform];
    const info = w && w !== 'loading' ? w : null;
    const logged = effLoggedIn(a);
    return (
      <div key={a.platform} className={`account-row${a.supported ? '' : ' is-unsupported'}`}>
        <span className="account-platform">{a.name}</span>
        <span className="account-who">
          {logged && info ? (
            <>
              <Avatar url={info.avatar} name={info.name || a.name} />
              <span className="account-nick" title={info.name || ''}>{info.name || '已登录'}</span>
            </>
          ) : (
            // 已登录但还没有 whoami 结果（B站 不自动校验、其他平台校验中）也要占住这一栏，不能留空
            <span className="account-note">{logged ? '已登录' : (a.note || '未登录')}</span>
          )}
        </span>
        {status(a)}
        <span className="account-actions">
          {logged ? (
            <>
              <Button size="sm" disabled={busyFor(a) || w === 'loading'} onClick={() => runWhoami(a.platform)}>
                {w === 'loading' ? '校验中…' : '校验'}
              </Button>
              <Button size="sm" disabled={logoutBusy === a.platform} onClick={() => handleLogout(a)}>
                {logoutBusy === a.platform ? '退出中…' : '退出'}
              </Button>
            </>
          ) : (
            // 公众号与其它平台统一：都走扫码登录（公众号扫的是后台会话，用于发布+数据）；海外平台弹窗口登录
            <Button size="sm" variant={a.supported ? 'primary' : 'secondary'}
              disabled={!a.supported || busyFor(a)}
              onClick={() => (a.backend === 'wechat-oa' ? handleMpLogin(a) : handleLogin(a))}>
              {busyFor(a) ? '启动中…' : loginLabel(a)}
            </Button>
          )}
        </span>
      </div>
    );
  };

  // 国内 / 海外分组；只有一组时不显示组标题（和以前一样是一整张列表）
  const groups = [
    { key: 'domestic', title: '国内', items: accounts.filter((a) => a.region !== 'overseas') },
    { key: 'overseas', title: '海外', items: accounts.filter((a) => a.region === 'overseas') },
  ].filter((g) => g.items.length > 0);
  const grouped = groups.length > 1;
```

4e. 把 JSX 里整个 `<div className="accounts-list"> {accounts.map((a) => { ... })} </div>` 替换为：

```tsx
      {groups.map((g) => (
        <section key={g.key} className="accounts-group" aria-label={grouped ? g.title : undefined}>
          {grouped && <h2 className="accounts-group-title">{g.title}</h2>}
          <div className="accounts-list">{g.items.map(renderRow)}</div>
        </section>
      ))}
```

- [ ] **Step 5: 加样式**

`web/frontend/src/styles/pages/accounts.css` 在 `.accounts-list { ... }` 下一行加：

```css
.accounts-group + .accounts-group { margin-top: var(--sp-6); }
.accounts-group-title { margin: 0 0 var(--sp-2); font-family: var(--font-serif); font-size: var(--fs-14); font-weight: 600; color: var(--c-ink-2); }
```

- [ ] **Step 6: 跑前端测试、构建、lint**

Run: `cd web/frontend && npm test && npm run build && npm run lint`
Expected: 测试全过；`tsc -b && vite build` 成功；lint 无 error（warning 数与 main 相同，现为 2 条）

- [ ] **Step 7: 提交**

```bash
git add web/frontend/src/lib/api.ts web/frontend/src/components/AccountsPage.tsx web/frontend/src/components/AccountsPage.test.tsx web/frontend/src/styles/pages/accounts.css
git commit -m "feat(accounts): 账号页按国内 / 海外分组，海外平台用「登录」按钮弹窗口

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 真机校准（需用户在场，每一步先征得同意）

**Files:**
- Modify（按校准结果）：`skills/shared/scripts/overseas/{tiktok,youtube,instagram,x,threads}.py` 的 `AUTH_COOKIES`、`LOGIN_MARKERS`、`HOME_URL`、`NAME_SELECTORS`、`AVATAR_SELECTORS` 和模块文档字符串里的校准说明
- 临时脚本（不提交）：会话 scratchpad 目录下的 `probe_overseas.py`

**Interfaces:**
- Consumes: Task 4 的 `overseas_publisher.py login / whoami`、Task 2 的 `base.launch`、`base.profile_dir`、`base.first_page`
- Produces: 五个平台的真机登录判定与身份读取都可用

这一步会打开真实平台页面、使用用户的真实账号，**开始前先问用户**：「现在可以逐个平台弹 Chrome 窗口让你登录吗？只登录和读昵称，不发任何内容。」得到同意后再做。全程只读：不点任何发布、关注、点赞按钮。

- [ ] **Step 1: 写只读探针（不提交）**

`<scratchpad>/probe_overseas.py`：

```python
"""只读探针：打印登录后首页地址、登录 cookie 名（不打印值）、当前判定、候选头像图片。不点任何按钮。"""
import sys

sys.path.insert(0, "skills/shared/scripts")
from overseas import base, get  # noqa: E402

mod = get(sys.argv[1])
with base.launch(base.profile_dir(mod), headed=False) as ctx:
    page = base.first_page(ctx)
    page.goto(mod.HOME_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    print("url:", page.url)
    print("cookie names:", sorted({c["name"] for c in ctx.cookies([mod.COOKIE_URL])}))
    print("is_logged_in:", mod.is_logged_in(page), "identity:", mod.read_identity(page))
    for img in page.query_selector_all("img")[:60]:
        alt = (img.get_attribute("alt") or "")[:60]
        src = (img.get_attribute("src") or "")[:80]
        if alt or "avatar" in src or "profile" in src:
            print("img alt=%r src=%r" % (alt, src))
```

- [ ] **Step 2: 逐个平台登录**

对 `x`、`instagram`、`threads`、`tiktok`、`youtube` 依次运行（项目根目录）：

```bash
.venv/bin/python skills/shared/scripts/overseas_publisher.py login --platform <平台码>
```

用户在弹出的 Chrome 窗口里登录。Expected：终端打印 `✅ <平台> 登录成功，已重开浏览器确认登录态已保存`。

若用户已登录完成而终端仍在等待：另开终端跑 `.venv/bin/python <scratchpad>/probe_overseas.py <平台码>`（登录窗口占着锁时先关掉登录命令），按打印的 `url` 与 `cookie names` 修正该平台的 `AUTH_COOKIES` / `LOGIN_MARKERS` / `HOME_URL`，再重跑 login（已登录会直接进入确认）。

- [ ] **Step 3: 校准昵称与头像**

对每个平台运行：

```bash
.venv/bin/python skills/shared/scripts/overseas_publisher.py whoami --platform <平台码>
```

Expected：`{"loggedIn": true, "name": "<昵称>", "avatar": "https://..."}`。`name` 或 `avatar` 为空时，看 probe 打印的候选图片，或把 probe 里的 `headed=False` 临时改成 `True` 观察页面，填好该平台的 `NAME_SELECTORS` / `AVATAR_SELECTORS`（每个候选选择器内部不要含逗号），重跑 whoami 直到读到。

- [ ] **Step 4: 确认没登录时判未登录**

征得用户同意后，选一个平台在账号页点「退出」（删登录目录），再跑该平台的 whoami。Expected：`{"loggedIn": false, "name": "", "avatar": ""}`，且没有起浏览器（登录目录已不存在）。之后让用户重新登录该平台。

- [ ] **Step 5: 回归离线测试并提交**

把各模块文档字符串里的「待真机校准（PR 1 计划 Task 7）」改为「真机校准于 <实际日期>」。

Run: `.venv/bin/python -m pytest tests/test_overseas_platforms.py tests/test_overseas_login.py -q && .venv/bin/python skills/shared/scripts/overseas_publisher.py selftest`
Expected: 全部 PASS，selftest ✅

```bash
git add skills/shared/scripts/overseas/
git commit -m "fix(overseas): 真机校准五个平台的登录判定与昵称头像读取

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 全量验证、整体审查与合并

**Files:** 无新增

- [ ] **Step 1: 全量检查**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_skills.py
.venv/bin/python scripts/validate_skill_commands.py
.venv/bin/python skills/shared/scripts/overseas_publisher.py selftest
cd web/frontend && npm test && npm run build && npm run lint
```

Expected：pytest 全过（数量 = main 基线 534 + 本 PR 新增）；两个 validator OK；selftest ✅；前端测试 / 构建通过，lint 无 error。

- [ ] **Step 2: 整体代码审查**

派独立审查（Sonnet），输入 `git diff origin/main...HEAD`，重点：国内平台行为是否零改动、登录状态机每条路是否落终态、锁与 whoami 的互斥、Windows 兼容、前端分组与可访问性。修掉确认的问题后做一次范围审查。

- [ ] **Step 3: 推送、开 PR、合并、清理**

```bash
git push -u origin feat/overseas-login
gh pr create --base main --title "feat(overseas): 海外平台窗口登录（TikTok / YouTube / Instagram / X / Threads）" --body "<变更、验证结果、真机校准记录，结尾 🤖 Generated with [Claude Code](https://claude.com/claude-code)>"
gh pr merge --merge
```

合并后：删 worktree 里的 `.venv`、`node_modules` 软链 → `git worktree remove ../Easel-wt-os` → 主目录 `git pull --ff-only` → 删本地与远端分支 → `cd web/frontend && npm run build`。告诉用户：后端有改动，等手上任务结束后重启 `easel web`，账号页才会出现海外平台。
