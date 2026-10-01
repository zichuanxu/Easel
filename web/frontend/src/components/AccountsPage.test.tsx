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

  it('已登录但没有 whoami 信息（B站 不自动校验）时，身份栏不留空，显示「已登录」', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'bilibili', name: 'B站', backend: 'biliup', supported: true, loggedIn: true, note: '' },
    ]);
    render(<AccountsPage />);
    const row = (await screen.findByText('B站')).closest('.account-row') as HTMLElement;
    expect(row.querySelector('.account-who')?.textContent).toBe('已登录');
  });

  it('国内、海外分两组；海外平台的登录按钮叫「登录」', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', region: 'domestic', supported: true, loggedIn: false, note: '' },
      { platform: 'youtube', name: 'YouTube', backend: 'overseas', region: 'overseas', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    const overseas = await screen.findByRole('region', { name: '海外' });
    const domestic = screen.getByRole('region', { name: '国内' });
    expect(within(overseas).getByText('YouTube')).toBeTruthy();
    expect(within(domestic).getByText('知乎')).toBeTruthy();
    expect(within(overseas).getByRole('heading', { level: 2, name: '海外' })).toBeTruthy();
    expect(within(overseas).getByRole('button', { name: '登录' })).toBeTruthy();
    expect(within(domestic).getByRole('button', { name: '扫码登录' })).toBeTruthy();
  });

  it('只有国内平台时不显示分组标题', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: false, note: '' },
    ]);
    render(<AccountsPage />);
    await screen.findByText('知乎');
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });

  it('没桌面时海外平台显示「不可用」和原因，登录按钮置灰', async () => {
    vi.mocked(api.fetchAccounts).mockResolvedValue([
      { platform: 'zhihu', name: '知乎', backend: 'web', region: 'domestic', supported: true, loggedIn: false, note: '' },
      { platform: 'x', name: 'X', backend: 'overseas', region: 'overseas', supported: false, loggedIn: false,
        note: '需要在有桌面的本机登录（会弹出 Chrome 窗口）' },
    ]);
    render(<AccountsPage />);
    const row = (await screen.findByText('X')).closest('.account-row') as HTMLElement;
    expect(within(row).getByText('不可用')).toBeTruthy();
    expect(within(row).getByText(/有桌面的本机/)).toBeTruthy();
    expect((within(row).getByRole('button', { name: '登录' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
