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
