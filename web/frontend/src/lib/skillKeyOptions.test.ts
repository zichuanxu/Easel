import { describe, it, expect } from 'vitest';
import { skillKeyOptions } from './skillKeyOptions';

describe('skillKeyOptions', () => {
  it('已配置：首项显示掩码文案', () => {
    const o = skillKeyOptions({ choices: ['a', 'b'], configured: true, masked: 'dash***' });
    expect(o[0]).toEqual({ value: '', label: '当前：dash***' });
  });
  it('未配置：首项为「不设置」', () => {
    expect(skillKeyOptions({ choices: ['a'], configured: false, masked: '' })[0]).toEqual({ value: '', label: '不设置' });
  });
  it('choices 顺序不变，且只出现掩码值', () => {
    const o = skillKeyOptions({ choices: ['z', 'a', 'm'], configured: true, masked: 'sk-***9' });
    expect(o.map((x) => x.value)).toEqual(['', 'z', 'a', 'm']);
    expect(o.map((x) => x.label).join('|')).toBe('当前：sk-***9|z|a|m');
  });
  it('已配置但掩码缺失：首项显示「当前：已配置」', () => {
    expect(skillKeyOptions({ choices: ['a'], configured: true, masked: '' })[0].label).toBe('当前：已配置');
    expect(skillKeyOptions({ choices: ['a'], configured: true })[0].label).toBe('当前：已配置');
  });
});
