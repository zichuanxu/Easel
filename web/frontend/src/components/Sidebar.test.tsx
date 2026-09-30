import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
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

  it('选中项变化时用 scrollIntoView({ block: nearest }) 滚进可视区', () => {
    const spy = vi.fn();
    const orig = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = spy;
    try {
      const { rerender } = render(<Sidebar {...base} currentPage="dashboard" onPageChange={() => {}} />);
      spy.mockClear();
      rerender(<Sidebar {...base} currentPage="profile" onPageChange={() => {}} />);
      expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
      expect(spy.mock.contexts[0]).toBe(within(screen.getByRole('navigation', { name: '主导航' })).getByRole('button', { name: /画像/ }));
    } finally {
      Element.prototype.scrollIntoView = orig;
    }
  });

  describe('画像选择', () => {
    it('selectedPersona 不在列表里（画像被删）时，触发器显示「选择画像」而非空白', () => {
      render(<Sidebar {...base} personas={[{ name: '小林' }] as never} selectedPersona="已删除的画像" currentPage="dashboard" onPageChange={() => {}} />);
      expect(screen.getByRole('button', { name: '画像', expanded: false }).textContent).toContain('选择画像');
    });

    const personas = [{ name: '小林' }, { name: '阿舟' }] as never;
    const trigger = () => screen.getByRole('button', { name: '画像', expanded: false });

    it('选画像调用 onPersonaChange，选通用模式传空串', () => {
      const onPersonaChange = vi.fn();
      const { rerender } = render(<Sidebar {...base} personas={personas} onPersonaChange={onPersonaChange} currentPage="dashboard" onPageChange={() => {}} />);
      fireEvent.click(trigger());
      fireEvent.click(screen.getByRole('option', { name: '阿舟' }));
      expect(onPersonaChange).toHaveBeenCalledWith('阿舟');
      rerender(<Sidebar {...base} personas={personas} selectedPersona="阿舟" onPersonaChange={onPersonaChange} currentPage="dashboard" onPageChange={() => {}} />);
      fireEvent.click(trigger());
      fireEvent.click(screen.getByRole('option', { name: '通用模式' }));
      expect(onPersonaChange).toHaveBeenLastCalledWith('');
    });

    it('新建画像走操作项，调用 onNewProfile，不调用 onPersonaChange', () => {
      const onNewProfile = vi.fn();
      const onPersonaChange = vi.fn();
      render(<Sidebar {...base} personas={personas} onNewProfile={onNewProfile} onPersonaChange={onPersonaChange} currentPage="dashboard" onPageChange={() => {}} />);
      fireEvent.click(trigger());
      fireEvent.click(screen.getByRole('option', { name: '新建画像' }));
      expect(onNewProfile).toHaveBeenCalledTimes(1);
      expect(onPersonaChange).not.toHaveBeenCalled();
    });

    it('会话里已有消息时禁用并给出说明', () => {
      render(<Sidebar {...base} personas={personas} activeSessionHasMessages currentPage="dashboard" onPageChange={() => {}} />);
      const t = trigger();
      expect((t as HTMLButtonElement).disabled).toBe(true);
      expect(t.getAttribute('title')).toBe('当前对话已绑定画像，切换画像将新建对话');
      fireEvent.click(t);
      expect(screen.queryByRole('listbox')).toBeNull();
    });
  });
});
