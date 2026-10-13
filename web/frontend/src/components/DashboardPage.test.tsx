import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchTrends: vi.fn(),
  fetchSchedule: vi.fn(),
  fetchOutputs: vi.fn(),
  fetchAccounts: vi.fn(),
  fetchIdeas: vi.fn(),
  fetchAnalyticsPlatforms: vi.fn(),
}));
vi.mock('../lib/whoami', () => ({
  getWhoamiCache: vi.fn(() => ({})),
  verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import DashboardPage from './DashboardPage';

const ok = <T,>(v: T) => Promise.resolve(v);

beforeEach(() => {
  vi.mocked(api.fetchTrends).mockReturnValue(ok({
    trends: [{ platform: 'weibo', label: '微博', items: [{ title: '国庆出片大赛', hot: '1', url: '' }] }],
    updated: 0,
  }));
  vi.mocked(api.fetchSchedule).mockReturnValue(ok([]));
  vi.mocked(api.fetchOutputs).mockReturnValue(ok([]));
  vi.mocked(api.fetchAccounts).mockReturnValue(ok([
    { platform: 'xiaohongshu', name: '小红书', backend: 'xhs', supported: true, loggedIn: true, note: '' },
    { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
  ]));
  vi.mocked(api.fetchIdeas).mockReturnValue(ok([]));
  vi.mocked(api.fetchAnalyticsPlatforms).mockReturnValue(ok([]));
});

describe('DashboardPage', () => {
  it('流水线五栏按顺序显示层名', async () => {
    const { container } = render(<DashboardPage apiDirect={false} agentRuntime="openclaw" persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    const names = [...container.querySelectorAll('.pipe-stage-name')].map((n) => n.textContent);
    expect(names).toEqual(['发现', '策划', '生产', '发布', '归因']);
    await waitFor(() => expect(screen.getByText('1/2')).toBeTruthy());   // 发布：已登录/总数
  });

  it('没有可看数据的平台时，归因栏显示「—」', async () => {
    const { container } = render(<DashboardPage apiDirect={false} agentRuntime="openclaw" persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    await waitFor(() => expect(container.querySelector('[data-stage="attribute"] .pipe-stage-num')?.textContent).toBe('—'));
  });

  it('点热点调 onUseTopic，点「开始对话」跳到对话页', async () => {
    const onUseTopic = vi.fn();
    const onNavigate = vi.fn();
    render(<DashboardPage apiDirect={false} agentRuntime="openclaw" persona="" gatewayStatus="connected" onNavigate={onNavigate} onUseTopic={onUseTopic} />);
    fireEvent.click(await screen.findByText('国庆出片大赛'));
    expect(onUseTopic).toHaveBeenCalledWith('国庆出片大赛');
    fireEvent.click(screen.getByRole('button', { name: '开始对话' }));
    expect(onNavigate).toHaveBeenCalledWith('chat');
  });

  it('热点拉不到时给出下一步提示', async () => {
    vi.mocked(api.fetchTrends).mockReturnValue(Promise.reject(new Error('net')));
    render(<DashboardPage apiDirect={false} agentRuntime="openclaw" persona="" gatewayStatus="connected" onNavigate={() => {}} onUseTopic={() => {}} />);
    expect(await screen.findByText(/热点暂时拉不到/)).toBeTruthy();
  });
  describe('按执行引擎提示状态', () => {
    const notice = (props: { gatewayStatus: string; apiDirect?: boolean; agentRuntime?: string }) => {
      const { container } = render(
        <DashboardPage apiDirect={false} agentRuntime="openclaw" persona="" onNavigate={() => {}} onUseTopic={() => {}} {...props} />,
      );
      return container.querySelector('.dash-date .ui-tag')?.textContent ?? null;
    };

    it('OpenClaw：连上了不提示，没连上提示网关', () => {
      expect(notice({ gatewayStatus: 'connected' })).toBeNull();
      expect(notice({ gatewayStatus: 'disconnected' })).toBe('网关未连接，对话暂不可用');
    });

    it('仅聊天模式：没配好提示去配模型 API', () => {
      expect(notice({ gatewayStatus: 'connected', apiDirect: true })).toBeNull();
      expect(notice({ gatewayStatus: 'disconnected', apiDirect: true })).toBe('请先配置仅聊天模式的模型 API');
    });

    it('原生 CLI 引擎：装好了提示登录与模型要发消息才验证，没装提示去安装', () => {
      expect(notice({ gatewayStatus: 'connected', agentRuntime: 'codex' })).toMatch(/codex CLI 已安装.*发消息时才会验证/);
      expect(notice({ gatewayStatus: 'disconnected', agentRuntime: 'codex' })).toBe('请先在服务器安装并配置 codex CLI');
    });
  });
});
