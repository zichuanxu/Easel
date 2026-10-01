import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  createSchedule: vi.fn(), executeSkill: vi.fn(), runAgent: vi.fn(), streamChat: vi.fn(),
  fetchAccounts: vi.fn(() => Promise.resolve([])), publishNow: vi.fn(), publishStatus: vi.fn(),
  submitPublishSms: vi.fn(), fetchOutputs: vi.fn(() => Promise.resolve([])), mediaUrl: (p: string) => p,
}));

import PublishPage from './PublishPage';

describe('PublishPage 海外平台', () => {
  beforeEach(() => localStorage.clear());

  it('平台分国内、海外两组', () => {
    render(<PublishPage persona="" />);
    const overseas = screen.getByRole('group', { name: '海外平台' });
    expect(within(overseas).getByRole('button', { name: 'TikTok' })).toBeTruthy();
    const domestic = screen.getByRole('group', { name: '国内平台' });
    expect(within(domestic).getByRole('button', { name: '小红书' })).toBeTruthy();
  });

  it('选了 TikTok：卡片里有可见范围选择', () => {
    render(<PublishPage persona="" />);
    fireEvent.click(screen.getByRole('button', { name: 'TikTok' }));
    const select = screen.getByRole('combobox', { name: 'TikTok 可见范围' }) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['', 'everyone', 'friends', 'only_me']);
  });
});
