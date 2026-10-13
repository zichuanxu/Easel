import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

// 创作数据已经从工作台挪到独立的「创作数据」页，抓取状态由 lib/useAnalyticsData.ts 的 hook 管理，
// 原来的「同平台重复点击共用一次抓取」「完成后可再次刷新」「只缓存成功结果」「失败显示后端原因并可重试」
// 四条行为在 web/frontend/src/lib/useAnalyticsData.test.tsx（vitest，npm test）里对 hook 断言。
// 这里只保留不依赖 React 的请求时限契约。

const require = createRequire(new URL('../../web/frontend/package.json', import.meta.url));
const ts = require('typescript');

test('analytics requests have platform-specific bounded deadlines', async () => {
  const api = readFileSync(new URL('../../web/frontend/src/lib/api.ts', import.meta.url), 'utf8');
  const apiParsed = ts.createSourceFile('api.ts', api, ts.ScriptTarget.Latest, true);
  const fetchDeclaration = apiParsed.statements.find(node =>
    ts.isFunctionDeclaration(node) && node.name?.text === 'fetchAccountAnalytics');
  const compiled = ts.transpileModule(fetchDeclaration.getText(apiParsed), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const exports = {}, calls = [];
  runInNewContext(compiled, {
    exports, encodeURIComponent,
    AbortSignal: { timeout: duration => ({ duration }) },
    request: async (path, options) => { calls.push({ path, options }); return {}; },
  });
  await exports.fetchAccountAnalytics('xiaohongshu');
  await exports.fetchAccountAnalytics('wechat-oa');
  assert.equal(calls[0].options.signal.duration, 105000);
  assert.equal(calls[1].options.signal.duration, 195000);
  // 手动刷新（国内浏览器平台点「刷新数据」）带 manual 标志，其余请求不带
  await exports.fetchAccountAnalytics('zhihu', true);
  assert.equal(calls[0].path, '/api/analytics/xiaohongshu');
  assert.equal(calls[2].path, '/api/analytics/zhihu?manual=1');
});
