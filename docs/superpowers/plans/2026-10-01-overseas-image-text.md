# 海外平台图文与纯文字发布 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第二期视频发布的基础上，接通图文（TikTok / Instagram / X / Threads）和纯文字（X / Threads），发布中心与对话同步放开。

**Architecture:** 沿用 `overseas/<平台>.py` 的 `publish(drv, fields, post)`，按 `post.kind` 分支；`PageDriver` 新增 `wait_count`（等 N 个预览挂上），`type_text` 输完以话题 / @ 结尾的行时补空格、联想框还开着就按 Esc。`READY_KINDS` 扩到各平台的 `KINDS`（YouTube 仍为空）。Web 和前端把「只能发视频」收窄到 YouTube，「必须带媒体」收窄到 TikTok / Instagram / YouTube。

**Tech Stack:** Python 3.12 + Playwright（同步 API）、FastAPI、React 19 + Vitest。

**Spec:** `docs/superpowers/specs/2026-10-01-overseas-publishing-design.md`（§5.1 平台能力、§8 PR 3）

## Global Constraints

- 测试不连真平台、不调真模型；不碰 `.env`、`~/.openclaw-easel`、浏览器登录目录、真实 `outputs/`。
- 真发只在用户同意的范围内：TikTok 图文（仅自己可见）、X 图文 + 纯文字、Instagram 图文、Threads 图文 + 纯文字（公开，用户自己删）。文案 `Easel test post — please ignore #easeltest`。
- 结果待确认（unknown）= 退出码 5，不重试、不记日历；最终发布按钮一律 `drv.commit(...)`，点之前先 `wait_enabled`。
- YouTube 保持不开放（`READY_KINDS = frozenset()`）。
- 提交前缀 `feat/fix/docs/chore/polish`，中文说明；提交末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 本地跑全量：`python -m pytest`、两个 validator、两个 selftest、前端 `vitest` / `build` / `lint`。

## 真机校准（2026-10-01，只读，已获同意）

| 平台 | 图文 | 纯文字 | 话题联想框 |
|---|---|---|---|
| X | `/compose/post` 弹窗，`fileInput` 可多选（≤4），每张图一个 `[aria-label="Remove media"]`，Post 可点 | 同一弹窗只输文字，Post 可点 | `role=listbox`，第一项默认选中（回车会换成联想的标签）；补空格即收 |
| Threads | 首页「What's new?」弹窗，文件框可多选，预览是 `img[src^="blob:"]`，Post 可点 | 同一弹窗只输文字 | `ul role=listbox`「Tag new topic」；补空格**不收**，按 Esc 只收联想框、弹窗还在；回车会把标签变成话题并从正文拿掉 |
| Instagram | New post → 选多张 → Crop → Next → Edit → Next → 写说明 → Share（无 Reels 提示） | 不支持 | 普通列表（非 listbox）；补空格即收 |
| TikTok | `/tiktokstudio/upload?tab=photo`，`input[accept*="image"]` 可多选，进 `/upload/post/photo`；每张图一个 `button[aria-label="Delete photo"]`；说明框同视频（无预填）；可见范围同视频；Post 按钮**没有** `data-e2e`，用 `button:has(:text-is("Post"))`（唯一） | 不支持 | `role=option`「#tag Add」；补空格即收 |

校准时上传过的图片都没保存草稿；TikTok 作品管理里只有第二期那条视频。

## Review Focus

1. 某行以话题标签结尾、下面还有一行：不能被联想框换成别的标签，也不能丢换行（Task 1 driver 测试）。
2. X 纯文字在加权 280 边上、且以话题结尾：补的空格也要计入，超限在开浏览器前就报退出码 2（Task 1 post 测试）。
3. 多张图只挂上了一部分：不能去点发布，报 StepFailed（Task 2/3/5 的 `wait_count` 测试）。
4. YouTube 仍拒绝一切形式；Web 端 YouTube 带图片返回 400（Task 6）。
5. Web 端 X / Threads 纯文字不带 `--media` 也能走到脚本；TikTok / Instagram / YouTube 不带媒体返回 400（Task 6）。

---

### Task 1: 打字安全与媒体计数（底座）

**Files:**
- Modify: `skills/shared/scripts/overseas/post.py`
- Modify: `skills/shared/scripts/overseas/base.py`
- Test: `tests/test_overseas_post.py`, `tests/test_overseas_driver.py`, `tests/test_overseas_flows.py`（FakeDriver）

**Interfaces:**
- Produces: `post.TAG_AT_LINE_END`、`post.typed_extra(text) -> int`；`PageDriver.wait_count(sel, n, timeout_ms=120000) -> bool`；`PageDriver.type_text` 新行为；FakeDriver 新增 `counts: dict[str, int]` 与 `wait_count`。

- [ ] **Step 1: 写失败测试**

`tests/test_overseas_post.py` 追加：

```python
def test_typed_extra_counts_lines_ending_in_tag_or_mention():
    assert post_mod.typed_extra("Hello #ai\nworld") == 1
    assert post_mod.typed_extra("Hello\n\n#ai #tech") == 1
    assert post_mod.typed_extra("ping @bob\n#x\nend") == 2
    assert post_mod.typed_extra("no tags here") == 0


def test_validate_counts_space_typed_after_trailing_tag():
    """打字时以话题结尾的行会补一个空格收联想框：X 卡在 280 的文案要提前报超限（Review Focus 2）。"""
    text = "a" * 276 + " #ai"            # 280
    with pytest.raises(PostError, match="280"):
        validate(Post(desc=text), name="X", kinds={"text"}, limits=Limits(caption=280, weighted=True))
```

`tests/test_overseas_driver.py` 追加：

```python
def test_type_text_closes_tag_suggestions_before_next_line():
    """以话题结尾的行：先补空格（X / Instagram / TikTok 的联想框就收了），联想框还开着（Threads）再按 Esc，然后才回车（Review Focus 1）。"""
    page = FakePWPage()
    page.present.update({"#box", '[role="listbox"]'})
    drv_for(page).type_text("#box", "Hi #ai\nBye", clear=False)
    assert page.keyboard.events == [("type", "Hi #ai"), ("type", " "), ("press", "Escape"),
                                    ("press", "Enter"), ("type", "Bye"), ("press", "Escape")]


def test_type_text_never_presses_escape_without_suggestions():
    page = FakePWPage()
    page.present.add("#box")
    drv_for(page).type_text("#box", "Hi #ai", clear=False)
    assert page.keyboard.events == [("type", "Hi #ai"), ("type", " ")]


def test_wait_count_waits_for_n_matches():
    page = FakePWPage()
    page.counts = {"img.preview": 1}
    assert drv_for(page).wait_count("img.preview", 2, timeout_ms=1500) is False
    page.counts["img.preview"] = 2
    assert drv_for(page).wait_count("img.preview", 2, timeout_ms=1500) is True
```

`FakePWPage` 加 `self.counts: dict = {}`，`FakeLocator.count()` 改为 `return self.page.counts.get(self.sel, 1 if self.sel in self.page.present else 0)`。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_overseas_post.py tests/test_overseas_driver.py -q`
Expected: FAIL（`typed_extra` / `wait_count` 不存在，键盘事件不含补空格）

- [ ] **Step 3: 实现**

`post.py`：

```python
# 行尾是话题 / @：打字时补一个空格把联想框收掉（见 PageDriver.type_text），校验字数时也要算上
TAG_AT_LINE_END = re.compile(r"[#@][^\s#@]+$")


def typed_extra(text: str) -> int:
    return sum(1 for line in text.split("\n") if TAG_AT_LINE_END.search(line))
```

`validate` 里 `n = (x_weighted_length(body) if limits.weighted else len(body)) + typed_extra(body)`。

`base.py`：`from .post import TAG_AT_LINE_END`；`SUGGESTIONS = '[role="listbox"]'`；

```python
    def type_text(self, sel, text, *, clear=True, timeout_ms=15000):
        self.click(sel, timeout_ms)
        kb = self.page.keyboard
        if clear:
            ...
        for i, line in enumerate(text.split("\n")):
            if i:
                kb.press("Enter")
            if line:
                kb.type(line, delay=random.randint(15, 45))
            if TAG_AT_LINE_END.search(line):
                kb.type(" ")                 # 话题 / @ 联想框：X、Instagram、TikTok 打空格就收
            if self.visible(SUGGESTIONS):
                kb.press("Escape")           # Threads 的话题框打空格不收；Esc 只收联想框，不关发帖弹窗
        self._rest()

    def wait_count(self, sel, n, timeout_ms=120000):
        """等页面上至少有 n 个匹配（多张图的预览都挂上了）。"""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self.count(sel) >= n:
                return True
            if time.monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(500)
```

`tests/test_overseas_flows.py` 的 `FakeDriver`：`__init__` 加 `counts=None` → `self.counts = dict(counts or {})`；`count(sel)` 返回 `self.counts.get(sel, 1 if sel in self.visible_set else 0)`；新增

```python
    def wait_count(self, sel, n, timeout_ms=120000):
        self._do("wait_count", sel, n)
        return self.count(sel) >= n
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_overseas_post.py tests/test_overseas_driver.py tests/test_overseas_flows.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add skills/shared/scripts/overseas/post.py skills/shared/scripts/overseas/base.py tests/test_overseas_post.py tests/test_overseas_driver.py tests/test_overseas_flows.py
git commit -m "feat(overseas): 打字时收起话题联想框，等多张图预览都挂上"
```

### Task 2: X 图文与纯文字

**Files:**
- Modify: `skills/shared/scripts/overseas/x.py`
- Test: `tests/test_overseas_flows.py`

**Interfaces:**
- Consumes: Task 1 `wait_count`、FakeDriver `counts`
- Produces: `x.READY_KINDS = {"video","image","text"}`、`x.MEDIA_WAIT_MS`、`x.TEXT_WAIT_MS`

- [ ] **Step 1: 写失败测试**

```python
def test_x_publishes_images_after_every_preview_attached():
    d = x_driver()
    d.hooks[("upload", X.FILE_INPUT)] = lambda dr: dr.counts.__setitem__(X.MEDIA_READY, 2)
    p = Post(media=[IMG, IMG2], desc="Hello")
    assert X.publish(d, X.compose(p), p).status == "success"
    assert ("wait_count", X.MEDIA_READY, 2) in d.actions


def test_x_partial_image_attach_never_posts():
    """2 张图只挂上 1 张：不去点发布（Review Focus 3）。"""
    d = x_driver()
    d.hooks[("upload", X.FILE_INPUT)] = lambda dr: dr.counts.__setitem__(X.MEDIA_READY, 1)
    p = Post(media=[IMG, IMG2], desc="Hello")
    with pytest.raises(base.StepFailed, match="图片没全挂上"):
        X.publish(d, X.compose(p), p)
    assert not d.committed


def test_x_text_only_post_skips_upload():
    d = x_driver()
    p = Post(desc="Just text #ai")
    assert X.publish(d, X.compose(p), p).status == "success"
    assert not d.acts("upload") and d.acts("type")[0][2] == "Just text #ai"
    assert X.READY_KINDS == {"video", "image", "text"}
```

`IMG` / `IMG2` 为 `tests/test_overseas_flows.py` 顶部新增的假路径常量（`Path("/tmp/a.jpg")`、`Path("/tmp/b.png")`，流程测试不读文件）。删掉 `test_registry_publish_contract` 里 `READY_KINDS == {"video"}` 那行。

- [ ] **Step 2: 跑测试确认失败** — `.venv/bin/python -m pytest tests/test_overseas_flows.py -q -k x_` → FAIL
- [ ] **Step 3: 实现**

```python
READY_KINDS = frozenset({"video", "image", "text"})
MEDIA_WAIT_MS = 120000                    # 视频 / 图片挂上的最长等待
TEXT_WAIT_MS = 30000                      # 纯文字：发布按钮该立刻能点


def publish(drv, fields, post):
    drv.goto(PUBLISH_URL)
    if not drv.wait_for(TEXTBOX, 30000):
        raise base.StepFailed("没打开发帖框")
    if post.media:
        drv.upload(FILE_INPUT, post.media)
        if not drv.wait_count(MEDIA_READY, len(post.media), MEDIA_WAIT_MS):
            raise base.StepFailed("视频没挂上（没出现 Remove media）" if post.kind == "video"
                                  else f"图片没全挂上（{len(post.media)} 张里没全出现 Remove media）")
    drv.type_text(TEXTBOX, fields["caption"])
    if not drv.wait_enabled(POST_BUTTON, PROCESS_WAIT_MS if post.media else TEXT_WAIT_MS):
        raise base.StepFailed("视频处理超时，发布按钮一直不能点" if post.media else "发布按钮一直不能点（文案可能超长）")
    drv.commit(POST_BUTTON)
    ...（toast 循环不变）
```

- [ ] **Step 4: 跑测试确认通过** — 同上 → PASS
- [ ] **Step 5: 提交** — `feat(overseas): X 接通图文（≤4 张）和纯文字`

### Task 3: Threads 图文与纯文字

**Files:** Modify `skills/shared/scripts/overseas/threads.py`；Test `tests/test_overseas_flows.py`

**Interfaces:** Produces `threads.READY_KINDS = {"video","image","text"}`、`threads.MEDIA_READY: dict[str, str]`（video / image）、`threads.TEXT_WAIT_MS`

- [ ] **Step 1: 写失败测试**

```python
def test_threads_publishes_images():
    d = threads_driver()
    d.hooks[("upload", TH.FILE_INPUT)] = lambda dr: dr.counts.__setitem__(TH.MEDIA_READY["image"], 2)
    p = Post(media=[IMG, IMG2], desc="Hello")
    assert TH.publish(d, TH.compose(p), p).status == "success"
    assert ("wait_count", TH.MEDIA_READY["image"], 2) in d.actions


def test_threads_partial_image_attach_never_posts():
    d = threads_driver()
    d.hooks[("upload", TH.FILE_INPUT)] = lambda dr: dr.counts.__setitem__(TH.MEDIA_READY["image"], 1)
    p = Post(media=[IMG, IMG2], desc="Hello")
    with pytest.raises(base.StepFailed, match="图片没全挂上"):
        TH.publish(d, TH.compose(p), p)
    assert not d.committed


def test_threads_text_only_post():
    d = threads_driver()
    p = Post(desc="Just text")
    assert TH.publish(d, TH.compose(p), p).status == "success"
    assert not d.acts("upload") and TH.READY_KINDS == {"video", "image", "text"}
```

`threads_driver` 改成打开弹窗时就让 `POST_BUTTON` 可见（纯文字不上传也要能点），上传钩子改用 `TH.MEDIA_READY["video"]`；删掉 `test_threads_publishes_video` 里 `READY_KINDS == {"video"}`。

- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**

```python
READY_KINDS = frozenset({"video", "image", "text"})
MEDIA_READY = {"video": f'{DIALOG} video', "image": f'{DIALOG} img[src^="blob:"]'}
MEDIA_WAIT_MS = 120000
TEXT_WAIT_MS = 30000

    if post.media:
        drv.upload(FILE_INPUT, post.media)
        if not drv.wait_count(MEDIA_READY[post.kind], len(post.media), MEDIA_WAIT_MS):
            raise base.StepFailed("视频没挂上（弹窗里没出现视频预览）" if post.kind == "video"
                                  else f"图片没全挂上（{len(post.media)} 张里没全出现预览）")
    drv.type_text(TEXTBOX, fields["caption"], clear=False)
    if not drv.wait_enabled(POST_BUTTON, PROCESS_WAIT_MS if post.media else TEXT_WAIT_MS):
        raise base.StepFailed("视频处理超时，发布按钮一直不能点" if post.media else "发布按钮一直不能点（文案可能超长）")
```

- [ ] **Step 4: 确认通过** → PASS
- [ ] **Step 5: 提交** — `feat(overseas): Threads 接通图文（≤10 张）和纯文字`

### Task 4: Instagram 图文

**Files:** Modify `skills/shared/scripts/overseas/instagram.py`；Test `tests/test_overseas_flows.py`

**Interfaces:** Produces `instagram.READY_KINDS = {"video","image"}`

- [ ] **Step 1: 写失败测试**

```python
def test_instagram_publishes_carousel_without_reel_notice():
    d = ig_driver(reel_notice=False)
    d.hooks[("click", IG.SHARE)] = lambda dr: dr.texts.__setitem__(IG.DIALOG, "Post shared\nYour post has been shared.")
    p = Post(media=[IMG, IMG2], desc="Hello")
    assert IG.publish(d, IG.compose(p), p).status == "success"
    assert ("wait_for", IG.REEL_OK) not in d.actions       # 图片没有 Reels 提示，别白等 8 秒
    assert d.acts("upload")[0][2] == (str(IMG), str(IMG2))
    assert IG.READY_KINDS == {"video", "image"}
```

删掉 `test_instagram_publishes_reel_through_crop_and_edit` 里的 `READY_KINDS == {"video"}`。

- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现** — `READY_KINDS = frozenset({"video", "image"})`；`if post.kind == "video" and drv.wait_for(REEL_OK, 8000): drv.click(REEL_OK)`。
- [ ] **Step 4: 确认通过** → PASS
- [ ] **Step 5: 提交** — `feat(overseas): Instagram 接通图文（≤10 张）`

### Task 5: TikTok 图文

**Files:** Modify `skills/shared/scripts/overseas/tiktok.py`；Test `tests/test_overseas_flows.py`

**Interfaces:** Produces `tiktok.READY_KINDS = {"video","image"}`、`PHOTO_URL`、`PHOTO_INPUT`、`PHOTO_READY`、`PHOTO_POST_BUTTON`

- [ ] **Step 1: 写失败测试**

```python
def tiktok_photo_driver(n=2):
    d = FakeDriver(visible={TT.PHOTO_INPUT, TT.CAPTION, TT.VISIBILITY_BUTTON, TT.PHOTO_POST_BUTTON},
                   enabled={TT.PHOTO_POST_BUTTON})
    d.hooks[("upload", TT.PHOTO_INPUT)] = lambda dr: dr.counts.__setitem__(TT.PHOTO_READY, n)
    d.hooks[("click", TT.VISIBILITY_BUTTON)] = lambda dr: dr.visible_set.update(
        {TT.option(v) for v in TT.VISIBILITY_LABEL.values()})
    d.hooks[("click", TT.PHOTO_POST_BUTTON)] = lambda dr: setattr(dr, "_url", "https://www.tiktok.com/tiktokstudio/content")
    return d


def test_tiktok_publishes_photos_on_photo_tab():
    d = tiktok_photo_driver()
    p = Post(media=[IMG, IMG2], desc="Hello", visibility="only_me")
    assert TT.publish(d, TT.compose(p), p).status == "success"
    assert d.acts("goto")[0][1] == TT.PHOTO_URL
    assert d.acts("commit") == [("commit", TT.PHOTO_POST_BUTTON)]
    assert TT.option("Only you") in [a[1] for a in d.acts("click")]
    assert TT.READY_KINDS == {"video", "image"}


def test_tiktok_photos_not_all_uploaded_never_posts():
    d = tiktok_photo_driver(n=1)
    p = Post(media=[IMG, IMG2], desc="Hello")
    with pytest.raises(base.StepFailed, match="图片上传超时"):
        TT.publish(d, TT.compose(p), p)
    assert not d.committed
```

删掉 `test_tiktok_publishes_with_visibility` 里的 `READY_KINDS == {"video"}`。

- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**

```python
READY_KINDS = frozenset({"video", "image"})
PHOTO_URL = "https://www.tiktok.com/tiktokstudio/upload?tab=photo"
PHOTO_INPUT = 'input[type="file"][accept*="image"]'
PHOTO_READY = 'button[aria-label="Delete photo"]'          # 每张图一个
PHOTO_POST_BUTTON = 'button:has(:text-is("Post"))'          # 图文页的 Post 没有 data-e2e；页面上唯一


def publish(drv, fields, post):
    if post.kind == "image":
        return _publish_photos(drv, fields, post)
    ...（视频流程不变，写说明到点发布抽成 _fill_and_post，发布后的等待抽成 _await_posted）


def _publish_photos(drv, fields, post):
    drv.goto(PHOTO_URL)
    if not drv.wait_for(PHOTO_INPUT, 30000, state="attached"):
        raise base.StepFailed("图文上传页没打开（找不到选择图片）")
    drv.upload(PHOTO_INPUT, post.media)
    if not drv.wait_count(PHOTO_READY, len(post.media), UPLOAD_WAIT_S * 1000):
        raise base.StepFailed("图片上传超时（不是每张都出现了删除按钮）")
    _fill_and_post(drv, fields, PHOTO_POST_BUTTON)
    return _await_posted(drv)
```

- [ ] **Step 4: 确认通过** → PASS（含原有视频测试）
- [ ] **Step 5: 提交** — `feat(overseas): TikTok 接通图文（网页版 Photos）`

### Task 6: 发布器与 Web 放开

**Files:** Modify `skills/shared/scripts/overseas_publisher.py`、`web/app.py`；Test `tests/test_overseas_publish.py`、`tests/test_overseas_web.py`

**Interfaces:** Produces `web.MEDIA_REQUIRED`、`web.VIDEO_ONLY_PUBLISH` 新取值

- [ ] **Step 1: 写失败测试**

`test_overseas_publish.py`：把 `test_kind_not_ready_yet_is_exit_2` 换成

```python
def test_kind_not_ready_yet_is_rejected(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8")
    mod = SimpleNamespace(NAME="Demo", KINDS=frozenset({"video", "image"}), READY_KINDS=frozenset({"video"}),
                          LIMITS=Limits(caption=100, images=4), VISIBILITY=())
    with pytest.raises(PostError, match="Demo 的图文发布还没接通"):
        op.check_publishable(mod, Post(media=[img], desc="hi"))


def test_text_only_dry_run_on_x(monkeypatch, capsys):
    assert cli(monkeypatch, "--platform", "x", "--desc", "just text") == 0
    assert '"kind": "text"' in capsys.readouterr().out
```

`test_overseas_web.py`：把 `test_publish_overseas_requires_video_for_now` 换成

```python
def test_publish_overseas_media_rules(monkeypatch, tmp_path):
    """X / Threads 可纯文字；TikTok / Instagram / YouTube 要媒体；只有 YouTube 只收视频（Review Focus 4、5）。"""
    _outputs_with(tmp_path, monkeypatch, "a.png", b"\x89PNG")
    started = []
    monkeypatch.setattr(web, "_start_async_publish", lambda platform, cmd, *a: started.append((platform, cmd)) or {"async": True})
    for platform in ("x", "threads"):
        asyncio.run(web.api_publish(platform, web.PublishRequest(body="hi")))
    assert [p for p, _ in started] == ["x", "threads"] and all("--media" not in c for _, c in started)
    for platform in ("tiktok", "instagram", "youtube"):
        with pytest.raises(web.HTTPException) as ei:
            asyncio.run(web.api_publish(platform, web.PublishRequest(body="hi")))
        assert ei.value.status_code == 400
    asyncio.run(web.api_publish("instagram", web.PublishRequest(body="hi", media=["proj/a.png"])))
    assert started[-1][0] == "instagram" and "--media" in started[-1][1]
    with pytest.raises(web.HTTPException) as ei:
        asyncio.run(web.api_publish("youtube", web.PublishRequest(title="T", body="hi", media=["proj/a.png"])))
    assert ei.value.status_code == 400
```

- [ ] **Step 2: 确认失败** → FAIL
- [ ] **Step 3: 实现**

`overseas_publisher.check_publishable`：`raise PostError(f"{mod.NAME} 的{KIND_LABEL[post.kind]}发布还没接通")`（去掉「目前只能发视频」）。

`web/app.py`：

```python
OVERSEAS_PUBLISH = {"tiktok", "youtube", "instagram", "x", "threads"}
# 海外平台：X / Threads 可以纯文字，其余要带媒体；只收视频的只有 YouTube
MEDIA_REQUIRED = {"xiaohongshu", "douyin", "kuaishou", "weixin-channels", "bilibili", "tiktok", "youtube", "instagram"}
VIDEO_ONLY_PUBLISH = {"douyin", "weixin-channels", "bilibili", "youtube"}
```

- [ ] **Step 4: 确认通过** → PASS
- [ ] **Step 5: 提交** — `feat(publish): 海外平台放开图文与纯文字（YouTube 仍只收视频）`

### Task 7: 发布中心前端

**Files:** Modify `web/frontend/src/lib/overseasPublish.ts`、`web/frontend/src/components/PublishPage.tsx`；Test `web/frontend/src/lib/overseasPublish.test.ts`

**Interfaces:** Produces `OverseasPlatform.mediaRequired: boolean`、`OverseasPlatform.videoOnly: boolean`、`OVERSEAS_MEDIA_REQUIRED: string[]`、`OVERSEAS_VIDEO_ONLY: string[]`

- [ ] **Step 1: 写失败测试**

```ts
  it('媒体要求与后端一致：X / Threads 可纯文字，只有 YouTube 只收视频', () => {
    expect(OVERSEAS_MEDIA_REQUIRED).toEqual(['tiktok', 'youtube', 'instagram']);
    expect(OVERSEAS_VIDEO_ONLY).toEqual(['youtube']);
    expect(OVERSEAS_PLATFORMS.find((p) => p.key === 'x')!.hint).toContain('纯文字');
  });
```

- [ ] **Step 2: 确认失败** — `cd web/frontend && npx vitest run src/lib/overseasPublish.test.ts` → FAIL
- [ ] **Step 3: 实现** — 每个平台加 `mediaRequired` / `videoOnly`，hint 改为：
  - TikTok：`英文说明≤2200，附 1 个视频或 ≤35 张图`
  - YouTube：原文不变（仍需视频）
  - Instagram：`英文说明≤2200、话题≤30，视频发成 Reels，或 ≤10 张图`
  - X：`英文≤280（中日韩文字算 2），可附 1 个视频或 ≤4 张图，也可纯文字`
  - Threads：`英文≤500，话题只能 1 个，可附 1 个视频或 ≤10 张图，也可纯文字`

  导出 `OVERSEAS_MEDIA_REQUIRED` / `OVERSEAS_VIDEO_ONLY`；`PublishPage.tsx` 的 `MEDIA_REQUIRED` / `VIDEO_ONLY` 改用它们，媒体区提示改成「小红书/抖音/快手/视频号/B站/TikTok/Instagram/YouTube 必需；抖音、视频号、B站、YouTube 须为视频；X、Threads 可纯文字」。
- [ ] **Step 4: 确认通过** — `npx vitest run` 全部 → PASS
- [ ] **Step 5: 提交** — `feat(publish): 发布中心海外平台支持图文与纯文字`

### Task 8: 技能文档与路由登记

**Files:** Modify `skills/openclaw/skill-overseas-publish/SKILL.md`、`skills/openclaw/skill-overseas-publish/references/platforms.md`、`skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py`

- [ ] **Step 1: 写失败的 selftest 断言** — `publish_dispatch.py` selftest 加：

```python
    assert PLATFORMS["x"]["types"] == ["video", "image", "text"] and PLATFORMS["threads"]["types"] == ["video", "image", "text"]
    assert PLATFORMS["tiktok"]["types"] == ["video", "image"] and PLATFORMS["instagram"]["types"] == ["video", "image"]
    assert PLATFORMS["youtube"]["types"] == ["video"]
```

- [ ] **Step 2: 确认失败** — `python skills/openclaw/skill-cross-platform-publish/scripts/publish_dispatch.py selftest` → AssertionError
- [ ] **Step 3: 实现** — 改 `types` 与 `note`；SKILL.md 的描述与提示改成「视频 / 图文 / 纯文字」，命令加一条图文、一条纯文字示例：

```bash
python skills/shared/scripts/overseas_publisher.py publish --platform instagram --media outputs/项目/1.jpg --media outputs/项目/2.jpg --desc "English caption"
python skills/shared/scripts/overseas_publisher.py publish --platform x --desc "English text post #ai"
```

  platforms.md 的「已接通」列与校准记录同步（含话题联想框结论、Threads 的话题保留为正文文字而非「话题」）。
- [ ] **Step 4: 确认通过** — selftest + `validate_skills.py` + `validate_skill_commands.py` → OK
- [ ] **Step 5: 提交** — `docs(overseas): 技能说明与跨平台路由登记图文、纯文字`

### Task 9: 真机测试发帖（已获同意）

- [ ] **Step 1:** 用 `overseas_publisher.py publish --exec`（CWD=worktree 根），文案 `Easel test post — please ignore #easeltest`，依次：TikTok 图文 2 张 `--visibility only_me`；X 图文 2 张；X 纯文字；Instagram 图文 2 张；Threads 图文 2 张；Threads 纯文字。每条看退出码和状态文件，成功则记链接。
- [ ] **Step 2:** 失败时按 `outputs/_login/<平台>-publish-fail.*` 修选择器：点发布前失败（没发出去）→ 修后重试同一条；退出码 5 → 不重发，先去平台核对。
- [ ] **Step 3:** platforms.md 追加真发结果；提交 `fix(overseas): 真机测试图文 / 纯文字发布，记录结果`（有修正时）或 `docs(overseas): 记录图文 / 纯文字真发结果`。

### Task 10: 终审与合并

- [ ] **Step 1:** 全量验证（pytest、两个 validator、两个 selftest、前端 test / build / lint）。
- [ ] **Step 2:** review-package → 独立审查（sonnet，只读）→ 按 executing-plans 终审流程修正。
- [ ] **Step 3:** push `feat/overseas-image-text` → PR → merge；清理 worktree 与分支；main `git pull --ff-only` 并重建前端；运行 `bash openclaw/sync.sh`（用户已授权）。
