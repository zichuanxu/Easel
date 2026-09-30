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
