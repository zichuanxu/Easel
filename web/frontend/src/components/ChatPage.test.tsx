import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({ uploadFiles: vi.fn(), adoptOversize: vi.fn() }));

import ChatPage from './ChatPage';
import type { ChatSession } from '../lib/store';

const empty = { id: 's1', title: '新对话', created: 0, messages: [] } as unknown as ChatSession;
const EMOJI = /\p{Extended_Pictographic}/u;

describe('ChatPage 空态', () => {
  it('四条起步建议带层色小方块、不含 emoji，点击直接发送', () => {
    const onSend = vi.fn();
    const { container } = render(
      <ChatPage session={empty} onSend={onSend} onStop={() => {}} onResend={() => {}} />,
    );
    const items = container.querySelectorAll('.starter');
    expect(items.length).toBe(4);
    items.forEach((el) => {
      expect(el.querySelector('.ui-swatch')).toBeTruthy();
      expect(EMOJI.test(el.textContent || '')).toBe(false);
    });
    fireEvent.click(screen.getByText('蹭个热点'));
    expect(onSend).toHaveBeenCalledWith('看看现在微博和抖音有什么热搜，挑几个适合我做二创的选题');
  });

  it('标题用问候语加「想创作点什么？」', () => {
    render(<ChatPage session={empty} onSend={() => {}} onStop={() => {}} onResend={() => {}} />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/想创作点什么？$/);
  });
});

describe('ChatPage 对话态', () => {
  it('页头显示会话标题和画像', () => {
    const s = { ...empty, title: '国庆出片文案', persona: '在逃空指针', messages: [{ role: 'user', content: '写一条' }] } as unknown as ChatSession;
    render(<ChatPage session={s} onSend={() => {}} onStop={() => {}} onResend={() => {}} />);
    expect(screen.getByRole('heading', { level: 2, name: '国庆出片文案' })).toBeTruthy();
    expect(screen.getByText('画像：在逃空指针')).toBeTruthy();
  });
});
