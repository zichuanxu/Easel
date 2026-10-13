import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Sidebar from './Sidebar';

const base = {
  personas: [], selectedPersona: '', onPersonaChange: () => {}, onNewProfile: () => {},
  gatewayStatus: 'connected', apiDirect: false, agentRuntime: 'openclaw', onOpenSettings: () => {},
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

  describe('底部状态按执行引擎换说法', () => {
    const text = (props: Record<string, unknown>) => {
      const { container } = render(<Sidebar {...base} {...props} currentPage="dashboard" onPageChange={() => {}} />);
      return container.querySelector('.sidebar-status-text')?.textContent;
    };

    it('OpenClaw：网关已连接 / 网关离线 / 连接中', () => {
      expect(text({ gatewayStatus: 'connected' })).toBe('网关已连接');
      expect(text({ gatewayStatus: 'disconnected' })).toBe('网关离线');
      expect(text({ gatewayStatus: 'connecting' })).toBe('连接中…');
    });

    it('仅聊天模式：看 API 配置是否完整', () => {
      expect(text({ apiDirect: true, gatewayStatus: 'connected' })).toBe('仅聊天模式已配置');
      expect(text({ apiDirect: true, gatewayStatus: 'disconnected' })).toBe('API 配置不完整');
    });

    it('原生 CLI 引擎：看命令行是否装好', () => {
      expect(text({ agentRuntime: 'codex', gatewayStatus: 'connected' })).toBe('codex CLI 已安装');
      expect(text({ agentRuntime: 'opencode', gatewayStatus: 'disconnected' })).toBe('opencode CLI 未配置');
    });
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

    it('会话里已有消息时画像照样可选：切换会新建对话，由 App 负责', () => {
      const onPersonaChange = vi.fn();
      render(<Sidebar {...base} personas={personas} onPersonaChange={onPersonaChange} currentPage="dashboard" onPageChange={() => {}} />);
      const t = trigger();
      expect((t as HTMLButtonElement).disabled).toBe(false);
      expect(t.getAttribute('title')).toBe('选择用户画像（一个对话对应一个画像：切换会新建一个对话）');
      fireEvent.click(t);
      fireEvent.click(screen.getByRole('option', { name: '阿舟' }));
      expect(onPersonaChange).toHaveBeenCalledWith('阿舟');
    });
  });
});
