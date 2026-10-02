# xhs-publisher 命令样例

> 统一走 `../../shared/scripts/xhs_publish.py`（Playwright 驱动**本机 Chrome 窗口**）。CWD=项目根。
> 流程/选择器移植自 xpzouying/xiaohongshu-mcp。旧 CDP 脚本已退役删除。
>
> **为什么开窗口**：2026-10 账号被判「第三方脚本 / AI 托管发文」封 30 天，当时用的是 Playwright 自带内核的
> 无头模式（UA 写着 HeadlessChrome）。现在所有小红书操作都开本机正式版 Chrome（没有就 Edge）的窗口，
> 鼠标沿曲线移过去点、按词组输入；`--headed` 已是默认行为。只有没有桌面的机器才设 `EASEL_XHS_HEADLESS=1`
> 强开无头（很容易被识别）。

## 环境检查

```bash
python skills/shared/scripts/xhs_publish.py check
# ✅ playwright 已安装 / ✅ chromium 内核 / 登录态目录
```

## 登录（开 Chrome 窗口扫码，二维码也抠成图片）

```bash
python skills/shared/scripts/xhs_publish.py login
# 把登录二维码抠成 PNG → 默认 outputs/_login/xhs-login-qrcode.png（可在 Easel Web UI 的 outputs 查看）
# 用小红书 App 扫这张图 → 脚本轮询到登录成功后持久化 cookie（下次免登）
#   --qr-out <path>   自定义二维码输出路径
#   --timeout <秒>    等待扫码超时（默认 180）
#   --headed / --headed-fallback  旧参数，现在默认就开窗口（仅 EASEL_XHS_HEADLESS=1 时才有区别）
# 登录态存 ~/.easel-browser-profiles/XiaohongshuProfile
# 扫码后先等登录 cookie 落盘、再用同一份登录态重开创作平台发布页，看到发布页真渲染出来才打印「登录成功」；
# 没保存上会明说「登录看似成功但登录态没能保存，请重试」并返回非 0；
# 登录窗口中途被关 / 浏览器异常也会写 error 状态、明说原因并返回非 0（不会停在半路）。
# CLI 直跑（不带 --status-file、默认登录目录）成功后也会写 outputs/_login/xiaohongshu.json，Web 账号页随之显示已登录。
```

> ⚠️ **风险 IP 拦截**：小红书会把机房/公司代理出口判为风险 IP（报「安全限制 300012 · IP存在风险」），
> 此时二维码根本不弹。没桌面、只能无头时：
> ① `--proxy socks5://<干净/家宽IP代理>`；
> ② 在正常网络的机器上 `login` 拿到登录态，再把 `~/.easel-browser-profiles/XiaohongshuProfile`
> 整个目录拷到本机复用（登录态可移植）。本机/代理出口 IP 常被平台判风险，需换干净 IP。

## 发布前预检（dry-run，离线不启浏览器）

```bash
python skills/shared/scripts/xhs_publish.py plan \
  --title "500元改造出租屋の神仙好物" \
  --content "分享几个平价好物……" \
  --images /abs/a.jpg,/abs/b.jpg \
  --tags "出租屋改造,好物分享"
# 打印：标题长度校验 / 媒体 / 话题 / AI 声明 / 8 步流程
```

## 图文发布

```bash
# dry-run（默认，不加 --exec 不会真发）
python skills/shared/scripts/xhs_publish.py publish \
  --title "标题" --content "正文" --images /abs/a.jpg,/abs/b.jpg --tags "AI,教程"

# 真正发布（开 Chrome 窗口，用户能看着它操作；发布过程中不要动那个窗口）
python skills/shared/scripts/xhs_publish.py publish --exec \
  --title "标题" --content "正文" --images /abs/a.jpg,/abs/b.jpg --tags "AI,教程"
# 内容确实不是 AI 生成/合成的（用户自己拍的照片 + 自己写的字）才加 --no-ai-declare
```

### AI 合成声明（默认勾）

小红书要求 AI 生成/合成的内容主动声明。脚本默认在发布前勾上「笔记含AI合成内容」；**勾不上就停在
发布前、不发（退出码 6）**，窗口里可以手动勾好再自己点发布。只有内容确实不是 AI 生成的才加 `--no-ai-declare`。

### 频率闸门（按账号算，只记成功的）

| 操作 | 两次之间至少 | 24 小时内最多 | 环境变量 |
|------|------|------|------|
| 发笔记 | 60 分钟 | 3 条 | `EASEL_XHS_MIN_GAP_MIN` / `EASEL_XHS_DAILY_MAX` |
| 回复评论 | 每条间隔 ≥20s（再随机多等） | 30 条 | `EASEL_XHS_REPLY_DAILY_MAX` |
| 去别人笔记下评论 | 10 分钟 | 5 条 | `EASEL_XHS_COMMENT_GAP_MIN` / `EASEL_XHS_COMMENT_DAILY_MAX` |

超限时 `--exec` 直接拒绝（退出码 5），dry-run 会提前提示。记录在登录目录的 `.easel-activity.json`。

## 视频发布

```bash
python skills/shared/scripts/xhs_publish.py publish-video --exec \
  --title "标题" --content "正文" --video /abs/clip.mp4 --tags "vlog"
# 视频上传后脚本等发布按钮可点击（最长 10min = 平台处理完成）再提交
```

## 代理与登录态

```bash
--proxy http://host:port     # 显式外网代理（默认取 env http(s)_proxy，小红书是外网需代理）
--no-proxy                   # 禁用代理
--profile-base /path         # 登录态根目录（默认 ~/.easel-browser-profiles）
--keep-open                  # 发布后不关闭浏览器（调试用）
```

## 参数速查

| 参数 | 说明 |
|------|------|
| `--title` | 标题，≤20 全角字（脚本按小红书口径 `calc_title_length` 校验） |
| `--content` | 正文 |
| `--images` | 图片路径，逗号分隔（图文发布；绝对路径） |
| `--video` | 视频路径（视频发布；绝对路径） |
| `--tags` | 话题，逗号分隔（如 `AI,教程`；脚本走话题联想真绑定） |
| `--exec` | 真正发布（缺省为 dry-run） |
| `--no-ai-declare` | 不勾「笔记含AI合成内容」（仅内容确实不是 AI 生成时） |
| `--headed` | 旧参数，现在默认就开窗口 |

## 排障

- **未登录**：先 `login` 扫码。
- **步骤超时 / 找不到元素**：小红书改版了——改 `xhs_publish.py` 顶部 `SELECTORS` 字典（单点维护，每条标了参考源），看着窗口定位。
- **AI 声明勾不上（退出码 6）**：改 `AI_DECLARE_*` 文案常量；当场可在窗口里手动勾选后自己点发布。
- **被频率闸门拦（退出码 5）**：按提示的时间之后再发，不要调大上限去「补发」。
- **发布未确认成功**：脚本以「URL 离开 /publish/publish」判成功；若卡在发布页说明平台校验未过（标题/正文超限、内容违规等），按提示排查。
- **自检**：`python skills/shared/scripts/xhs_publish.py selftest`（离线，验选择器字典/标题算法/参数解析）。
