import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Sidebar from './Sidebar';

const base = {
  personas: [], selectedPersona: '', onPersonaChange: () => {}, onNewProfile: () => {},
  activeSessionHasMessages: false, gatewayStatus: 'connected', onOpenSettings: () => {},
};

describe('Sidebar', () => {
  it('按层显示分组名，顺序为发现到归因', () => {
    const { container } = render(<Sidebar {...base} currentPage="dashboard" onPageChange={() => {}} />);
    const titles = [...container.querySelectorAll('.nav-group-title')].map((n) => n.textContent);
    expect(titles).toEqual(['发现', '策划', '生产', '发布', '归因']);
  });

  it('当前页标 aria-current，点击切页', () => {
    const onPageChange = vi.fn();
    render(<Sidebar {...base} currentPage="accounts" onPageChange={onPageChange} />);
    expect(screen.getByRole('button', { name: /账号/ }).getAttribute('aria-current')).toBe('page');
    fireEvent.click(screen.getByRole('button', { name: /热点雷达/ }));
    expect(onPageChange).toHaveBeenCalledWith('trends');
  });

  it('不再包含会话列表；设置按钮打开设置', () => {
    const onOpenSettings = vi.fn();
    const { container } = render(<Sidebar {...base} onOpenSettings={onOpenSettings} currentPage="dashboard" onPageChange={() => {}} />);
    expect(container.querySelector('.session-item')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /设置/ }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it('对话项旁显示当前会话标题', () => {
    render(<Sidebar {...base} activeChatTitle="国庆出片文案" currentPage="dashboard" onPageChange={() => {}} />);
    expect(screen.getByText('国庆出片文案')).toBeTruthy();
  });
});
