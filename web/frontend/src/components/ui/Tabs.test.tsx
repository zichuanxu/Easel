import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Tabs from './Tabs';

const ITEMS = [
  { key: 'chat', label: '对话与脚本' },
  { key: 'image', label: '生图' },
  { key: 'video', label: '视频' },
] as const;

describe('Tabs', () => {
  it('当前项 aria-selected，点击切换', () => {
    const onChange = vi.fn();
    render(<Tabs items={[...ITEMS]} value="chat" onChange={onChange} ariaLabel="模型通道" />);
    expect(screen.getByRole('tab', { name: '对话与脚本' }).getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('tab', { name: '视频' }));
    expect(onChange).toHaveBeenCalledWith('video');
  });

  it('左右方向键循环切换', () => {
    const onChange = vi.fn();
    render(<Tabs items={[...ITEMS]} value="video" onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: '视频' }), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('chat');
    fireEvent.keyDown(screen.getByRole('tab', { name: '视频' }), { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledWith('image');
  });
});
