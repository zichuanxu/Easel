import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Button, { buttonClass } from './Button';

describe('Button', () => {
  it('变体和尺寸映射到规范类名', () => {
    expect(buttonClass('primary', 'md', false)).toBe('btn btn-primary');
    expect(buttonClass('secondary', 'sm', false)).toBe('btn btn-sm');
    expect(buttonClass('ghost', 'md', true)).toBe('btn btn-ghost btn-block');
    expect(buttonClass('danger', 'sm', false)).toBe('btn btn-danger btn-sm');
  });

  it('默认 type=button、次要样式', () => {
    render(<Button>取消</Button>);
    const b = screen.getByRole('button', { name: '取消' });
    expect(b.getAttribute('type')).toBe('button');
    expect(b.className).toBe('btn');
  });

  it('loading 时禁用并标记 aria-busy，点击不触发', () => {
    const onClick = vi.fn();
    render(<Button variant="primary" loading onClick={onClick}>保存</Button>);
    const b = screen.getByRole('button', { name: '保存' });
    expect((b as HTMLButtonElement).disabled).toBe(true);
    expect(b.getAttribute('aria-busy')).toBe('true');
    fireEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });
});
