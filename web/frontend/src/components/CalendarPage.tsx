import { useState, useEffect, useCallback, useMemo } from 'react';
import { fetchSchedule, createSchedule, updateSchedule, deleteSchedule, fetchScheduleContext } from '../lib/api';
import type { ScheduleItem, ScheduleInput, ScheduleContext } from '../lib/api';
import { IconTrash, IconChevron } from './icons';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Modal from './ui/Modal';
import Tabs from './ui/Tabs';
import { Input, Textarea } from './ui/Field';

const STATUS_META: Record<string, { label: string; color: string }> = {
  idea: { label: '选题', color: 'var(--c-ink-3)' },
  draft: { label: '草稿', color: 'var(--layer-plan)' },
  scheduled: { label: '待发', color: 'var(--layer-discover)' },
  published: { label: '已发', color: 'var(--c-ok)' },
  unknown: { label: '待确认', color: 'var(--c-warn)' },   // 已提交但发布结果待确认（海外发布超时 / 5xx）
};
const EVENT_COLOR = 'var(--layer-plan)';
const EVENT_TYPES = ['节日', '电商', '平台活动', '行业'];
const SOURCE_LABEL: Record<string, string> = {
  chat: '对话页', 'publish-page': '发布页', manual: '手动', scheduler: '排期',
};
const PLATFORMS = ['小红书', '抖音', 'B站', '微信视频号', '快手', '公众号', '微博', '知乎'];
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];
type Filter = 'all' | 'content' | 'event';

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const kindOf = (it: ScheduleItem) => (it.kind === 'event' ? 'event' : 'content');
const MAX_VISIBLE = 3;   // 每格最多显示几条，超出折叠成「+N 更多」→ 点开当天详情
const EMPTY: ScheduleInput = {
  title: '', date: '', platform: '', time: '', status: 'idea', note: '',
  kind: 'content', url: '', source: 'manual', event_type: '', end_date: '',
};

export default function CalendarPage() {
  const today = useMemo(() => new Date(), []);
  const [cursor, setCursor] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [editing, setEditing] = useState<ScheduleItem | null>(null);   // 现有项
  const [form, setForm] = useState<ScheduleInput | null>(null);        // 弹窗表单（null=关闭）
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [ctx, setCtx] = useState<ScheduleContext | null>(null);
  const [showSuggest, setShowSuggest] = useState(true);
  const [dayView, setDayView] = useState<string | null>(null);   // 展开查看某天全部（date，null=关闭）

  const load = useCallback(() => {
    fetchSchedule().then(setItems).catch(() => {});
    fetchScheduleContext(14).then(setCtx).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const visible = useMemo(
    () => (filter === 'all' ? items : items.filter((it) => kindOf(it) === filter)),
    [items, filter]);

  // 每格：活动（事件）在上、内容在下
  const byDate = useMemo(() => {
    const m: Record<string, { events: ScheduleItem[]; content: ScheduleItem[] }> = {};
    for (const it of visible) {
      const bucket = (m[it.date] ||= { events: [], content: [] });
      (kindOf(it) === 'event' ? bucket.events : bucket.content).push(it);
    }
    return m;
  }, [visible]);

  // 构造当月网格（周一开头）
  const cells = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const startOffset = (first.getDay() + 6) % 7;  // 周一=0
    const start = new Date(first); start.setDate(1 - startOffset);
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start); d.setDate(start.getDate() + i); return d;
    });
  }, [cursor]);

  const openNew = (date: string) => {
    setDayView(null);
    setEditing(null);
    setForm({ ...EMPTY, date, kind: filter === 'event' ? 'event' : 'content' });
  };
  const openEdit = (it: ScheduleItem) => { setDayView(null); setEditing(it); setForm({ ...EMPTY, ...it }); };
  const close = () => { setForm(null); setEditing(null); };

  // 单条 chip（活动=色条，内容=按状态上色的圆点），日历格与当天详情共用
  const renderChip = (it: ScheduleItem) => {
    if (kindOf(it) === 'event') {
      return (
        <div key={it.id} className="cal-event is-event"
          title={it.event_type ? `${it.event_type}·${it.title}` : it.title}
          style={{ ['--ev' as string]: EVENT_COLOR }}
          onClick={(e) => { e.stopPropagation(); openEdit(it); }}>
          <span className="cal-event-dot" />
          <span className="cal-event-title">{it.title}</span>
        </div>
      );
    }
    return (
      <div key={it.id} className="cal-event" title={it.title}
        style={{ ['--ev' as string]: STATUS_META[it.status]?.color || 'var(--c-ink-3)' }}
        onClick={(e) => { e.stopPropagation(); openEdit(it); }}>
        <span className="cal-event-dot" />
        <span className="cal-event-title">{it.platform ? `[${it.platform}] ` : ''}{it.title}</span>
        {it.status === 'published' && it.source && SOURCE_LABEL[it.source]
          && <span className="cal-src">{SOURCE_LABEL[it.source]}</span>}
      </div>
    );
  };

  const save = async () => {
    if (!form || !form.title.trim() || !form.date) return;
    setSaving(true);
    try {
      if (editing) await updateSchedule(editing.id, form);
      else await createSchedule(form);
      close(); load();
    } finally { setSaving(false); }
  };
  const remove = async () => {
    if (!editing) return;
    setSaving(true);
    try { await deleteSchedule(editing.id); close(); load(); } finally { setSaving(false); }
  };

  const monthLabel = `${cursor.getFullYear()} 年 ${cursor.getMonth() + 1} 月`;
  const shift = (n: number) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + n, 1));
  const todayStr = ymd(today);
  const isEvent = form?.kind === 'event';
  const suggestions = ctx?.suggestions || [];

  return (
    <div className="page-scroll calendar-page">
      <PageHeader
        layer="plan"
        title="内容日历"
        description="每天各平台发什么一目了然——发布自动落库，可记录排期与平台活动。"
        actions={
          <div className="cal-nav">
            <Button size="sm" onClick={() => shift(-1)} aria-label="上个月"><span className="cal-prev"><IconChevron size={14} /></span></Button>
            <Button size="sm" onClick={() => setCursor(new Date(today.getFullYear(), today.getMonth(), 1))}>本月</Button>
            <span className="cal-month">{monthLabel}</span>
            <Button size="sm" onClick={() => shift(1)} aria-label="下个月"><IconChevron size={14} /></Button>
          </div>
        }
      />

      {showSuggest && suggestions.length > 0 && (
        <div className="cal-suggest">
          <div className="cal-suggest-head">
            <span>日历建议（近 {ctx?.window_days ?? 14} 天）</span>
            <button className="icon-btn" onClick={() => setShowSuggest(false)} aria-label="关闭建议">×</button>
          </div>
          <ul>{suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}

      <div className="cal-legend">
        {Object.entries(STATUS_META).map(([k, m]) => (
          <span key={k} className="cal-legend-item">
            <span className="cal-legend-swatch" style={{ ['--sw' as string]: m.color }} />{m.label}
          </span>
        ))}
        <span className="cal-legend-item">
          <span className="cal-legend-swatch sq" style={{ ['--sw' as string]: EVENT_COLOR }} />平台活动
        </span>
        <span className="cal-legend-filter">
          <Tabs<Filter> size="sm" ariaLabel="类型筛选" value={filter} onChange={setFilter}
            items={[{ key: 'all', label: '全部' }, { key: 'content', label: '内容' }, { key: 'event', label: '活动' }]} />
        </span>
      </div>

      <div className="cal-grid-head">
        {WEEKDAYS.map((w) => <div key={w} className="cal-wd">周{w}</div>)}
      </div>
      <div className="cal-grid">
        {cells.map((d, i) => {
          const ds = ymd(d);
          const inMonth = d.getMonth() === cursor.getMonth();
          const bucket = byDate[ds] || { events: [], content: [] };
          const dayItems = [...bucket.events, ...bucket.content];  // 活动在前
          const shown = dayItems.slice(0, MAX_VISIBLE);
          const hidden = dayItems.length - shown.length;
          return (
            <div key={i} className={`cal-cell ${inMonth ? '' : 'dim'} ${ds === todayStr ? 'today' : ''}`}
              onClick={() => (dayItems.length ? setDayView(ds) : openNew(ds))}>
              <div className="cal-daynum">{d.getDate()}</div>
              <div className="cal-events">
                {shown.map(renderChip)}
                {hidden > 0 && (
                  <button className="cal-more" onClick={(e) => { e.stopPropagation(); setDayView(ds); }}>
                    +{hidden} 更多
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {dayView && (() => {
        const b = byDate[dayView] || { events: [], content: [] };
        const list = [...b.events, ...b.content];
        return (
          <Modal title={`${dayView}（${list.length} 项）`} width={420} onClose={() => setDayView(null)}
            footer={<Button variant="primary" size="sm" onClick={() => openNew(dayView)}>新增</Button>}>
            <div className="cal-dayview-list">
              {list.map(renderChip)}
            </div>
          </Modal>
        );
      })()}

      {form && (
        <Modal title={`${editing ? '编辑' : '新增'}${isEvent ? '平台活动' : '排期'}`} onClose={close}
          footer={<>
            {editing
              ? <Button variant="danger" size="sm" className="cal-del" icon={<IconTrash size={13} />} onClick={remove} disabled={saving}>删除</Button>
              : null}
            <Button size="sm" onClick={close}>取消</Button>
            <Button variant="primary" size="sm" onClick={save} disabled={saving || !form.title.trim() || !form.date}>
              {saving ? '保存中…' : '保存'}
            </Button>
          </>}>
          <label className="field-label">类型</label>
          <Tabs<'content' | 'event'> size="sm" ariaLabel="类型" value={isEvent ? 'event' : 'content'}
            onChange={(k) => setForm(k === 'event' ? { ...form, kind: 'event', status: 'idea' } : { ...form, kind: 'content' })}
            items={[{ key: 'content', label: '内容 / 发布' }, { key: 'event', label: '平台活动' }]} />
          <label className="field-label">标题 *</label>
          <Input value={form.title} autoFocus placeholder={isEvent ? '活动/节点名称' : '要发什么内容'}
            onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <div className="cal-form-row">
            <div className="cal-form-grow">
              <label className="field-label">{isEvent ? '开始日期 *' : '日期 *'}</label>
              <Input type="date" value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </div>
            {isEvent ? (
              <div className="cal-form-grow">
                <label className="field-label">结束日期</label>
                <Input type="date" value={form.end_date || ''}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              </div>
            ) : (
              <div className="cal-form-time">
                <label className="field-label">时间</label>
                <Input type="time" value={form.time}
                  onChange={(e) => setForm({ ...form, time: e.target.value })} />
              </div>
            )}
          </div>
          {isEvent ? (
            <>
              <label className="field-label">活动类型</label>
              <div className="cal-chips">
                {EVENT_TYPES.map((t) => (
                  <button key={t} className={`chip ${form.event_type === t ? 'active' : ''}`}
                    onClick={() => setForm({ ...form, event_type: form.event_type === t ? '' : t })}>{t}</button>
                ))}
              </div>
              <label className="field-label">关联平台（可选）</label>
              <div className="cal-chips">
                {PLATFORMS.map((p) => (
                  <button key={p} className={`chip ${form.platform === p ? 'active' : ''}`}
                    onClick={() => setForm({ ...form, platform: form.platform === p ? '' : p })}>{p}</button>
                ))}
              </div>
            </>
          ) : (
            <>
              <label className="field-label">平台</label>
              <div className="cal-chips">
                {PLATFORMS.map((p) => (
                  <button key={p} className={`chip ${form.platform === p ? 'active' : ''}`}
                    onClick={() => setForm({ ...form, platform: form.platform === p ? '' : p })}>{p}</button>
                ))}
              </div>
              <label className="field-label">状态</label>
              <Tabs size="sm" ariaLabel="状态" value={form.status}
                onChange={(k) => setForm({ ...form, status: k })}
                items={Object.entries(STATUS_META).map(([k, m]) => ({ key: k, label: m.label }))} />
            </>
          )}
          <label className="field-label">备注</label>
          <Textarea className="cal-note-input" value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Modal>
      )}
    </div>
  );
}
