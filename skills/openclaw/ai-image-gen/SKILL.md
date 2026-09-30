---
name: ai-image-gen
description: "通用 AI 生图：文生图 / 图生图 / 图像变体。当用户说 AI 生图、AI 画图、文生图、图生图、生成图片、生成配图、图像生成、AI 出图、AI 作图、换图、改图、图像编辑、给我画一张、生成一张图 时使用。支持 OpenAI 兼容 API、apimart 异步 API（用户自备 key），以及本机 Codex CLI（ChatGPT 登录，免 key）。"
layer: produce
---

# ai-image-gen Skill

> 通用 AI 文生图 / 图生图 / 图像变体。后端二选一：用户自备的图像 API key（OpenAI 兼容 或 apimart 异步），或本机 Codex CLI（ChatGPT 登录，免 key）。产物写入 `outputs/`。

调用共享脚本 `skills/shared/scripts/ai_image.py`（纯标准库，无第三方依赖）。
本 SKILL 不索要、不回显、不写入、不提交任何真实 API key —— key 只存在于用户自己的 `.env`。

## 边界（和相邻 SKILL 区分）

- **ai-image-gen（本 SKILL）**：通用 AI 生图，任意题材，文生图 / 图生图 / 变体。
- **ecom-details-image**：电商详情页 / 商品主图专用出图（25 场景模板、PDP 序列）。要做电商商品图走它。
- **card-\* / poster-\***：HTML+CSS 渲染截图（金句卡、小红书卡、海报），**非 AI 生成**，是确定性设计出图。
- **image-editing**：已有图片的确定性处理（改尺寸/裁剪/加水印/压缩），不生成新画面。

## 配置（执行前必读）

> **配置检查路径铁律**：先 `cd` 到 `AGENTS.md` 末尾给出的 Easel 项目根，确认当前目录有 `.env` 和 `skills/shared/scripts/ai_image.py`，再运行下列命令。不得在 OpenClaw workspace 用 `./shared/scripts/...` 检查，也不得用 `env` / `printenv` 代替读取项目 `.env`；否则会把已配置的 `IMG_BASE_URL`/Key 误判为缺失。

需在项目根目录 `.env` 中设置三项（脚本从当前目录向上自动查找 `.env`）：

| 变量 | 说明 | 兼容别名 |
|---|---|---|
| `IMG_BASE_URL` | API 根地址 | `OPENAI_BASE_URL` / `OPENAI_API_BASE` / `BASE_URL` |
| `IMG_MODEL` | 图片模型名 | `OPENAI_IMAGE_MODEL` / `IMAGE_MODEL` / `OPENAI_MODEL` |
| `IMG_API_KEY` | API key | `OPENAI_API_KEY` / `API_KEY` |

支持两类服务，脚本按 `base_url` 自动检测（也可 `--mode sync|async` 强制）：

- **OpenAI 兼容（同步）**：`base_url` 不含 apimart。走 `/images/generations`、`/images/edits`、`/images/variations`。
  示例：`IMG_BASE_URL=https://api.openai.com/v1`，`IMG_MODEL=gpt-image-1`。
- **apimart（异步轮询）**：`base_url` 含 `apimart`。提交任务 → 轮询 `/tasks/<id>` → 下载。
  示例：`IMG_BASE_URL=https://api.apimart.ai/v1`。

### 本机 Codex CLI（免 key）

`.env` 设 `IMG_PROVIDER=codex-cli`（或 Web「设置 → 模型配置 → 生图」把 Codex CLI 设为主）后，
text2img / img2img / variations 都改由本机 `codex exec` 出图，不需要上面三项。前提：本机装了 codex 且已 `codex login`。

- 可选：`IMG_CODEX_MODEL`（默认 `gpt-6.1-sol`）、`IMG_CODEX_TIMEOUT`（单张超时秒数，默认 300）、`IMG_CODEX_BIN`（codex 路径，默认自动查找）。
- 每张约 1 分钟，占用户的 ChatGPT 订阅额度；`--n` 张逐张生成。**多张先告诉用户预计耗时。**
- `--size` 只决定横 / 竖 / 方（实际出 1024×1536、1536×1024 或 1024×1024）；要精确尺寸再交给 `image-editing`。
- 不支持 `--mask`：把要改的区域写进 prompt。临时指定后端用 `--mode codex` 或 `--mode sync|async`。

## 执行步骤

### 1. 先确认配置（离线，不发请求）

```bash
python skills/shared/scripts/ai_image.py check
```

打印三项配置状态（key 脱敏显示）、命中的别名、自动检测的模式；选了 Codex CLI 时改为打印 codex 路径、模型和登录状态。缺项时给出填写示例并以退出码 2 结束。**配置未就绪就不要往下走**，直接把缺什么、怎么配告诉用户。

### 2. 文生图 text2img

先把用户诉求写成一条清晰的图像 Prompt（主体 + 风格 + 构图 + 光线 + 画质），再执行：

```bash
python skills/shared/scripts/ai_image.py text2img \
  --prompt "一只戴墨镜的柴犬，扁平插画风，明亮撞色背景，高细节" \
  --size 1024x1024 --n 1 \
  --output outputs/主题名/ai-image
```

- `--size`：同步模式用像素（`1024x1024` / `1536x1024` / `1024x1536`…）；异步模式用比例（`1:1` / `16:9` / `9:16`…）。
- `--n`：生成张数（多张时按序号自动命名）。
- `--output`：目录（多张自动编号）或含扩展名的单文件；统一放 `outputs/主题名/`。
- 同步可加 `--quality low|medium|high`；异步可加 `--resolution 1k|2k|4k`。

### 3. 图生图 / 图像编辑 img2img

基于一张输入图 + 指令生成新图（OpenAI 走 `/images/edits` multipart，可选 `--mask` 局部编辑；apimart 把输入图作参考图走生成端点）：

```bash
python skills/shared/scripts/ai_image.py img2img \
  --prompt "把背景换成夜晚霓虹街道，保留主体" \
  --image path/to/input.png \
  --output outputs/主题名/edited.png
```

### 4. 图像变体 variations

由一张图生成多个变体：

```bash
python skills/shared/scripts/ai_image.py variations \
  --image path/to/input.png --n 3 \
  --output outputs/主题名/variations
```

### 5. 交付

告诉用户产物路径、生成参数（模式/模型/尺寸/张数）。如需再改尺寸/加水印/压缩，转 `image-editing`。

## 产物

统一输出到 `outputs/主题名/`。脚本会自动创建目录，多张按时间戳 + 序号命名。

## Profile 感知

有账号 Profile（`=== EASEL ACCOUNT PROFILE ===`）时，把品牌视觉风格（配色 / 调性 / 元素偏好）融入 Prompt，保持系列图统一；无 Profile 时按用户描述走通用生成。

## 常见问题

- **缺 key / 缺配置**：`check` 会明确指出缺哪项及 `.env` 示例；报错为友好中文，不抛 traceback。
- **同步 vs 异步用错尺寸格式**：同步用像素、异步用比例。用 `--mode` 可强制模式。
- **不要把真实 key 写进任何产物或提交**。
