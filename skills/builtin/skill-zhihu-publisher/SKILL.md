---
name: skill-zhihu-publisher
description: >-
  知乎发布：把文章发布到知乎专栏（也可用于回答草稿）。当用户说"发知乎""知乎发布"
  "发布知乎文章""知乎专栏""投知乎"时使用。基于通用浏览器发布框架（Playwright + 登录态持久化）。
layer: publish
---

# 知乎发布

> 基于通用浏览器发布框架 `../../shared/scripts/web_publisher.py`（`--platform zhihu`）。
> 发布到知乎专栏写作页（zhuanlan.zhihu.com/write）。

## ⚠️ 环境依赖

- `pip install playwright` + `playwright install chromium`
- 首次 `login` 登录知乎，登录态持久化复用
  - 远程/headless 环境用 `login-qr --platform zhihu`（抠二维码成图轮询），或走 Web「账号」页登录
- **选择器时效**：知乎正文为 Draft.js contenteditable，发布可能有二次确认弹窗；内置选择器为
  最佳努力，**首次务必 `plan` + `--headed` 校验**，失效时更新 `web_publisher.py` 的 zhihu 配置。

无浏览器环境可用 `platforms` / `plan` / `check`。

## 半自动发布与发布闸门（默认，必读）

- **半自动**：`--exec` 后脚本在**可见的真实浏览器窗口**里把内容全部填好，**停在「发布」前**，由用户亲自检查并点击；
  脚本只被动观察结果（成功才记账）。**agent 不得替用户点发布，也不得设置/建议设置 `EASEL_DOMESTIC_AUTO_PUBLISH=1`**
  （该逃生口只能用户自己开）。状态文件（`--status-file`）会出现 `awaiting_user_click`；等用户点的最长时间 `--handoff-timeout`（默认 3600 秒）。
- **发布闸门**（起浏览器前）：同平台 30 天内媒体/标题重复 → 退出码 **8**（仅当用户明确要求重发才加 `--allow-repost`）；
  平台冷却 → 退出码 **9**，任何参数都绕不过，**只有用户能解除**（`python skills/shared/scripts/publish_guard.py cooldown clear --platform <平台>`，agent 不要主动清）。
- **fail-stop**：窗口被关/等点击超时 → 提示「未发布」并非零退出，**不要自动重试**；检测到平台处罚/限流 toast → 设冷却并退出 9，先向用户汇报。
- 冷却期内**所有自动起浏览器的子命令**（whoami --live、评论/抓取等）也一律退出 9；`login` 由用户发起，只警告不拦。状态文件 `verifying` 是非终态，核对通过才写 `success`，失败写 `error`。
- 不做发布频率限制（小红书原有间隔闸门保持不变）。
- **浏览器内核**：同 `real_browser`（CloakBrowser → 本机 Chrome/Edge，`EASEL_ZHIHU_BROWSER=chrome` 强制 Chrome，`EASEL_ZHIHU_HEADLESS=1` 仅无桌面机器）。
  **从旧版升级后需重新扫码登录一次**。内容含 AI 生成时，交接提示会提醒手动勾选 AI 声明（`--no-ai-declare` 关闭提醒）。

## 执行

```bash
ROOT=<项目根>; WP=$ROOT/skills/shared/scripts/web_publisher.py
python $WP check
python $WP login   --platform zhihu
python $WP plan    --platform zhihu --title "标题" --desc "正文..."
python $WP publish --platform zhihu --title "标题" --desc "正文..." --exec   # 开窗口填好，停在『发布』前等你点
```

## Profile 感知

- 有 Profile：文风专业、有逻辑链，贴合 `style.md`；话题标签按垂类。
- 无 Profile：按知乎通用规范（专业、结构化、有论据）。

## 规则

1. 知乎重深度与专业性，正文结构清晰、有论据；标题克制不标题党。
2. 长文可先用 video-to-article / social-content 成稿，再来发布。
3. 首次 `--headed` 目视确认写作页与发布弹窗；选择器失效即更新配置。
4. 正文为富文本编辑器，复杂排版建议登录后人工微调再发。

## 参考来源

知乎专栏写作页网页流程；复用统一 Playwright 框架。正文 Draft.js 编辑器，选择器按现状维护。
