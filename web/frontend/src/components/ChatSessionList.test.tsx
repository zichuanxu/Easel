import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatSessionList from './ChatSessionList';
import type { ChatSession } from '../lib/store';

const LONG = '这是一个非常非常长的会话标题用来检查单行省略和悬停提示是否正常工作';
const S = (id: string, title: string, extra: Partial<ChatSession> = {}): ChatSession => ({
  id, title, created: 0, messages: [{ role: 'user', content: 'hi' }], ...extra,
} as ChatSession);

function setup(over: Partial<Parameters<typeof ChatSessionList>[0]> = {}) {
  const props = {
    sessions: [S('a', '国庆出片文案'), S('b', LONG), S('c', '旧会话', { archived: true })],
    activeSessionId: 'a',
    onSelect: vi.fn(), onDelete: vi.fn(), onRename: vi.fn(), onArchive: vi.fn(), onNew: vi.fn(),
    ...over,
  };
  render(<ChatSessionList {...props} />);
  return props;
}

describe('ChatSessionList', () => {
  it('列出未归档会话，已归档默认收起', () => {
    setup();
    expect(screen.getByText('国庆出片文案')).toBeTruthy();
    expect(screen.queryByText('旧会话')).toBeNull();
    fireEvent.click(screen.getByText(/已归档/));
    expect(screen.getByText('旧会话')).toBeTruthy();
  });

  it('长标题带 title 属性（配合 CSS 单行省略）', () => {
    setup();
    expect(screen.getByText(LONG).getAttribute('title')).toBe(LONG);
  });

  it('选中、新建、删除、归档回调', () => {
    const p = setup();
    fireEvent.click(screen.getByText(LONG));
    expect(p.onSelect).toHaveBeenCalledWith('b');
    fireEvent.click(screen.getByRole('button', { name: '新对话' }));
    expect(p.onNew).toHaveBeenCalled();
    fireEvent.click(screen.getAllByTitle('删除')[0]);
    expect(p.onDelete).toHaveBeenCalledWith('a');
    fireEvent.click(screen.getAllByTitle('归档')[0]);
    expect(p.onArchive).toHaveBeenCalledWith('a', true);
  });

  it('重命名：Enter 提交', () => {
    const p = setup();
    fireEvent.click(screen.getAllByTitle('重命名')[0]);
    const input = screen.getByDisplayValue('国庆出片文案');
    fireEvent.change(input, { target: { value: '新标题' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(p.onRename).toHaveBeenCalledWith('a', '新标题');
  });

  it('重命名：输入法组字中的回车不提交', () => {
    const p = setup();
    fireEvent.click(screen.getAllByTitle('重命名')[0]);
    const input = screen.getByDisplayValue('国庆出片文案');
    fireEvent.change(input, { target: { value: '新标题' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    expect(p.onRename).not.toHaveBeenCalled();
  });

  it('会话主体是真按钮：名称为标题，点击/回车走 onSelect；操作按钮并列且可按角色查到', () => {
    const p = setup();
    const body = screen.getByRole('button', { name: '国庆出片文案' });
    expect(body.tagName).toBe('BUTTON');
    expect(body.closest('.session-item')?.getAttribute('role')).toBeNull();
    // 主体按钮不嵌套其他交互元素
    expect(body.querySelector('button')).toBeNull();
    fireEvent.click(body);
    expect(p.onSelect).toHaveBeenCalledWith('a');
    expect(screen.getAllByRole('button', { name: '重命名' }).length).toBe(2);
    expect(screen.getAllByRole('button', { name: '归档' }).length).toBe(2);
    expect(screen.getAllByRole('button', { name: '删除' }).length).toBe(2);
  });
});
