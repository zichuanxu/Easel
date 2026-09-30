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
