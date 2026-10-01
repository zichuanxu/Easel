# 海外平台规格（与 overseas/<平台>.py 的 LIMITS 一致）

| 平台 | 已接通 | 文案字段 | 上限 | 可见范围 | 备注 |
|---|---|---|---|---|---|
| TikTok | 视频、图文（≤35 张） | `--desc`（+ `--tags`） | 说明 ≤2200 | everyone / friends / only_me | 竖版 9:16；图文走上传页 Photos |
| YouTube | 待频道校准 | `--title` + `--desc` | 标题 ≤100，描述 ≤5000 | public / unlisted / private | 竖版 ≤3 分钟自动成 Shorts |
| Instagram | 视频（Reels）、图文（≤10 张） | `--desc` | 说明 ≤2200，话题 ≤30 | — | 竖版 9:16 |
| X | 视频、图文（≤4 张）、纯文字 | `--desc` | 加权 ≤280（中日韩文字算 2，链接算 23） | — | 免费账号视频 ≤2 分 20 秒 |
| Threads | 视频、图文（≤10 张）、纯文字 | `--desc` | ≤500，话题 1 个 | — | 话题标签留在正文里，不会变成 Threads「话题」 |

英文改写要点：开头一句就是钩子；口语、短句；话题标签 3–5 个（Threads 1 个），放在末尾；不要中文。

真机校准记录（2026-10-01）：
- 发布页元素先只读校准，再各真发一条 4 秒测试视频：TikTok（仅自己可见）、X、Instagram（Reels）、Threads 均成功，
  成功信号命中（X toast 带帖子链接、Threads「View」链接、Instagram「shared」、TikTok 跳到作品管理）。
- Threads 的「Post」按钮是 `div[role=button] > div > 文字`，Playwright 的 `:text-is` 只匹配直接装着文字的那层，
  所以选择器用 `:has(:text-is("Post"))`。
- YouTube：账号尚无频道，发布未开放。
- 图文 / 纯文字（第三期）先只读校准：X、Threads、Instagram 的图片都走原发帖弹窗（文件框可多选）；TikTok 图文在上传页
  Photos 标签（`?tab=photo`），每张图一个「Delete photo」，Post 按钮没有 `data-e2e`。
- 话题联想框：以 `#话题` / `@某人` 结尾的行，打字时补一个空格把联想框收掉（X、Instagram、TikTok 就收了），
  Threads 补空格不收、按 Esc 只收联想框。否则回车会选中联想项（X 默认选第一项，`#ai` 会变成 `#AIart`）。
  补的空格计入字数校验。
- 第三期真发（文案带 `#easeltest`，各 2 张 1080×1350 测试图）：TikTok 图文（仅自己可见）、X 图文、X 纯文字、
  Instagram 图文（轮播）、Threads 图文、Threads 纯文字均一次成功；回读确认图数正确、话题标签原样未被联想替换。

页面改版时对照 `outputs/_login/<平台>-publish-fail.*`（截图 + HTML）更新模块里的选择器。
