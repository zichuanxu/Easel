# 已知问题

本页记录目前已知、且与 Easel 使用相关的问题，以及推荐的规避方式。遇到未列出的问题，欢迎提交 [Issue](https://github.com/ZJU-REAL/Easel/issues)。

---

## Claude CLI 路线：隔一会儿再追问，agent 忘了前面的对话

- **影响范围**：用本机 Claude Code 登录跑 agent（`EASEL_AGENT_RUNTIME=claude-cli`）且使用默认的隔离配置目录 `~/.claude-easel` 时；OpenClaw 2026.9.7 实测。
- **表现**：一轮任务做完，过一会儿在同一个对话里追问，agent 像新会话一样回答，比如复述画像设置、说「这条消息里还没有具体任务」。紧接着追问（上一轮的 Claude Code 进程还在）不受影响。
- **网关日志**（`/tmp/easel-gateway.log`）：

  ```
  claude-cli transcript probe v4 miss … expectedPath=~/.claude/projects/<工作区>/<id>.jsonl fileExists=false
  cli session reset: provider=claude-cli reason=transcript-missing
  ```

### 根因

续聊前 OpenClaw 会确认上一轮的 Claude Code 会话文件还在，但它把路径写死成 `~/.claude/projects/<工作区>/`，不看传给 claude 的 `CLAUDE_CONFIG_DIR`。Easel 默认把 Claude Code 隔离到 `~/.claude-easel`，会话文件写在 `~/.claude-easel/projects/<工作区>/`，OpenClaw 找不到就重置会话，agent 只看得到当前这一条消息。问题在上游 OpenClaw，不在 Easel 仓库内。

### 规避

`bash setup.sh` 会把 `~/.claude/projects/<工作区>` 软链到 `~/.claude-easel/projects/<工作区>`：只动这一个目录，里面原有的文件先挪进隔离目录，同名冲突就停下、不覆盖。已经装好的机器运行一次：

```bash
python -m easel.claude_cli_link
```

`easel doctor` 的「Claude CLI session resume」一项会检查这个软链。OpenClaw 改为按 `CLAUDE_CONFIG_DIR` 找会话文件之后，删掉这个软链即可。

---

## CLI 终端对话中「问答题」后回复重复显示

- **影响范围**：仅 `easel chat`（终端对话）。**Web 工作台不受影响**。
- **表现**：当 Agent 触发一次 `ask_user` 问答题、用户回答之后，Agent 的下一条回复在终端里可能被重复渲染一次（内容正确，只是显示了两遍）。
- **性质**：这是**纯显示层**问题，不影响实际对话内容、产物生成或发布结果。

### 根因

问题位于上游 [OpenClaw](https://www.npmjs.com/package/openclaw) 本体的**会话投影（session projection）**逻辑，不在 Easel 仓库内。

`easel chat` 底层调用 `openclaw tui`，由 OpenClaw 的 gateway-client 负责在终端重建对话记录。当一条实时回复与另一行（例如 `ask_user` 的问答行）发生错误匹配、且两者不共享 transcript identity 时，投影逻辑会把该回复重新插入一次，导致重复渲染。

我们已核实该根因，并在上游的回归测试中复现（修复前 3 条相关用例失败，修复后全部通过）。

### 上游修复进展

修复已提交至 OpenClaw，跟踪 PR：

- openclaw#144730
- openclaw#144892

修复采用四层策略：全内容唯一匹配、要求终端证据、暂定恢复记录、以及在暂定恢复无法表示时保留后续独立 final 可见。

### 规避与升级

- **推荐**：使用 **Web 工作台**（`easel web`，默认 `http://localhost:7860`）。Web 后端从原始事件流自行渲染，不经过上述会话投影逻辑，因此**不受此问题影响**，并且提供比 CLI 更完整的会话、素材、账号、画像、内容库与发布管理能力。
- 若坚持使用 `easel chat`：待上游发布含修复的版本后，升级 OpenClaw 即可解决：

  ```bash
  npm i -g openclaw@latest
  ```

- Easel 安装的是 OpenClaw 全局 CLI（预构建产物），因此我们**不在 Easel 仓库内内置该补丁**，而是跟随上游最新版本。`easel doctor` 已加入 OpenClaw 最低版本检查（≥ 2026.6.11），版本过旧会直接提示升级。

---

## 第三方代理 / 兼容端点 LLM 一直超时（#9、#11）

- **影响范围**：配置第三方代理或 Anthropic/OpenAI-compatible 端点的安装。
- **表现**：`easel ping` 或小请求可能正常，但稍大、带思考的请求持续超时；部分版本上 `setup.sh` 还会报 `baseUrl: expected string, received undefined` 或 `Unrecognized key: "timeoutSeconds"`。

### 根因（已修复）

- 旧版 OpenClaw（如 2026.3.x）的 provider schema 要求 anthropic 配置**原子写入**；逐字段写入时中间态缺 `baseUrl`，整份校验失败。`setup.sh` 已改为整块一次性写入。
- 旧版本不认识 `timeoutSeconds` 字段，单次请求 600 秒空闲超时写不进去，回落到默认短超时，首个 token 稍慢即超时。该写入在老版本上已降级为尽力而为，不再中断安装。

### 建议

```bash
npm i -g openclaw@latest
git pull
bash setup.sh
```

升级后 `easel doctor` 会校验 OpenClaw ≥ 2026.6.11。不升级时安装不再报错，但请求超时受旧版默认超时限制；请确认模型名带 provider 前缀（如 `anthropic/claude-sonnet-4-6`），具体卡在哪一步可看 `easel gateway logs`。

## 小红书：账号被判「第三方脚本 / AI 托管发文」

- **现场（2026-10）**：账号收到「笔记存在利用 AI 托管进行发文/互动」「使用第三方脚本或工具」警告并被封 30 天。当时 Easel 在 macOS 上用 Playwright 自带内核的**无头浏览器**操作小红书（UA 写着 `HeadlessChrome`），而且账号页每次打开都在后台开一次浏览器校验登录，创作数据页开着时也会定时重抓；发出去的 AI 视频没有做 AI 合成声明。
- **现在的做法**：
  - 发布、评论、看数据都开窗口，鼠标沿曲线移过去点、按词组输入；过程中别动那个窗口。
  - 浏览器优先 **CloakBrowser**（`pip install cloakbrowser && python -m cloakbrowser install`）：每个账号一套固定指纹，存在登录目录 `.easel-fingerprint.json`（Mac 上是 macOS 身份），浏览器数据在 `cloak-browser/` 子目录。没装 Cloak（或 `EASEL_XHS_BROWSER=chrome`）用本机 Chrome / Edge；都没有才退回自带 Chromium 并警告。Cloak 和 Chrome 的登录态分开，换浏览器要重新扫码（以前在 Windows 上用 Cloak 的，登录态原来在登录目录本身，现在挪到 `cloak-browser/`，也要重新扫码一次）。账号页「退出」会删掉登录态，但保留固定指纹和频率记录。
  - 账号页不再为小红书开浏览器，只看本地登录记录（登录过期要等发布时才发现）；创作数据只在点「刷新数据」时抓。
  - 发布默认勾「笔记含AI合成内容」，勾不上就停在发布前不发（退出码 6）；内容确实不是 AI 生成才加 `--no-ai-declare`。
  - 频率闸门：笔记两条之间 ≥60 分钟、24 小时 ≤3 条；回复每条间隔 ≥20 秒、24 小时 ≤30 条；去别人笔记下评论两条之间 ≥10 分钟、24 小时 ≤5 条。超限退出码 5。
- **仍然有风险**：平台不允许第三方工具代发，以上只能降低被识别的概率。被封期间不要再用 Easel 碰这个账号；解封后先手动正常使用几天，再少量使用。
- **没有桌面的机器**：开不了窗口，只能设 `EASEL_XHS_HEADLESS=1` 强开无头，很容易被识别，不建议。

## 海外平台登录：要在有桌面的本机，最好装 Google Chrome

- **影响范围**：账号页的 TikTok / YouTube / Instagram / X / Threads。
- **表现**：点「登录」会在运行 Easel 的这台电脑上弹出 Chrome 窗口，需要在窗口里亲手登录（含两步验证），最长 10 分钟。没有桌面的环境（Linux 服务器、无 `DISPLAY`）弹不出窗口，账号页的登录按钮会置灰。
- **Google 登录**：Google 会拦截自动化用的 Chromium（「此浏览器或应用可能不安全」）。Easel 优先用本机安装的 Google Chrome；没装时退回 Playwright 自带的 Chromium，YouTube 登录大概率失败。解决：安装 Google Chrome 后重新点登录。
- **网络**：海外平台不强制直连。配了 `EASEL_PROXY` 就走该代理，否则用系统网络设置。国内平台照旧直连。
- **登录目录**：`~/.easel-browser-profiles/<平台>Profile`（如 `YouTubeProfile`）。账号页「退出」会删掉它。

## 海外平台发布：页面改版、人工验证与「结果待确认」

- **影响范围**：发布中心和对话里发 TikTok / Instagram / X / Threads（YouTube 要账号先有频道，暂未开放）。
- **页面改版**：发布靠本机浏览器按页面元素一步步操作，平台改版后可能找不到按钮，报「页面可能改版了」，没有发出去。现场截图和 HTML 在 `outputs/_login/<平台>-publish-fail.png/.html`，对着它改 `skills/shared/scripts/overseas/<平台>.py` 里的选择器。
- **界面语言**：选择器和成功提示按英文界面校准。平台界面是其它语言时，多半在点发布之前就停下报改版，或点了之后报「结果待确认」。请把这几个平台的账号语言设成英文。
- **人工验证**：平台要验证码 / 安全检查时，无头浏览器过不去，会自动在本机弹出窗口，最长等 5 分钟让你在窗口里完成，期间别关窗口。没有桌面的环境弹不出窗口，这时发布直接失败，没有发出去。
- **结果待确认（退出码 5）**：已经点了发布、但没等到平台的成功提示（包括点完之后页面出错、窗口被关）。帖子可能已经发出去了，**先到平台上看一眼，不要直接重发**。
- **同一平台一次只发一条**：上一条还在发时，再点发布会提示「正在发布上一条」。
