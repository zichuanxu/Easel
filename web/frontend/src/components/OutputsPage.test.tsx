import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchOutputs: vi.fn(() => Promise.resolve([
    { name: '国庆专题', type: 'dir', path: '国庆专题', fileCount: 2, children: [
      { name: 'a.md', type: 'file', path: '国庆专题/a.md', kind: 'text', size: 1 },
    ] },
  ])),
  fetchOutputContent: vi.fn(), mediaUrl: (p: string) => p, deleteOutput: vi.fn(),
}));

import OutputsPage from './OutputsPage';

describe('OutputsPage 卡片', () => {
  it('卡片主体是真按钮，点击进入项目；删除按钮并列、不嵌套', async () => {
    render(<OutputsPage />);
    const name = await screen.findByText('国庆专题');
    const body = name.closest('button') as HTMLButtonElement;
    expect(body).toBeTruthy();
    expect(body.querySelector('button')).toBeNull();
    const del = screen.getByRole('button', { name: '删除' });
    expect(body.contains(del)).toBe(false);
    fireEvent.click(body);
    expect(await screen.findByText('a.md')).toBeTruthy();
  });
});
