# 海外平台发布设计：TikTok / YouTube / Instagram / X / Threads

- 日期：2026-10-01
- 范围：新增海外平台的登录、登录态校验、发布（视频 / 图文 / 纯文字），接入账号页、发布中心、对话
- 状态：设计已在对话中逐段确认，待评审本规格

## 1. 背景与目标

发布层只覆盖国内平台。上游 PR ZJU-REAL/Easel#74 走 Upload-Post 第三方付费服务（免费版每月 10 次，TikTok 要付费版），合并后已撤回（#9、#10）。改为自建：在本机用浏览器自动化发到自己的账号，不依赖任何付费聚合服务。

不用各平台官方 API 的原因（2026-10 调研）：

| 平台 | 官方 API 的卡点 |
|---|---|
| TikTok | 应用未过审核只能发「仅自己可见」，审核面向公司应用 |
| YouTube | 未过合规审核的项目，上传一律锁成私享 |
| Instagram | 媒体必须放在公网 URL；要专业账号 |
| Threads | 媒体必须放在公网 URL |
| X | 2026-02 起无免费层，按条付费 |

用户已确认的决策：

| 决策项 | 结论 |
|---|---|
| 技术路线 | 浏览器自动化（Playwright + 持久化登录目录），与国内平台同一套思路 |
| 平台范围 | TikTok、YouTube、Instagram、X、Threads 一期全做 |
| 内容形式 | 短视频、图文、纯文字（按平台能力取交集，见第 5 节） |
| 文案语言 | 对话里由智能体按平台规则改写成英文；发布中心可手动改 |
| 架构 | 新建海外发布器 + 每平台一个小模块，不改国内平台代码（方案 A） |
| 登录方式 | 账号页弹出本机 Chrome 窗口，用户亲手登录（含两步验证） |
| 交付 | 3 个 PR：底座与登录 → 视频发布与接入 → 图文与纯文字 |

非目标：
- 不做海外平台的创作数据（`ANALYTICS_PLATFORMS` 不加）、定时发布、评论互动。
- 不接任何官方 API 或第三方聚合服务；以后某平台审核通过了再单独评估。
- 发布中心不做「一键改写成英文」；改写只在对话里由智能体完成。
- 不改国内平台的登录、发布、代理行为。

## 2. 总体结构

```
skills/shared/scripts/
  overseas_publisher.py      命令行入口：login / whoami / publish / platforms / selftest
  overseas/
    __init__.py              PLATFORMS 注册表：平台码 → 模块
    base.py                  浏览器底座：启动、登录目录、代理、等待落定、人类节奏、失败现场
    post.py                  Post 数据结构、文案拼接、字数/标签校验（纯函数，不碰浏览器）
    tiktok.py  youtube.py  instagram.py  x.py  threads.py
skills/openclaw/skill-overseas-publish/
  SKILL.md                   何时用、英文改写规则、预览 → 确认 → --exec 流程、待确认处理
  EASEL-META.md
  references/<平台>.md       各平台注意事项（页面形态、限制、真机校准记录）
```

平台码：`tiktok`、`youtube`、`instagram`、`x`、`threads`。显示名：TikTok、YouTube、Instagram、X、Threads。

`overseas_publisher.py` 与现有共享脚本一样从项目根目录运行（`python skills/shared/scripts/overseas_publisher.py ...`），测试里以模块名导入。

### 2.1 平台模块接口

每个平台模块实现同一组成员（`base.py` 里定义协议，`selftest` 校验齐全）：

| 成员 | 说明 |
|---|---|
| `KEY`、`NAME`、`PROFILE` | 平台码、显示名、登录目录名 |
| `HOME_URL`、`LOGIN_URL` | 首页（whoami 用）、登录页 |
| `KINDS` | 支持的形式子集：`{"video", "image", "text"}` |
| `LIMITS` | 文案上限、标签上限、图片张数上限、视频数上限 |
| `is_logged_in(page) -> bool` | 只读判断：URL 不在登录页 + 已登录元素可见 |
| `read_identity(page) -> dict` | `{"name", "avatar"}`，尽力而为 |
| `compose(post) -> dict` | 把 Post 拼成该平台要填的字段（见第 5 节） |
| `publish(page, fields, post) -> Result` | 在已登录的页面上执行发布，返回 `Result` |

`Result`：`status`（`success` / `failed` / `unknown`）、`url`（拿得到就填）、`message`。

### 2.2 登录目录

`~/.easel-browser-profiles/` 下：`TikTokProfile`、`YouTubeProfile`、`InstagramProfile`、`XProfile`、`ThreadsProfile`，与国内平台并列。Instagram 与 Threads 各用各的目录，避免两个进程同时写同一个目录。

## 3. 浏览器底座（`overseas/base.py`）

- **浏览器：** 优先 `channel="chrome"`（本机 Google Chrome，Google 登录只认它）；没装时退回 Playwright 自带 Chromium，并在输出里提示「YouTube 登录可能被 Google 拦截，建议安装 Chrome」。
- **启动参数：** 复用国内的反自动化标记（`--disable-blink-features=AutomationControlled` 等），**不加** `--no-proxy-server`。
- **代理：** 配了 `EASEL_PROXY` 就传给 Playwright 的 `proxy`；否则用系统网络设置（用户在日本，直连）。国内平台照旧直连，`web_publisher.py` 不动。
- **等待落定：** 打开页面后等客户端跳转稳定再判断登录态（同 `web_publisher._settle_login` 的思路）。
- **人类节奏：** 输入、点击之间加随机短停顿；文案逐段输入而非一次性注入（富文本框需要真实输入事件）。
- **失败现场：** 找不到元素或判定失败时，截图 + 保存 DOM 到 `outputs/_login/<平台>-publish-fail.png/.html`。

## 4. 登录与登录态

### 4.1 窗口登录（`overseas_publisher.py login`）

参数：`--platform`、`--status-file`、`--timeout`（默认 600 秒）。状态写 `login_state` JSON，与现有 runner 同格式，账号页轮询读取。

1. 启动**有头**浏览器，打开 `LOGIN_URL`，写 `window_login`，消息「已弹出 Chrome 窗口，请在窗口里登录 <平台>，不要关掉它」。
2. 每 2 秒检查 `is_logged_in`。若登录前已是登录态，直接走第 3 步。
3. 检测到登录 → 写 `verifying`（「登录成功，正在确认登录态已保存…」）→ 等 cookie 落盘 → 关浏览器。
4. 用**无头**浏览器重开同一目录，`is_logged_in` 为真且读到身份 → 写 `success`（消息为昵称）；否则写 `error`「登录看似成功但登录态没能保存，请重试」。
5. 窗口被关 → `error`「登录窗口被关掉了，登录没有完成」；超时 → `expired`；任何异常 → `error` 带原因。弹窗不会停在非终态。

账号页只在本机能弹窗口时提供海外登录（macOS / Windows / 有 `DISPLAY` 的 Linux）；否则按钮置灰并说明原因（复用 `_xhs_headed_fallback_available` 的判断思路，抽成通用函数）。

### 4.2 whoami 与退出

- `overseas_publisher.py whoami --platform P`：无头打开 `HOME_URL`，输出单行 JSON `{"loggedIn", "name", "avatar"}`；校验本身失败时带 `error` 字段（后端据此不删标记）。
- 后端 `_account_whoami` 新增 `overseas` 分支，沿用现有缓存、指纹、浏览器锁、「登录进行中不校验」逻辑。
- 退出：删该平台登录目录 + `outputs/_login/<平台>.*` 状态文件，与 `web` 后端一致。

### 4.3 账号页

- `LOGIN_RUNNERS` 新增 5 条：`{"name": ..., "backend": "overseas", "op": "<平台码>", "profile": "<目录名>", "region": "overseas"}`；国内条目补 `"region": "domestic"`。
- `/api/accounts` 透出 `region`；前端按「国内」「海外」两组渲染。
- `api_login_start` 的 `overseas` 分支调用 `overseas_publisher.py login`，超时用 `OVERSEAS_LOGIN_TIMEOUT = 600`（与 `LOGIN_TIMEOUT` 放在一起）。

## 5. 发布

### 5.1 平台能力与文案拼接

| 平台 | 视频 | 图文 | 纯文字 | 文案字段 | 上限 | 可见范围 |
|---|---|---|---|---|---|---|
| YouTube | 1 个（竖屏短视频自动成 Shorts） | — | — | 标题 = title；描述 = desc + 换行 + #标签 | 标题 ≤100，描述 ≤5000 | public / unlisted / private |
| TikTok | 1 个 | 图片轮播（网页版若不支持则报不支持） | — | 说明 = title + 换行 + desc + #标签 | ≤2200 | everyone / friends / only_me |
| Instagram | 1 个（Reels） | 1～10 张 | — | 说明同上 | ≤2200，标签 ≤30 | — |
| X | 1 个 | ≤4 张 | ✓ | 正文同上 | 加权 ≤280：CJK 字符计 2，URL 计 23 | — |
| Threads | 1 个 | ≤10 张 | ✓ | 正文同上 | ≤500 | — |

- `post.py` 的 `Post`：`kind`、`media`（Path 列表）、`title`、`desc`、`tags`、`visibility`。`kind` 由媒体推断：无媒体 = text，1 个视频 = video，1～N 张图 = image，混用报错。
- 标签：逗号 / 空格分隔，统一加 `#`，去重。
- 可见范围参数 `--visibility`：YouTube 默认 `public`，TikTok 默认 `everyone`；其它平台传了就报错。

### 5.2 发布流程（`overseas_publisher.py publish`）

参数：`--platform`、`--media`（可重复）、`--title`、`--desc`、`--tags`、`--visibility`、`--exec`、`--headed`、`--allow-unsafe`。

1. **校验，不开浏览器：** 平台存在、形式受支持、字数 / 标签 / 张数在上限内、媒体文件存在且**真实路径**后缀是图片或视频（防符号链接指向 `.env` 等）。不合格直接退出（码 2）。
2. **预览（默认）：** 打印该平台最终会填的字段，不开浏览器、不联网。
3. **`--exec`：**
   - `content_guard.guard_or_die`：title、desc、tags、媒体文件名都过闸门（检出密钥退出码 7）。
   - 无头打开发布页；未登录 → 退出码 6「<平台>未登录，请先在账号页登录」。
   - 遇到验证码 / 异常活动页：未加 `--headed` 时改为有头窗口重试一次并提示；仍被拦则失败退出。
   - 执行平台模块的 `publish`：上传 → 等处理完成 → 填文案 → 设可见范围 → 点发布 → 等明确的成功信号。
   - `success`：尽量取帖子链接，`calendar_ops.record_publish` 记日历，退出码 0。
   - `failed`：留失败现场，退出码 1。
   - `unknown`（已点发布但没等到成功信号）：退出码 5，提示「结果待确认，请先到平台查看，不要直接重发」，**不自动重试**，不记日历。
4. `calendar_ops.PLATFORM_NAMES` 补 5 个平台的显示名。

### 5.3 发布中心

- 平台选择分「国内」「海外」两组；海外 5 个平台显示字数上限和支持的形式（与 `post.py` 的 `LIMITS` 一致，前端常量 + 后端校验双保险）。
- YouTube、TikTok 多一个可见范围选择。
- 后端 `api_publish` 新增 `overseas` 分支：`overseas_publisher.py publish --exec ...`，走异步发布（`_start_async_publish`，同抖音），前端轮询进度。`MEDIA_REQUIRED` 加 tiktok / youtube / instagram；`VIDEO_ONLY_PUBLISH` 加 youtube；纯文字允许 x / threads。

### 5.4 对话

- 新技能 `skill-overseas-publish`（`layer: publish`）：识别「发 TikTok / YouTube / Instagram / X / Threads / 海外」；按 5.1 的上限把文案改写成英文；先跑预览给用户看，用户确认后才 `--exec`；退出码 5 时只引导用户去平台核对。
- `skill-cross-platform-publish` 的 `publish_dispatch.py` `PLATFORMS` 增加 5 个平台，`publisher` 指向 `skill-overseas-publish`，约束与 5.1 一致；selftest 补断言。
- `skill-my-account` 说明海外平台在账号页窗口登录。

### 5.5 登记

- `scripts/validate_skills.py` 的 `PUBLISH_SCRIPT_CONTRACTS` 加 `overseas_publisher.py`。
- `docs/skill-function-mapping.md`（技能数 +1）、`web/frontend/src/lib/skillDisplayNames.ts`、`capabilityMenu.ts`。
- `docs/known-issues.md`：海外平台页面改版、风控与 Google 登录需本机 Chrome 的说明。

## 6. 错误处理汇总

| 情况 | 行为 | 退出码 |
|---|---|---|
| 参数 / 字数 / 媒体类型不合格 | 开浏览器前退出，说明哪一项超限 | 2 |
| 缺 Playwright | 提示安装 | 3 |
| 发布结果未确认 | 提示去平台核对，不重试、不记日历 | 5 |
| 未登录 | 提示去账号页登录 | 6 |
| 文案含敏感信息 | 内容安全闸门拦下 | 7 |
| 页面元素找不到 / 发布失败 | 截图 + DOM，提示「页面可能改版」 | 1 |

## 7. 测试

离线（不起真浏览器、不连平台）：
- `post.py`：各平台拼接、字数（含 X 加权）、标签数、张数、形式推断、混用报错。
- 登录状态机（假 Playwright，参考 `tests/test_xhs_login.py`）：窗口登录 → 验证中 → 成功；关窗口、超时、没保存住、登录前已登录。
- 发布门禁：预览不开浏览器；`--exec` 前过闸门（含文件名）；符号链接指向非媒体被拒；未登录退出码 6；`unknown` 不重试、不记日历。
- 每个平台模块：用假页面走一遍 `publish` 的步骤顺序与成功 / 未确认判定。
- 网页后端：`LOGIN_RUNNERS` 海外条目、`api_login_start` / `_account_whoami` / `api_publish` 的命令拼装、`/api/accounts` 的 `region`、发布中心的校验集合。
- 前端：账号页分组、发布中心分组与可见范围选择。
- `overseas_publisher.py selftest`、`publish_dispatch.py selftest`、两个 validator。

真机（每一步先征得用户同意）：
1. 用户在账号页登录 5 个平台。
2. 只读校准：打开各平台发布页，走到点发布之前停下，核对元素。
3. 每个平台真发一条测试：YouTube 私享、TikTok 仅自己可见；X / Instagram / Threads 无私密发布，测试帖公开，可发后删除或延后。

## 8. 交付拆分

| PR | 内容 | 完成标准 |
|---|---|---|
| 1 底座与登录 | `overseas/base.py`、`post.py`、5 个模块的登录 / 身份部分、`overseas_publisher.py login/whoami/platforms/selftest`、账号页接入与分组 | 5 个平台都能在账号页登录、校验、退出 |
| 2 视频发布 | 5 个模块的视频发布、`publish` 命令、发布中心与对话接入、登记 | 5 个平台都能从发布中心和对话发视频 |
| 3 图文与纯文字 | 图文（TikTok 视网页版能力）、X / Threads 纯文字 | 各平台支持的形式都能发 |

## 9. 风险

- **页面改版：** 元素选择器集中在各平台模块里，失败留现场，便于快速修。
- **风控：** 自动发帖可能触发平台限制。缓解：本机 Chrome、持久登录、人类节奏、低频；被拦时改有头窗口让用户介入。
- **Google 登录：** 只认真实 Chrome；没装 Chrome 时 YouTube 登录大概率失败，已在提示里说明。
- **TikTok 网页版图文：** 网页版可能不支持发图片轮播，真机确认后若不支持，就在 `KINDS` 里去掉并在发布中心标注。
