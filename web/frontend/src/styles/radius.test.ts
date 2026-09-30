import { describe, it, expect } from 'vitest';

// 以原始文本读入全部样式（tokens.css 除外）
const css = import.meta.glob('./**/*.css', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

// 圆角只允许三级 token；字面量只放行 50%、0，以及 ≤ 2px 的细条（进度条、指示条、滚动条滑块）
const okValue = (v: string): boolean => {
  if (/^var\(--r-(control|panel|overlay)\)$/.test(v)) return true;
  if (v === '50%' || v === '0') return true;
  const px = /^(\d+(?:\.\d+)?)px$/.exec(v);
  return !!px && parseFloat(px[1]) <= 2;
};

// 用户消息气泡「靠右那个角收尖」的 4px 单独放行
const ALLOWED: Record<string, string> = {
  '.message-bubble.user': 'var(--r-panel) var(--r-panel) 4px var(--r-panel)',
};

describe('圆角只用三级 token', () => {
  it('每个 border-radius 的每个值都合规', () => {
    const hits: string[] = [];
    for (const [p, text] of Object.entries(css)) {
      if (p.endsWith('tokens.css')) continue;
      const rules = text.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g);
      for (const [, sel, body] of rules) {
        const selector = sel.trim();
        for (const m of body.matchAll(/(?:^|[;\s])border-radius\s*:\s*([^;]+)/g)) {
          const value = m[1].trim();
          if (ALLOWED[selector] === value) continue;
          const parts = value.split(/\s+(?![^(]*\))/);
          if (!parts.every(okValue)) hits.push(`${p} ${selector}: ${value}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });
});
