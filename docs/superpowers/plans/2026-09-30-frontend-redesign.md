# Easel 前端改版（画室 · 矿物色）实施计划

> **给执行代理：** 必须使用子技能 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按任务逐个实施。步骤用复选框（`- [ ]`）跟踪。

**目标：** 按设计规格把 `web/frontend` 改成「画室 · 矿物色」视觉，按流水线五层重组导航，并抽出共用组件库。功能和后端接口不变。

**架构：**
- 先落地设计变量和字体。原来的 `styles/index.css` 改名为 `legacy.css`，作为过渡层；在 `tokens.css` 里给旧变量名起别名，让全站在第一步就换成新配色。
- 再建共用组件（`components/ui/`）和层定义（`lib/layers.ts`）。之后逐页迁移：每页迁完，就把它在 `legacy.css` 里的旧段落删掉，并新建 `styles/pages/<页>.css`。
- 最后删掉 `legacy.css` 和旧变量别名。

**技术栈：**
- React 19、TypeScript 6、Vite 8、oxlint
- 新增测试：vitest 5、@testing-library/react 16、jsdom 30
- 新增字体：@fontsource/noto-serif-sc、@fontsource/bodoni-moda

**规格：** `docs/superpowers/specs/2026-09-30-frontend-redesign-design.md`。执行前先通读，它和本计划一起构成需求。

## 全局约束

- 颜色只能写在 `src/styles/tokens.css` 里。其他 CSS 和 TSX 一律用 `var(--…)`；TSX 里不允许出现十六进制颜色。
- 主按钮是墨色：`--c-ink #1F2328`，文字 `--c-on-ink #FFFFFF`。五种矿物色只用来标记流水线层，不用在按钮上。
- 层名统一为：发现、策划、生产、发布、归因、通用。不再出现「制作」。
- 层与颜料对应：发现是群青 `#2F4E9C`，策划是赭石 `#9A6034`，生产是朱砂 `#C8412E`，发布是石绿 `#3E8E6E`，归因是藤黄 `#D9A21B`，通用是墨灰 `#868C94`。
- 字体：
  - 标题、大数字、技能名、平台名用 `--font-serif`（Noto Serif SC，600）。
  - 正文用 `--font-sans`，即系统字体栈。
  - 品牌字标用 `--font-brand`（Bodoni Moda 斜体 600），只用在侧栏的 Easel 字标。
- 排版禁忌：不用全大写标签；按钮和链接文字后面不加「→」；界面文案里不用 emoji；不给标题里的单个词换颜色。
- 圆角三级：控件 6px、面板 10px、浮层 14px。只有浮层和对话输入框有阴影。
- 必须尊重 `prefers-reduced-motion`；所有可交互元素在 `:focus-visible` 时显示 2px 墨色外框，外偏移 2px。
- 不改以下内容的行为：
  - `lib/api.ts`、`lib/store.ts`、`lib/whoami.ts`、`lib/linkifyOutputs.ts`、`lib/sanitize.ts`
  - `App.tsx` 的流式对话和会话持久化逻辑
  - 各页调用的接口、参数和轮询节奏
  - `localStorage` 的键名
- 界面文案用中文，写法贴近用户：说「做选题」，不说「create idea」。
- 不引入 Tailwind、CSS-in-JS 或 UI 组件库。

## 评审重点（测试覆盖不到、最可能坑到用户的五类情况）

1. **超长文本：** 会话标题、技能名、平台昵称、热点标题、文件名很长时，应该单行省略（`text-overflow: ellipsis`，并用 `title` 属性给出全文），不能撑破布局或挤掉按钮。由 Task 5 的 `ChatSessionList.test.tsx` 断言 `title` 属性；Task 12 用注入长文本的截图检查。
2. **窄屏（1024×768 及更窄）：**
   - 侧栏收成 64px 图标条，对话记录栏收起，由按钮展开。
   - 全站不能出现横向滚动条。
   - 由 Task 5 的 `layout.css` 媒体查询实现，Task 12 在 1024×768 下截图检查。
3. **流式对话进行中切页或切会话：** 会话栏移进对话页之后，流式中切到别的页再回来，消息必须继续流；流式中的会话也要能删除、归档。App 的流式逻辑不动。Task 5 的 App 接线步骤要保留原回调原样透传，Task 12 在真机上点测。
4. **字体加载失败（离线或包没装上）：**
   - 标题退到 `Songti SC` 或 `serif`，品牌字退到 `Didot` 或 `serif`，页面照常可读。
   - Task 1 的 `tokens.test.ts` 断言字体栈包含这些回退字体。
5. **接口失败或空数据：**
   - 热点拉不到（没配代理）、账号接口出错、技能列表加载失败时，要显示说明下一步怎么做的空状态，不能是空白。
   - 创作数据没有可用平台时，归因栏显示「—」。
   - Task 4、7、8 的页面测试覆盖空数据和失败分支。

## 文件结构

```
web/frontend/
  package.json                 新增依赖与 "test" 脚本
  vite.config.ts               vitest 配置（jsdom）
  index.html                   删 Google Fonts
  src/main.tsx                 引入字体 CSS；BUILD_ID → studio-1
  src/test/setup.ts            RTL cleanup
  src/lib/layers.ts            层定义、Page 类型、导航分组、页面到层的映射（唯一来源）
  src/lib/useAnalyticsPlatforms.ts   归因平台加载与 whoami 自愈（工作台和创作数据页共用）
  src/components/ui/
    Button.tsx  Tag.tsx  StatusDot.tsx  Swatch.tsx  LayerMark.tsx
    PageHeader.tsx  Panel.tsx  EmptyState.tsx  Field.tsx  Modal.tsx  Tabs.tsx
  src/components/Sidebar.tsx         重写：按层分组，不再含会话列表
  src/components/ChatSessionList.tsx 新增：会话列表（从 Sidebar 挪出）
  src/components/ChatLayout.tsx      新增：对话页两栏外壳和窄屏开关
  src/components/AnalyticsPage.tsx   新增：创作数据页（从工作台卡片搬出）
  src/components/SubNav.tsx          删除
  src/styles/
    index.css      只负责 @import
    tokens.css     设计变量和迁移期别名
    base.css       reset、排版基础、焦点、reduced-motion、关键帧
    legacy.css     原 index.css 去掉 :root 和 reset 之后的内容，逐任务删减，Task 12 删掉
    layout.css     应用外壳和侧栏
    ui/button.css  ui/field.css  ui/overlay.css  ui/primitives.css
    pages/dashboard.css  analytics.css  chat.css  skills.css  accounts.css  settings.css
          discover.css  plan.css  outputs.css  publish.css  profile.css
```

组件类名约定：
- 全站原有的通用类继续作为规范类名，在新样式文件里按新变量重写：`.btn` 系列、`.field`、`.overlay`、`.modal`、`.drawer*`、`.toast`、`.icon-btn`、`.card`、`.chip`、`.badge*`、`.page-title`、`.page-subtitle`、`.empty-state`、`.spinner`、`.loading`。
- 新组件自己的类一律加 `ui-` 前缀，避免和页面里现有的 `.panel`、`.page-head` 等类冲突：`.ui-page-header`、`.ui-panel`、`.ui-empty`、`.ui-tag`、`.ui-dot`、`.ui-swatch`、`.ui-layer-mark`、`.ui-tabs`。

## 对规格的落地说明（执行者照此实现）

- **技能库页不显示层标：** 规格 §2.1 把「技能库」列在通用层。但技能库横跨所有层，已确认的样稿也没给它层标，所以 `PAGE_LAYER` 里不给 `skills` 配层，页头不显示层标。画像页显示「通用」层标。
- **对话里的技能运行标签：** 规格 §6 写的是「层色小方块 + 技能名 + 状态」。但流式时的 `activity` 是一句自由文本，里面没有结构化的技能名和层信息。所以实现为：一个药丸形标签，前面是朱砂色（生产层）小方块，后面是原来的活动文本。不新增解析逻辑。
- **产物文件卡片：** 规格 §6 说「产物文件显示为卡片」。产物链接本来就由 `linkifyOutputs` 生成：文件链接是 `a[href*="/api/media/"]`，目录链接是 `a[href^="#/outputs/"]`。实现方式是只用 CSS 把这两类链接排成文件卡片（边框、朱砂小方块、单行省略），不改 `linkifyOutputs`。
- **组件类名：** 规格 §5 说旧的通用类「由组件取代」。实际做法是组件渲染时继续用这些规范类名，只把样式按新变量重写。页面专属的旧类在迁移完成后删除。
- **窄屏下的画像选择：** 规格 §4.1 说窄屏时画像选择「收成头像按钮」。图标条只有 64px，放下拉框不现实，所以窄屏下隐藏画像选择；要切画像可以把窗口拉宽，或在对话页头看当前画像。这样不用新增头像菜单组件。

## 执行约定

- **分支：** 在 `feat/studio-redesign` 分支上工作，每个任务结束提交一次到本地分支。推送和合并等用户确认后再做。
- **提交信息：** 格式为 `polish(web): <中文描述>` 或 `feat(web): <中文描述>`，结尾附 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- **每个任务的标准检查**（在 `web/frontend` 目录下执行）：
  ```bash
  npm test && npm run build && npm run lint
  ```
  lint 基线是 2 个既有 warning：`linkifyOutputs.ts:27` 和 `AccountsPage.tsx` 里 `openCred` 的依赖。不允许新增 warning。
- **后端测试**（仓库根目录）：`source .venv/bin/activate && python -m pytest -q`，基线是 458 passed、1 skipped。前端改动不应影响这个结果；Task 1 和 Task 12 各跑一次。
- **查看效果：** `easel web` 已在 7860 端口运行，直接读 `web/frontend/dist/`。`npm run build` 之后刷新浏览器就能看到新样式。改版期间这台机器上的 Easel 会显示半迁移状态，这是预期的。
- **测试写法：**
  - 只从 `vitest` 显式 import `describe`、`it`、`expect`、`vi`，不开 globals。
  - 页面测试用 `vi.mock('../lib/api')`（按需也 mock `../lib/whoami`），不发真实请求。mock 工厂必须包含被测组件从这些模块导入的每一个运行时值：先 `grep -n "from '../lib/api'" <组件>` 核对，计划里给出的 mock 缺了就补上。
  - 需要读 CSS 文本时用 `import css from './x.css?raw'`。

---

### Task 1：分支、测试基建、设计变量与字体

**Files:**
- Modify: `web/frontend/package.json`、`web/frontend/vite.config.ts`、`web/frontend/index.html`、`web/frontend/src/main.tsx`
- Create: `web/frontend/src/test/setup.ts`、`src/styles/tokens.css`、`src/styles/base.css`、`src/styles/tokens.test.ts`
- Rename：`src/styles/index.css` 改名为 `src/styles/legacy.css`
- Create：新的 `src/styles/index.css`

**Interfaces:**
- Produces（后续任务都会用到）：
  - CSS 变量：`--c-*`、`--layer-<key>`、`--layer-<key>-text`、`--layer-<key>-soft`、`--font-*`、`--fs-*`、`--sp-*`、`--r-*`、`--shadow-*`、`--t`、`--t-fast`、`--sidebar-width`、`--sidebar-rail`
  - `npm test` 命令
  - 迁移期的旧变量别名

- [ ] **Step 1：建分支，提交规格和计划文档**

```bash
cd /Users/xuzichuan/vscode/Easel
git checkout -b feat/studio-redesign
git add docs/superpowers/specs/2026-09-30-frontend-redesign-design.md docs/superpowers/plans/2026-09-30-frontend-redesign.md
git commit -m "docs(web): 前端改版设计规格与实施计划

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2：装依赖**

```bash
cd web/frontend
npm install -D vitest@^5.0.2 jsdom@^30.1.1 @testing-library/react@^16.3.3 @testing-library/dom@^10.4.2
npm install @fontsource/noto-serif-sc@^5.3.0 @fontsource/bodoni-moda@^5.3.0
```

如果 npm 11 提示有安装脚本需要批准，执行 `npm install-scripts approve <包@版本>` 后再 `npm rebuild`。

- [ ] **Step 3：配置 vitest**

在 `package.json` 的 `scripts` 里加上 `"test": "vitest run"`。

`vite.config.ts` 整个替换为：

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',  // 相对路径，适配 proxy
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

`src/test/setup.ts`：

```ts
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// vitest 不开 globals 时 RTL 不会自动清理，这里手动注册
afterEach(() => cleanup());
```

- [ ] **Step 4：写失败的变量契约测试**

`src/styles/tokens.test.ts`：

```ts
import { describe, it, expect } from 'vitest';
import css from './tokens.css?raw';

const REQUIRED: Record<string, string> = {
  '--c-canvas': '#F6F7F5',
  '--c-surface': '#FFFFFF',
  '--c-side': '#EEF0EC',
  '--c-sunken': '#F2F3F0',
  '--c-rule': '#E3E6E1',
  '--c-rule-strong': '#D2D6D0',
  '--c-ink': '#1F2328',
  '--c-ink-2': '#4B5159',
  '--c-ink-3': '#868C94',
  '--c-on-ink': '#FFFFFF',
  '--c-danger': '#B4312A',
  '--layer-discover': '#2F4E9C',
  '--layer-plan': '#9A6034',
  '--layer-produce': '#C8412E',
  '--layer-publish': '#3E8E6E',
  '--layer-attribute': '#D9A21B',
  '--layer-general': '#868C94',
  '--layer-plan-text': '#8A5530',
  '--layer-produce-text': '#B23A29',
  '--layer-publish-text': '#2F7358',
  '--layer-attribute-text': '#8A650C',
};

describe('设计变量契约', () => {
  it.each(Object.entries(REQUIRED))('%s 取值为 %s', (name, value) => {
    expect(css).toMatch(new RegExp(`${name}:\\s*${value};`, 'i'));
  });

  it('每一层都有本色、文字色、浅底三件套', () => {
    for (const k of ['discover', 'plan', 'produce', 'publish', 'attribute', 'general']) {
      for (const suffix of ['', '-text', '-soft']) {
        expect(css).toContain(`--layer-${k}${suffix}:`);
      }
    }
  });

  it('字体栈带回退：标题退到 Songti SC，品牌字退到 Didot', () => {
    expect(css).toMatch(/--font-serif:[^;]*'Songti SC'[^;]*serif;/);
    expect(css).toMatch(/--font-brand:[^;]*'Didot'[^;]*serif;/);
    expect(css).toMatch(/--font-sans:[^;]*'PingFang SC'[^;]*sans-serif;/);
  });
});
```

运行：`npm test`。预期：失败，报错找不到 `./tokens.css?raw`（文件还不存在）。

- [ ] **Step 5：写 `src/styles/tokens.css`**

```css
/* ============================================================
 * 设计变量：颜色只允许在这个文件里出现
 * 规格：docs/superpowers/specs/2026-09-30-frontend-redesign-design.md §2
 * ============================================================ */
:root {
  /* ---- 中性色 ---- */
  --c-canvas: #F6F7F5;       /* 应用底色（画布） */
  --c-surface: #FFFFFF;      /* 面板、输入框、弹窗（纸面） */
  --c-side: #EEF0EC;         /* 主侧栏 */
  --c-sunken: #F2F3F0;       /* 页内次级栏、空状态底 */
  --c-tint: #EEF0EC;         /* 用户消息气泡 */
  --c-hover: rgba(31, 35, 40, 0.05);
  --c-rule: #E3E6E1;
  --c-rule-strong: #D2D6D0;
  --c-ink: #1F2328;
  --c-ink-hover: #343A42;
  --c-ink-2: #4B5159;
  --c-ink-3: #868C94;
  --c-on-ink: #FFFFFF;
  --c-scrim: rgba(31, 35, 40, 0.38);

  /* ---- 层色（矿物色）：本色 / 文字色 / 浅底 ---- */
  --layer-discover: #2F4E9C;
  --layer-discover-text: #2F4E9C;
  --layer-discover-soft: rgba(47, 78, 156, 0.12);
  --layer-plan: #9A6034;
  --layer-plan-text: #8A5530;
  --layer-plan-soft: rgba(154, 96, 52, 0.12);
  --layer-produce: #C8412E;
  --layer-produce-text: #B23A29;
  --layer-produce-soft: rgba(200, 65, 46, 0.12);
  --layer-publish: #3E8E6E;
  --layer-publish-text: #2F7358;
  --layer-publish-soft: rgba(62, 142, 110, 0.12);
  --layer-attribute: #D9A21B;
  --layer-attribute-text: #8A650C;
  --layer-attribute-soft: rgba(217, 162, 27, 0.14);
  --layer-general: #868C94;
  --layer-general-text: #4B5159;
  --layer-general-soft: rgba(134, 140, 148, 0.14);

  /* ---- 语义色（复用层色） ---- */
  --c-ok: #3E8E6E;
  --c-ok-soft: rgba(62, 142, 110, 0.12);
  --c-warn: #8A650C;
  --c-warn-soft: rgba(217, 162, 27, 0.14);
  --c-danger: #B4312A;
  --c-danger-soft: rgba(180, 49, 42, 0.10);
  --c-focus: #1F2328;

  /* ---- 字体 ---- */
  --font-brand: 'Bodoni Moda', 'Didot', 'Bodoni 72', serif;
  --font-serif: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', serif;
  --font-sans: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'SF Mono', Menlo, Consolas, monospace;
  --fs-12: 12px;
  --fs-13: 13px;
  --fs-14: 14px;
  --fs-16: 16px;
  --fs-20: 20px;
  --fs-26: 26px;
  --fs-34: 34px;
  --lh-body: 1.65;
  --lh-title: 1.25;

  /* ---- 间距（4px 基准） ---- */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;

  /* ---- 圆角 / 阴影 / 动效 ---- */
  --r-control: 6px;
  --r-panel: 10px;
  --r-overlay: 14px;
  --shadow-overlay: 0 24px 60px -20px rgba(31, 35, 40, 0.35), 0 2px 8px rgba(31, 35, 40, 0.08);
  --shadow-pop: 0 12px 32px -12px rgba(31, 35, 40, 0.28);
  --shadow-composer: 0 8px 24px -16px rgba(31, 35, 40, 0.30);
  --ease: cubic-bezier(0.4, 0, 0.2, 1);
  --t-fast: 0.12s var(--ease);
  --t: 0.2s var(--ease);

  /* ---- 布局 ---- */
  --sidebar-width: 232px;
  --sidebar-rail: 64px;
}

/* ============================================================
 * 迁移期旧变量别名：legacy.css 和尚未迁移的内联样式还在用。
 * Task 12 全部迁移完后整段删除。
 * ============================================================ */
:root {
  --bg: var(--c-canvas);
  --bg-elev: var(--c-surface);
  --surface: var(--c-surface);
  --surface-2: var(--c-sunken);
  --surface-hover: var(--c-hover);
  --border: var(--c-rule);
  --border-strong: var(--c-rule-strong);
  --text: var(--c-ink);
  --text-secondary: var(--c-ink-2);
  --text-tertiary: var(--c-ink-3);
  --accent-start: var(--c-ink);
  --accent-end: var(--c-ink);
  --accent-soft: var(--c-hover);
  --accent-gradient: var(--c-ink);
  --accent-gradient-soft: var(--c-sunken);
  --green: var(--c-ok);
  --green-soft: var(--c-ok-soft);
  --amber: var(--c-warn);
  --amber-soft: var(--c-warn-soft);
  --red: var(--c-danger);
  --red-soft: var(--c-danger-soft);
  --trend-up: var(--c-ok);
  --trend-down: var(--c-danger);
  --code-bg: var(--c-sunken);
  --radius-sm: 4px;
  --radius: var(--r-control);
  --radius-lg: var(--r-panel);
  --radius-xl: var(--r-overlay);
  --shadow-sm: none;
  --shadow-md: var(--shadow-pop);
  --shadow-lg: var(--shadow-overlay);
  --glow: 0 0 0 1px var(--c-rule-strong);
}
```

运行：`npm test`。预期：`tokens.test.ts` 全部通过。

- [ ] **Step 6：`legacy.css` 改名与裁剪**

```bash
git mv src/styles/index.css src/styles/legacy.css
```

1. 删掉 `legacy.css` 开头从第 1 行到 `/* ============ Layout ============ */` 注释之前的全部内容，即原来的 `:root`、reset、`html/body`、滚动条、`@keyframes`。这些由 `tokens.css` 和 `base.css` 接管。
2. 执行 `grep -n 'gradient' src/styles/legacy.css`，按下表逐个选择器改掉装饰性渐变：

| 选择器 | 改成 |
|---|---|
| `.sidebar` 的 `background: linear-gradient(...)` | `background: var(--c-side);` |
| `.main-content, .page-host` 的三层 `radial-gradient` 加 `#fff` | `background: var(--c-canvas);` |
| 对话欢迎区（`.chat-hero` 或它所在的规则）的三层 `radial-gradient` | `background: none;` |
| 进度条的 `linear-gradient(90deg, var(--accent-start), var(--accent-end))` | `background: var(--c-ink);` |
| `.brush-*` 两处 `linear-gradient(135deg, …)` | `background: var(--c-sunken);`，同时把 `border` 改为 `1px solid var(--c-rule)` |
| `background: var(--accent-gradient-soft); color: #303238;` | `background: var(--c-sunken); color: var(--c-ink);` |
| `.chat-input-area` 的 `linear-gradient(180deg, transparent, var(--bg) 40%)` | `background: var(--c-canvas);` |
| `.account-avatar-fallback` 的渐变 | 保留（头像占位允许用渐变） |
| `var(--accent-gradient)` 的引用 | 不动（别名已指向墨色） |

完成后执行 `grep -c 'radial-gradient' src/styles/legacy.css`，预期输出 `0`。

- [ ] **Step 7：写 `src/styles/base.css`**

```css
/* 基础层：reset、排版、焦点、reduced-motion、关键帧 */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, #root { height: 100%; width: 100%; overflow: hidden; }

body {
  font-family: var(--font-sans);
  font-size: var(--fs-14);
  line-height: var(--lh-body);
  color: var(--c-ink);
  background: var(--c-canvas);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

h1, h2, h3, h4 { font-family: var(--font-serif); font-weight: 600; line-height: var(--lh-title); }

button, input, select, textarea { font: inherit; color: inherit; }

code, pre, kbd, samp { font-family: var(--font-mono); }

::selection { background: var(--layer-discover-soft); }

:focus-visible { outline: 2px solid var(--c-focus); outline-offset: 2px; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--c-rule-strong); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--c-ink-3); }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes blink { 50% { opacity: 0; } }
@keyframes slideInRight { from { transform: translateX(24px); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes popIn { from { transform: scale(0.97); opacity: 0; } to { transform: none; opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 8：新的 `src/styles/index.css`、字体引入、`index.html`**

`src/styles/index.css`：

```css
/* 样式入口：只负责按顺序 @import。legacy 在新层之前，同优先级时新样式胜出。 */
@import './tokens.css';
@import './base.css';
@import './legacy.css';
```

`src/main.tsx` 顶部，在 `import './index.css'` 之前加：

```ts
import '@fontsource/noto-serif-sc/600.css';
import '@fontsource/bodoni-moda/latin-600-italic.css';
```

`index.html`：删掉全部 `fonts.googleapis.com`、`fonts.gstatic.com` 的 `<link>`（两组 preconnect 和两个 stylesheet），其余保持原样，包括补结尾斜杠的脚本。

- [ ] **Step 9：检查**

```bash
npm test && npm run build && npm run lint
grep -c 'fonts.googleapis' index.html   # 预期 0
ls dist/assets | grep -c 'noto-serif-sc' # 预期 > 0
cd ../.. && source .venv/bin/activate && python -m pytest -q   # 预期 458 passed, 1 skipped
```

刷新 http://127.0.0.1:7860/ 检查：
- 背景变成纯画布色，没有模糊色块。
- 主按钮是墨色。
- 页面标题是宋体。

- [ ] **Step 10：提交**

```bash
git add -A web/frontend
git commit -m "polish(web): 设计变量、自托管字体与测试基建，全站换画室底色

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2：层定义与基础组件

**Files:**
- Create：
  - `src/lib/layers.ts`、`src/lib/layers.test.ts`
  - `src/components/ui/Button.tsx`、`Tag.tsx`、`StatusDot.tsx`、`Swatch.tsx`、`LayerMark.tsx`、`PageHeader.tsx`、`Panel.tsx`、`EmptyState.tsx`、`Field.tsx`
  - `src/components/ui/Button.test.tsx`、`src/components/ui/PageHeader.test.tsx`
  - `src/styles/ui/button.css`、`ui/field.css`、`ui/primitives.css`
- Modify：
  - `src/components/Sidebar.tsx`：`Page` 类型改为从 `lib/layers` 转出
  - `src/styles/index.css`
  - `src/styles/legacy.css`：删掉「Reusable components」段里按钮、徽章、chip、输入框、卡片、标题、空状态这几部分，只保留 `/* Modal / drawer */` 起到 toast 为止（它们由 Task 3 接管）

**Interfaces:**
- Produces：
  - `lib/layers.ts` 导出：
    - `type LayerKey = 'discover' | 'plan' | 'produce' | 'publish' | 'attribute' | 'general'`
    - `type Page = 'dashboard' | 'chat' | 'trends' | 'ideas' | 'calendar' | 'publish' | 'breakdown' | 'skills' | 'outputs' | 'accounts' | 'profile' | 'analytics'`
    - `ALL_PAGES: Page[]`
    - `LAYERS: LayerInfo[]`，其中 `LayerInfo = { key, name, pigment, desc }`
    - `PIPELINE: LayerKey[]`（五层，按流程顺序）
    - `layerInfo(key: LayerKey): LayerInfo`
    - `isLayerKey(v: string): v is LayerKey`
    - `PAGE_LAYER: Partial<Record<Page, LayerKey>>`
    - `NAV_GROUPS: NavGroup[]`，其中 `NavGroup = { layer?: LayerKey; items: { page: Page; label: string }[] }`
  - `ui/Button`：
    - 默认导出组件，props 为 `ButtonProps = ButtonHTMLAttributes & { variant?: 'primary'|'secondary'|'ghost'|'danger'; size?: 'sm'|'md'; icon?: ReactNode; loading?: boolean; block?: boolean }`
    - 另导出 `buttonClass(variant, size, block): string`
  - `ui/Tag`：`<Tag tone?: 'neutral'|'ok'|'warn'|'danger'|LayerKey>`
  - `ui/StatusDot`：`<StatusDot tone: 'ok'|'idle'|'warn'|'danger'>{文字}</StatusDot>`
  - `ui/Swatch`：`<Swatch layer: LayerKey size?: 'sm'|'md' />`
  - `ui/LayerMark`：`<LayerMark layer: LayerKey />`
  - `ui/PageHeader`：`<PageHeader layer? title description? actions? />`
  - `ui/Panel`：`<Panel title? action?: { label: string; onClick: () => void } className? >`
  - `ui/EmptyState`：`<EmptyState text action?: { label: string; onClick: () => void } />`
  - `ui/Field`：`Input`、`Select`、`Textarea`，透传原生 props，类名为 `field`

- [ ] **Step 1：写失败的 `layers.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
import { ALL_PAGES, LAYERS, NAV_GROUPS, PAGE_LAYER, PIPELINE, isLayerKey, layerInfo } from './layers';

describe('layers', () => {
  it('五层流水线按顺序：发现、策划、生产、发布、归因', () => {
    expect(PIPELINE.map((k) => layerInfo(k).name)).toEqual(['发现', '策划', '生产', '发布', '归因']);
  });

  it('不再出现「制作」', () => {
    expect(LAYERS.map((l) => l.name)).not.toContain('制作');
  });

  it('每个页面恰好出现在一个导航分组里', () => {
    const seen = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.page));
    expect([...seen].sort()).toEqual([...ALL_PAGES].sort());
    expect(new Set(seen).size).toBe(seen.length);
  });

  it('带层的分组里，每一页的 PAGE_LAYER 都等于这一组的层', () => {
    for (const g of NAV_GROUPS) {
      if (!g.layer) continue;
      for (const it of g.items) expect(PAGE_LAYER[it.page]).toBe(g.layer);
    }
  });

  it('五层流水线每层都有导航分组', () => {
    const grouped = NAV_GROUPS.map((g) => g.layer).filter(Boolean);
    expect(grouped).toEqual(PIPELINE);
  });

  it('技能库不配层标，画像是通用层', () => {
    expect(PAGE_LAYER.skills).toBeUndefined();
    expect(PAGE_LAYER.profile).toBe('general');
  });

  it('isLayerKey 能识别合法和非法的 key', () => {
    expect(isLayerKey('produce')).toBe(true);
    expect(isLayerKey('other')).toBe(false);
  });
});
```

运行：`npm test -- src/lib/layers.test.ts`。预期：失败，报错找不到 `./layers`。

- [ ] **Step 2：写 `src/lib/layers.ts`**

```ts
/**
 * 流水线层与页面的唯一定义：侧栏分组、页头层标、工作台色条、技能库分段都从这里取。
 * 颜色不在这里——CSS 变量 `--layer-<key>` / `-text` / `-soft` 见 styles/tokens.css。
 */
export type LayerKey = 'discover' | 'plan' | 'produce' | 'publish' | 'attribute' | 'general';

export type Page =
  | 'dashboard' | 'chat' | 'trends' | 'ideas' | 'calendar' | 'publish' | 'breakdown'
  | 'skills' | 'outputs' | 'accounts' | 'profile' | 'analytics';

export const ALL_PAGES: Page[] = [
  'dashboard', 'chat', 'trends', 'ideas', 'calendar', 'publish', 'breakdown',
  'skills', 'outputs', 'accounts', 'profile', 'analytics',
];

export interface LayerInfo {
  key: LayerKey;
  name: string;      // 中文层名
  pigment: string;   // 矿物色名
  desc: string;      // 一句话说明（技能库分段、提示用）
}

export const LAYERS: LayerInfo[] = [
  { key: 'discover', name: '发现', pigment: '群青', desc: '找热点、看同行、盯平台规则' },
  { key: 'plan', name: '策划', pigment: '赭石', desc: '定选题、排日程、做规划' },
  { key: 'produce', name: '生产', pigment: '朱砂', desc: '写文案、做图、剪视频、配音' },
  { key: 'publish', name: '发布', pigment: '石绿', desc: '多平台发布与账号管理' },
  { key: 'attribute', name: '归因', pigment: '藤黄', desc: '看数据、做复盘' },
  { key: 'general', name: '通用', pigment: '墨灰', desc: '画像、素材、模板等基础能力' },
];

/** 五层流水线（不含通用），按流程先后。 */
export const PIPELINE: LayerKey[] = ['discover', 'plan', 'produce', 'publish', 'attribute'];

const BY_KEY: Record<LayerKey, LayerInfo> = Object.fromEntries(
  LAYERS.map((l) => [l.key, l]),
) as Record<LayerKey, LayerInfo>;

export function layerInfo(key: LayerKey): LayerInfo {
  return BY_KEY[key];
}

export function isLayerKey(v: string): v is LayerKey {
  return v in BY_KEY;
}

/** 页面所属层：决定页头层标。技能库横跨所有层，不配。 */
export const PAGE_LAYER: Partial<Record<Page, LayerKey>> = {
  trends: 'discover',
  breakdown: 'discover',
  ideas: 'plan',
  calendar: 'plan',
  outputs: 'produce',
  publish: 'publish',
  accounts: 'publish',
  analytics: 'attribute',
  profile: 'general',
};

export interface NavItem { page: Page; label: string; }
export interface NavGroup { layer?: LayerKey; items: NavItem[]; }

/** 侧栏导航：无 layer 的组不显示组名。 */
export const NAV_GROUPS: NavGroup[] = [
  { items: [{ page: 'dashboard', label: '工作台' }, { page: 'chat', label: '对话' }] },
  { layer: 'discover', items: [{ page: 'trends', label: '热点雷达' }, { page: 'breakdown', label: '爆款拆解' }] },
  { layer: 'plan', items: [{ page: 'ideas', label: '选题库' }, { page: 'calendar', label: '内容日历' }] },
  { layer: 'produce', items: [{ page: 'outputs', label: '内容库' }] },
  { layer: 'publish', items: [{ page: 'publish', label: '发布中心' }, { page: 'accounts', label: '账号' }] },
  { layer: 'attribute', items: [{ page: 'analytics', label: '创作数据' }] },
  { items: [{ page: 'skills', label: '技能库' }, { page: 'profile', label: '画像' }] },
];
```

运行：`npm test -- src/lib/layers.test.ts`。预期：全部通过。

- [ ] **Step 3：`Sidebar.tsx` 改为从 `layers` 转出 `Page`**

把 `Sidebar.tsx` 第 12 行 `export type Page = ...;` 替换为：

```ts
export type { Page } from '../lib/layers';
```

同时在文件顶部 import 区加一行 `import type { Page } from '../lib/layers';`，文件内部还要用这个类型。其余导入 `Page from './Sidebar'` 的文件不用改。

运行：`npm run build`。预期：通过。新增的 `'analytics'` 只会让 `App.tsx` 的 `switch` 多走一次 `default` 分支，目前没有任何入口会跳到这个页面。

- [ ] **Step 4：写失败的组件测试**

`src/components/ui/Button.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Button, { buttonClass } from './Button';

describe('Button', () => {
  it('变体和尺寸映射到规范类名', () => {
    expect(buttonClass('primary', 'md', false)).toBe('btn btn-primary');
    expect(buttonClass('secondary', 'sm', false)).toBe('btn btn-sm');
    expect(buttonClass('ghost', 'md', true)).toBe('btn btn-ghost btn-block');
    expect(buttonClass('danger', 'sm', false)).toBe('btn btn-danger btn-sm');
  });

  it('默认 type=button、次要样式', () => {
    render(<Button>取消</Button>);
    const b = screen.getByRole('button', { name: '取消' });
    expect(b.getAttribute('type')).toBe('button');
    expect(b.className).toBe('btn');
  });

  it('loading 时禁用并标记 aria-busy，点击不触发', () => {
    const onClick = vi.fn();
    render(<Button variant="primary" loading onClick={onClick}>保存</Button>);
    const b = screen.getByRole('button', { name: '保存' });
    expect((b as HTMLButtonElement).disabled).toBe(true);
    expect(b.getAttribute('aria-busy')).toBe('true');
    fireEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });
});
```

`src/components/ui/PageHeader.test.tsx`：

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PageHeader from './PageHeader';

describe('PageHeader', () => {
  it('有 layer 时在标题上方显示层标', () => {
    const { container } = render(<PageHeader layer="publish" title="账号" description="扫码登录" />);
    expect(screen.getByRole('heading', { level: 1, name: '账号' })).toBeTruthy();
    const mark = container.querySelector('.ui-layer-mark');
    expect(mark?.textContent).toBe('发布');
    expect(mark?.querySelector('.ui-swatch')?.getAttribute('data-layer')).toBe('publish');
  });

  it('没有 layer 时不渲染层标', () => {
    const { container } = render(<PageHeader title="技能库" />);
    expect(container.querySelector('.ui-layer-mark')).toBeNull();
  });
});
```

运行：`npm test`。预期：失败，这些组件文件还不存在。

- [ ] **Step 5：写组件**

`src/components/ui/Button.tsx`：

```tsx
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  loading?: boolean;
  block?: boolean;
}

/** 规范类名：页面里还没换成组件的按钮也可以直接用这个函数拼类名。 */
export function buttonClass(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', block = false): string {
  return [
    'btn',
    variant === 'secondary' ? '' : `btn-${variant}`,
    size === 'sm' ? 'btn-sm' : '',
    block ? 'btn-block' : '',
  ].filter(Boolean).join(' ');
}

export default function Button({
  variant = 'secondary', size = 'md', icon, loading = false, block = false,
  className, children, disabled, type = 'button', ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[buttonClass(variant, size, block), className].filter(Boolean).join(' ')}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="btn-spinner" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}
```

`src/components/ui/Swatch.tsx`：

```tsx
import type { LayerKey } from '../../lib/layers';

/** 层色小方块：颜色由 CSS 按 data-layer 取 --layer-<key>。 */
export default function Swatch({ layer, size = 'md' }: { layer: LayerKey; size?: 'sm' | 'md' }) {
  return <span className={`ui-swatch${size === 'sm' ? ' ui-swatch-sm' : ''}`} data-layer={layer} aria-hidden="true" />;
}
```

`src/components/ui/LayerMark.tsx`：

```tsx
import type { LayerKey } from '../../lib/layers';
import { layerInfo } from '../../lib/layers';
import Swatch from './Swatch';

export default function LayerMark({ layer }: { layer: LayerKey }) {
  return <span className="ui-layer-mark"><Swatch layer={layer} />{layerInfo(layer).name}</span>;
}
```

`src/components/ui/Tag.tsx`：

```tsx
import type { ReactNode } from 'react';
import type { LayerKey } from '../../lib/layers';

export type TagTone = 'neutral' | 'ok' | 'warn' | 'danger' | LayerKey;

export default function Tag({ tone = 'neutral', title, children }: { tone?: TagTone; title?: string; children: ReactNode }) {
  return <span className="ui-tag" data-tone={tone} title={title}>{children}</span>;
}
```

`src/components/ui/StatusDot.tsx`：

```tsx
import type { ReactNode } from 'react';

export type DotTone = 'ok' | 'idle' | 'warn' | 'danger';

export default function StatusDot({ tone, children }: { tone: DotTone; children: ReactNode }) {
  return <span className="ui-dot" data-tone={tone}><i aria-hidden="true" />{children}</span>;
}
```

`src/components/ui/PageHeader.tsx`：

```tsx
import type { ReactNode } from 'react';
import type { LayerKey } from '../../lib/layers';
import LayerMark from './LayerMark';

interface PageHeaderProps {
  layer?: LayerKey;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export default function PageHeader({ layer, title, description, actions }: PageHeaderProps) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header-main">
        {layer && <LayerMark layer={layer} />}
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-subtitle">{description}</p>}
      </div>
      {actions && <div className="ui-page-header-actions">{actions}</div>}
    </header>
  );
}
```

`src/components/ui/Panel.tsx`：

```tsx
import type { ReactNode } from 'react';

interface PanelProps {
  title?: ReactNode;
  action?: { label: string; onClick: () => void };
  className?: string;
  children: ReactNode;
}

export default function Panel({ title, action, className, children }: PanelProps) {
  return (
    <section className={['ui-panel', className].filter(Boolean).join(' ')}>
      {(title || action) && (
        <header className="ui-panel-head">
          {title && <h3 className="ui-panel-title">{title}</h3>}
          {action && <button type="button" className="ui-panel-action" onClick={action.onClick}>{action.label}</button>}
        </header>
      )}
      {children}
    </section>
  );
}
```

`src/components/ui/EmptyState.tsx`：

```tsx
import type { ReactNode } from 'react';
import Button from './Button';

interface EmptyStateProps {
  text: ReactNode;
  action?: { label: string; onClick: () => void };
}

/** 空状态：文案要写清楚下一步做什么。 */
export default function EmptyState({ text, action }: EmptyStateProps) {
  return (
    <div className="ui-empty">
      <p>{text}</p>
      {action && <Button size="sm" onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}
```

`src/components/ui/Field.tsx`：

```tsx
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

const cls = (extra?: string) => ['field', extra].filter(Boolean).join(' ');

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cls(className)} {...rest} />;
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cls(className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cls(className)} {...rest} />;
}
```

运行：`npm test`。预期：`Button.test.tsx`、`PageHeader.test.tsx`、`layers.test.ts`、`tokens.test.ts` 全部通过。

- [ ] **Step 6：写组件样式，删掉 legacy 里的同名段落**

`src/styles/ui/button.css`：

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  height: 34px; padding: 0 14px;
  font: 500 var(--fs-13)/1 var(--font-sans);
  color: var(--c-ink); background: var(--c-surface);
  border: 1px solid var(--c-rule-strong); border-radius: var(--r-control);
  box-shadow: none; filter: none;
  cursor: pointer; white-space: nowrap; text-decoration: none;
  transition: background var(--t-fast), border-color var(--t-fast), color var(--t-fast);
}
.btn:hover:not(:disabled) { background: var(--c-sunken); border-color: var(--c-ink-3); }
.btn:active:not(:disabled) { transform: translateY(1px); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 10px; font-size: var(--fs-12); }
.btn-block { display: flex; width: 100%; }
.btn-primary { background: var(--c-ink); border-color: var(--c-ink); color: var(--c-on-ink); }
.btn-primary:hover:not(:disabled) { background: var(--c-ink-hover); border-color: var(--c-ink-hover); }
.btn-ghost { background: transparent; border-color: transparent; color: var(--c-ink-2); }
.btn-ghost:hover:not(:disabled) { background: var(--c-hover); border-color: transparent; color: var(--c-ink); }
.btn-danger { color: var(--c-danger); }
.btn-danger:hover:not(:disabled) { background: var(--c-danger-soft); border-color: var(--c-danger); }
.btn-spinner {
  width: 12px; height: 12px; border-radius: 50%;
  border: 1.5px solid currentColor; border-right-color: transparent;
  animation: spin 0.7s linear infinite;
}
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; padding: 0;
  background: none; border: none; border-radius: var(--r-control);
  color: var(--c-ink-2); font-size: 20px; line-height: 1; cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.icon-btn:hover { color: var(--c-ink); background: var(--c-hover); }
```

`src/styles/ui/field.css`：

```css
.field {
  width: 100%; min-height: 36px; padding: 7px 12px;
  background: var(--c-surface); color: var(--c-ink);
  border: 1px solid var(--c-rule-strong); border-radius: var(--r-control);
  font-size: var(--fs-14); line-height: 1.5; outline: none;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.field:hover:not(:disabled) { border-color: var(--c-ink-3); }
.field:focus { border-color: var(--c-ink); box-shadow: 0 0 0 3px var(--c-hover); }
.field:disabled { background: var(--c-sunken); color: var(--c-ink-3); cursor: not-allowed; }
.field::placeholder { color: var(--c-ink-3); }
textarea.field { resize: vertical; min-height: 90px; }
select.field { cursor: pointer; }
```

`src/styles/ui/primitives.css`：

```css
/* ---- 层色小方块 / 层标 ---- */
.ui-swatch { display: inline-block; width: 9px; height: 9px; border-radius: 2px; flex: none; background: var(--layer-general); }
.ui-swatch-sm { width: 7px; height: 7px; }
.ui-swatch[data-layer="discover"] { background: var(--layer-discover); }
.ui-swatch[data-layer="plan"] { background: var(--layer-plan); }
.ui-swatch[data-layer="produce"] { background: var(--layer-produce); }
.ui-swatch[data-layer="publish"] { background: var(--layer-publish); }
.ui-swatch[data-layer="attribute"] { background: var(--layer-attribute); }
.ui-swatch[data-layer="general"] { background: var(--layer-general); }
.ui-layer-mark { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-12); color: var(--c-ink-3); }

/* ---- 标签 ---- */
.ui-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 7px; border-radius: 4px;
  font-size: var(--fs-12); line-height: 1.6; white-space: nowrap;
  color: var(--c-ink-2); background: var(--c-sunken);
}
.ui-tag[data-tone="ok"] { color: var(--c-ok); background: var(--c-ok-soft); }
.ui-tag[data-tone="warn"] { color: var(--c-warn); background: var(--c-warn-soft); }
.ui-tag[data-tone="danger"] { color: var(--c-danger); background: var(--c-danger-soft); }
.ui-tag[data-tone="discover"] { color: var(--layer-discover-text); background: var(--layer-discover-soft); }
.ui-tag[data-tone="plan"] { color: var(--layer-plan-text); background: var(--layer-plan-soft); }
.ui-tag[data-tone="produce"] { color: var(--layer-produce-text); background: var(--layer-produce-soft); }
.ui-tag[data-tone="publish"] { color: var(--layer-publish-text); background: var(--layer-publish-soft); }
.ui-tag[data-tone="attribute"] { color: var(--layer-attribute-text); background: var(--layer-attribute-soft); }
.ui-tag[data-tone="general"] { color: var(--layer-general-text); background: var(--layer-general-soft); }

/* ---- 状态点 ---- */
.ui-dot { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-13); color: var(--c-ink-2); white-space: nowrap; }
.ui-dot i { width: 7px; height: 7px; border-radius: 50%; background: var(--c-rule-strong); flex: none; }
.ui-dot[data-tone="ok"] i { background: var(--c-ok); }
.ui-dot[data-tone="warn"] i { background: var(--layer-attribute); }
.ui-dot[data-tone="danger"] i { background: var(--c-danger); }

/* ---- 页头 ---- */
.ui-page-header { display: flex; align-items: flex-end; gap: var(--sp-4); margin-bottom: var(--sp-6); }
.ui-page-header-main { min-width: 0; }
.ui-page-header-main .ui-layer-mark { margin-bottom: var(--sp-1); }
.ui-page-header-actions { margin-left: auto; display: flex; gap: var(--sp-2); flex-wrap: wrap; }
.page-title { font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-26); line-height: var(--lh-title); letter-spacing: 0.5px; color: var(--c-ink); }
.page-subtitle { margin-top: var(--sp-1); font-size: var(--fs-13); color: var(--c-ink-2); max-width: 72ch; }

/* ---- 面板 ---- */
.ui-panel { background: var(--c-surface); border: 1px solid var(--c-rule); border-radius: var(--r-panel); padding: 16px 18px; min-width: 0; }
.ui-panel-head { display: flex; align-items: baseline; gap: var(--sp-2); margin-bottom: var(--sp-3); }
.ui-panel-title { font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-16); }
.ui-panel-action {
  margin-left: auto; background: none; border: none; padding: 0; cursor: pointer;
  font-size: var(--fs-12); color: var(--c-ink-3); border-bottom: 1px solid transparent;
}
.ui-panel-action:hover { color: var(--c-ink); border-bottom-color: var(--c-rule-strong); }

/* ---- 空状态 ---- */
.ui-empty { padding: var(--sp-4); border-radius: 8px; background: var(--c-sunken); color: var(--c-ink-2); font-size: var(--fs-13); }
.ui-empty .btn { margin-top: var(--sp-3); }

/* ---- 规范类：卡片 / chip / 徽章 / 分段标题 / 通用空状态 ---- */
.card { background: var(--c-surface); border: 1px solid var(--c-rule); border-radius: var(--r-panel); box-shadow: none; transition: border-color var(--t-fast); }
.card-hover { cursor: pointer; }
.card-hover:hover { border-color: var(--c-ink-3); transform: none; box-shadow: none; }
.chip {
  padding: 4px 12px; border-radius: var(--r-control); font-size: var(--fs-13); cursor: pointer;
  border: 1px solid var(--c-rule-strong); background: var(--c-surface); color: var(--c-ink-2);
  transition: border-color var(--t-fast), background var(--t-fast), color var(--t-fast);
}
.chip:hover { border-color: var(--c-ink-3); color: var(--c-ink); }
.chip.active { background: var(--c-ink); border-color: var(--c-ink); color: var(--c-on-ink); }
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 7px; border-radius: 4px; border: none;
  font-size: var(--fs-12); font-weight: 500; line-height: 1.6;
  color: var(--c-ink-2); background: var(--c-sunken);
}
.badge-accent { color: var(--c-ink); background: var(--c-hover); }
.badge-warn { color: var(--c-warn); background: var(--c-warn-soft); }
.badge-ok { color: var(--c-ok); background: var(--c-ok-soft); }
.section-title {
  display: flex; align-items: baseline; gap: var(--sp-2);
  margin: var(--sp-6) 0 var(--sp-3);
  font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-16);
  color: var(--c-ink); text-transform: none; letter-spacing: 0;
}
.section-title::after { content: ''; flex: 1; height: 1px; background: var(--c-rule); align-self: center; }
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; gap: var(--sp-3); padding: 40px; text-align: center; color: var(--c-ink-2);
}
.empty-state .empty-icon { font-size: 40px; opacity: 0.3; }
.empty-state h3 { color: var(--c-ink); font-size: var(--fs-16); }
.empty-state p { font-size: var(--fs-13); max-width: 40ch; }
.spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid var(--c-rule-strong); border-top-color: var(--c-ink);
  animation: spin 0.8s linear infinite;
}
```

在 `legacy.css` 的「Reusable components」段里，删掉从 `.btn {` 到 `.empty-state p {…}` 为止的全部规则，即按钮、徽章、chip、输入框、卡片、分段标题、页面标题、空状态。`/* Modal / drawer */` 注释到 `.toast .toast-icon` 为止的内容先保留。

`src/styles/index.css` 末尾追加：

```css
@import './ui/button.css';
@import './ui/field.css';
@import './ui/primitives.css';
```

注意：CSS 规定 `@import` 必须写在文件最前面。本文件只有 `@import`，按顺序追加即可。

- [ ] **Step 7：检查并提交**

```bash
npm test && npm run build && npm run lint
```

刷新 7860 端口，检查各页的按钮、徽章、输入框已经是新样式，没有样式丢失的裸按钮。

```bash
git add -A web/frontend
git commit -m "feat(web): 层定义 lib/layers 与基础组件（按钮、标签、状态点、页头、面板、空状态、输入框）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3：弹窗与标签页组件

**Files:**
- Create：
  - `src/components/ui/Modal.tsx`、`src/components/ui/Tabs.tsx`
  - `src/components/ui/Modal.test.tsx`、`src/components/ui/Tabs.test.tsx`
  - `src/styles/ui/overlay.css`
- Modify：
  - `src/App.tsx`：首次使用的欢迎弹窗改用 `Modal`，并去掉 👋
  - `src/styles/legacy.css`：删掉 `/* Modal / drawer */` 到 `.toast .toast-icon` 为止的规则
  - `src/styles/index.css`

**Interfaces:**
- Consumes：Task 2 的 `Button`。
- Produces：
  - `Modal`，props 为 `{ title?: ReactNode; onClose: () => void; width?: number; footer?: ReactNode; className?: string; closeOnBackdrop?: boolean; children: ReactNode }`
    - 挂载即打开，由调用方条件渲染控制。
    - Esc 关闭；打开时焦点移入；卸载后焦点回到打开前的元素。
  - `Tabs<K extends string>`，props 为 `{ items: { key: K; label: ReactNode }[]; value: K; onChange: (k: K) => void; size?: 'sm' | 'md'; ariaLabel?: string }`

- [ ] **Step 1：写失败的测试**

`src/components/ui/Modal.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import Modal from './Modal';

function Harness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>打开</button>
      {open && (
        <Modal title="登录 小红书" onClose={() => { onClose(); setOpen(false); }}>
          <button type="button">里面的按钮</button>
        </Modal>
      )}
    </div>
  );
}

describe('Modal', () => {
  it('打开时焦点移入，关闭后回到触发按钮', () => {
    render(<Harness onClose={() => {}} />);
    const trigger = screen.getByRole('button', { name: '打开' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '登录 小红书' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('Esc 调用 onClose', () => {
    const onClose = vi.fn();
    render(<Modal title="设置" onClose={onClose}><p>内容</p></Modal>);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('点遮罩关闭，点弹窗内部不关闭', () => {
    const onClose = vi.fn();
    const { container } = render(<Modal title="设置" onClose={onClose}><p>内容</p></Modal>);
    fireEvent.mouseDown(screen.getByText('内容'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(container.querySelector('.overlay')!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closeOnBackdrop=false 时点遮罩不关闭', () => {
    const onClose = vi.fn();
    const { container } = render(<Modal title="向导" closeOnBackdrop={false} onClose={onClose}><p>内容</p></Modal>);
    fireEvent.mouseDown(container.querySelector('.overlay')!);
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

`src/components/ui/Tabs.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Tabs from './Tabs';

const ITEMS = [
  { key: 'chat', label: '对话与脚本' },
  { key: 'image', label: '生图' },
  { key: 'video', label: '视频' },
] as const;

describe('Tabs', () => {
  it('当前项 aria-selected，点击切换', () => {
    const onChange = vi.fn();
    render(<Tabs items={[...ITEMS]} value="chat" onChange={onChange} ariaLabel="模型通道" />);
    expect(screen.getByRole('tab', { name: '对话与脚本' }).getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('tab', { name: '视频' }));
    expect(onChange).toHaveBeenCalledWith('video');
  });

  it('左右方向键循环切换', () => {
    const onChange = vi.fn();
    render(<Tabs items={[...ITEMS]} value="video" onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: '视频' }), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('chat');
    fireEvent.keyDown(screen.getByRole('tab', { name: '视频' }), { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledWith('image');
  });
});
```

运行：`npm test`。预期：两个新测试文件失败，组件还不存在。

- [ ] **Step 2：写 `Modal.tsx` 和 `Tabs.tsx`**

`src/components/ui/Modal.tsx`：

```tsx
import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export interface ModalProps {
  title?: ReactNode;
  onClose: () => void;
  width?: number;
  footer?: ReactNode;
  className?: string;
  closeOnBackdrop?: boolean;
  children: ReactNode;
}

const FOCUSABLE = 'input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])';

/** 通用弹窗：挂载即打开（调用方条件渲染）；Esc 关闭；焦点移入，卸载后还给打开前的元素。 */
export default function Modal({
  title, onClose, width = 480, footer, className, closeOnBackdrop = true, children,
}: ModalProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // 首次渲染时（提交前）记下打开前的焦点，关闭后还回去
  const [returnTo] = useState(() => document.activeElement as HTMLElement | null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });

  useEffect(() => {
    const box = boxRef.current;
    if (box && !box.contains(document.activeElement)) {
      (box.querySelector<HTMLElement>(FOCUSABLE) ?? box).focus();
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      returnTo?.focus?.();
    };
  }, [returnTo]);

  return (
    <div
      className="overlay"
      onMouseDown={(e) => { if (closeOnBackdrop && e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={boxRef}
        className={['modal', className].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        style={{ width, maxWidth: '100%' }}
      >
        {title && <h2 id={titleId} className="modal-title">{title}</h2>}
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
```

`src/components/ui/Tabs.tsx`：

```tsx
import type { KeyboardEvent, ReactNode } from 'react';

export interface TabItem<K extends string> { key: K; label: ReactNode; }

interface TabsProps<K extends string> {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  size?: 'sm' | 'md';
  ariaLabel?: string;
}

export default function Tabs<K extends string>({ items, value, onChange, size = 'md', ariaLabel }: TabsProps<K>) {
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const step = e.key === 'ArrowRight' ? 1 : -1;
    onChange(items[(i + step + items.length) % items.length].key);
  };
  return (
    <div className={`ui-tabs${size === 'sm' ? ' ui-tabs-sm' : ''}`} role="tablist" aria-label={ariaLabel}>
      {items.map((t, i) => {
        const active = t.key === value;
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={`ui-tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
```

运行：`npm test`。预期：全部通过。

- [ ] **Step 3：写 `overlay.css`，删掉 legacy 里的对应段落**

`src/styles/ui/overlay.css`：

```css
.overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: var(--c-scrim);
  display: flex; align-items: center; justify-content: center; padding: var(--sp-5);
  animation: fadeIn 0.16s var(--ease);
}
.modal {
  background: var(--c-surface); border: 1px solid var(--c-rule);
  border-radius: var(--r-overlay); box-shadow: var(--shadow-overlay);
  padding: var(--sp-6); max-height: calc(100vh - 40px); overflow: auto;
  animation: popIn 0.18s var(--ease);
}
.modal:focus { outline: none; }
.modal-title { font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-20); margin-bottom: var(--sp-3); }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--sp-2); margin-top: var(--sp-5); }
.modal-text { color: var(--c-ink-2); font-size: var(--fs-14); }

.drawer-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: var(--c-scrim);
  display: flex; justify-content: flex-end;
  animation: fadeIn 0.16s var(--ease);
}
.drawer {
  width: 560px; max-width: 92vw; height: 100%;
  background: var(--c-surface); border-left: 1px solid var(--c-rule);
  border-radius: var(--r-overlay) 0 0 var(--r-overlay);
  box-shadow: var(--shadow-overlay); overflow-y: auto;
  animation: slideInRight 0.22s var(--ease);
}
.drawer-header {
  position: sticky; top: 0; z-index: 2;
  background: var(--c-surface); border-bottom: 1px solid var(--c-rule);
  padding: var(--sp-5) var(--sp-6);
}
.drawer-body { padding: var(--sp-5) var(--sp-6) 40px; }

.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  z-index: 2000; padding: 10px 18px; border-radius: var(--r-control);
  background: var(--c-ink); color: var(--c-on-ink); border: none;
  box-shadow: var(--shadow-pop); font-size: var(--fs-13);
  animation: popIn 0.18s var(--ease);
}
.toast .toast-icon { color: var(--c-on-ink); margin-right: 7px; }

.ui-tabs { display: flex; gap: var(--sp-1); border-bottom: 1px solid var(--c-rule); }
.ui-tab {
  position: relative; padding: 8px 12px; background: none; border: none; cursor: pointer;
  font-size: var(--fs-14); color: var(--c-ink-2);
  transition: color var(--t-fast);
}
.ui-tab:hover { color: var(--c-ink); }
.ui-tab.is-active { color: var(--c-ink); font-weight: 600; }
.ui-tab.is-active::after { content: ''; position: absolute; left: 12px; right: 12px; bottom: -1px; height: 2px; background: var(--c-ink); border-radius: 1px; }
.ui-tabs-sm .ui-tab { padding: 5px 10px; font-size: var(--fs-13); }
```

从 `legacy.css` 删掉 `/* Modal / drawer */` 注释到 `.toast .toast-icon {…}` 为止的全部规则。`index.css` 末尾追加 `@import './ui/overlay.css';`。

- [ ] **Step 4：`App.tsx` 的欢迎弹窗改用 Modal**

在 `App.tsx` 顶部加上：

```ts
import Modal from './components/ui/Modal';
import Button from './components/ui/Button';
```

把 `{showRecommend && ( <div className="overlay"> … </div> )}` 整块替换为：

```tsx
{showRecommend && (
  <Modal
    title="欢迎使用 Easel"
    width={440}
    onClose={dismissRecommend}
    footer={(
      <>
        <Button onClick={dismissRecommend}>先用通用模式</Button>
        <Button variant="primary" onClick={openWizard}>开始配置</Button>
      </>
    )}
  >
    <p className="modal-text">
      配置你的账号画像，生成的内容会更贴合你的风格、受众和平台调性。大约 2 分钟，之后也可以在侧栏的画像选择里新建。
    </p>
  </Modal>
)}
```

- [ ] **Step 5：检查并提交**

```bash
npm test && npm run build && npm run lint
```

在浏览器里点测：
1. 在控制台执行 `localStorage.removeItem('easel_onboarding_seen')`，然后刷新。
2. 欢迎弹窗应显示为新样式；按 Esc 能关闭。
3. 技能库点开一个技能，抽屉应为新样式。

```bash
git add -A web/frontend
git commit -m "feat(web): 通用弹窗与标签页组件，欢迎弹窗、抽屉、提示条换新样式

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4：工作台重排与创作数据独立成页

**Files:**
- Create：
  - `src/lib/useAnalyticsPlatforms.ts`
  - `src/components/AnalyticsPage.tsx`、`src/components/AnalyticsPage.test.tsx`
  - `src/components/DashboardPage.test.tsx`
  - `src/styles/pages/dashboard.css`、`src/styles/pages/analytics.css`
- Modify：
  - `src/components/DashboardPage.tsx`（整文件重写）
  - `src/App.tsx`（新增 `analytics` 路由）
  - `src/styles/legacy.css`：删掉 `/* ============ 工作台 ============ */` 和 `/* ============ 创作数据（归因）宽卡 ============ */` 两段，到下一个 `/* ====` 注释之前为止
  - `src/styles/index.css`

**Interfaces:**
- Consumes：
  - `PageHeader`、`Panel`、`EmptyState`、`Tag`、`Swatch`、`Button`、`Tabs`
  - `PIPELINE`、`layerInfo`、`Page`（来自 `lib/layers`）
- Produces：
  - `useAnalyticsPlatforms(onLoggedIn?: (platform: string) => void): { plats: AnalyticsPlatform[]; logged: AnalyticsPlatform[] }`
  - `AnalyticsPage`，props 为 `{ onNavigate: (page: Page) => void }`

- [ ] **Step 1：写失败的页面测试**

`src/components/DashboardPage.test.tsx`：

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchTrends: vi.fn(),
  fetchSchedule: vi.fn(),
  fetchOutputs: vi.fn(),
  fetchAccounts: vi.fn(),
  fetchIdeas: vi.fn(),
  fetchAnalyticsPlatforms: vi.fn(),
}));
vi.mock('../lib/whoami', () => ({
  getWhoamiCache: vi.fn(() => ({})),
  verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import DashboardPage from './DashboardPage';

const ok = <T,>(v: T) => Promise.resolve(v);

beforeEach(() => {
  vi.mocked(api.fetchTrends).mockReturnValue(ok({
    trends: [{ platform: 'weibo', label: '微博', items: [{ title: '国庆出片大赛', hot: '1', url: '' }] }],
    updated: 0,
  }));
  vi.mocked(api.fetchSchedule).mockReturnValue(ok([]));
  vi.mocked(api.fetchOutputs).mockReturnValue(ok([]));
  vi.mocked(api.fetchAccounts).mockReturnValue(ok([
    { platform: 'xiaohongshu', name: '小红书', backend: 'xhs', supported: true, loggedIn: true, note: '' },
    { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
  ]));
  vi.mocked(api.fetchIdeas).mockReturnValue(ok([]));
  vi.mocked(api.fetchAnalyticsPlatforms).mockReturnValue(ok([]));
});

describe('DashboardPage', () => {
  it('流水线五栏按顺序显示层名', async () => {
    const { container } = render(<DashboardPage persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    const names = [...container.querySelectorAll('.pipe-stage-name')].map((n) => n.textContent);
    expect(names).toEqual(['发现', '策划', '生产', '发布', '归因']);
    await waitFor(() => expect(screen.getByText('1/2')).toBeTruthy());   // 发布：已登录/总数
  });

  it('没有可看数据的平台时，归因栏显示「—」', async () => {
    const { container } = render(<DashboardPage persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    await waitFor(() => expect(container.querySelector('[data-stage="attribute"] .pipe-stage-num')?.textContent).toBe('—'));
  });

  it('点热点调 onUseTopic，点「开始对话」跳到对话页', async () => {
    const onUseTopic = vi.fn();
    const onNavigate = vi.fn();
    render(<DashboardPage persona="" gatewayStatus="connected" onNavigate={onNavigate} onUseTopic={onUseTopic} />);
    fireEvent.click(await screen.findByText('国庆出片大赛'));
    expect(onUseTopic).toHaveBeenCalledWith('国庆出片大赛');
    fireEvent.click(screen.getByRole('button', { name: '开始对话' }));
    expect(onNavigate).toHaveBeenCalledWith('chat');
  });

  it('热点拉不到时给出下一步提示', async () => {
    vi.mocked(api.fetchTrends).mockReturnValue(Promise.reject(new Error('net')));
    render(<DashboardPage persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    expect(await screen.findByText(/热点暂时拉不到/)).toBeTruthy();
  });
});
```

`src/components/AnalyticsPage.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchAnalyticsPlatforms: vi.fn(),
  fetchAccountAnalytics: vi.fn(() => new Promise(() => {})),
}));
vi.mock('../lib/whoami', () => ({
  getWhoamiCache: vi.fn(() => ({})),
  verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import AnalyticsPage from './AnalyticsPage';

describe('AnalyticsPage', () => {
  it('没有已登录平台时引导去账号页', async () => {
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: false }]);
    const onNavigate = vi.fn();
    render(<AnalyticsPage onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole('button', { name: '去账号页' }));
    expect(onNavigate).toHaveBeenCalledWith('accounts');
  });

  it('有已登录平台时显示平台标签页，页头层标为归因', async () => {
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: true }]);
    const { container } = render(<AnalyticsPage onNavigate={() => {}} />);
    expect(await screen.findByRole('tab', { name: '小红书' })).toBeTruthy();
    expect(container.querySelector('.ui-layer-mark')?.textContent).toBe('归因');
  });
});
```

运行：`npm test`。预期：失败，`.pipe-stage-name` 和 `AnalyticsPage` 都还不存在。

- [ ] **Step 2：写 `src/lib/useAnalyticsPlatforms.ts`**

逻辑原样搬自 `DashboardPage.tsx` 当前的 `fetchAnalyticsPlatforms` 加 `verifyStale` 那段 `useEffect`：

```ts
import { useEffect, useRef, useState } from 'react';
import { fetchAnalyticsPlatforms } from './api';
import type { AccountWhoami, AnalyticsPlatform } from './api';
import { getWhoamiCache, verifyStale } from './whoami';

/**
 * 归因层平台加载 + whoami 自愈（工作台与创作数据页共用，行为与原工作台卡片一致）。
 * onLoggedIn：发现第一个已登录平台 / 自愈确认某平台已登录时回调（创作数据页用来默认选中）。
 */
export function useAnalyticsPlatforms(onLoggedIn?: (platform: string) => void) {
  const [plats, setPlats] = useState<AnalyticsPlatform[]>([]);
  const [whoamiMap, setWhoamiMap] = useState<Record<string, AccountWhoami>>(() => getWhoamiCache());
  const cb = useRef(onLoggedIn);
  useEffect(() => { cb.current = onLoggedIn; });

  useEffect(() => {
    fetchAnalyticsPlatforms().then((ps) => {
      setPlats(ps);
      const cache = getWhoamiCache();
      const first = ps.find((p) => p.loggedIn || !!cache[p.platform]?.loggedIn);
      if (first) cb.current?.(first.platform);
      // 开页后台自愈：对非 API 式的归因平台真校验（whoami），刷新登录态；
      // B 站走 cookie、公众号走凭证/官方 API 判定，都不起浏览器。
      const API_BASED = new Set(['bilibili', 'wechat-oa']);
      verifyStale(ps.filter((p) => !API_BASED.has(p.platform)).map((p) => p.platform), {
        onUpdate: (platform, r) => {
          setWhoamiMap((m) => ({ ...m, [platform]: r }));
          if (r.loggedIn) cb.current?.(platform);
        },
      });
    }).catch(() => {});
  }, []);

  const logged = plats.filter((p) => p.loggedIn || whoamiMap[p.platform]?.loggedIn);
  return { plats, logged };
}
```

- [ ] **Step 3：写 `src/components/AnalyticsPage.tsx`**

- 顶部：`fmtNum`、`growthInfo` 两个函数和 `WIN` 表原样搬自 `DashboardPage.tsx`。`growthInfo` 里的颜色改为 `var(--c-ok)` 和 `var(--c-danger)`。
- 主体：原「创作数据」宽卡的 JSX，改动如下：

```tsx
import { useState } from 'react';
import { fetchAccountAnalytics } from '../lib/api';
import type { AccountAnalytics } from '../lib/api';
import type { Page } from '../lib/layers';
import { useAnalyticsPlatforms } from '../lib/useAnalyticsPlatforms';
import PageHeader from './ui/PageHeader';
import Panel from './ui/Panel';
import EmptyState from './ui/EmptyState';
import Tabs from './ui/Tabs';
import Button from './ui/Button';

/** 大数格式化：12000 → 1.2万。 */
function fmtNum(n: number | null): string {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 10000) return (n / 10000).toFixed(a >= 100000 ? 0 : 1) + '万';
  return String(n);
}
/** 增长量渲染信息：正=石绿↑，负=深朱砂↓，0/缺失=不显示。 */
function growthInfo(n: number | null): { text: string; color: string } | null {
  if (n == null || n === 0) return null;
  return n > 0
    ? { text: `▲+${fmtNum(n)}`, color: 'var(--c-ok)' }
    : { text: `▼${fmtNum(Math.abs(n))}`, color: 'var(--c-danger)' };
}

type Win = 'last' | 'day' | 'week' | 'month' | 'year';
const WIN: { key: Win; label: string }[] = [
  { key: 'last', label: '较上次' }, { key: 'day', label: '较昨日' }, { key: 'week', label: '较上周' },
  { key: 'month', label: '较上月' }, { key: 'year', label: '较去年' },
];

export default function AnalyticsPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const [anaSel, setAnaSel] = useState('');
  const [anaData, setAnaData] = useState<Record<string, AccountAnalytics | 'loading' | 'error'>>(() => {
    try { return JSON.parse(localStorage.getItem('easel_analytics') || '{}'); } catch { return {}; }
  });
  const [anaWin, setAnaWin] = useState<Win>('week');
  const { plats, logged } = useAnalyticsPlatforms((p) => setAnaSel((s) => s || p));

  const runAna = (platform: string) => {
    setAnaSel(platform);
    setAnaData((d) => ({ ...d, [platform]: 'loading' }));
    fetchAccountAnalytics(platform)
      .then((r) => setAnaData((d) => {
        const next = { ...d, [platform]: r };
        try { localStorage.setItem('easel_analytics', JSON.stringify(next)); } catch { /* quota */ }
        return next;
      }))
      .catch(() => setAnaData((d) => ({ ...d, [platform]: 'error' as const })));
  };

  const d = anaSel ? anaData[anaSel] : undefined;

  return (
    <div className="page-scroll analytics-page">
      <PageHeader
        layer="attribute"
        title="创作数据"
        description="各平台已登录账号的粉丝、获赞、关注，增长趋势和最新作品。"
        actions={anaSel && d && d !== 'loading'
          ? <Button size="sm" onClick={() => runAna(anaSel)}>刷新数据</Button>
          : undefined}
      />
      {plats.length === 0 ? (
        <EmptyState text="正在加载平台列表。如果一直没有内容，检查网络或代理设置。" />
      ) : logged.length === 0 ? (
        <EmptyState
          text="还没有能拉取数据的账号。先去账号页扫码登录，这里就能看到各平台的粉丝、获赞和最新作品。"
          action={{ label: '去账号页', onClick: () => onNavigate('accounts') }}
        />
      ) : (
        <>
          <Tabs
            ariaLabel="平台"
            items={logged.map((p) => ({ key: p.platform, label: p.name }))}
            value={anaSel}
            onChange={runAna}
          />
          <div className="analytics-body">
            {/* 下面四种状态的 JSX 原样搬自原工作台卡片，只做以下替换：
                「点上方平台查看该账号数据」→ 「点上方的平台，拉取这个账号的数据。」；
                失败提示的内联 color 去掉，改用 <EmptyState text="拉取失败：可能是登录失效，或平台页面改版了。点上方平台重试。" />；
                「该平台登录态已失效，去账号页重登 →」→ EmptyState + action {label:'去账号页', onClick:()=>onNavigate('accounts')}；
                loading 保留 <div className="loading"><div className="spinner" />正在拉取数据，需要启动浏览器，约数秒…</div>；
                三列 .ana-col 结构、.ana-stat、.ana-metric、.ana-note 类名保持不变（样式在 analytics.css 重写）；
                窗口切换 .ana-wins 那一排按钮换成 <Tabs size="sm" items={WIN} value={anaWin} onChange={setAnaWin} ariaLabel="对比时段" />；
                指标涨跌颜色用 growthInfo 的 color；环比 vs 的颜色改为 up ? 'var(--c-ok)' : 'var(--c-danger)'；
                笔记无封面时的「📝」占位改为 <span className="ana-note-cover ana-note-cover-ph" aria-hidden="true" />；「↗」保留。 */}
          </div>
        </>
      )}
    </div>
  );
}
```

执行者要把注释里描述的四种状态分支（`!d`、`'loading'`、`'error'`、正常数据，以及 `!d.loggedIn`）写成真实的 JSX：以当前 `DashboardPage.tsx` 里「创作数据」卡片的实现为底稿，按注释里的替换项修改，然后删掉这段注释。`Panel` 包住三列中每一列的内容（`<Panel title="概览">`、`<Panel title="近 7 日环比">`、`<Panel title="最新作品">`），`.ana-sub` 小标题由 Panel 的标题取代。

`src/styles/pages/analytics.css`：

```css
.analytics-page { padding: 26px 34px 40px; }
.analytics-page .ui-tabs { margin-bottom: var(--sp-4); }
.analytics-body { display: grid; grid-template-columns: 1.1fr 1fr 1.2fr; gap: var(--sp-4); align-items: start; }
.ana-id { font-size: var(--fs-13); color: var(--c-ink-3); margin-bottom: var(--sp-2); }
.ana-overview { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-3); }
.ana-stat-val, .ana-metric-val { font-family: var(--font-serif); font-weight: 600; font-size: 26px; line-height: 1.2; font-variant-numeric: tabular-nums; }
.ana-stat-label, .ana-metric-label { font-size: var(--fs-12); color: var(--c-ink-3); }
.ana-stat-delta, .ana-metric-vs { font-size: var(--fs-12); font-variant-numeric: tabular-nums; }
.ana-muted { color: var(--c-ink-3); }
.ana-col-main .ui-tabs { margin: var(--sp-4) 0 var(--sp-1); }
.ana-wins-note { font-size: var(--fs-12); color: var(--c-ink-3); }
.ana-metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--sp-3) var(--sp-4); }
.ana-notes { display: flex; flex-direction: column; }
.ana-note { display: flex; align-items: center; gap: var(--sp-3); padding: 8px 0; border-bottom: 1px solid var(--c-rule); color: var(--c-ink); text-decoration: none; min-width: 0; }
.ana-note:last-child { border-bottom: 0; }
.ana-note:hover .ana-note-title { text-decoration: underline; }
.ana-note-cover { width: 40px; height: 52px; border-radius: 4px; object-fit: cover; flex: none; background: var(--c-sunken); }
.ana-note-main { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.ana-note-title { font-size: var(--fs-13); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ana-note-stat { font-size: var(--fs-12); color: var(--c-ink-3); }
.ana-note-go { color: var(--c-ink-3); }
.analytics-page .loading { display: flex; align-items: center; gap: var(--sp-3); padding: 28px 0; font-size: var(--fs-13); color: var(--c-ink-2); }
@media (max-width: 1100px) { .analytics-body { grid-template-columns: 1fr; } }
```

- [ ] **Step 4：重写 `src/components/DashboardPage.tsx`**

```tsx
import { useState, useEffect } from 'react';
import { fetchTrends, fetchSchedule, fetchOutputs, fetchAccounts, fetchIdeas } from '../lib/api';
import type { TrendGroup, ScheduleItem, OutputNode, AccountItem, Idea } from '../lib/api';
import { layerInfo } from '../lib/layers';
import type { LayerKey, Page } from '../lib/layers';
import { useAnalyticsPlatforms } from '../lib/useAnalyticsPlatforms';
import Button from './ui/Button';
import Panel from './ui/Panel';
import EmptyState from './ui/EmptyState';
import Tag from './ui/Tag';

interface DashboardProps {
  persona: string;
  gatewayStatus: string;
  onNavigate: (page: Page) => void;
  onUseTopic: (title: string) => void;
}

const STATUS_LABEL: Record<string, string> = { idea: '选题', draft: '草稿', scheduled: '待发', published: '已发' };
const WEEK = ['日', '一', '二', '三', '四', '五', '六'];

interface Stage { layer: LayerKey; num: string; label: string; link: { label: string; page: Page } }

export default function DashboardPage({ persona, gatewayStatus, onNavigate, onUseTopic }: DashboardProps) {
  const [trends, setTrends] = useState<TrendGroup[]>([]);
  const [trendsFailed, setTrendsFailed] = useState(false);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [outputs, setOutputs] = useState<OutputNode[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const { logged: anaLogged } = useAnalyticsPlatforms();

  useEffect(() => {
    fetchTrends('weibo,douyin', 6).then((d) => setTrends(d.trends)).catch(() => setTrendsFailed(true));
    fetchSchedule().then(setSchedule).catch(() => {});
    fetchOutputs().then(setOutputs).catch(() => {});
    fetchAccounts().then(setAccounts).catch(() => {});
    fetchIdeas().then(setIdeas).catch(() => {});
  }, []);

  const now = new Date();
  const hour = now.getHours();
  const greet = hour < 6 ? '夜深了' : hour < 12 ? '上午好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
  const dateLine = `${now.getMonth() + 1}月${now.getDate()}日 周${WEEK[now.getDay()]}`;
  const todayStr = now.toISOString().slice(0, 10);
  const upcoming = [...schedule]
    .filter((s) => s.date >= todayStr && s.status !== 'published')
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)).slice(0, 5);
  const recent = outputs.slice(0, 5);
  const pendingIdeas = ideas.filter((i) => i.status === 'pending');
  const loggedIn = accounts.filter((a) => a.loggedIn).length;
  const trendCount = trends.reduce((n, g) => n + g.items.length, 0);

  const stages: Stage[] = [
    { layer: 'discover', num: String(trendCount), label: '条今日热点', link: { label: '热点雷达', page: 'trends' } },
    { layer: 'plan', num: String(pendingIdeas.length), label: '个待做选题', link: { label: '选题库', page: 'ideas' } },
    { layer: 'produce', num: String(outputs.length), label: '个内容项目', link: { label: '内容库', page: 'outputs' } },
    { layer: 'publish', num: accounts.length ? `${loggedIn}/${accounts.length}` : '—', label: '个账号已登录', link: { label: '账号', page: 'accounts' } },
    { layer: 'attribute', num: anaLogged.length ? String(anaLogged.length) : '—', label: anaLogged.length ? '个平台可看数据' : '暂无可看数据的平台', link: { label: '创作数据', page: 'analytics' } },
  ];

  return (
    <div className="page-scroll dash-page">
      <header className="dash-head">
        <div>
          <h1 className="dash-greet">{greet}</h1>
          <p className="dash-date">
            {dateLine}。{persona ? `当前画像：${persona}。` : '通用模式，选一个画像生成的内容会更贴合你。'}
            {gatewayStatus !== 'connected' && <Tag tone="danger">网关未连接，对话暂不可用</Tag>}
          </p>
        </div>
        <div className="dash-actions">
          <Button onClick={() => onNavigate('breakdown')}>拆一条爆款</Button>
          <Button variant="primary" onClick={() => onNavigate('chat')}>开始对话</Button>
        </div>
      </header>

      <section className="pipe" aria-label="内容流水线">
        {stages.map((s) => (
          <div key={s.layer} className="pipe-stage" data-stage={s.layer}>
            <span className="pipe-band" aria-hidden="true" />
            <span className="pipe-stage-name">{layerInfo(s.layer).name}</span>
            <span className="pipe-stage-num">{s.num}</span>
            <span className="pipe-stage-label">{s.label}</span>
            <button type="button" className="pipe-stage-link" onClick={() => onNavigate(s.link.page)}>{s.link.label}</button>
          </div>
        ))}
      </section>

      <div className="dash-cols">
        <Panel title="今日热点" action={{ label: '热点雷达', onClick: () => onNavigate('trends') }}>
          {trends.length === 0 && (
            <EmptyState text={trendsFailed
              ? '热点暂时拉不到。检查网络，或在设置里配置代理后刷新。'
              : '正在拉取微博和抖音的热搜…'} />
          )}
          {trends.map((g) => (
            <div key={g.platform} className="hot-group">
              <div className="hot-plat">{g.label}</div>
              {g.items.slice(0, 5).map((it, i) => (
                <button key={i} type="button" className="hot-row" title={`${it.title}（点击做成内容）`} onClick={() => onUseTopic(it.title)}>
                  <span className="hot-rank">{i + 1}</span>
                  <span className="hot-title">{it.title}</span>
                  <span className="hot-act">做选题</span>
                </button>
              ))}
            </div>
          ))}
        </Panel>

        <div className="dash-stack">
          <Panel title="选题 · 待做" action={{ label: '选题库', onClick: () => onNavigate('ideas') }}>
            {pendingIdeas.length === 0
              ? <EmptyState text="还没有待做的选题。在热点雷达里收藏几个，会出现在这里。" />
              : pendingIdeas.slice(0, 5).map((it) => (
                <button key={it.id} type="button" className="dash-row" title="点击做成内容" onClick={() => onUseTopic(it.title)}>
                  <span className="dash-row-title">{it.title}</span>
                  {it.source && <Tag>{it.source}</Tag>}
                </button>
              ))}
          </Panel>
          <Panel title="近期排期" action={{ label: '内容日历', onClick: () => onNavigate('calendar') }}>
            {upcoming.length === 0
              ? <EmptyState text="还没有排期。从选题库挑一条排进日历。" action={{ label: '去排期', onClick: () => onNavigate('calendar') }} />
              : upcoming.map((s) => (
                <button key={s.id} type="button" className="dash-row" onClick={() => onNavigate('calendar')}>
                  <span className="dash-row-date">{s.date.slice(5)}</span>
                  <span className="dash-row-title">{s.platform ? `[${s.platform}] ` : ''}{s.title}</span>
                  <Tag>{STATUS_LABEL[s.status] || s.status}</Tag>
                </button>
              ))}
          </Panel>
          <Panel title="最近产物" action={{ label: '内容库', onClick: () => onNavigate('outputs') }}>
            {recent.length === 0
              ? <EmptyState text="还没有产物。在对话里让 Easel 写一篇，成品会出现在这里。" />
              : recent.map((g) => (
                <button key={g.name} type="button" className="dash-row" onClick={() => onNavigate('outputs')}>
                  <span className="dash-row-title">{g.meta?.title || g.name}</span>
                  <Tag>{g.meta?.platform || (g.type === 'dir' ? `${g.fileCount ?? 0} 个文件` : '单文件')}</Tag>
                </button>
              ))}
          </Panel>
        </div>
      </div>
    </div>
  );
}
```

`src/styles/pages/dashboard.css`：

```css
.dash-page { padding: 30px 36px 40px; }
.dash-head { display: flex; align-items: flex-end; gap: var(--sp-4); }
.dash-greet { font-family: var(--font-serif); font-weight: 600; font-size: 28px; letter-spacing: 0.5px; }
.dash-date { margin-top: var(--sp-1); font-size: var(--fs-13); color: var(--c-ink-3); display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.dash-actions { margin-left: auto; display: flex; gap: var(--sp-2); }

.pipe { margin-top: var(--sp-6); display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); background: var(--c-surface); border: 1px solid var(--c-rule); border-radius: var(--r-panel); overflow: hidden; }
.pipe-stage { display: flex; flex-direction: column; align-items: flex-start; padding: 0 18px 16px; border-right: 1px solid var(--c-rule); min-width: 0; }
.pipe-stage:last-child { border-right: 0; }
.pipe-band { align-self: stretch; height: 5px; margin: 0 -18px 14px; background: var(--layer-general); }
.pipe-stage[data-stage="discover"] .pipe-band { background: var(--layer-discover); }
.pipe-stage[data-stage="plan"] .pipe-band { background: var(--layer-plan); }
.pipe-stage[data-stage="produce"] .pipe-band { background: var(--layer-produce); }
.pipe-stage[data-stage="publish"] .pipe-band { background: var(--layer-publish); }
.pipe-stage[data-stage="attribute"] .pipe-band { background: var(--layer-attribute); }
.pipe-stage-name { font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-14); }
.pipe-stage[data-stage="discover"] .pipe-stage-name { color: var(--layer-discover-text); }
.pipe-stage[data-stage="plan"] .pipe-stage-name { color: var(--layer-plan-text); }
.pipe-stage[data-stage="produce"] .pipe-stage-name { color: var(--layer-produce-text); }
.pipe-stage[data-stage="publish"] .pipe-stage-name { color: var(--layer-publish-text); }
.pipe-stage[data-stage="attribute"] .pipe-stage-name { color: var(--layer-attribute-text); }
.pipe-stage-num { margin-top: var(--sp-2); font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-34); line-height: 1.15; font-variant-numeric: lining-nums tabular-nums; }
.pipe-stage-label { font-size: var(--fs-13); color: var(--c-ink-2); }
.pipe-stage-link { margin-top: var(--sp-3); padding: 0; background: none; border: none; border-bottom: 1px solid var(--c-rule-strong); font-size: var(--fs-12); color: var(--c-ink-2); cursor: pointer; }
.pipe-stage-link:hover { color: var(--c-ink); border-bottom-color: var(--c-ink); }

.dash-cols { display: grid; grid-template-columns: 3fr 2fr; gap: var(--sp-4); margin-top: var(--sp-4); align-items: start; }
.dash-stack { display: grid; gap: var(--sp-4); }
.hot-group + .hot-group { margin-top: var(--sp-3); }
.hot-plat { font-size: var(--fs-12); color: var(--c-ink-3); margin-bottom: 2px; }
.hot-row, .dash-row {
  display: flex; align-items: baseline; gap: var(--sp-2); width: 100%; min-width: 0;
  padding: 7px 0; background: none; border: none; border-bottom: 1px dashed var(--c-rule);
  text-align: left; cursor: pointer; color: var(--c-ink); font-size: var(--fs-14);
}
.hot-row:last-child, .dash-row:last-child { border-bottom: 0; }
.hot-rank { width: 20px; flex: none; font-family: var(--font-serif); font-weight: 600; color: var(--layer-discover-text); font-variant-numeric: tabular-nums; }
.hot-title, .dash-row-title { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hot-act { font-size: var(--fs-12); color: var(--c-ink-3); opacity: 0; transition: opacity var(--t-fast); }
.hot-row:hover .hot-act, .hot-row:focus-visible .hot-act { opacity: 1; }
.hot-row:hover .hot-title, .dash-row:hover .dash-row-title { text-decoration: underline; text-underline-offset: 3px; }
.dash-row-date { flex: none; font-size: var(--fs-12); color: var(--c-ink-3); font-variant-numeric: tabular-nums; }

@media (max-width: 1180px) {
  .pipe { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .pipe-stage:nth-child(3) { border-right: 0; }
  .pipe-stage:nth-child(n+4) { border-top: 1px solid var(--c-rule); }
  .dash-cols { grid-template-columns: 1fr; }
}
```

- [ ] **Step 5：接上路由和样式，删掉 legacy 段落**

在 `App.tsx` 里 import `AnalyticsPage`，并在 `renderPage` 的 `switch` 中 `'profile'` 之前加一行：

```tsx
      case 'analytics':
        return <AnalyticsPage onNavigate={setCurrentPage} />;
```

`index.css` 追加：

```css
@import './pages/dashboard.css';
@import './pages/analytics.css';
```

从 `legacy.css` 删掉 `/* ============ 工作台 ============ */` 和 `/* ============ 创作数据（归因）宽卡 ============ */` 两段，每段删到下一个 `/* ====` 注释之前为止。

- [ ] **Step 6：检查并提交**

```bash
npm test && npm run build && npm run lint
```

刷新 7860 端口，对照 `.superpowers/brainstorm/1524-1790746178/content/visual-style.html` 检查工作台：
- 五色色条和数字与样稿一致。
- 点「创作数据」链接能进新页面。
- 1024 宽时色条折成三栏加两栏。

```bash
git add -A web/frontend
git commit -m "feat(web): 工作台改为五色流水线，创作数据独立成页

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5：应用外壳与按层分组的导航

**Files:**
- Create：
  - `src/components/ChatSessionList.tsx`、`src/components/ChatLayout.tsx`
  - `src/components/Sidebar.test.tsx`、`src/components/ChatSessionList.test.tsx`
  - `src/styles/layout.css`、`src/styles/pages/chat.css`（本任务只放会话栏和两栏外壳）
- Modify：
  - `src/components/Sidebar.tsx`（整文件重写）
  - `src/App.tsx`
  - `src/main.tsx`（`BUILD_ID = 'studio-1'`）
  - `src/styles/legacy.css`：删掉 `/* ============ Layout ============ */` 段、`/* ============ 侧栏会话操作（重命名/归档/删除）============ */` 段、`/* ============ 子工具顶部小导航 ============ */` 段
  - `src/styles/index.css`
- Delete：`src/components/SubNav.tsx`

**Interfaces:**
- Consumes：`NAV_GROUPS`、`layerInfo`、`Page`、`Swatch`。
- Produces：
  - `Sidebar`，props 为 `{ currentPage; onPageChange; personas; selectedPersona; onPersonaChange; onNewProfile; activeSessionHasMessages: boolean; activeChatTitle?: string; gatewayStatus: string; onOpenSettings: () => void }`，不再接收会话相关的 props。
  - `ChatSessionList`，props 为 `{ sessions: ChatSession[]; activeSessionId: string | null; onSelect(id); onDelete(id); onRename(id, title); onArchive(id, archived: boolean); onNew() }`
  - `ChatLayout`，props 为 `{ sessions: ReactNode; children: ReactNode }`

- [ ] **Step 1：写失败的测试**

`src/components/Sidebar.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Sidebar from './Sidebar';

const base = {
  personas: [], selectedPersona: '', onPersonaChange: () => {}, onNewProfile: () => {},
  activeSessionHasMessages: false, gatewayStatus: 'connected', onOpenSettings: () => {},
};

describe('Sidebar', () => {
  it('按层显示分组名，顺序为发现到归因', () => {
    const { container } = render(<Sidebar {...base} currentPage="dashboard" onPageChange={() => {}} />);
    const titles = [...container.querySelectorAll('.nav-group-title')].map((n) => n.textContent);
    expect(titles).toEqual(['发现', '策划', '生产', '发布', '归因']);
  });

  it('当前页标 aria-current，点击切页', () => {
    const onPageChange = vi.fn();
    render(<Sidebar {...base} currentPage="accounts" onPageChange={onPageChange} />);
    expect(screen.getByRole('button', { name: /账号/ }).getAttribute('aria-current')).toBe('page');
    fireEvent.click(screen.getByRole('button', { name: /热点雷达/ }));
    expect(onPageChange).toHaveBeenCalledWith('trends');
  });

  it('不再包含会话列表；设置按钮打开设置', () => {
    const onOpenSettings = vi.fn();
    const { container } = render(<Sidebar {...base} onOpenSettings={onOpenSettings} currentPage="dashboard" onPageChange={() => {}} />);
    expect(container.querySelector('.session-item')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /设置/ }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it('对话项旁显示当前会话标题', () => {
    render(<Sidebar {...base} activeChatTitle="国庆出片文案" currentPage="dashboard" onPageChange={() => {}} />);
    expect(screen.getByText('国庆出片文案')).toBeTruthy();
  });
});
```

`src/components/ChatSessionList.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatSessionList from './ChatSessionList';
import type { ChatSession } from '../lib/store';

const LONG = '这是一个非常非常长的会话标题用来检查单行省略和悬停提示是否正常工作';
const S = (id: string, title: string, extra: Partial<ChatSession> = {}): ChatSession => ({
  id, title, created: 0, messages: [{ role: 'user', content: 'hi' }], ...extra,
} as ChatSession);

function setup(over: Partial<Parameters<typeof ChatSessionList>[0]> = {}) {
  const props = {
    sessions: [S('a', '国庆出片文案'), S('b', LONG), S('c', '旧会话', { archived: true })],
    activeSessionId: 'a',
    onSelect: vi.fn(), onDelete: vi.fn(), onRename: vi.fn(), onArchive: vi.fn(), onNew: vi.fn(),
    ...over,
  };
  render(<ChatSessionList {...props} />);
  return props;
}

describe('ChatSessionList', () => {
  it('列出未归档会话，已归档默认收起', () => {
    setup();
    expect(screen.getByText('国庆出片文案')).toBeTruthy();
    expect(screen.queryByText('旧会话')).toBeNull();
    fireEvent.click(screen.getByText(/已归档/));
    expect(screen.getByText('旧会话')).toBeTruthy();
  });

  it('长标题带 title 属性（配合 CSS 单行省略）', () => {
    setup();
    expect(screen.getByText(LONG).getAttribute('title')).toBe(LONG);
  });

  it('选中、新建、删除、归档回调', () => {
    const p = setup();
    fireEvent.click(screen.getByText(LONG));
    expect(p.onSelect).toHaveBeenCalledWith('b');
    fireEvent.click(screen.getByRole('button', { name: '新对话' }));
    expect(p.onNew).toHaveBeenCalled();
    fireEvent.click(screen.getAllByTitle('删除')[0]);
    expect(p.onDelete).toHaveBeenCalledWith('a');
    fireEvent.click(screen.getAllByTitle('归档')[0]);
    expect(p.onArchive).toHaveBeenCalledWith('a', true);
  });

  it('重命名：Enter 提交', () => {
    const p = setup();
    fireEvent.click(screen.getAllByTitle('重命名')[0]);
    const input = screen.getByDisplayValue('国庆出片文案');
    fireEvent.change(input, { target: { value: '新标题' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(p.onRename).toHaveBeenCalledWith('a', '新标题');
  });
});
```

运行：`npm test`。预期：失败，新组件不存在，Sidebar 也还是旧结构。

- [ ] **Step 2：写 `ChatSessionList.tsx`**

逻辑原样搬自旧 `Sidebar.tsx` 的 `renderItem`、`active`、`archived`、`showArchived`、重命名状态：

```tsx
import { useState } from 'react';
import type { ChatSession } from '../lib/store';
import { IconNewChat, IconEdit, IconArchive, IconUnarchive, IconTrash, IconChevron } from './icons';

interface ChatSessionListProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onArchive: (id: string, archived: boolean) => void;
  onNew: () => void;
}

/** 对话记录（从全局侧栏挪进对话页）：新建 / 切换 / 重命名 / 归档 / 删除 / 查看已归档。 */
export default function ChatSessionList({
  sessions, activeSessionId, onSelect, onDelete, onRename, onArchive, onNew,
}: ChatSessionListProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const startRename = (s: ChatSession) => { setRenamingId(s.id); setRenameValue(s.title); };
  const commitRename = () => {
    if (renamingId) onRename(renamingId, renameValue);
    setRenamingId(null);
  };

  const active = sessions.filter((s) => !s.archived && (s.messages.length > 0 || s.id === activeSessionId));
  const archived = sessions.filter((s) => s.archived);

  const renderItem = (s: ChatSession, isArchived: boolean) => {
    if (renamingId === s.id) {
      return (
        <div key={s.id} className="session-item">
          <input
            className="field session-rename-input"
            value={renameValue}
            autoFocus
            onChange={(e) => setRenameValue(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename();
              else if (e.key === 'Escape') setRenamingId(null);
            }}
            onBlur={commitRename}
          />
        </div>
      );
    }
    return (
      <div
        key={s.id}
        className={`session-item${s.id === activeSessionId ? ' active' : ''}`}
        onClick={() => onSelect(s.id)}
      >
        <span className="session-item-title" title={s.title}>{s.title}</span>
        <div className="session-actions">
          <button type="button" className="session-act" title="重命名"
            onClick={(e) => { e.stopPropagation(); startRename(s); }}><IconEdit size={14} /></button>
          <button type="button" className="session-act" title={isArchived ? '取消归档' : '归档'}
            onClick={(e) => { e.stopPropagation(); onArchive(s.id, !isArchived); }}>
            {isArchived ? <IconUnarchive size={14} /> : <IconArchive size={14} />}
          </button>
          <button type="button" className="session-act danger" title="删除"
            onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}><IconTrash size={14} /></button>
        </div>
      </div>
    );
  };

  return (
    <div className="session-list">
      <div className="session-list-head">
        <h2 className="session-list-title">对话</h2>
        <button type="button" className="btn btn-sm" onClick={onNew}><IconNewChat size={13} />新对话</button>
      </div>
      <div className="session-list-body">
        {active.length === 0 && <p className="session-empty">还没有对话。在右边输入框里说说你想做什么。</p>}
        {active.map((s) => renderItem(s, false))}
        {archived.length > 0 && (
          <>
            <button type="button" className="archived-header" onClick={() => setShowArchived((v) => !v)} aria-expanded={showArchived}>
              <span className={`archived-chevron${showArchived ? ' open' : ''}`}><IconChevron size={12} /></span>
              已归档（{archived.length}）
            </button>
            {showArchived && archived.map((s) => renderItem(s, true))}
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3：写 `ChatLayout.tsx`**

```tsx
import { useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';

/** 对话页两栏外壳：宽屏常驻会话栏；窄屏（<1200px）收起，点按钮展开，选中会话后自动收起。 */
export default function ChatLayout({ sessions, children }: { sessions: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const closeOnPick = (e: MouseEvent) => {
    const item = (e.target as HTMLElement).closest('.session-item');
    if (item && !item.querySelector('input')) setOpen(false);
  };
  return (
    <div className={`chat-layout${open ? ' sessions-open' : ''}`}>
      <button type="button" className="btn btn-sm chat-sessions-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        对话记录
      </button>
      <aside className="chat-sessions-pane" onClick={closeOnPick}>{sessions}</aside>
      <div className="chat-main">{children}</div>
    </div>
  );
}
```

- [ ] **Step 4：重写 `Sidebar.tsx`**

```tsx
import type { ComponentType } from 'react';
import type { PersonaItem } from '../lib/api';
import { NAV_GROUPS, layerInfo } from '../lib/layers';
import type { Page } from '../lib/layers';
import {
  IconDashboard, IconChat, IconFire, IconLayers, IconIdea, IconCalendar,
  IconOutputs, IconPublish, IconAccounts, IconChart, IconSkills, IconProfile,
} from './icons';
import { IconGear } from './settingsIcons';
import Swatch from './ui/Swatch';

export type { Page } from '../lib/layers';

interface SidebarProps {
  currentPage: Page;
  onPageChange: (page: Page) => void;
  personas: PersonaItem[];
  selectedPersona: string;
  onPersonaChange: (persona: string) => void;
  onNewProfile: () => void;
  activeSessionHasMessages: boolean;
  activeChatTitle?: string;
  gatewayStatus: string;
  onOpenSettings: () => void;
}

const PAGE_ICON: Record<Page, ComponentType<{ size?: number }>> = {
  dashboard: IconDashboard, chat: IconChat,
  trends: IconFire, breakdown: IconLayers,
  ideas: IconIdea, calendar: IconCalendar,
  outputs: IconOutputs,
  publish: IconPublish, accounts: IconAccounts,
  analytics: IconChart,
  skills: IconSkills, profile: IconProfile,
};

export default function Sidebar({
  currentPage, onPageChange, personas, selectedPersona, onPersonaChange, onNewProfile,
  activeSessionHasMessages, activeChatTitle, gatewayStatus, onOpenSettings,
}: SidebarProps) {
  const statusText = gatewayStatus === 'connected' ? '网关已连接'
    : gatewayStatus === 'disconnected' ? '网关离线' : '连接中…';
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img className="sidebar-logo-icon" src="./static/easel-icon-transparent.png" alt="" />
        <span className="sidebar-wordmark">Easel</span>
      </div>

      <select
        className="field persona-select"
        value={selectedPersona}
        onChange={(e) => {
          if (e.target.value === '__new__') { onNewProfile(); return; }
          onPersonaChange(e.target.value);
        }}
        disabled={activeSessionHasMessages}
        title={activeSessionHasMessages ? '当前对话已绑定画像，切换画像将新建对话' : '选择用户画像'}
        aria-label="画像"
      >
        <option value="">通用模式</option>
        {personas.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
        <option value="__new__">+ 新建画像…</option>
      </select>

      <nav className="sidebar-nav" aria-label="主导航">
        {NAV_GROUPS.map((g, gi) => (
          <div key={gi} className="nav-group">
            {g.layer && (
              <div className="nav-group-title"><Swatch layer={g.layer} />{layerInfo(g.layer).name}</div>
            )}
            {g.items.map(({ page, label }) => {
              const Icon = PAGE_ICON[page];
              const active = currentPage === page;
              return (
                <button
                  key={page}
                  type="button"
                  className={`nav-item${active ? ' active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  title={label}
                  onClick={() => onPageChange(page)}
                >
                  <span className="nav-icon"><Icon size={16} /></span>
                  <span className="nav-label">{label}</span>
                  {page === 'chat' && activeChatTitle && (
                    <span className="nav-sub" title={activeChatTitle}>{activeChatTitle}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-status">
        <span className={`status-dot${gatewayStatus === 'connected' ? '' : ' offline'}`} aria-hidden="true" />
        <span className="sidebar-status-text">{statusText}</span>
        <button type="button" className="settings-gear" onClick={onOpenSettings} title="设置（模型 · 环境 · 更多）">
          <IconGear size={14} /><span className="nav-label">设置</span>
        </button>
      </div>
    </aside>
  );
}
```

先确认 `icons.tsx` 导出了 `IconFire`、`IconIdea`、`IconCalendar`、`IconPublish`、`IconChart`、`IconLayers`：

```bash
grep -n "export const Icon\(Fire\|Idea\|Calendar\|Publish\|Chart\|Layers\)" src/components/icons.tsx
```

预期 6 行。缺哪个就换成语义相近的已有图标。

- [ ] **Step 5：`App.tsx` 接线，删掉 `SubNav.tsx`**

1. 删掉 `import SubNav from './components/SubNav';`，然后 `git rm src/components/SubNav.tsx`。
2. 加上 `import ChatSessionList from './components/ChatSessionList';` 和 `import ChatLayout from './components/ChatLayout';`。
3. `<Sidebar …/>` 的 props 改为：

```tsx
      <Sidebar
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        personas={personas}
        selectedPersona={selectedPersona}
        onPersonaChange={handlePersonaChange}
        onNewProfile={() => setShowWizard(true)}
        activeSessionHasMessages={activeSession ? activeSession.messages.length > 0 : false}
        activeChatTitle={activeSession && activeSession.messages.length > 0 ? activeSession.title : undefined}
        gatewayStatus={gatewayStatus}
        onOpenSettings={() => setSettingsOpen(true)}
      />
```

4. `<main className="main-content">` 里删掉 SubNav 那段条件渲染，只保留 `<div className="page-host">{renderPage()}</div>`。
5. `renderPage` 的 `case 'chat':` 改为用 `ChatLayout` 包住。`ChatPage` 元素原样放进去，它的 `key` 和全部 props（`session`、`stream`、`onSend`、`onStop`、`onResend`、`onQuestionAnswered` 那一整段回调）一个字都不改：

```tsx
      case 'chat':
        return (
          <ChatLayout
            sessions={(
              <ChatSessionList
                sessions={sessions}
                activeSessionId={activeSessionId}
                onSelect={handleSessionSelect}
                onDelete={handleSessionDelete}
                onRename={handleSessionRename}
                onArchive={handleSessionArchive}
                onNew={handleNewChat}
              />
            )}
          >
            {activeSession ? (
              <ChatPage
                key={activeSession.id}
                session={activeSession}
                stream={streams[activeSession.id]}
                onSend={(displayText, attachments) => handleSendMessage(activeSession.id, displayText, attachments)}
                onStop={() => handleStopStream(activeSession.id)}
                onResend={(userIndex, displayText, attachments, legacyAgentText) => handleResend(
                  activeSession.id, userIndex, displayText, attachments, legacyAgentText,
                )}
                onQuestionAnswered={(qid) => {
                  /* 原有函数体整段原样保留，不改一行 */
                }}
              />
            ) : null}
          </ChatLayout>
        );
```

   `onQuestionAnswered` 的函数体必须是原来的完整实现（`answeredRef` 和 `streamAcc` 那段）。上面的注释只是表示「照搬」，提交前确认没有被替换成注释。

6. `main.tsx`：`export const BUILD_ID = 'studio-1';`

- [ ] **Step 6：写 `layout.css` 和 `pages/chat.css`（外壳部分），删掉 legacy 段落**

`src/styles/layout.css`：

```css
.app-layout { display: flex; height: 100%; width: 100%; }
.main-content { flex: 1; min-width: 0; height: 100%; overflow: hidden; display: flex; flex-direction: column; background: var(--c-canvas); }
.page-host { flex: 1; min-height: 0; overflow: hidden; background: var(--c-canvas); }
.page-scroll { height: 100%; overflow-y: auto; }

.sidebar {
  width: var(--sidebar-width); min-width: var(--sidebar-width); height: 100%;
  display: flex; flex-direction: column; gap: var(--sp-3);
  padding: 18px 12px 12px; overflow: hidden;
  background: var(--c-side); border-right: 1px solid var(--c-rule);
}
.sidebar-brand { display: flex; align-items: center; gap: 9px; padding: 0 6px; }
.sidebar-logo-icon { width: 26px; height: 26px; border-radius: 7px; object-fit: cover; display: block; }
.sidebar-wordmark { font-family: var(--font-brand); font-style: italic; font-weight: 600; font-size: 24px; letter-spacing: -0.5px; line-height: 1; color: var(--c-ink); }
.persona-select { font-size: var(--fs-13); min-height: 34px; padding: 6px 10px; }

.sidebar-nav { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.nav-group { display: flex; flex-direction: column; gap: 1px; }
.nav-group-title { display: flex; align-items: center; gap: 7px; padding: 4px 10px 2px; font-size: var(--fs-12); color: var(--c-ink-3); }
.nav-item {
  position: relative; display: flex; align-items: center; gap: 9px; min-width: 0;
  padding: 6px 10px; border: none; border-radius: var(--r-control); background: none;
  color: var(--c-ink-2); font-size: 13.5px; text-align: left; cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.nav-item:hover { background: var(--c-hover); color: var(--c-ink); }
.nav-item.active { background: var(--c-surface); color: var(--c-ink); font-weight: 600; box-shadow: 0 1px 0 var(--c-rule); }
.nav-item.active::before { content: ''; position: absolute; left: -12px; top: 7px; bottom: 7px; width: 3px; border-radius: 0 2px 2px 0; background: var(--c-ink); }
.nav-icon { display: inline-flex; flex: none; opacity: 0.8; }
.nav-label { flex: none; }
.nav-sub { flex: 1; min-width: 0; text-align: right; font-size: var(--fs-12); font-weight: 400; color: var(--c-ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.sidebar-status { display: flex; align-items: center; gap: var(--sp-2); padding: 10px 6px 0; border-top: 1px solid var(--c-rule); font-size: var(--fs-12); color: var(--c-ink-3); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--c-ok); flex: none; box-shadow: none; }
.status-dot.offline { background: var(--c-danger); }
.sidebar-status-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.settings-gear { margin-left: auto; display: inline-flex; align-items: center; gap: 5px; padding: 4px 8px; background: none; border: 1px solid transparent; border-radius: var(--r-control); color: var(--c-ink-2); font-size: var(--fs-12); cursor: pointer; }
.settings-gear:hover { background: var(--c-hover); color: var(--c-ink); }

/* ---- 窄屏：侧栏收成图标条 ---- */
@media (max-width: 1023px) {
  .sidebar { width: var(--sidebar-rail); min-width: var(--sidebar-rail); padding: 14px 8px 10px; align-items: center; }
  .sidebar-wordmark, .nav-label, .nav-sub, .nav-group-title, .sidebar-status-text { display: none; }
  .persona-select { display: none; }
  .nav-group { align-items: center; }
  .nav-group + .nav-group { border-top: 1px solid var(--c-rule); padding-top: 8px; }
  .nav-item { justify-content: center; width: 40px; height: 36px; padding: 0; }
  .nav-item.active::before { left: -8px; }
  .sidebar-status { flex-direction: column; padding: 8px 0 0; }
  .settings-gear { margin-left: 0; }
}
```

`src/styles/pages/chat.css`（本任务只写外壳和会话栏，Task 6 再追加对话区样式）：

```css
/* ---- 两栏外壳 ---- */
.chat-layout { position: relative; display: grid; grid-template-columns: 236px minmax(0, 1fr); height: 100%; }
.chat-sessions-pane { min-height: 0; overflow: hidden; background: var(--c-sunken); border-right: 1px solid var(--c-rule); }
.chat-main { min-width: 0; min-height: 0; height: 100%; }
.chat-sessions-toggle { display: none; }

/* ---- 会话列表 ---- */
.session-list { display: flex; flex-direction: column; height: 100%; padding: 16px 10px; }
.session-list-head { display: flex; align-items: center; justify-content: space-between; padding: 0 6px 10px; }
.session-list-title { font-size: 15px; }
.session-list-body { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
.session-empty { padding: 8px 6px; font-size: var(--fs-12); color: var(--c-ink-3); }
.session-item {
  display: flex; align-items: center; gap: 4px; min-width: 0;
  padding: 7px 8px 7px 10px; border-radius: var(--r-control);
  font-size: var(--fs-13); color: var(--c-ink-2); cursor: pointer;
  transition: background var(--t-fast), color var(--t-fast);
}
.session-item:hover { background: var(--c-hover); color: var(--c-ink); }
.session-item.active { background: var(--c-surface); color: var(--c-ink); font-weight: 600; box-shadow: 0 1px 0 var(--c-rule); }
.session-item-title { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-actions { display: none; gap: 2px; flex: none; }
.session-item:hover .session-actions, .session-item:focus-within .session-actions { display: flex; }
.session-act { display: inline-flex; padding: 3px; border: none; background: none; border-radius: 4px; color: var(--c-ink-3); cursor: pointer; }
.session-act:hover { color: var(--c-ink); background: var(--c-hover); }
.session-act.danger:hover { color: var(--c-danger); background: var(--c-danger-soft); }
.session-rename-input { min-height: 28px; padding: 3px 8px; font-size: var(--fs-13); }
.archived-header { display: flex; align-items: center; gap: 6px; margin-top: 10px; padding: 6px 10px; border: none; background: none; font-size: var(--fs-12); color: var(--c-ink-3); cursor: pointer; text-align: left; }
.archived-header:hover { color: var(--c-ink); }
.archived-chevron { display: inline-flex; transition: transform var(--t-fast); }
.archived-chevron.open { transform: rotate(90deg); }

/* ---- 窄屏：会话栏收起为浮层 ---- */
@media (max-width: 1199px) {
  .chat-layout { grid-template-columns: minmax(0, 1fr); }
  .chat-sessions-pane { display: none; position: absolute; z-index: 20; top: 0; bottom: 0; left: 0; width: 260px; box-shadow: var(--shadow-pop); }
  .chat-layout.sessions-open .chat-sessions-pane { display: block; }
  .chat-sessions-toggle { display: inline-flex; position: absolute; z-index: 21; top: 12px; left: 16px; }
  .chat-layout.sessions-open .chat-sessions-toggle { left: 276px; }
}
```

从 `legacy.css` 删掉 `/* ============ Layout ============ */` 段（到下一个 `/* ====` 注释之前）、`侧栏会话操作` 段、`子工具顶部小导航` 段。`index.css` 在 `ui/overlay.css` 之后、pages 之前插入 `@import './layout.css';`，在 pages 部分追加 `@import './pages/chat.css';`。

- [ ] **Step 7：检查并提交**

```bash
npm test && npm run build && npm run lint
grep -rn "SubNav" src   # 预期无结果
```

浏览器点测：
- 在 1440 宽下，侧栏按五层分组；对话页左侧是会话栏；新建、重命名、归档、删除、查看已归档都正常。
- 在 1100 宽下，会话栏收起，「对话记录」按钮能展开，选中会话后自动收起。
- 在 1000 宽下，侧栏变成图标条。
- 流式对话进行中切到工作台再切回来，消息继续流。

```bash
git add -A web/frontend
git commit -m "feat(web): 侧栏按流水线五层分组，对话记录移进对话页，去掉子工具导航

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6：对话页

**Files:**
- Modify：
  - `src/components/ChatPage.tsx`：空态、会话页头、建议列表
  - `src/components/MessageBubble.tsx`：只改展示文字，去 emoji
  - `src/components/QuestionCards.tsx`、`src/components/BrushEntry.tsx`：换用 `Button`、`Tag`、`Tabs`，去掉内联颜色
  - `src/styles/pages/chat.css`（追加）
  - `src/styles/legacy.css`：删掉 `/* ============ Chat page ============ */`（含 ask_user 问答卡片小节）、`/* ============ Loading / typing ============ */`、`/* ============ 消息操作条… */` 三段
- Create：`src/components/ChatPage.test.tsx`

**Interfaces:**
- Consumes：`Swatch`、`Button`、`Tag`、`Tabs`、`LayerKey`。
- Produces：`ChatPage` 的 props 不变。

- [ ] **Step 1：写失败的测试**

`src/components/ChatPage.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({ uploadFiles: vi.fn(), adoptOversize: vi.fn() }));

import ChatPage from './ChatPage';
import type { ChatSession } from '../lib/store';

const empty = { id: 's1', title: '新对话', created: 0, messages: [] } as ChatSession;
const EMOJI = /\p{Extended_Pictographic}/u;

describe('ChatPage 空态', () => {
  it('四条起步建议带层色小方块、不含 emoji，点击直接发送', () => {
    const onSend = vi.fn();
    const { container } = render(
      <ChatPage session={empty} onSend={onSend} onStop={() => {}} onResend={() => {}} />,
    );
    const items = container.querySelectorAll('.starter');
    expect(items.length).toBe(4);
    items.forEach((el) => {
      expect(el.querySelector('.ui-swatch')).toBeTruthy();
      expect(EMOJI.test(el.textContent || '')).toBe(false);
    });
    fireEvent.click(screen.getByText('蹭个热点'));
    expect(onSend).toHaveBeenCalledWith('看看现在微博和抖音有什么热搜，挑几个适合我做二创的选题');
  });

  it('标题用问候语加「想创作点什么？」', () => {
    render(<ChatPage session={empty} onSend={() => {}} onStop={() => {}} onResend={() => {}} />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/想创作点什么？$/);
  });
});

describe('ChatPage 对话态', () => {
  it('页头显示会话标题和画像', () => {
    const s = { ...empty, title: '国庆出片文案', persona: '在逃空指针', messages: [{ role: 'user', content: '写一条' }] } as ChatSession;
    render(<ChatPage session={s} onSend={() => {}} onStop={() => {}} onResend={() => {}} />);
    expect(screen.getByRole('heading', { level: 2, name: '国庆出片文案' })).toBeTruthy();
    expect(screen.getByText('画像：在逃空指针')).toBeTruthy();
  });
});
```

jsdom 没有 `scrollIntoView`。如果 `ChatPage` 在 effect 里调用了它，就在 `src/test/setup.ts` 末尾加一行 `Element.prototype.scrollIntoView = () => {};`。

运行：`npm test -- src/components/ChatPage.test.tsx`。预期：失败，`.starter` 还不存在，也还没有对话页头。

- [ ] **Step 2：改 `ChatPage.tsx`**

1. `SUGGESTIONS` 改为下面这样（提示词原样保留）：

```ts
const SUGGESTIONS: { layer: LayerKey; title: string; prompt: string }[] = [
  { layer: 'discover', title: '蹭个热点', prompt: '看看现在微博和抖音有什么热搜，挑几个适合我做二创的选题' },
  { layer: 'produce', title: '写小红书文案', prompt: '帮我写一条小红书种草文案，主题先问我' },
  { layer: 'produce', title: '做金句卡片', prompt: '把一句走心的话做成一张适合发朋友圈的金句卡片' },
  { layer: 'produce', title: '口播脚本', prompt: '帮我写一条 60 秒的口播短视频脚本，主题先问我' },
];
```

   同时加上 `import type { LayerKey } from '../lib/layers';` 和 `import Swatch from './ui/Swatch';`。

2. 空态 `return` 整块替换为：

```tsx
  if (isEmpty) {
    return (
      <div className="chat-page">
        <div className="chat-hero">
          <div className="chat-hero-brand">
            <img src="./static/easel-icon-transparent.png" alt="" />
            <span>Easel</span>
          </div>
          <h1 className="chat-hero-title">{greeting()}</h1>
          <p className="chat-hero-sub">从选题到发布，把想法做成能发的内容。</p>
          {inputBox(true)}
          <ul className="starters" aria-label="起步建议">
            {SUGGESTIONS.map((s) => (
              <li key={s.title}>
                <button type="button" className="starter" disabled={isStreaming}
                  onClick={() => { if (!isStreaming) onSend(s.prompt); }}>
                  <Swatch layer={s.layer} />
                  <span className="starter-title">{s.title}</span>
                  <span className="starter-text">{s.prompt}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
```

3. 对话态：在 `<div className="chat-messages">` 之前插入会话页头：

```tsx
      <header className="chat-head">
        <h2 className="chat-head-title" title={session.title}>{session.title}</h2>
        <span className="chat-head-persona">画像：{session.persona || '通用模式'}</span>
      </header>
```

4. 输入框底栏的提示文字 `'Enter 发送 · Shift+Enter 换行'` 改为 `'Enter 发送，Shift+Enter 换行'`。

- [ ] **Step 3：`MessageBubble.tsx` 只改展示文字**

- `🧠 执行过程（N 步）` 改为 `执行过程（N 步）`。
- `💭 思考过程` 改为 `思考过程`。
- `<span className="live-still"> · {liveHint}</span>` 改为 `<span className="live-still">{liveHint}</span>`，间距交给 CSS。
- 其余逻辑一行都不动。

- [ ] **Step 4：`QuestionCards.tsx` 和 `BrushEntry.tsx`**

- 所有 `<button className="btn …">` 改为 `<Button variant=… size=…>`。原来的 `btn-primary` 对应 `primary`，`btn-sm` 对应 `size="sm"`，`btn-ghost` 对应 `ghost`。
- 删掉所有内联的 `color`、`background`、`border` 样式，改用 CSS 类，写进 `chat.css`。
- `BrushEntry` 里的分类切换如果是一排按钮加 `active` 类，改用 `<Tabs size="sm" …>`。状态点 `DOT` 映射保留原类名，只在 `chat.css` 里改颜色：`s-done` 用 `--c-ok`，`s-ready` 用 `--layer-discover`，`s-need` 用 `--c-warn`，`s-incoming` 用 `--c-ink-3`。
- 去掉文案里的 emoji。

- [ ] **Step 5：`chat.css` 追加对话区样式，删掉 legacy 段落**

执行前先 `grep -n "className=" src/components/ChatPage.tsx src/components/MessageBubble.tsx src/components/QuestionCards.tsx src/components/BrushEntry.tsx` 列出实际用到的类名。下面的规则必须覆盖其中每一个在 legacy 里有样式的类；没列出的类，在删掉 legacy 段落之前，把原规则搬过来并改用新变量。

```css
/* ---- 对话区 ---- */
.chat-page { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.chat-head { display: flex; align-items: center; gap: var(--sp-3); padding: 14px 28px; border-bottom: 1px solid var(--c-rule); min-width: 0; }
.chat-head-title { flex: 1; min-width: 0; font-size: var(--fs-16); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-head-persona { flex: none; font-size: var(--fs-12); color: var(--c-ink-3); }
.chat-messages { flex: 1; min-height: 0; overflow-y: auto; }
.chat-thread { max-width: 760px; margin: 0 auto; padding: 22px 28px; display: flex; flex-direction: column; gap: 18px; }

.message-row { display: flex; }
.message-row.user { justify-content: flex-end; }
.msg-col { display: flex; flex-direction: column; min-width: 0; }
.msg-col.user { align-items: flex-end; max-width: 70%; }
.msg-col.assistant { max-width: 680px; width: 100%; }
.message-bubble.user { background: var(--c-tint); color: var(--c-ink); border-radius: 12px 12px 3px 12px; padding: 9px 14px; white-space: pre-wrap; word-break: break-word; }
.message-bubble.assistant { background: none; border: none; padding: 0; color: var(--c-ink); line-height: 1.75; word-break: break-word; }
.message-bubble.assistant h1, .message-bubble.assistant h2, .message-bubble.assistant h3, .message-bubble.assistant h4 { font-family: var(--font-serif); margin: 14px 0 6px; }
.message-bubble.assistant h1 { font-size: 19px; }
.message-bubble.assistant h2 { font-size: 17px; }
.message-bubble.assistant h3, .message-bubble.assistant h4 { font-size: 15.5px; }
.message-bubble.assistant p { margin: 6px 0; }
.message-bubble.assistant ul, .message-bubble.assistant ol { padding-left: 22px; margin: 6px 0; }
.message-bubble.assistant code { background: var(--c-sunken); padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
.message-bubble.assistant pre { background: var(--c-sunken); border: 1px solid var(--c-rule); border-radius: 8px; padding: 12px 14px; overflow-x: auto; }
.message-bubble.assistant pre code { background: none; padding: 0; }
.message-bubble.assistant blockquote { border-left: 3px solid var(--c-rule-strong); padding-left: 12px; color: var(--c-ink-2); }
.message-bubble.assistant table { border-collapse: collapse; margin: 8px 0; font-size: var(--fs-13); }
.message-bubble.assistant th, .message-bubble.assistant td { border: 1px solid var(--c-rule); padding: 5px 10px; }
.message-bubble.assistant img { max-width: 100%; border-radius: 8px; border: 1px solid var(--c-rule); }

/* 产物链接排成文件卡片（链接由 linkifyOutputs 生成，不改逻辑） */
.message-bubble.assistant a { color: var(--c-ink); text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--c-rule-strong); }
.message-bubble.assistant a[href*="/api/media/"],
.message-bubble.assistant a[href^="#/outputs/"] {
  display: inline-flex; align-items: center; gap: 8px; max-width: 100%;
  margin: 2px 0; padding: 6px 12px; border: 1px solid var(--c-rule); border-radius: 8px;
  background: var(--c-surface); text-decoration: none; font-size: var(--fs-13);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle;
}
.message-bubble.assistant a[href*="/api/media/"]::before,
.message-bubble.assistant a[href^="#/outputs/"]::before { content: ''; flex: none; width: 8px; height: 8px; border-radius: 2px; background: var(--layer-produce); }
.message-bubble.assistant a[href*="/api/media/"]:hover,
.message-bubble.assistant a[href^="#/outputs/"]:hover { border-color: var(--c-ink-3); }

/* 运行中标签 / 思考过程 */
.live-panel { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.live-activity { display: inline-flex; align-items: center; gap: 8px; align-self: flex-start; max-width: 100%; padding: 3px 10px; border: 1px solid var(--c-rule); border-radius: var(--r-control); background: var(--c-surface); font-size: var(--fs-12); color: var(--c-ink-2); }
.live-pulse { width: 8px; height: 8px; border-radius: 2px; background: var(--layer-produce); flex: none; animation: blink 1.4s ease-in-out infinite; }
.live-still { color: var(--c-ink-3); }
.live-still::before { content: '，'; }
.thinking-block { border: 1px solid var(--c-rule); border-radius: 8px; background: var(--c-sunken); font-size: var(--fs-12); color: var(--c-ink-2); }
.thinking-block summary { padding: 6px 10px; cursor: pointer; }
.thinking-text { padding: 0 10px 8px; white-space: pre-wrap; max-height: 240px; overflow-y: auto; }
.streaming-cursor { display: inline-block; width: 7px; height: 15px; margin-left: 2px; vertical-align: -2px; background: var(--c-ink); animation: blink 1s step-end infinite; }
.typing-indicator { display: inline-flex; gap: 4px; padding: 6px 0; }
.typing-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--c-ink-3); animation: blink 1.2s ease-in-out infinite; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

/* 消息操作条 */
.msg-actions { display: flex; gap: 2px; margin-top: 4px; opacity: 0; transition: opacity var(--t-fast); }
.message-row:hover .msg-actions, .msg-actions:focus-within { opacity: 1; }
.msg-action { display: inline-flex; align-items: center; gap: 4px; padding: 3px 7px; border: none; border-radius: 4px; background: none; font-size: var(--fs-12); color: var(--c-ink-3); cursor: pointer; }
.msg-action:hover { background: var(--c-hover); color: var(--c-ink); }

/* 输入框 */
.chat-input-area { padding: 8px 28px 18px; background: var(--c-canvas); }
.chat-input-inner { max-width: 760px; margin: 0 auto; }
.composer-bar { display: flex; align-items: center; gap: var(--sp-2); margin-top: var(--sp-2); }
.composer-hint { margin-left: auto; font-size: var(--fs-12); color: var(--c-ink-3); }
.composer-attach-btn { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px; border: 1px solid var(--c-rule-strong); border-radius: var(--r-control); background: var(--c-surface); font-size: var(--fs-12); color: var(--c-ink-2); cursor: pointer; }
.composer-attach-btn:hover:not(:disabled) { border-color: var(--c-ink-3); color: var(--c-ink); }
.send-btn { display: inline-grid; place-items: center; width: 32px; height: 32px; border: none; border-radius: 8px; background: var(--c-ink); color: var(--c-on-ink); cursor: pointer; }
.send-btn:hover:not(:disabled) { background: var(--c-ink-hover); }
.send-btn:disabled { background: var(--c-rule-strong); cursor: not-allowed; }

/* 空态 */
.chat-hero { max-width: 700px; margin: 0 auto; padding: 12vh 28px 40px; display: flex; flex-direction: column; align-items: stretch; background: none; }
.chat-hero-brand { display: flex; align-items: center; justify-content: center; gap: 9px; }
.chat-hero-brand img { width: 30px; height: 30px; }
.chat-hero-brand span { font-family: var(--font-brand); font-style: italic; font-weight: 600; font-size: 28px; letter-spacing: -0.5px; }
.chat-hero-title { margin-top: var(--sp-4); text-align: center; font-size: 30px; letter-spacing: 0.5px; }
.chat-hero-sub { margin: var(--sp-2) 0 var(--sp-6); text-align: center; font-size: var(--fs-14); color: var(--c-ink-2); }
.starters { list-style: none; margin-top: var(--sp-5); display: grid; grid-template-columns: 1fr 1fr; gap: 0 var(--sp-5); }
.starter { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; align-items: baseline; width: 100%; padding: 12px 4px; border: none; border-bottom: 1px solid var(--c-rule); background: none; text-align: left; cursor: pointer; }
.starter .ui-swatch { align-self: center; }
.starter-title { font-family: var(--font-serif); font-weight: 600; font-size: 15px; color: var(--c-ink); }
.starter-text { grid-column: 2; font-size: var(--fs-13); color: var(--c-ink-2); }
.starter:hover .starter-title { text-decoration: underline; text-underline-offset: 3px; }
.starter:disabled { opacity: 0.5; cursor: not-allowed; }
@media (max-width: 1199px) { .chat-head { padding-left: 120px; } }
@media (max-width: 760px) { .starters { grid-template-columns: 1fr; } }
```

输入框外壳（以 `inputBox()` 里实际用到的类名为准）的样式：白底 `var(--c-surface)`，边框 `1px solid var(--c-rule-strong)`，圆角 12px，阴影 `var(--shadow-composer)`，内边距 12px 14px；`:focus-within` 时边框变为 `var(--c-ink-3)`。把这条规则写进 `chat.css`。

从 `legacy.css` 删掉 Chat page、Loading / typing、消息操作条三段。删除之前，用上面 grep 得到的类名逐个核对新 `chat.css` 里都有对应规则。

- [ ] **Step 6：检查并提交**

```bash
npm test && npm run build && npm run lint
```

浏览器点测：
- 空对话的欢迎页和四条建议。
- 发一条短消息，比如「你好，只回复一个字」：流式光标、运行中标签、思考过程折叠、复制和重试都正常。
- 让 Easel 生成一个带产物路径的回复（或打开一个旧会话），检查产物链接是否显示成文件卡片。
- 笔入口菜单、问答卡片。

```bash
git add -A web/frontend
git commit -m "polish(web): 对话页改版，会话页头、起步建议、产物卡片与输入框

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7：技能库

**Files:**
- Modify：
  - `src/components/SkillPage.tsx`（渲染和层定义整体改写，数据逻辑保留）
  - `src/components/SkillDrawer.tsx`：换用 `Button`、`Tag`、`Field`，去内联颜色，显示英文代号
  - `src/styles/legacy.css`：删掉 `/* ============ Skills gallery ============ */` 段，以及散落在文件末尾的 `.skill-card-*`、`.skill-detail-*` 规则（先 `grep -n "skill-" src/styles/legacy.css` 定位）
  - `src/styles/index.css`
- Create：`src/components/SkillPage.test.tsx`、`src/styles/pages/skills.css`

**Interfaces:**
- Consumes：`LAYERS`、`isLayerKey`、`LayerKey`、`PageHeader`、`Swatch`、`Tag`、`EmptyState`、`Input`。
- Produces：无新接口。

- [ ] **Step 1：写失败的测试**

`src/components/SkillPage.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({ fetchSkills: vi.fn() }));
vi.mock('./SkillDrawer', () => ({ default: ({ skillName }: { skillName: string }) => <div role="dialog">{skillName}</div> }));

import * as api from '../lib/api';
import SkillPage from './SkillPage';

const SKILLS = [
  { name: 'skill-trending-topics', description: '抓取实时热搜', layer: 'discover', needsApi: false, apiConfigured: false },
  { name: 'skill-news-intelligence', description: '行业情报', layer: 'discover', needsApi: true, apiConfigured: false },
  { name: 'copywriting', description: '营销文案', layer: 'produce', needsApi: false, apiConfigured: false },
  { name: 'ai-video-gen', description: '生成视频', layer: 'produce', needsApi: true, apiConfigured: true },
];

describe('SkillPage', () => {
  it('左侧索引显示各层真实数量，层名用「生产」不用「制作」', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    const { container } = render(<SkillPage persona="" />);
    await screen.findAllByText('营销 / 带货文案');
    const idx = [...container.querySelectorAll('.skill-index-item')].map((n) => n.textContent);
    expect(idx).toEqual(['发现2', '生产2']);
    expect(container.textContent).not.toContain('制作');
  });

  it('只有「需要 key 且未配置」的技能挂「需 key」，不显示英文代号', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    const { container } = render(<SkillPage persona="" />);
    await screen.findAllByText('营销 / 带货文案');
    expect(screen.getAllByText('需 key').length).toBe(1);
    expect(container.textContent).not.toContain('skill-news-intelligence');
  });

  it('点技能打开详情抽屉', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    render(<SkillPage persona="" />);
    fireEvent.click(await screen.findByText('营销 / 带货文案'));
    expect(screen.getByRole('dialog').textContent).toBe('copywriting');
  });

  it('加载失败时给出提示和重试', async () => {
    vi.mocked(api.fetchSkills).mockRejectedValue(new Error('x'));
    render(<SkillPage persona="" />);
    expect(await screen.findByText(/技能列表加载失败/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
  });
});
```

`'营销 / 带货文案'` 来自 `skillDisplayNames.ts` 里 `copywriting` 的中文名。执行前先 `grep -n "'copywriting'" src/lib/skillDisplayNames.ts` 确认；如果名称不同，同步改测试里的字符串。

运行：`npm test -- src/components/SkillPage.test.tsx`。预期：失败。

- [ ] **Step 2：改写 `SkillPage.tsx`**

删掉 `LAYERS`、`LAYER_META`、`OTHER`、`iconFor`、`LAYER_DESC` 和所有图标 import。`load`、`filtered`、`selected` 的逻辑保留，`grouped` 的分组键改用 `isLayerKey`。完整文件如下：

```tsx
import { useState, useEffect, useMemo, useRef } from 'react';
import { fetchSkills } from '../lib/api';
import type { SkillItem } from '../lib/api';
import SkillDrawer from './SkillDrawer';
import { displayName } from '../lib/skillDisplayNames';
import { LAYERS, isLayerKey } from '../lib/layers';
import type { LayerKey } from '../lib/layers';
import PageHeader from './ui/PageHeader';
import Swatch from './ui/Swatch';
import Tag from './ui/Tag';
import EmptyState from './ui/EmptyState';
import { Input } from './ui/Field';

interface SkillPageProps { persona: string; }

type GroupKey = LayerKey | 'other';

export default function SkillPage({ persona }: SkillPageProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [activeLayer, setActiveLayer] = useState<GroupKey | ''>('');
  const bodyRef = useRef<HTMLDivElement>(null);

  const load = () => {
    setError('');
    fetchSkills().then(setSkills).catch(() => setError('技能列表加载失败'));
  };
  useEffect(load, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter((s) =>
      s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q) || displayName(s.name).toLowerCase().includes(q));
  }, [skills, query]);

  const grouped = useMemo(() => {
    const g: Partial<Record<GroupKey, SkillItem[]>> = {};
    for (const s of filtered) {
      const key: GroupKey = isLayerKey(s.layer) ? s.layer : 'other';
      (g[key] ||= []).push(s);
    }
    return g;
  }, [filtered]);

  const sections: { key: GroupKey; name: string; desc: string }[] = [
    ...LAYERS.map((l) => ({ key: l.key as GroupKey, name: l.name, desc: l.desc })),
    { key: 'other' as GroupKey, name: '其他', desc: '未标注层的技能' },
  ].filter((sec) => grouped[sec.key]?.length);

  const needKeyCount = skills.filter((s) => s.needsApi && !s.apiConfigured).length;

  // 滚动时高亮当前层（jsdom 无 IntersectionObserver，跳过）
  useEffect(() => {
    const root = bodyRef.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (top) setActiveLayer((top.target as HTMLElement).dataset.layer as GroupKey);
    }, { root, rootMargin: '0px 0px -70% 0px' });
    root.querySelectorAll('section[data-layer]').forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [sections.length]);

  const jump = (key: GroupKey) => {
    setActiveLayer(key);
    document.getElementById(`skill-layer-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const current = activeLayer || sections[0]?.key || '';

  return (
    <div className="skills-page">
      <div className="skills-top">
        <PageHeader
          title="技能库"
          description={`共 ${skills.length} 个技能${needKeyCount ? `，其中 ${needKeyCount} 个要先配 key 才能用` : ''}。点一项看说明，就地运行。`}
        />
      </div>
      <div className="skills-grid">
        <nav className="skill-index" aria-label="按层浏览">
          {sections.map((sec) => (
            <button key={sec.key} type="button"
              className={`skill-index-item${current === sec.key ? ' active' : ''}`}
              onClick={() => jump(sec.key)}>
              <Swatch layer={sec.key === 'other' ? 'general' : sec.key} />
              <span className="skill-index-name">{sec.name}</span>
              <span className="skill-index-count">{grouped[sec.key]?.length ?? 0}</span>
            </button>
          ))}
        </nav>
        <div className="skills-body" ref={bodyRef}>
          <div className="skill-search">
            <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索技能名或说明" aria-label="搜索技能" />
          </div>
          {error && <EmptyState text={`${error}。检查网关是否在运行，然后重试。`} action={{ label: '重试', onClick: load }} />}
          {!error && skills.length > 0 && sections.length === 0 && (
            <EmptyState text={`没有找到和「${query}」相关的技能。换个关键词试试。`} action={{ label: '清除搜索', onClick: () => setQuery('') }} />
          )}
          {sections.map((sec) => (
            <section key={sec.key} id={`skill-layer-${sec.key}`} data-layer={sec.key} className="skill-section">
              <header className="skill-section-head">
                <h2>{sec.name}</h2>
                <span>{sec.desc}</span>
              </header>
              <div className="skill-list">
                {(grouped[sec.key] || []).map((s) => (
                  <button key={s.name} type="button" className="skill-row" onClick={() => setSelected(s.name)}>
                    <span className="skill-row-name">{displayName(s.name)}</span>
                    {s.needsApi && !s.apiConfigured && <Tag tone="warn" title="需要先在详情里配置 API key">需 key</Tag>}
                    <span className="skill-row-desc">{s.description?.trim() || '点开查看说明'}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      {selected && (
        <SkillDrawer
          skillName={selected}
          persona={persona}
          onClose={() => setSelected(null)}
          onConfigured={load}
        />
      )}
    </div>
  );
}
```

`src/styles/pages/skills.css`：

```css
.skills-page { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.skills-top { padding: 26px 34px 0; }
.skills-top .ui-page-header { margin-bottom: var(--sp-4); }
.skills-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 28px; padding: 0 34px; }
.skill-index { display: flex; flex-direction: column; gap: 2px; padding-top: 2px; }
.skill-index-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: none; border-radius: var(--r-control); background: none; font-size: 13.5px; color: var(--c-ink-2); cursor: pointer; text-align: left; }
.skill-index-item:hover { background: var(--c-hover); color: var(--c-ink); }
.skill-index-item.active { background: var(--c-surface); color: var(--c-ink); font-weight: 600; box-shadow: 0 1px 0 var(--c-rule); }
.skill-index-name { flex: 1; }
.skill-index-count { font-size: var(--fs-12); color: var(--c-ink-3); font-variant-numeric: tabular-nums; }
.skills-body { min-height: 0; overflow-y: auto; padding-bottom: 40px; }
.skill-search { max-width: 420px; margin-bottom: var(--sp-2); }
.skill-section { scroll-margin-top: 8px; }
.skill-section-head { display: flex; align-items: baseline; gap: 10px; margin: 20px 0 4px; padding-bottom: 8px; border-bottom: 2px solid var(--layer-general); }
.skill-section[data-layer="discover"] .skill-section-head { border-bottom-color: var(--layer-discover); }
.skill-section[data-layer="plan"] .skill-section-head { border-bottom-color: var(--layer-plan); }
.skill-section[data-layer="produce"] .skill-section-head { border-bottom-color: var(--layer-produce); }
.skill-section[data-layer="publish"] .skill-section-head { border-bottom-color: var(--layer-publish); }
.skill-section[data-layer="attribute"] .skill-section-head { border-bottom-color: var(--layer-attribute); }
.skill-section-head h2 { font-size: 17px; }
.skill-section-head span { font-size: 12.5px; color: var(--c-ink-3); }
.skill-list { display: grid; grid-template-columns: 1fr 1fr; column-gap: 28px; }
.skill-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; align-items: center; padding: 11px 0; border: none; border-bottom: 1px solid var(--c-rule); background: none; text-align: left; cursor: pointer; min-width: 0; }
.skill-row-name { font-family: var(--font-serif); font-weight: 600; font-size: 15px; color: var(--c-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.skill-row-desc { grid-column: 1 / -1; font-size: var(--fs-13); line-height: 1.55; color: var(--c-ink-2); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.skill-row:hover .skill-row-name { text-decoration: underline; text-underline-offset: 3px; }
@media (max-width: 1180px) { .skill-list { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .skills-grid { grid-template-columns: 1fr; } .skill-index { flex-direction: row; flex-wrap: wrap; } }
```

- [ ] **Step 3：`SkillDrawer.tsx`**

- 抽屉头部标题用宋体（沿用 `.drawer-header h2`，已由 base.css 统一为宋体）。
- 在标题下面加一行 `<div className="skill-detail-rawname">{skillName}</div>`，英文代号只在这里显示。
- 所有按钮换成 `Button`；输入框换成 `Input`、`Textarea`；状态标记换成 `Tag`，其中已配置用 `ok`，需要 key 用 `warn`。
- 删掉内联颜色，缺少的样式写进 `skills.css`，写法沿用原 `.skill-detail-*` 规则，改用新变量。
- `.skill-detail-rawname` 的样式为 `font-family: var(--font-mono); font-size: var(--fs-12); color: var(--c-ink-3);`。
- markdown 说明区 `.skill-body-md` 的规则从 legacy 搬到 `skills.css`：标题用宋体，代码底色用 `var(--c-sunken)`。

- [ ] **Step 4：接样式并删掉 legacy 段落，然后检查、提交**

`index.css` 追加 `@import './pages/skills.css';`。从 legacy 删掉 Skills gallery 段，以及 `grep -n "skill-" src/styles/legacy.css` 找到的其余技能规则（确认已搬进 `skills.css`）。

```bash
npm test && npm run build && npm run lint
```

对照 `key-pages.html` 的技能库样稿检查：
- 左侧索引数量是真实值，点击能跳转，滚动时高亮跟着变。
- 搜索和清除正常。
- 抽屉的详情、配置 key、运行都正常。

```bash
git add -A web/frontend
git commit -m "polish(web): 技能库改为按层索引加两栏列表，层名统一为生产

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8：账号页

**Files:**
- Modify：
  - `src/components/AccountsPage.tsx`：只改 `badge` 函数和 `return (...)` 的 JSX，第 1 到 275 行的逻辑一行不动
  - `src/styles/legacy.css`：删掉 `/* ============ Accounts page ============ */` 段，以及 `.account-*`、`.qr-img`、`.accounts-grid` 相关规则
  - `src/styles/index.css`
- Create：`src/components/AccountsPage.test.tsx`、`src/styles/pages/accounts.css`

**Interfaces:**
- Consumes：`PageHeader`、`StatusDot`、`Button`、`Modal`、`Input`。

- [ ] **Step 1：写失败的测试**

`src/components/AccountsPage.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchAccounts: vi.fn(), startLogin: vi.fn(), loginStatus: vi.fn(), mediaUrl: (p: string) => p,
  accountWhoami: vi.fn(() => new Promise(() => {})), logoutAccount: vi.fn(), submitLoginSms: vi.fn(),
  saveCredentials: vi.fn(), getCredentials: vi.fn(), startMpLogin: vi.fn(), mpLoginStatus: vi.fn(),
}));
vi.mock('../lib/whoami', () => ({
  dropOutdatedWhoami: vi.fn(() => []), getWhoamiCache: vi.fn(() => ({})),
  setWhoamiCache: vi.fn(), verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import AccountsPage from './AccountsPage';

describe('AccountsPage', () => {
  it('一行一个平台：已登录显示校验和退出，未登录显示扫码登录主按钮', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'xiaohongshu', name: '小红书', backend: 'xhs', supported: true, loggedIn: true, note: '' },
      { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    const xhs = (await screen.findByText('小红书')).closest('.account-row') as HTMLElement;
    expect(within(xhs).getAllByText('已登录').length).toBeGreaterThan(0);
    expect(within(xhs).getByRole('button', { name: '校验' })).toBeTruthy();
    expect(within(xhs).getByRole('button', { name: '退出' })).toBeTruthy();
    const zhihu = screen.getByText('知乎').closest('.account-row') as HTMLElement;
    const login = within(zhihu).getByRole('button', { name: '扫码登录' });
    expect(login.className).toContain('btn-primary');
  });

  it('页头层标为发布，标题为账号', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([]);
    const { container } = render(<AccountsPage />);
    expect(screen.getByRole('heading', { level: 1, name: '账号' })).toBeTruthy();
    expect(container.querySelector('.ui-layer-mark')?.textContent).toBe('发布');
  });
});
```

运行：`npm test -- src/components/AccountsPage.test.tsx`。预期：失败。

- [ ] **Step 2：改 `badge` 和 JSX**

在文件顶部加上：

```ts
import PageHeader from './ui/PageHeader';
import StatusDot from './ui/StatusDot';
import Button from './ui/Button';
import Modal from './ui/Modal';
import { Input } from './ui/Field';
```

`badge` 函数改名为 `status` 并改为：

```tsx
  const status = (a: AccountItem) => {
    if (!a.supported) return <StatusDot tone="idle">待重写</StatusDot>;
    if (whoami[a.platform] === 'loading') return <StatusDot tone="idle">校验中…</StatusDot>;
    if (effLoggedIn(a)) return <StatusDot tone="ok">已登录</StatusDot>;
    return <StatusDot tone="idle">未登录</StatusDot>;
  };
```

`return (...)` 整块替换为下面的 JSX。每个事件处理和禁用条件都和原来一模一样，只换了容器和组件：

```tsx
  const busyFor = (a: AccountItem) => busy === a.platform || busy === a.platform + ':mp';

  return (
    <div className="page-scroll accounts-page">
      <PageHeader
        layer="publish"
        title="账号"
        description="用手机 App 扫码登录。登录状态保存在本机，之后发布不用再登。"
        actions={<Button size="sm" onClick={load}>刷新状态</Button>}
      />

      {err && <p className="accounts-error" role="alert">{err}</p>}
      {terminalMsg && <div className="accounts-notice">{terminalMsg}</div>}

      <div className="accounts-list">
        {accounts.map((a) => {
          const w = whoami[a.platform];
          const info = w && w !== 'loading' ? w : null;
          const logged = effLoggedIn(a);
          return (
            <div key={a.platform} className={`account-row${a.supported ? '' : ' is-unsupported'}`}>
              <span className="account-platform">{a.name}</span>
              <span className="account-who">
                {logged && info ? (
                  <>
                    <Avatar url={info.avatar} name={info.name || a.name} />
                    <span className="account-nick" title={info.name || ''}>{info.name || '已登录'}</span>
                  </>
                ) : (
                  <span className="account-note">{logged ? '已登录' : (a.note || '未登录')}</span>
                )}
              </span>
              {status(a)}
              <span className="account-actions">
                {logged ? (
                  <>
                    <Button size="sm" disabled={busyFor(a) || w === 'loading'} onClick={() => runWhoami(a.platform)}>
                      {w === 'loading' ? '校验中…' : '校验'}
                    </Button>
                    <Button size="sm" disabled={logoutBusy === a.platform} onClick={() => handleLogout(a)}>
                      {logoutBusy === a.platform ? '退出中…' : '退出'}
                    </Button>
                  </>
                ) : (
                  // 公众号与其它平台统一：都走扫码登录（公众号扫的是后台会话，用于发布+数据）
                  <Button size="sm" variant={a.supported ? 'primary' : 'secondary'}
                    disabled={!a.supported || busyFor(a)}
                    onClick={() => (a.backend === 'wechat-oa' ? handleMpLogin(a) : handleLogin(a))}>
                    {busyFor(a) ? '启动中…' : '扫码登录'}
                  </Button>
                )}
              </span>
            </div>
          );
        })}
      </div>

      <p className="accounts-warn">
        机房或代理 IP 可能被平台判为风险，二维码会弹不出来。遇到这种情况，换干净的家宽网络，或者在能正常登录的机器上登好，再把登录目录拷过来。
      </p>

      {qr && (
        <Modal title={`登录${qr.name}`} width={380} onClose={closeQr}
          footer={<Button onClick={closeQr}>{qr.state === 'success' ? '完成' : '关闭'}</Button>}>
          <p className={`qr-state${qr.state === 'success' ? ' is-ok' : ['error', 'expired'].includes(qr.state) ? ' is-bad' : ''}`}>
            {STATE_LABEL[qr.state] || qr.state}{qr.message ? `：${qr.message}` : ''}
          </p>
          {/* 状态分支，与原实现逐一对应，只换展示：
              sms_required → 说明文字（原正则命中出错关键词时加 qr-error 类）+ <Input className="sms-input" …原 value/onChange/onKeyDown/placeholder/inputMode/autoFocus，去掉 style…> + smsErr（<p className="qr-error">）+ <Button variant="primary" block loading={smsBusy} onClick={submitSms}>提交验证码</Button>
              qr_ready 且有 qr → 原 <img className="qr-img" src={`${mediaUrl(qr.qr)}?v=${qr.qrTs || qrNonce}`} alt="登录二维码" />
              window_login → 有 qr 显示同上 img，否则 <div className="loading"><div className="spinner" />{qr.message || '已弹出浏览器窗口，请在窗口里完成登录，不要关掉它'}</div>
              scanned → loading「扫码成功，正在跳转验证…（首次可能要十几秒）」
              verifying → loading {qr.message || '验证中…'}
              success → <div className="qr-done">登录成功</div>
              error / expired → <p className="qr-error">{qr.message || '登录失败'}。可以关闭后重试，或换干净的网络。</p>
              其他 → loading「准备二维码…」 */}
        </Modal>
      )}

      {cred && (
        <Modal title={`配置${cred.name}`} width={440} onClose={closeCred}
          footer={(
            <>
              <Button onClick={closeCred}>关闭</Button>
              <Button variant="primary" loading={credBusy} onClick={submitCred}>保存并验证</Button>
            </>
          )}>
          <p className="modal-text">
            公众号用官方接口发布，需要填开发者凭证（公众平台 → 设置与开发 → 开发接口管理）。
            还要把本服务器的出口 IP 加进公众号的 IP 白名单，否则会报 40164。文章会发到草稿箱，群发请到公众号后台确认。
          </p>
          {credMsg && <p className="cred-ok">{credMsg}</p>}
          <label className="cred-label">AppID
            <Input value={credForm.appId} autoFocus placeholder="wx..."
              onChange={(e) => setCredForm((f) => ({ ...f, appId: e.target.value.trim() }))} />
          </label>
          <label className="cred-label">AppSecret
            <Input type="password" value={credForm.appSecret} placeholder="开发者密钥（不会回显）"
              onChange={(e) => setCredForm((f) => ({ ...f, appSecret: e.target.value.trim() }))} />
          </label>
          <label className="cred-label">默认作者（可选）
            <Input value={credForm.author} placeholder="文章署名"
              onChange={(e) => setCredForm((f) => ({ ...f, author: e.target.value }))} />
          </label>
          {credErr && <p className="qr-error">{credErr}</p>}
        </Modal>
      )}
    </div>
  );
```

执行者要把 QR 弹窗注释里的每个分支写成真实的 JSX（三元链，顺序与原实现一致），以改动前的原实现为底稿，按注释只换展示，然后删掉这段注释。

`Avatar` 组件保持原逻辑，类名不变（`account-avatar`、`account-avatar-fallback`），样式写进 `accounts.css`。

- [ ] **Step 3：写 `accounts.css`，删掉 legacy 段落**

```css
.accounts-page { padding: 26px 34px 40px; }
.accounts-list { background: var(--c-surface); border: 1px solid var(--c-rule); border-radius: var(--r-panel); }
.account-row { display: grid; grid-template-columns: 130px minmax(0, 1fr) 110px auto; align-items: center; gap: var(--sp-4); padding: 12px 20px; border-bottom: 1px solid var(--c-rule); }
.account-row:last-child { border-bottom: 0; }
.account-row.is-unsupported { opacity: 0.6; }
.account-platform { font-family: var(--font-serif); font-weight: 600; font-size: 15px; }
.account-who { display: flex; align-items: center; gap: 10px; min-width: 0; }
.account-nick { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.account-note { font-size: var(--fs-13); color: var(--c-ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.account-avatar { width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex: none; }
.account-avatar-fallback { display: flex; align-items: center; justify-content: center; font-size: var(--fs-12); font-weight: 600; color: var(--c-on-ink); background: linear-gradient(135deg, var(--layer-discover), var(--layer-publish)); }
.account-actions { display: flex; gap: var(--sp-2); justify-content: flex-end; min-width: 170px; }
.accounts-error { margin-bottom: var(--sp-3); color: var(--c-danger); font-size: var(--fs-13); }
.accounts-notice { margin-bottom: var(--sp-3); padding: 10px 14px; border: 1px solid var(--c-rule); border-radius: 8px; background: var(--c-surface); font-size: var(--fs-13); }
.accounts-warn { margin-top: var(--sp-3); max-width: 80ch; padding: 4px 0 4px 12px; border-left: 3px solid var(--layer-attribute); font-size: 12.5px; color: var(--c-ink-2); }
.qr-state { font-size: var(--fs-13); color: var(--c-ink-2); margin-bottom: var(--sp-3); }
.qr-state.is-ok { color: var(--c-ok); }
.qr-state.is-bad { color: var(--c-danger); }
.qr-img { display: block; width: 220px; height: 220px; margin: 0 auto; object-fit: contain; border: 1px solid var(--c-rule); border-radius: 8px; }
.qr-done { padding: 32px 0; text-align: center; font-family: var(--font-serif); font-weight: 600; font-size: var(--fs-20); color: var(--c-ok); }
.qr-error { font-size: var(--fs-13); color: var(--c-danger); }
.sms-input { text-align: center; letter-spacing: 6px; font-size: var(--fs-20); margin: var(--sp-2) 0; }
.cred-label { display: flex; flex-direction: column; gap: 4px; margin-top: var(--sp-3); font-size: var(--fs-12); color: var(--c-ink-2); }
.cred-ok { font-size: var(--fs-13); color: var(--c-ok); margin-top: var(--sp-2); }
.modal .loading { display: flex; flex-direction: column; align-items: center; gap: var(--sp-3); padding: 36px 0; font-size: var(--fs-13); color: var(--c-ink-2); text-align: center; }
@media (max-width: 900px) { .account-row { grid-template-columns: 1fr auto; } .account-who { grid-column: 1 / -1; order: 3; } }
```

`index.css` 追加 `@import './pages/accounts.css';`。从 legacy 删掉 Accounts page 段和其余 `account-`、`qr-img`、`accounts-grid` 规则。

- [ ] **Step 4：检查并提交**

```bash
npm test && npm run build && npm run lint
```

真机点测，不要真的退出已登录的账号：
- 点快手或知乎的「扫码登录」，弹窗出现，状态文字正确。点关闭后再点一次，确认复用的是同一个后台进程，不会起第二个。
- 点小红书的「校验」，状态变为校验中，之后恢复。
- 按 Esc 能关闭弹窗。

```bash
git add -A web/frontend
git commit -m "polish(web): 账号页改为一行一个平台，扫码与凭证弹窗换用通用弹窗

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9：设置面板与画像向导

**Files:**
- Modify：
  - `src/components/SettingsPanel.tsx`、`src/components/EnvBoard.tsx`
  - `src/components/OnboardingWizard.tsx`
  - `src/styles/legacy.css`：删掉所有 `.settings-overlay` 开头的规则、`.env-*`、`.st-*` 规则，以及向导相关规则（先 grep 定位）
  - `src/styles/index.css`
- Create：`src/styles/pages/settings.css`、`src/components/SettingsPanel.test.tsx`

**Interfaces:**
- Consumes：`Modal`、`Tabs`、`Button`、`StatusDot`、`Tag`、`Input`、`Select`。

- [ ] **Step 1：写失败的测试**

`src/components/SettingsPanel.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchEnvTools: vi.fn(() => Promise.resolve({ tools: [], python: '' })),
  startEnvInstall: vi.fn(), fetchEnvJob: vi.fn(),
  fetchModelChannels: vi.fn(() => Promise.resolve({ channels: { chat: { rows: [] }, transcribe: { rows: [] } }, primary: '' })),
  runChannelSelftest: vi.fn(), saveModelConfig: vi.fn(),
}));

import SettingsPanel from './SettingsPanel';

describe('SettingsPanel', () => {
  it('是对话框，六个模型通道是标签页，Esc 关闭', async () => {
    const onClose = vi.fn();
    render(<SettingsPanel onClose={onClose} />);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(await screen.findAllByRole('tab')).toHaveLength(6);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
```

运行：`npm test -- src/components/SettingsPanel.test.tsx`。预期：失败（现在不是 dialog，也没有 tab 角色）。如果 `fetchModelChannels` 的真实返回结构和 mock 不一致导致渲染报错，按 `lib/api.ts` 里的类型补全 mock。

- [ ] **Step 2：`SettingsPanel.tsx` 换外壳**

1. 先读懂结构：执行 `grep -n "return (\|className=\"settings" src/components/SettingsPanel.tsx`，找到最外层的遮罩和面板容器，以及头部的标题、「保存配置」「全部自测」、关闭按钮。
2. 最外层遮罩和面板容器换成：

```tsx
<Modal width={1080} className="settings-modal" onClose={onClose} closeOnBackdrop={false}
  title={<span className="settings-title">设置<small>模型配置、环境安装和更多设置</small></span>}>
  …原来面板里的内容…
</Modal>
```

3. 删掉文件里原有的 Esc 监听 `useEffect`（Modal 已处理 Esc）。
4. 头部的「保存配置」换成 `<Button variant="primary" loading={saving} …>`，「全部自测」换成 `<Button …>`。原来的关闭按钮换成 `<Button variant="ghost" size="sm" aria-label="关闭设置" onClick={onClose}>关闭</Button>`，保持在头部操作区。
5. 横向的六个模型通道换成 `Tabs`：

```tsx
<Tabs ariaLabel="模型通道" items={CHANNELS.map((c) => ({ key: c.id, label: c.label }))} value={chan} onChange={setChan} />
```

6. 左侧竖向分类（模型配置、环境安装、更多设置）保留为竖向导航，类名沿用原来的，样式改写进 `settings.css`：
   - 选中项的写法和主侧栏 `.nav-item.active` 一样：白底、600 字重、左侧 3px 墨色竖条。
   - 「六个通道」「6/11」这类计数用 `Tag`。
7. 通道状态「已配置 / 未配置」换成 `StatusDot`（`ok` 或 `idle`）；自测结果的好坏用 `ok` 或 `danger`。
8. 所有 `<input>`、`<select>` 换成 `Input`、`Select`。
9. 删掉所有内联的颜色和渐变。`.settings-overlay .btn-primary` 那组渐变覆盖规则随 legacy 一起删掉。

- [ ] **Step 3：`EnvBoard.tsx`**

- 分组标题（视频产线套件、发布链、常用库）用宋体 `<h3 className="env-group-title">`，旁边的「4/7 就绪」用 `Tag`。
- 工具卡片保留网格布局。每张卡片：
  - 名称用宋体 15px。
  - 说明文字。
  - 底部一行：版本号（或状态说明）加操作按钮。
  - 状态用 `StatusDot`：已装是 `ok`，未装是 `idle`，需目录是 `warn`，失败是 `danger`。
- 卡片上的图标方块删掉，图标改为跟在名称前面的 14px 线性图标，颜色 `--c-ink-3`。
- 顶部就绪进度条用墨色（`--c-ink`），底色 `--c-rule`。
- 「全部安装」「整组安装」用 `Button`：「全部安装」是 primary，「整组安装」是 sm secondary。

- [ ] **Step 4：`OnboardingWizard.tsx`**

- 外壳换成 `<Modal title="配置账号画像" width={560} closeOnBackdrop={false} onClose={onClose} footer={…上一步 / 下一步 / 完成…}>`。
- 步骤指示改为墨色：已完成和当前步骤是墨色小圆点，未到的步骤是 `--c-rule-strong`。
- 表单控件换成 `Input`、`Select`、`Textarea`，按钮换成 `Button`。
- 去掉 emoji 和内联颜色。

- [ ] **Step 5：写 `settings.css`，删掉 legacy 规则**

```css
.settings-modal { display: flex; flex-direction: column; height: min(760px, calc(100vh - 40px)); padding: 0; overflow: hidden; }
.settings-modal .modal-title { padding: 20px 24px 12px; margin: 0; border-bottom: 1px solid var(--c-rule); }
.settings-modal .modal-body { flex: 1; min-height: 0; display: flex; }
.settings-title { display: flex; align-items: baseline; gap: 12px; }
.settings-title small { font-family: var(--font-sans); font-weight: 400; font-size: var(--fs-12); color: var(--c-ink-3); }
.env-group-title { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-16); margin: var(--sp-5) 0 var(--sp-3); }
```

- 左侧分类栏宽 200px，底色 `var(--c-sunken)`，右边框 `var(--c-rule)`；内容区 `flex: 1; overflow-y: auto; padding: 20px 24px`。
- 工具卡片：白底、`--c-rule` 边框、`--r-panel` 圆角、内边距 14px 16px；悬停时边框变为 `--c-ink-3`。
- 通道行表格：行分隔线 `--c-rule`；表头 12px `--c-ink-3`，不用全大写。
- 进度条：高 4px，圆角 2px，底色 `--c-rule`，填充 `--c-ink`。
- 底部说明条：12px `--c-ink-3`，上边框 `--c-rule`。

把上面这些规则按 `grep -n "className=" src/components/SettingsPanel.tsx src/components/EnvBoard.tsx src/components/OnboardingWizard.tsx` 得到的实际类名写全。在 legacy 里删掉这些类的旧规则之前，逐个确认新规则已经覆盖。

`index.css` 追加 `@import './pages/settings.css';`。

- [ ] **Step 6：检查并提交**

```bash
npm test && npm run build && npm run lint
```

真机点测：
- 打开设置。六个通道能切换，键盘左右方向键也能切换。
- 「自测本通道」正常。只改一个无害的显示字段、不填 key，确认「保存配置」的提示正常；不要改真实 key。
- 环境安装页的「重新检测」正常。
- Esc 能关闭设置。
- 从侧栏画像选择「+ 新建画像…」打开向导，能走到第二步，然后取消。

```bash
git add -A web/frontend
git commit -m "polish(web): 设置面板与画像向导换用通用弹窗、标签页和状态点

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10：发现层与策划层页面（热点雷达、爆款拆解、选题库、内容日历）

**Files:**
- Modify：`src/components/TrendsPage.tsx`、`BreakdownPage.tsx`、`IdeasPage.tsx`、`CalendarPage.tsx`
- Create：`src/styles/pages/discover.css`、`src/styles/pages/plan.css`、`src/components/CalendarPage.test.tsx`
- Modify：`src/styles/legacy.css`：删掉 `热点雷达`、`内容日历`、`选题库看板` 段，以及爆款拆解相关规则（先 grep 定位）；`src/styles/index.css`

**Interfaces:**
- Consumes：`PageHeader`、`Panel`、`EmptyState`、`Tag`、`Button`、`Tabs`、`Input`、`Select`、`Textarea`、`Modal`。

四个页面统一按下面的规则改。

**换肤规则：**

| 原来的写法 | 改成 |
|---|---|
| 页面顶部的 `<h1 className="page-title">…</h1><p className="page-subtitle">…</p>` | `<PageHeader layer={…} title=… description=… actions=… />`。热点雷达、爆款拆解是 `discover`，选题库、内容日历是 `plan` |
| `<button className="btn …">` | `<Button variant=… size=…>` |
| `<input className="field">`、`<select>`、`<textarea>` | `Input`、`Select`、`Textarea` |
| `<span className="badge …">` | `<Tag tone=…>`：`badge-ok` 对应 `ok`，`badge-warn` 对应 `warn`，普通 `badge` 对应 `neutral` |
| 自绘的 `overlay` 加 `modal` 弹窗 | `<Modal title=… onClose=… footer=…>` |
| 一排互斥的 `chip` 或自绘标签按钮 | `<Tabs>`；可以多选的筛选保留 `.chip`（已按新样式重写） |
| 内联的 `color`、`background`、`border`、`boxShadow` | 删掉，改用本页 CSS 类，颜色用变量 |
| `var(--layer-discover)` 这类层色引用 | 保留（变量名已是新值） |
| 文案里的 emoji、按钮和链接文字后的「→」 | 删掉 |
| 卡片悬停上浮（`card-hover` 的 translateY） | 已由 primitives.css 取消，不用管 |

**内容日历的颜色映射**（`CalendarPage.tsx` 顶部的 `STATUS_META`、`EVENT_COLOR`）：

- `EVENT_COLOR` 改为 `'var(--layer-plan)'`。事件属于策划层，现在用的是 `--layer-discover`。
- `STATUS_META` 各状态的颜色改为语义变量：
  - `idea` 用 `var(--c-ink-3)`
  - `draft` 用 `var(--layer-plan)`
  - `scheduled` 用 `var(--layer-discover)`
  - `published` 用 `var(--c-ok)`
  - 其余状态用 `var(--c-ink-3)`
- 如果文件里有十六进制颜色，一律按上面的映射替换。

- [ ] **Step 1：写失败的日历颜色测试**

`src/components/CalendarPage.test.tsx`：

```tsx
import { describe, it, expect } from 'vitest';
import src from './CalendarPage.tsx?raw';

describe('CalendarPage 颜色', () => {
  it('不含十六进制颜色，事件色用策划层', () => {
    expect(src).not.toMatch(/['"]#[0-9a-fA-F]{3,8}['"]/);
    expect(src).toContain("EVENT_COLOR = 'var(--layer-plan)'");
  });
});
```

运行：`npm test -- src/components/CalendarPage.test.tsx`。预期：失败，`EVENT_COLOR` 现在是 `--layer-discover`。

- [ ] **Step 2：按规则改四个页面**

每个页面依次执行：
1. `grep -n "className=\|style={{" <文件>` 列出结构。
2. 按换肤规则替换。
3. 把本页用到、但 legacy 里有样式的类，迁到 `discover.css`（热点雷达、爆款拆解）或 `plan.css`（选题库、内容日历），并改用新变量。
4. 页面外层统一加 `className="page-scroll <原外层类>"`，内边距统一为 `26px 34px 40px`。

`discover.css`、`plan.css` 的写法约定：
- 列表行统一用「1px `--c-rule` 分隔线、7 到 10px 上下内边距」的样式，不再用每行一张卡片。
- 排名数字用 `--font-serif` 加 `--layer-discover-text`。
- 看板的列（选题库）用 `--c-sunken` 底色，列标题用宋体 15px。
- 日历格子边框 `--c-rule`，今天的格子用 2px `--c-ink` 上边框，事件条用 `--layer-plan-soft` 底加 `--layer-plan-text` 字。

`index.css` 追加：

```css
@import './pages/discover.css';
@import './pages/plan.css';
```

- [ ] **Step 3：检查并提交**

```bash
npm test && npm run build && npm run lint
grep -n "#[0-9a-fA-F]\{3,6\}" src/components/TrendsPage.tsx src/components/BreakdownPage.tsx src/components/IdeasPage.tsx src/components/CalendarPage.tsx   # 预期无结果
```

真机点测：
- 热点雷达：切换平台，点一条热点做成选题。
- 爆款拆解：页面加载正常。输入框和按钮可用即可，不用真跑。
- 选题库：新增一条测试选题，改状态，然后删除。
- 内容日历：新增一条排期，打开当天详情，然后删除。

```bash
git add -A web/frontend
git commit -m "polish(web): 热点雷达、爆款拆解、选题库、内容日历换新组件与层标

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11：内容库、发布中心、画像、错误页

**Files:**
- Modify：`src/components/OutputsPage.tsx`、`PublishPage.tsx`、`ProfilePage.tsx`、`ErrorBoundary.tsx`
- Create：`src/styles/pages/outputs.css`、`publish.css`、`profile.css`、`src/components/ErrorBoundary.test.tsx`
- Modify：`src/styles/legacy.css`：删掉 `Outputs page`、`内容库画廊`、`发布中心`、`Profile page`、`通用页容器` 段；`src/styles/index.css`

**Interfaces:**
- Consumes：同 Task 10。

按 Task 10 的换肤规则改，另有以下具体要求：

- **`OutputsPage`**：
  - 层标为 `produce`，标题「内容库」。
  - 画廊卡片：白底、`--c-rule` 边框、`--r-panel` 圆角；缩略图区底色 `--c-sunken`；标题用宋体 14px，单行省略。
  - 类型和平台标签用 `Tag`。
  - 预览区（`.outputs-viewer-content`）的 markdown 规则搬进 `outputs.css`：标题用宋体，代码底色 `--c-sunken`，HTML 预览 iframe 边框 `--c-rule`。
  - 筛选如果是互斥的一排按钮，换成 `Tabs`。
- **`PublishPage`**：
  - 层标为 `publish`，标题「发布中心」。
  - 平台选择如果可以多选，保留 `.chip`；互斥的换成 `Tabs`。
  - 预检结果：通过用 `Tag tone="ok"`，警告用 `warn`，拦截用 `danger`。
  - 「真正发布」这类按钮是 `primary`；dry-run 是 secondary。
- **`ProfilePage`**：
  - 层标为 `general`，标题「画像」。
  - `.profile-content` 的 markdown 规则搬进 `profile.css`，写法同内容库预览。
  - 删除画像的按钮用 `variant="danger"`，二次确认用 `Modal`；如果原来用的是 `window.confirm`，保持不变。
- **`ErrorBoundary`**：
  - 去掉内联颜色。
  - 页面结构为：宋体标题「页面出错了」、一段说明「刷新页面通常能恢复。如果反复出现，把下面的错误信息发给维护者。」、错误详情放在 `<pre>`（`--font-mono`，`--c-sunken` 底色），以及一个 `Button variant="primary"`「刷新页面」（调用 `location.reload()`）。
  - 样式写进 `profile.css` 末尾，类名为 `.error-page`。

- [ ] **Step 1：写失败的测试**

`src/components/ErrorBoundary.test.tsx`：

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from './ErrorBoundary';

function Boom(): never { throw new Error('渲染炸了'); }

describe('ErrorBoundary', () => {
  it('出错时显示中文说明、错误详情和刷新按钮', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole('heading', { name: '页面出错了' })).toBeTruthy();
    expect(screen.getByText(/渲染炸了/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '刷新页面' })).toBeTruthy();
  });
});
```

运行：`npm test -- src/components/ErrorBoundary.test.tsx`。预期：失败，除非现有文案恰好一致；不一致就按上面的要求改。

- [ ] **Step 2：按规则改四个文件，迁移样式**

每个文件先 `grep -n "className=\|style={{"`，再按规则替换，把用到的旧类迁进对应的 pages css。`index.css` 追加：

```css
@import './pages/outputs.css';
@import './pages/publish.css';
@import './pages/profile.css';
```

- [ ] **Step 3：检查并提交**

```bash
npm test && npm run build && npm run lint
grep -n "#[0-9a-fA-F]\{3,6\}" src/components/OutputsPage.tsx src/components/PublishPage.tsx src/components/ProfilePage.tsx src/components/ErrorBoundary.tsx   # 预期无结果
```

真机点测：
- 内容库：打开一个项目，预览 markdown、图片、HTML。
- 发布中心：选平台，走一遍 dry-run 预检，不要加 `--exec`。
- 画像：切换画像查看内容。

```bash
git add -A web/frontend
git commit -m "polish(web): 内容库、发布中心、画像与错误页换新组件与层标

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12：收尾：删 legacy 与别名，全量验证

**Files:**
- Delete：`src/styles/legacy.css`
- Modify：`src/styles/tokens.css`（删掉迁移期别名段）、`src/styles/index.css`
- Modify：任何仍在引用旧变量或含颜色字面量的 TSX / CSS
- Create：`src/styles/no-legacy.test.ts`

- [ ] **Step 1：写失败的「无残留」测试**

`src/styles/no-legacy.test.ts`：

```ts
import { describe, it, expect } from 'vitest';

// 以原始文本读入全部源码与样式（vite 的 import.meta.glob + ?raw）
const tsx = import.meta.glob('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const css = import.meta.glob('./**/*.css', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

const OLD_VARS = [
  '--text', '--text-secondary', '--text-tertiary', '--border', '--border-strong', '--bg', '--bg-elev',
  '--surface', '--surface-2', '--surface-hover', '--accent-start', '--accent-end', '--accent-soft',
  '--accent-gradient', '--green', '--amber', '--red', '--trend-up', '--trend-down', '--code-bg',
  '--radius', '--radius-sm', '--radius-lg', '--radius-xl', '--shadow-sm', '--shadow-md', '--shadow-lg', '--glow',
];
const isTest = (p: string) => /\.test\.tsx?$/.test(p);

describe('迁移完成，没有残留', () => {
  it('不再有 legacy.css', () => {
    expect(Object.keys(css).some((p) => p.endsWith('legacy.css'))).toBe(false);
  });

  it('源码和样式里不再引用旧变量名', () => {
    const hits: string[] = [];
    for (const [p, text] of [...Object.entries(tsx), ...Object.entries(css)]) {
      if (isTest(p)) continue;
      for (const v of OLD_VARS) {
        if (new RegExp(`var\\(${v}[,)]`).test(text)) hits.push(`${p}: ${v}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it('只有 tokens.css 含颜色字面量', () => {
    const hits: string[] = [];
    for (const [p, text] of Object.entries(css)) {
      if (p.endsWith('tokens.css')) continue;
      if (/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(text)) hits.push(p);
    }
    for (const [p, text] of Object.entries(tsx)) {
      if (isTest(p)) continue;
      if (/['"`]#[0-9a-fA-F]{3,8}['"`]|rgba?\(/.test(text)) hits.push(p);
    }
    expect(hits).toEqual([]);
  });
});
```

运行：`npm test -- src/styles/no-legacy.test.ts`。预期：失败，列出所有残留。

- [ ] **Step 2：逐条清掉残留**

1. `legacy.css` 里如果还有剩余规则，逐条判断：
   - 仍被某个 TSX 用到的类（`grep -rn "<类名>" src/components src/App.tsx`），搬进对应的 pages 或 ui css，并改用新变量。
   - 没人用的，直接删。
   - 然后 `git rm src/styles/legacy.css`，并从 `index.css` 删掉 `@import './legacy.css';`。
2. 删掉 `tokens.css` 里的「迁移期旧变量别名」整段。
3. 按测试列出的残留逐个改：
   - 旧变量换成新变量：`--text` 换成 `--c-ink`，`--text-secondary` 换成 `--c-ink-2`，`--border` 换成 `--c-rule`，`--red` 换成 `--c-danger`，`--green` 换成 `--c-ok`，`--radius` 换成 `--r-control`，其余类推。
   - CSS 里的 `rgba()` 字面量：先在 `tokens.css` 新增有名字的变量（比如 `--c-scrim` 这类），再引用。
4. 运行 `npm test`，直到 `no-legacy.test.ts` 全部通过。

- [ ] **Step 3：全量检查**

```bash
npm test && npm run build && npm run lint
cd ../.. && source .venv/bin/activate && python -m pytest -q && python scripts/validate_skills.py && python scripts/validate_skill_commands.py
```

预期：前端测试全部通过；构建通过；lint 只有 2 个既有 warning；后端 458 passed、1 skipped；两个校验脚本都输出 OK。

- [ ] **Step 4：截图矩阵与评审重点逐项验证**

在 1440×900 和 1024×768 两个尺寸下，分别截图：
- 12 个页面：工作台、对话（空态和对话态）、热点雷达、爆款拆解、选题库、内容日历、内容库、发布中心、账号、创作数据、技能库、画像
- 设置面板（模型配置和环境安装）
- 扫码登录弹窗
- 技能抽屉
- 画像向导

截图保存到 `.playwright-mcp/after-*.png`。逐张检查：没有横向滚动，没有溢出和重叠，没有旧的蓝青渐变和模糊色块，没有全大写标签和 emoji。

评审重点逐项检查：
1. **长文本**：在浏览器控制台执行下面的代码，把第一个会话改成超长标题，刷新后在对话页和侧栏检查省略效果：
   ```js
   const s = JSON.parse(localStorage.getItem('easel_sessions') || '[]');
   if (s[0]) { s[0].title = '超长标题'.repeat(12); localStorage.setItem('easel_sessions', JSON.stringify(s)); }
   ```
   检查完把标题改回来。会话存储键以 `lib/store.ts` 里的实际键名为准，先 `grep -n "localStorage" src/lib/store.ts` 确认。
2. **窄屏**：在 1024×768 和 900×700 下，侧栏是图标条，对话记录栏收起，所有页面都没有横向滚动。
3. **流式中切页**：发一条消息，流式进行中切到工作台，3 秒后切回来，消息继续流；流式中的会话能归档。
4. **字体回退**：在开发者工具的 Network 面板屏蔽 `*noto-serif*` 后刷新，标题退到宋体系统字体，页面照常可读。
5. **失败和空数据**：断开代理，或在 Network 面板屏蔽 `/api/trends`，工作台热点栏显示「热点暂时拉不到…」；技能库屏蔽 `/api/skills` 时显示重试。

- [ ] **Step 5：提交**

```bash
git add -A web/frontend
git commit -m "chore(web): 删除 legacy 样式与旧变量别名，颜色只保留在 tokens.css

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

之后由控制者发起整条分支的代码评审和设计评审（对照规格和两份样稿），再请用户确认合并与推送。
