---
name: skill-douyin-upload
description: |
  将视频/图文内容发布到抖音（creator.douyin.com）。**半自动**：脚本在可见的真实浏览器窗口里填好标题/简介/话题/
  封面/AI 声明，停在发布按钮前，由用户亲自点「发布」；带重复发布/冷却闸门。基于 Playwright + 持久化登录态，
  流程与选择器移植自开源实现 douyin-upload-mcp-skill。适用场景：发布抖音视频、发布图文、扫码登录、发布前预检。
layer: publish
---

# 抖音发布助手（douyin-upload）

在用户确认后，调用 `douyin_publish.py` 完成**视频/图文发布**。

## 运行方式（Playwright + 可见真实浏览器，半自动）

统一走 **`../../shared/scripts/douyin_publish.py`**（CWD=项目根）。浏览器由 `real_browser` 启动：**CloakBrowser
（账号固定指纹）优先 → 本机 Chrome/Edge → Playwright 自带 Chromium（告警）**；环境变量 `EASEL_DOUYIN_BROWSER=chrome`
跳过 Cloak，`EASEL_DOUYIN_HEADLESS=1` 才允许无头（仅限无桌面机器，易被识别，**发布始终开窗口**）。鼠标/键盘走
`human_input` 真人节奏。**login 与发布共用同一引擎/登录目录；换内核（如新装了 Cloak）后需重新扫码登录一次。**

| 依赖 | 说明 |
|------|------|
| playwright + 浏览器内核 | `douyin_publish.py check` 验证并显示实际用哪个内核 |
| 已扫码登录 | `login` 抠二维码成 PNG（默认 `outputs/_login/douyin.png`，Web「账号」页可扫）→ cookie 持久化到 `~/.easel-browser-profiles/DouyinProfile` |
| 干净网络 IP | 抖音对机房/代理 IP 更易触发风控短信墙（登录与**发布**都可能弹）。短信墙**可过**——脚本支持验证码回填（见「短信验证码处理」），无需家宽 IP；仍建议尽量用干净 IP 降低触发频率 |

## 能力范围

- **现做**：视频发布、图文发布、扫码登录、发布前预检（plan）。
- 话题：写进作品简介的 `#话题`（抖音自动联想成话题）。
- 视频发布含：上传等转码（≤5min）+ 选 AI 推荐封面 + 横/竖双封面。
- 发布页「自主声明 → 内容由AI生成」默认自动勾（`--no-ai-declare` 关闭，仅内容确非 AI 生成时）。
  **该选择器未在真机校准**：半自动下勾不上不报错，只在状态消息里提示用户手动勾；自动点击模式勾不上则退出 6。

## 风险提示

抖音投稿功能曾因脚本/AI 托管被封，现一律**半自动**：脚本只填表，**不替用户点发布**。无发布频率限制，
但有两道闸门（`publish_guard.py`）：**重复发布**（同媒体内容/同标题已发过 → 退出 8，仅当用户明确要求
重发同一内容才加 `--allow-repost`）与**冷却**（见下，退出 9）。风险不可完全消除。

## 执行流程

```
check（环境就绪？）
  → 未登录 → login（抠二维码，Web 账号页扫 或 CLI 扫）
  → plan（dry-run 预检：标题长度/媒体路径/步骤）— 给用户确认最终标题、简介、媒体
  → 发布前人设检查（见下）
  → publish / publish-video --exec（后台脱离启动 + 轮询状态，见下「半自动交接」）
  → 状态 awaiting_user_click：告诉用户「已在窗口里填好，请检查后亲自点『发布』」，然后继续轮询
  → 用户点发布 → 成功校验（脚本内置：**读回创作者中心作品列表对账**——标题+时间窗对上该作品才算 success）→ 记入发布台账
  → 发布后留痕（见下）
```

## 半自动交接（发布必读）

1. 后台脱离启动（`setsid … &`，带 `--status-file`，见下节第 1 步），轮询状态文件。
2. 脚本顺序：闸门 → 开窗口 → 上传/转码 → 封面 → 填标题/简介/话题 → 自主声明 → **停下**。状态文件 `state`：
   `starting` → **`awaiting_user_click`**（message 即给用户的话；若 AI 声明没勾上，message 里会带
   「请在窗口里手动勾选『自主声明 → 内容由AI生成』」）→ `success` / `error`。
3. 读到 `awaiting_user_click`：**必须把 message 转述给用户**，让其在窗口里检查并亲自点「发布」；你**不得**设置
   `EASEL_DOMESTIC_AUTO_PUBLISH`、不得建议用户设它「省事」（它是用户自己的逃生口，开了才会脚本点发布）。
   默认最多等 `--handoff-timeout 3600` 秒；用户若在窗口里遇到短信墙，由用户自己在窗口里处理。
4. 结局：用户点发布并读回对账通过 → `success`；窗口被关/超时 → `error`「未发布：窗口已关闭/等待超时」，退出 5，
   **不要自动重试**，让用户去内容管理页核对；平台弹处罚提示 → 自动设冷却并退出 9。

### 退出码

| 码 | 含义 | 你该做什么 |
|----|------|-----------|
| 0 | 发布成功（读回核验） | 发布后留痕 |
| 5 | 发布未确认 / 窗口已关 / 等待超时 / 读回没对上 | 告知用户去内容管理页核对，不要重试 |
| 6 | 自动点击模式下 AI 声明没勾上；或读回时登录态失效 | 告知用户，必要时重新登录 |
| 8 | 重复发布（同内容/同标题已发过） | 告知用户并停止；用户明确要求重发才加 `--allow-repost` |
| 9 | 冷却中 / 平台返回处罚提示（已自动设冷却） | **立即停止、不重试、不换方式绕过**，向用户汇报并去平台消息中心查看 |

### 冷却

冷却（`outputs/_publish/cooldown.json`）**只有用户能解除**：用户在对话里明确说要解除时才可执行
`python skills/shared/scripts/publish_guard.py cooldown clear douyin`；查看状态 `publish_guard.py status`。

## 短信验证码处理（仅自动点击逃生口 / 旧流程）

> 半自动下短信墙由用户在窗口里自己过，本节不适用；以下仅当用户自己开了 `EASEL_DOMESTIC_AUTO_PUBLISH=1` 时才会走到。

抖音发布点「发布」后可能弹**风控短信墙**（提示『接收短信验证码』）。脚本已内置完整过墙能力（`_handle_publish_sms`：下发验证码 → 轮询码文件 → 填码提交，最多等 300s，可多次重输），**但对话页里 agent 必须主动把验证码递进去**——否则脚本会空等 300s 超时失败。

要码有两种姿势，**先探测本部署支持哪种**：

```bash
printenv EASEL_ASKUSER_CARDS   # "1"=支持选项卡片(OpenClaw 2026.9.x)；"0"/空=不支持(如 2026.6.11)
```

- `=="1"` → 走 **A. 卡片模式**（同轮弹卡、当场拿码，体验最好）。
- `=="0"` 或空 → 走 **B. 文字等待模式**（发文字要码 → **结束本轮** → 用户下一条消息回码 → 你写码文件）。**2026.6.11 必须用这条**，卡片在这版桥接不了、弹了也收不到答案。

无论哪种，前两步（后台启动 + 轮询）完全一样。

### 第 1 步：**后台脱离**启动发布（关键：必须能跨对话轮存活）

务必带 `--status-file` 和 `--sms-code-file`（路径放 `outputs/_login/` 下），并用 `setsid`+`&`+日志重定向**把进程脱离当前 shell**——否则本轮结束、openclaw 进程退出时会把它一起杀掉，文字等待模式就跨不了轮：

```bash
mkdir -p outputs/_login
setsid python skills/shared/scripts/douyin_publish.py publish-video --exec --no-proxy \
  --title "标题" --content "简介" --video /abs/v.mp4 --tags "旅行,攻略" \
  --status-file outputs/_login/douyin.publish.json \
  --sms-code-file outputs/_login/douyin.code \
  > outputs/_login/douyin.publish.log 2>&1 &
```

### 第 2 步：轮询状态

**每 2–3 秒查一次，用短命令**——别一次性长睡眠干等，墙一出现你才能立刻反应：

```bash
sleep 3; cat outputs/_login/douyin.publish.json
```

状态机（JSON 字段 `state`）：`starting`→可能 `sms_required`→`verifying`→`success`/`error`。**`success` 只在发布后读回创作者中心作品列表、对账通过才写入**，message 里带核验到的作品 id 与状态；读回没对上落 `error`，message 区分三种：登录态失效（需重新登录）/ 列表暂未见本次内容（需到内容管理页人工核对）/ 读回通道异常。

读到 `state=="sms_required"`（含『正在发送验证码』阶段——**看到就立即要码，不必等短信到**）后，按探测结果分流：

### A. 卡片模式（EASEL_ASKUSER_CARDS==1）

**马上调用 `ask_user` 工具弹【验证码卡片】要码——不要用普通文字消息**（卡片自带「自行输入…」填空，用户填完提交你直接拿到数字）。参数模板（`options` 必需 2–4 个；验证码本身走卡片自带的自由输入）：

```json
{"questions":[{"id":"sms_code","header":"发布验证","question":"抖音发布触发短信验证：请把手机收到的 6 位验证码填进来（点「自行输入…」后输入数字）。","options":[{"label":"重新发送验证码"},{"label":"取消本次发布"}]}],"timeoutSeconds":300}
```

用户提交后按答案分流：**纯数字（4–8 位）** → 写码文件（见下）；**「重新发送验证码」** → 建重发信号文件后**立刻再弹一张卡**（问题改为「已重发——把新收到的验证码填进来」）；**「取消本次发布」** → 告知脚本会自行超时退出。整轮不结束，卡片答完接着轮询到 `success`/`error`。

### B. 文字等待模式（EASEL_ASKUSER_CARDS==0 或空，如 2026.6.11）

后台进程已用 `setsid` 脱离、会一直等码（≤300s），所以你可以放心**结束本轮**、把要码交给下一轮：

1. 发一条**普通文字消息**告诉用户：抖音发布触发短信验证，请把手机收到的 6 位验证码直接发给你；若没收到可回「重发」。**然后结束本轮**（不要在本轮里 `sleep` 干等，用户此刻还没输码，Bash 白卡）。
2. **用户下一条消息**就是验证码（同一会话，你能看到发布上下文）。按内容分流：
   - **纯数字（4–8 位）** → 写码文件（见下），然后**立即恢复轮询**（后台进程还活着，`cat` 状态文件即可）；
   - 含「重发/没收到/重新发送」→ 建重发信号文件（见下），告诉用户已请求重发、收到新码再发你，本轮再结束等下一轮；
   - 「取消」→ 建取消/等超时，告知用户本次发布将退出。
3. 恢复轮询后若又回到 `sms_required`（码错/重发），重复本流程：再发文字要码 → 结束本轮 → 下轮收码。

> 跨轮要点：**别每轮都重新起发布进程**——第 1 步只在最开始跑一次。后续轮里先 `cat outputs/_login/douyin.publish.json` 看它是否还在 `sms_required`/`verifying`，在就只写码/轮询，不要重复 publish。

### 写码文件 / 重发信号（两种模式通用）

把**纯数字**写进码文件（一次性消费，脚本读走即删）：

```bash
printf '%s' "123456" > outputs/_login/douyin.code
```

请求重发（脚本收到信号会在墙上点「重新发送」再下发验证码，一次性）：

```bash
touch outputs/_login/douyin.code.resend
```

继续轮询直到 `success`/`error`。码错会退回 `sms_required`，可再要一次重写。

要点：验证码文件内容是纯数字（4–8 位）；**全程保持"后台脚本 + 短轮询"模式**——绝不要同步前台阻塞跑发布（不带 `&`）再想中途问用户（Bash 会一直卡住直到脚本退出）。发布页（Web「发布中心」）已用同一套文件协议自动弹原生输入框，与对话页无关、无需 agent 介入，任何版本都能用。

**速度要点（决定成败）**：墙出现 → 脚本识别（≤15s）→ 你读到 `sms_required` → **数秒内**要码（卡片模式弹卡 / 文字模式发消息，别先长篇解释）→ 拿到码 → **立即**写码文件（一条 `printf` 的事，不拖）。任何环节拖 30 秒以上，用户手机上的验证码就可能过期要重发。文字模式跨轮无妨（后台等 300s），但你自己收到码后别拖着不写。

## 发布前人设检查（有 Profile 时）

按 AGENTS.md「发布前人设一致性检查」：先 **skill-persona-check** 比对内容×画像，评分喂
`python skills/shared/scripts/persona_gate.py check --score 85`——低于 80 分时警告并给修改建议，
但不阻断发布；用户已明确要发布就继续执行。

## 发布后留痕

```
python skills/shared/scripts/persona_gate.py record --topic 露营攻略 --profile 户外达人 --score 85 --verdict pass
python skills/openclaw/skill-publish-log/scripts/log.py record --platform 抖音 --title "周末露营攻略" --profile 户外达人 --persona-score 85 --persona-verdict pass --skill-source skill-douyin-upload
```

## 必做约束

- 发布前必须让用户确认最终标题、简介、媒体（先跑 `plan`）。
- 图文发布必须有图片，视频发布必须有视频（二选一）。
- 标题 ≤ 30 字（脚本校验，超限拦下）。
- 文件路径必须绝对路径（脚本解析并校验存在）。
- 发布始终开窗口（`--headed` 仅为兼容保留）；首次或疑似改版时请用户在窗口里观察。
- 发布前不得为了「快」绕过闸门：重复/冷却命中就停（退出 8/9），不要换标题、改文件来骗过去重。
- 定位失败改 `douyin_publish.py` 顶部 `SELECTORS` 字典（单点集中，每条标了参考源）。

## 命令样例

```bash
python skills/shared/scripts/douyin_publish.py check
python skills/shared/scripts/douyin_publish.py login                     # 抠二维码扫码
python skills/shared/scripts/douyin_publish.py plan --title T --video /abs/v.mp4 --tags "旅行,攻略"
python skills/shared/scripts/douyin_publish.py publish-video --exec \
  --title "标题" --content "简介" --video /abs/v.mp4 --tags "旅行,攻略"
python skills/shared/scripts/douyin_publish.py publish --exec --no-ai-declare \
  --title "标题" --content "简介" --images /abs/a.jpg,/abs/b.jpg
```
