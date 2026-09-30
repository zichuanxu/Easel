import { describe, it, expect } from 'vitest';
import { precheckVerdict } from './precheckVerdict';

describe('precheckVerdict', () => {
  it.each([
    ['分析……\n✅可发', 'ok'],
    ['分析……\n⚠️建议修改：标题太长', 'warn'],
    ['结论：不可发布', 'warn'],
    ['结论：不建议发布', 'warn'],
    ['可发，但……\n建议修改标题', 'warn'],
    ['分析……\n✅可发\n\n  ', 'ok'],
    ['', null],
    ['只有一些分析，没有结论行', null],
  ])('%j -> %s', (input, expected) => {
    expect(precheckVerdict(input)).toBe(expected);
  });
});
