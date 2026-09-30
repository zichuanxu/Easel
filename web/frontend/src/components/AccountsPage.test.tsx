import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchAccounts: vi.fn(), startLogin: vi.fn(), loginStatus: vi.fn(), mediaUrl: (p: string) => p,
  accountWhoami: vi.fn(() => new Promise(() => {})), logoutAccount: vi.fn(), submitLoginSms: vi.fn(),
  saveCredentials: vi.fn(), getCredentials: vi.fn(), startMpLogin: vi.fn(), mpLoginStatus: vi.fn(),
}));
vi.mock('../lib/whoami', () => ({
  dropOutdatedWhoami: vi.fn(() => []), getWhoamiCache: vi.fn(() => ({})),
  setWhoamiCache: vi.fn(), verifyStale: vi.fn(),
}));

import * as api from '../lib/api';
import AccountsPage from './AccountsPage';

describe('AccountsPage', () => {
  it('一行一个平台：已登录显示校验和退出，未登录显示扫码登录主按钮', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'xiaohongshu', name: '小红书', backend: 'xhs', supported: true, loggedIn: true, note: '' },
      { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    const xhs = (await screen.findByText('小红书')).closest('.account-row') as HTMLElement;
    expect(within(xhs).getAllByText('已登录').length).toBeGreaterThan(0);
    expect(within(xhs).getByRole('button', { name: '校验' })).toBeTruthy();
    expect(within(xhs).getByRole('button', { name: '退出' })).toBeTruthy();
    const zhihu = screen.getByText('知乎').closest('.account-row') as HTMLElement;
    const login = within(zhihu).getByRole('button', { name: '扫码登录' });
    expect(login.className).toContain('btn-primary');
  });

  it('页头层标为发布，标题为账号', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([]);
    const { container } = render(<AccountsPage />);
    expect(screen.getByRole('heading', { level: 1, name: '账号' })).toBeTruthy();
    expect(container.querySelector('.ui-layer-mark')?.textContent).toBe('发布');
  });
});
