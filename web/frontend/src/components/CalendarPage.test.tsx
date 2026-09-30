import { describe, it, expect } from 'vitest';
import src from './CalendarPage.tsx?raw';

describe('CalendarPage 颜色', () => {
  it('不含十六进制颜色，事件色用策划层', () => {
    expect(src).not.toMatch(/['"]#[0-9a-fA-F]{3,8}['"]/);
    expect(src).toContain("EVENT_COLOR = 'var(--layer-plan)'");
  });
});
