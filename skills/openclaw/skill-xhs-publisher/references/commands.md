# xhs-publisher 命令样例

> 统一走 `../../shared/scripts/xhs_publish.py`（Playwright，headless 可用）。CWD=项目根。
> 流程/选择器移植自 xpzouying/xiaohongshu-mcp。旧 CDP 脚本已退役删除。

## 环境检查

```bash
python skills/shared/scripts/xhs_publish.py check
# ✅ playwright 已安装 / ✅ chromium 内核 / 登录态目录
```

## 登录（headless：抠二维码成图片扫码）

```bash
python skills/shared/scripts/xhs_publish.py login
# 把登录二维码抠成 PNG → 默认 outputs/_login/xhs-login-qrcode.png（可在 Easel Web UI 的 outputs 查看）
# 用小红书 App 扫这张图 → 脚本轮询到登录成功后持久化 cookie（下次免登）
#   --qr-out <path>   自定义二维码输出路径
#   --timeout <秒>    等待扫码超时（默认 180）
#   --headed          本地有桌面时用窗口内扫
#   --headed-fallback 无头被风控拦（300012）时自动改开有头窗口扫（本机有桌面时用；Web 账号页在 macOS/Windows/有 DISPLAY 的 Linux 上自动加）
# 登录态存 ~/.easel-browser-profiles/XiaohongshuProfile
# 扫码后先等登录 cookie 落盘、再用同一份登录态无头重开创作平台发布页，看到发布页真渲染出来才打印「登录成功」；
# 没保存上会明说「登录看似成功但登录态没能保存，请重试」并返回非 0；
# 登录窗口中途被关 / 浏览器异常也会写 error 状态、明说原因并返回非 0（不会停在半路）。
# CLI 直跑（不带 --status-file、默认登录目录）成功后也会写 outputs/_login/xiaohongshu.json，Web 账号页随之显示已登录。
```

本机有桌面、网络被判风险时，直接开窗口登录（有头浏览器通常不被拦）：

```bash
python skills/shared/scripts/xhs_publish.py login --headed --no-proxy
python skills/shared/scripts/xhs_publish.py login --headed-fallback --no-proxy   # 先试无头出码，被拦再弹窗口
```

> ⚠️ **风险 IP 拦截**：小红书会把机房/公司代理出口判为风险 IP（报「安全限制 300012 · IP存在风险」），
> 此时二维码根本不弹。实测它只拦「未登录 + 无头浏览器」：本机有桌面时用 `--headed`（或
> `--headed-fallback`）在窗口里登录即可，登录后无头发布/校验照常可用。没桌面时：
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
# 打印：标题长度校验 / 媒体 / 话题 / 7 步流程
```

## 图文发布

```bash
# dry-run（默认，不加 --exec 不会真发）
python skills/shared/scripts/xhs_publish.py publish \
  --title "标题" --content "正文" --images /abs/a.jpg,/abs/b.jpg --tags "AI,教程"

# 真正发布（首次建议 --headed 观察选择器，OK 后去掉转 headless）
python skills/shared/scripts/xhs_publish.py publish --exec --headed \
  --title "标题" --content "正文" --images /abs/a.jpg,/abs/b.jpg --tags "AI,教程"
```

## 视频发布

```bash
python skills/shared/scripts/xhs_publish.py publish-video --exec --headed \
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
| `--headed` | 有头模式（首次校验选择器） |

## 排障

- **未登录**：先 `login` 扫码。
- **步骤超时 / 找不到元素**：小红书改版了——改 `xhs_publish.py` 顶部 `SELECTORS` 字典（单点维护，每条标了参考源），先 `--headed` 观察定位。
- **发布未确认成功**：脚本以「URL 离开 /publish/publish」判成功；若卡在发布页说明平台校验未过（标题/正文超限、内容违规等），按提示排查。
- **自检**：`python skills/shared/scripts/xhs_publish.py selftest`（离线，验选择器字典/标题算法/参数解析）。
