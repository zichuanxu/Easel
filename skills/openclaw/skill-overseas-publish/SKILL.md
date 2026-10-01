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
