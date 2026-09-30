import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchIdeas: vi.fn(() => Promise.resolve([
    { id: 'i1', title: '国庆探店', note: '', source: '', status: 'pending', created: 0 },
  ])),
  createIdea: vi.fn(), updateIdea: vi.fn(), deleteIdea: vi.fn(), createSchedule: vi.fn(),
}));

import IdeasPage from './IdeasPage';

describe('IdeasPage', () => {
  it('选题卡的编辑、删除、做内容按钮都在 DOM 里，可按角色查到（不靠 display:none 隐藏）', async () => {
    render(<IdeasPage onUseTopic={() => {}} />);
    await screen.findByText('国庆探店');
    expect(screen.getByRole('button', { name: '编辑' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '删除' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /做内容/ })).toBeTruthy();
  });
});
