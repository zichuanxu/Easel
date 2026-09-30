import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchAnalyticsPlatforms: vi.fn(),
  fetchAccountAnalytics: vi.fn(() => new Promise(() => {})),
}));
vi.mock('../lib/whoami', () => ({
  getWhoamiCache: vi.fn(() => ({})),
  verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import AnalyticsPage from './AnalyticsPage';

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
});
