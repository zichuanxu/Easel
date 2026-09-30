import { useState } from 'react';
import type { ChatSession } from '../lib/store';
import { IconNewChat, IconEdit, IconArchive, IconUnarchive, IconTrash, IconChevron } from './icons';

interface ChatSessionListProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onArchive: (id: string, archived: boolean) => void;
  onNew: () => void;
}

/** 对话记录（从全局侧栏挪进对话页）：新建 / 切换 / 重命名 / 归档 / 删除 / 查看已归档。 */
export default function ChatSessionList({
  sessions, activeSessionId, onSelect, onDelete, onRename, onArchive, onNew,
}: ChatSessionListProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  const startRename = (s: ChatSession) => { setRenamingId(s.id); setRenameValue(s.title); };
  const commitRename = () => {
    if (renamingId) onRename(renamingId, renameValue);
    setRenamingId(null);
  };

  const active = sessions.filter((s) => !s.archived && (s.messages.length > 0 || s.id === activeSessionId));
  const archived = sessions.filter((s) => s.archived);

  const renderItem = (s: ChatSession, isArchived: boolean) => {
    if (renamingId === s.id) {
      return (
        <div key={s.id} className="session-item">
          <input
            className="field session-rename-input"
            value={renameValue}
            autoFocus
            onChange={(e) => setRenameValue(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename();
              else if (e.key === 'Escape') setRenamingId(null);
            }}
            onBlur={commitRename}
          />
        </div>
      );
    }
    return (
      <div
        key={s.id}
        className={`session-item${s.id === activeSessionId ? ' active' : ''}`}
      >
        <button type="button" className="session-item-main" onClick={() => onSelect(s.id)}>
          <span className="session-item-title" title={s.title}>{s.title}</span>
        </button>
        <div className="session-actions">
          <button type="button" className="session-act" title="重命名"
            onClick={() => startRename(s)}><IconEdit size={14} /></button>
          <button type="button" className="session-act" title={isArchived ? '取消归档' : '归档'}
            onClick={() => onArchive(s.id, !isArchived)}>
            {isArchived ? <IconUnarchive size={14} /> : <IconArchive size={14} />}
          </button>
          <button type="button" className="session-act danger" title="删除"
            onClick={() => onDelete(s.id)}><IconTrash size={14} /></button>
        </div>
      </div>
    );
  };

  return (
    <div className="session-list">
      <div className="session-list-head">
        <h2 className="session-list-title">对话</h2>
        <button type="button" className="btn btn-sm" onClick={onNew}><IconNewChat size={13} />新对话</button>
      </div>
      <div className="session-list-body">
        {active.length === 0 && <p className="session-empty">还没有对话。在右边输入框里说说你想做什么。</p>}
        {active.map((s) => renderItem(s, false))}
        {archived.length > 0 && (
          <>
            <button type="button" className="archived-header" onClick={() => setShowArchived((v) => !v)} aria-expanded={showArchived}>
              <span className={`archived-chevron${showArchived ? ' open' : ''}`}><IconChevron size={12} /></span>
              已归档（{archived.length}）
            </button>
            {showArchived && archived.map((s) => renderItem(s, true))}
          </>
        )}
      </div>
    </div>
  );
}
