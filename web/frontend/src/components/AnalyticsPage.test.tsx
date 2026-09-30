import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchAnalyticsPlatforms: vi.fn(),
  fetchAccountAnalytics: vi.fn(() => new Promise(() => {})),
  fetchCachedAnalytics: vi.fn(() => Promise.resolve(null)),
}));
vi.mock('../lib/whoami', () => ({
  getWhoamiCache: vi.fn(() => ({})),
  verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import AnalyticsPage from './AnalyticsPage';
import { fmtAgo } from '../lib/fmtAgo';

const sample = (ageMs: number) => ({
  platform: 'xiaohongshu', name: '小红书', nickname: 'tester', loggedIn: true, followers: 12000, likes: 5, following: 3, posts: 1,
  metrics: [], notes: [], growth: { last: null, day: null, week: null, month: null, year: null },
  fetched_at: Math.floor((Date.now() - ageMs) / 1000),
});

describe('AnalyticsPage', () => {
  it('没有已登录平台时引导去账号页', async () => {
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: false }]);
    const onNavigate = vi.fn();
    render(<AnalyticsPage onNavigate={onNavigate} />);
    fireEvent.click(await screen.findByRole('button', { name: '去账号页' }));
    expect(onNavigate).toHaveBeenCalledWith('accounts');
  });

  it('有已登录平台时显示平台标签页，页头层标为归因', async () => {
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: true }]);
    const { container } = render(<AnalyticsPage onNavigate={() => {}} />);
    expect(await screen.findByRole('tab', { name: '小红书' })).toBeTruthy();
    expect(container.querySelector('.ui-layer-mark')?.textContent).toBe('归因');
  });

  it('无缓存且正在抓取：显示骨架和首次拉取提示，没有 spinner', async () => {
    localStorage.clear();
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: true }]);
    const { container } = render(<AnalyticsPage onNavigate={() => {}} />);
    expect(await screen.findByText(/首次拉取这个平台的数据/)).toBeTruthy();
    expect(container.querySelectorAll('.ana-skel').length).toBeGreaterThan(0);
    expect(container.querySelector('.spinner')).toBeNull();
    expect((screen.getByRole('button', { name: '正在更新…' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('失败但有旧数据：保留数据，出现更新失败提示和重试按钮', async () => {
    localStorage.setItem('easel_analytics', JSON.stringify({ xiaohongshu: sample(3600_000 * 2) }));
    vi.mocked(api.fetchAnalyticsPlatforms).mockResolvedValue([{ platform: 'xiaohongshu', name: '小红书', loggedIn: true }]);
    vi.mocked(api.fetchAccountAnalytics).mockRejectedValueOnce(new Error('x'));
    render(<AnalyticsPage onNavigate={() => {}} />);
    expect(await screen.findByText(/更新失败，显示的是 2 小时前的数据/)).toBeTruthy();
    expect(screen.getByText('@tester')).toBeTruthy();
    vi.mocked(api.fetchAccountAnalytics).mockReturnValueOnce(new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await waitFor(() => expect(api.fetchAccountAnalytics).toHaveBeenCalledTimes(2));
  });
});

describe('fmtAgo', () => {
  const now = new Date(2026, 8, 30, 12, 0).getTime();
  it('四种区间', () => {
    expect(fmtAgo(now - 30_000, now)).toBe('刚刚');
    expect(fmtAgo(now - 5 * 60_000, now)).toBe('5 分钟前');
    expect(fmtAgo(now - 3 * 3600_000, now)).toBe('3 小时前');
    expect(fmtAgo(new Date(2026, 8, 28, 9, 5).getTime(), now)).toBe('9 月 28 日 09:05');
  });
});
