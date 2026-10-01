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
