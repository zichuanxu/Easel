import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

const require = createRequire(new URL('../../web/frontend/package.json', import.meta.url));
const ts = require('typescript');

// 组件依赖设计系统的 Button / Tag / Field（./ui/*）：按相对路径把真正的 TSX 逐个转译加载，
// 只有 ../lib/api 仍然桩成空对象（卡片只在点击时才会调它）。
function loadModule(file) {
  const { outputText } = ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
    },
  });
  const module = { exports: {} };
  runInNewContext(outputText, { exports: module.exports, require: name => resolve(name, file) });
  return module.exports;
}
function resolve(name, from) {
  if (name === '../lib/api') return {};
  if (!name.startsWith('.')) return require(name);
  const base = fileURLToPath(new URL(name, new URL(`file://${from}`)));
  const file = ['.tsx', '.ts'].map(extension => base + extension).find(existsSync);
  assert.ok(file, `cannot resolve ${name}`);
  return loadModule(file);
}
const component = {
  exports: loadModule(fileURLToPath(new URL('../../web/frontend/src/components/QuestionCards.tsx', import.meta.url))),
};
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

test('approval cards preserve long multiline commands and both permission choices', () => {
  const command = `Codex 请求额外权限（仅本次）：python /data/project/Easel/${'long_segment_'.repeat(200)}/render.py\n第二行 <script>alert(1)</script>`;
  const rendered = renderToStaticMarkup(React.createElement(component.exports.default, {
    questions: [{
      id: 'codex-approval',
      questions: [{
        questionId: 'permission',
        header: '执行授权',
        question: command,
        options: [{ label: '允许本次' }, { label: '拒绝' }],
      }],
    }],
  }));
  assert.ok(rendered.includes('long_segment_'.repeat(200)));
  assert.ok(rendered.includes('\n第二行 &lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.match(rendered, /<strong>允许本次<\/strong>/);
  assert.match(rendered, /<strong>拒绝<\/strong>/);
  assert.match(rendered, /disabled="">提交<\/button>/);
});

test('approval card grids can shrink and wrap commands without clipping their content', () => {
  // styles/index.css 只负责按顺序 @import：把被引入的样式文件按顺序拼起来再断言规则
  const directory = new URL('../../web/frontend/src/styles/', import.meta.url);
  const entry = readFileSync(new URL('index.css', directory), 'utf8');
  const styles = [...entry.matchAll(/@import\s+'\.\/([^']+)';/g)]
    .map(([, file]) => readFileSync(new URL(file, directory), 'utf8')).join('\n');
  const rule = selector => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matched = styles.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`));
    assert.ok(matched, selector);
    return matched[1];
  };
  for (const selector of ['.question-card', '.question-card__item', '.question-card__option']) {
    assert.match(rule(selector), /grid-template-columns:\s*minmax\(0,\s*1fr\)/);
    assert.match(rule(selector), /min-width:\s*0/);
  }
  assert.match(rule('.question-card'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('.question-card__title'), /white-space:\s*pre-wrap/);
  assert.match(rule('.question-card__options'), /minmax\(min\(150px,\s*100%\),\s*1fr\)/);
  // 自定义答案输入框现在是设计系统的 .field（不再是裸 input 选择器）
  assert.match(rule('.question-card__custom .field'), /min-width:\s*0/);
});
