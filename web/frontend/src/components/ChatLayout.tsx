import { useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';

/** 对话页两栏外壳：宽屏常驻会话栏；窄屏（<1200px）收起，点按钮展开，选中会话后自动收起。 */
export default function ChatLayout({ sessions, children }: { sessions: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const closeOnPick = (e: MouseEvent) => {
    const item = (e.target as HTMLElement).closest('.session-item');
    if (item && !item.querySelector('input') && !(e.target as HTMLElement).closest('.session-actions')) setOpen(false);
  };
  return (
    <div className={`chat-layout${open ? ' sessions-open' : ''}`}>
      <button type="button" className="btn btn-sm chat-sessions-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        对话记录
      </button>
      <aside className="chat-sessions-pane" onClick={closeOnPick}>{sessions}</aside>
      <div className="chat-main">{children}</div>
    </div>
  );
}
