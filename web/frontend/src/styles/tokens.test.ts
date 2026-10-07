import { describe, it, expect } from 'vitest';
import allCss from './tokens.css?raw';

// 浅色变量在 :root，夜间覆盖在 :root[data-theme='dark'] 之后；两段分开校验
const DARK_MARK = ":root[data-theme='dark']";
const css = allCss.split(DARK_MARK)[0];
const darkCss = allCss.slice(allCss.indexOf(DARK_MARK));

const REQUIRED: Record<string, string> = {
  '--c-canvas': '#F6F7F5',
  '--c-surface': '#FFFFFF',
  '--c-side': '#EEF0EC',
  '--c-sunken': '#F2F3F0',
  '--c-rule': '#E3E6E1',
  '--c-rule-strong': '#D2D6D0',
  '--c-ink': '#1F2328',
  '--c-ink-2': '#4B5159',
  '--c-ink-3': '#676D75',
  '--c-ok-text': '#2F7358',
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

  describe('文字对比度（WCAG，正文/辅助文字 ≥ 4.5:1）', () => {
    const val = (name: string): string => {
      const m = css.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6});`));
      if (!m) throw new Error(`tokens.css 里找不到 ${name}`);
      return m[1];
    };
    const lin = (c: number) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    const lum = (hex: string) => {
      const n = parseInt(hex.slice(1), 16);
      return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
    };
    const ratio = (a: string, b: string) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    const layerText = [...css.matchAll(/(--layer-[a-z]+-text):/g)].map((m) => m[1]);
    const FG = ['--c-ink', '--c-ink-2', '--c-ink-3', '--c-ok-text', '--c-warn', '--c-danger', ...layerText];
    const BG = ['--c-surface', '--c-canvas', '--c-sunken', '--c-side', '--c-tint'];

    it('覆盖全部六个 --layer-*-text', () => { expect(layerText.length).toBe(6); });

    for (const fg of FG) {
      for (const bg of BG) {
        it(`${fg} 在 ${bg} 上 ≥ 4.5`, () => {
          const r = ratio(val(fg), val(bg));
          console.info(`contrast ${fg} on ${bg} = ${r.toFixed(2)}`);
          expect(r).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  });

  describe('夜间模式（data-theme="dark"）', () => {
    const val = (name: string): string => {
      const m = darkCss.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6});`));
      if (!m) throw new Error(`夜间块里找不到 ${name}`);
      return m[1];
    };
    const lin = (c: number) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    const lum = (hex: string) => {
      const n = parseInt(hex.slice(1), 16);
      return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
    };
    const ratio = (a: string, b: string) => {
      const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    const FG = ['--c-ink', '--c-ink-2', '--c-ink-3', '--c-ok-text', '--c-warn', '--c-danger',
      '--layer-discover-text', '--layer-plan-text', '--layer-produce-text', '--layer-publish-text',
      '--layer-attribute-text', '--layer-general-text'];
    const BG = ['--c-surface', '--c-canvas', '--c-sunken', '--c-side', '--c-tint'];

    it('声明 color-scheme: dark', () => { expect(darkCss).toMatch(/color-scheme:\s*dark;/); });

    for (const fg of FG) {
      for (const bg of BG) {
        it(`${fg} 在 ${bg} 上 ≥ 4.5`, () => {
          expect(ratio(val(fg), val(bg))).toBeGreaterThanOrEqual(4.5);
        });
      }
    }

    it('主按钮：--c-on-ink 在 --c-ink 上 ≥ 4.5', () => {
      expect(ratio(val('--c-on-ink'), val('--c-ink'))).toBeGreaterThanOrEqual(4.5);
    });
  });
});
