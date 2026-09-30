import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatLayout from './ChatLayout';

function setup() {
  const { container } = render(
    <ChatLayout
      sessions={(
        <div className="session-item">
          <span>会话甲</span>
          <div className="session-actions"><button type="button">操作</button></div>
        </div>
      )}
    >
      <p>正文</p>
    </ChatLayout>,
  );
  fireEvent.click(screen.getByRole('button', { name: '对话记录' }));
  return container.querySelector('.chat-layout')!;
}

describe('ChatLayout', () => {
  it('点会话项操作按钮不收起，点会话项本身收起', () => {
    const layout = setup();
    expect(layout.classList.contains('sessions-open')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '操作' }));
    expect(layout.classList.contains('sessions-open')).toBe(true);
    fireEvent.click(screen.getByText('会话甲'));
    expect(layout.classList.contains('sessions-open')).toBe(false);
  });
});
