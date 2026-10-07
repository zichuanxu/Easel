---
name: skill-channels-upload
description: >-
  微信视频号发布：把竖版短视频发布到微信视频号（channels.weixin.qq.com）。当用户说
  "发视频号""上传视频号""视频号发布""发到微信视频号""视频号投稿"时使用。基于通用浏览器
  发布框架（Playwright + 登录态持久化），微信扫码登录。
layer: publish
---

# 微信视频号发布

> 基于通用浏览器发布框架 `../../shared/scripts/web_publisher.py`（`--platform weixin-channels`）。

## ⚠️ 环境依赖

- `pip install playwright` + `playwright install chromium`
- 首次 `login` 用**微信扫码**登录视频号助手，登录态持久化复用
  - 远程/headless 环境用 `login-qr --platform weixin-channels`（抠二维码成图轮询），或走 Web「账号」页登录
- **选择器时效**：视频号发布页描述区可能是富文本 div 而非 textarea，内置选择器为最佳努力，
  **首次务必 `plan` + `--headed` 校验**，失效时更新 `web_publisher.py` 的 weixin-channels 配置。

无浏览器环境可用 `platforms` / `plan` / `check`。

## 半自动发布与发布闸门（默认，必读）

- **半自动**：`--exec` 后脚本在**可见的真实浏览器窗口**里把内容全部填好，**停在「发表」前**，由用户亲自检查并点击；
  脚本只被动观察结果（成功才记账）。**agent 不得替用户点发布，也不得设置/建议设置 `EASEL_DOMESTIC_AUTO_PUBLISH=1`**
  （该逃生口只能用户自己开）。状态文件（`--status-file`）会出现 `awaiting_user_click`；等用户点的最长时间 `--handoff-timeout`（默认 3600 秒）。
- **发布闸门**（起浏览器前）：同平台 30 天内媒体/标题重复 → 退出码 **8**（仅当用户明确要求重发才加 `--allow-repost`）；
  平台冷却 → 退出码 **9**，任何参数都绕不过，**只有用户能解除**（`python skills/shared/scripts/publish_guard.py cooldown clear --platform <平台>`，agent 不要主动清）。
- **fail-stop**：窗口被关/等点击超时 → 提示「未发布」并非零退出，**不要自动重试**；检测到平台处罚/限流 toast → 设冷却并退出 9，先向用户汇报。
- 不做发布频率限制（小红书原有间隔闸门保持不变）。
- **浏览器内核**：与小红书同款 `real_browser`（CloakBrowser → 本机 Chrome/Edge，每平台独立登录目录 + 固定指纹；`EASEL_CHANNELS_BROWSER=chrome` 强制 Chrome，
  `EASEL_CHANNELS_HEADLESS=1` 仅无桌面机器）。**从旧版升级后内核变了，需要重新扫码登录一次**（账号页或 `login-qr`）。
- 内容是 AI 生成时，交接提示会提醒在窗口里**手动勾选**平台 AI 声明（`--no-ai-declare` 关闭该提醒；脚本不自动勾，选择器未校准）。

## 执行

```bash
ROOT=<项目根>; WP=$ROOT/skills/shared/scripts/web_publisher.py
python $WP check
python $WP login   --platform weixin-channels           # 微信扫码
python $WP plan    --platform weixin-channels --media out.mp4 --title "标题"
python $WP publish --platform weixin-channels --media out.mp4 --title "标题" --exec   # 开窗口填好，停在『发表』前等你点
```

## Profile 感知

- 有 Profile：标题短（≤22字）贴合人设；竖版 9:16；可带话题与合集。
- 无 Profile：按视频号通用规范（短标题、竖版、正向内容）。

## 规则

1. 视频号竖版 9:16；横版先 video-reframe 转制。
2. 标题要短（视频号标题偏短），正文可展开。
3. 首次 `--headed` 目视确认扫码与发布流程；选择器失效即更新配置。
4. 视频号内容审核偏严，发布前过 skill-quality-gate 合规检查。

## 参考来源

视频号助手网页发布流程；复用统一 Playwright 框架。微信登录需扫码，选择器按平台现状维护。
