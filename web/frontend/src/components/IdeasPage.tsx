import { useState, useEffect, useCallback, useMemo } from 'react';
import { fetchIdeas, createIdea, updateIdea, deleteIdea, createSchedule } from '../lib/api';
import type { Idea, IdeaInput } from '../lib/api';
import { IconEdit, IconTrash, IconChat, IconCalendar, IconChevron, IconCheck } from './icons';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Tag from './ui/Tag';
import Modal from './ui/Modal';
import Tabs from './ui/Tabs';
import { Input, Textarea } from './ui/Field';

interface IdeasPageProps {
  onUseTopic: (title: string) => void;
}

const COLUMNS: { key: string; label: string; color: string; empty: string }[] = [
  { key: 'pending', label: '待做', color: 'var(--c-ink-3)', empty: '还没有选题，从热点雷达或对话里加一个' },
  { key: 'doing', label: '进行中', color: 'var(--layer-plan)', empty: '没有正在做的选题' },
  { key: 'done', label: '已完成', color: 'var(--c-ok)', empty: '做完的选题会出现在这里' },
];
const NEXT: Record<string, string> = { pending: 'doing', doing: 'done', done: 'pending' };
const EMPTY: IdeaInput = { title: '', note: '', source: '', status: 'pending' };

export default function IdeasPage({ onUseTopic }: IdeasPageProps) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [form, setForm] = useState<IdeaInput | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [toast, setToast] = useState('');

  const load = useCallback(() => { fetchIdeas().then(setIdeas).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(''), 2200); };
  const byStatus = useMemo(() => {
    const g: Record<string, Idea[]> = { pending: [], doing: [], done: [] };
    for (const it of ideas) (g[it.status] || g.pending).push(it);
    return g;
  }, [ideas]);

  const openNew = () => { setEditId(null); setForm({ ...EMPTY }); };
  const openEdit = (it: Idea) => { setEditId(it.id); setForm({ title: it.title, note: it.note, source: it.source, status: it.status }); };
  const save = async () => {
    if (!form || !form.title.trim()) return;
    if (editId) await updateIdea(editId, form); else await createIdea(form);
    setForm(null); setEditId(null); load();
  };
  const advance = async (it: Idea) => { await updateIdea(it.id, { ...it, status: NEXT[it.status] }); load(); };
  const remove = async (it: Idea) => { await deleteIdea(it.id); load(); };
  const schedule = async (it: Idea) => {
    const d = new Date();
    await createSchedule({ title: it.title, date: d.toISOString().slice(0, 10), platform: '', time: '', status: 'idea', note: it.note });
    showToast('已加入日历（今天）');
  };

  return (
    <div className="page-scroll ideas-page">
      <PageHeader
        layer="plan"
        title="选题库"
        description="攒住每一个灵感——从热点收藏或手动新增，推进到「做内容」再进日历。"
        actions={<Button variant="primary" size="sm" onClick={openNew}>新建选题</Button>}
      />

      <div className="kanban">
        {COLUMNS.map((col) => (
          <div key={col.key} className="kanban-col">
            <div className="kanban-col-head">
              <span className="kanban-dot" style={{ ['--dot' as string]: col.color }} />
              {col.label}<span className="kanban-count">{byStatus[col.key].length}</span>
            </div>
            <div className="kanban-list">
              {byStatus[col.key].length === 0 && <div className="kanban-empty">{col.empty}</div>}
              {byStatus[col.key].map((it) => (
                <div key={it.id} className="card idea-card">
                  <div className="idea-card-actions">
                    <button className="session-act" title="编辑" onClick={() => openEdit(it)}><IconEdit size={13} /></button>
                    <button className="session-act danger" title="删除" onClick={() => remove(it)}><IconTrash size={13} /></button>
                  </div>
                  <div className="idea-title">{it.title}</div>
                  {it.source && <div className="idea-source"><Tag>{it.source}</Tag></div>}
                  {it.note && <div className="idea-note">{it.note}</div>}
                  <div className="idea-foot">
                    <Button variant="ghost" size="sm" icon={<IconChat size={13} />} onClick={() => onUseTopic(it.title)}>做内容</Button>
                    <Button variant="ghost" size="sm" icon={<IconCalendar size={13} />} onClick={() => schedule(it)}>排期</Button>
                    <Button variant="ghost" size="sm" className="idea-next" onClick={() => advance(it)} title="推进状态">
                      {COLUMNS.find((c) => c.key === NEXT[it.status])?.label} <IconChevron size={12} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {form && (
        <Modal title={editId ? '编辑选题' : '新建选题'} onClose={() => setForm(null)}
          footer={<>
            <Button size="sm" onClick={() => setForm(null)}>取消</Button>
            <Button variant="primary" size="sm" onClick={save} disabled={!form.title.trim()}>保存</Button>
          </>}>
          <label className="field-label">选题 *</label>
          <Input value={form.title} autoFocus placeholder="想做的内容 / 角度"
            onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <label className="field-label">备注 / 角度</label>
          <Textarea className="idea-note-input" value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <label className="field-label">来源</label>
          <Input value={form.source} placeholder="如：微博热搜 / 灵感"
            onChange={(e) => setForm({ ...form, source: e.target.value })} />
          <label className="field-label">状态</label>
          <Tabs size="sm" ariaLabel="状态" items={COLUMNS.map((c) => ({ key: c.key, label: c.label }))}
            value={form.status ?? 'pending'} onChange={(k) => setForm({ ...form, status: k })} />
        </Modal>
      )}

      {toast && <div className="toast ok"><span className="toast-icon" aria-hidden="true"><IconCheck size={14} /></span>{toast}</div>}
    </div>
  );
}
