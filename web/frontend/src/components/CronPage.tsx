import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cronAction, createCronJob, deleteCronJob, fetchCronJobs, fetchCronRuns } from '../lib/api';
import type { CronJob, CronRun } from '../lib/api';
import {
  WEEKDAY_NAMES, defaultScheduleForm, describeSchedule, fmtDateTime, fmtDuration, toSpec,
} from '../lib/cronSchedule';
import type { RepeatMode, ScheduleForm } from '../lib/cronSchedule';
import { IconCheck, IconChevron, IconPlus, IconTrash } from './icons';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Modal from './ui/Modal';
import Tabs from './ui/Tabs';
import Tag from './ui/Tag';
import EmptyState from './ui/EmptyState';
import SelectMenu from './ui/SelectMenu';
import { Input, Textarea } from './ui/Field';

const REFRESH_MS = 30_000;
// 和后端 CRON_PUBLISH_WORDS 一致：填写时就提醒，不等保存
const PUBLISH_WORDS = ['发布', '发帖', '发笔记', '发视频', '评论', '回复', '私信', '点赞', '上传'];
const MODES: { key: RepeatMode; label: string }[] = [
  { key: 'daily', label: '每天' },
  { key: 'weekly', label: '每周' },
  { key: 'every', label: '每隔一段时间' },
  { key: 'once', label: '只运行一次' },
  { key: 'cron', label: '自定义' },
];
const UNITS = [
  { value: 'minutes', label: '分钟' }, { value: 'hours', label: '小时' }, { value: 'days', label: '天' },
];
const EXAMPLES = [
  '收集今天 AI 领域的热点，挑 3 个适合我账号的选题，写进选题库',
  '汇总各平台最近 7 天的数据变化，写一份简短周报',
  '检查内容日历里明天要发的内容，素材缺什么列出来',
];

interface Draft { name: string; message: string; schedule: ScheduleForm }
const emptyDraft = (): Draft => ({ name: '', message: '', schedule: defaultScheduleForm() });

type Tone = 'ok' | 'warn' | 'danger' | 'neutral' | 'plan';

function statusOf(job: CronJob): { tone: Tone; label: string } {
  if (job.runningAtMs) return { tone: 'plan', label: '运行中' };
  if (!job.enabled) return { tone: 'neutral', label: '已暂停' };
  if (job.lastRunStatus === 'error') return { tone: 'danger', label: '上次失败' };
  if (job.lastRunStatus === 'ok') return { tone: 'ok', label: '上次成功' };
  if (job.lastRunStatus === 'skipped') return { tone: 'warn', label: '上次跳过' };
  return { tone: 'neutral', label: '等待运行' };
}

const RUN_STATUS: Record<string, { tone: Tone; label: string }> = {
  ok: { tone: 'ok', label: '成功' }, error: { tone: 'danger', label: '失败' }, skipped: { tone: 'warn', label: '跳过' },
};

export default function CronPage() {
  const [jobs, setJobs] = useState<CronJob[] | null>(null);
  const [minGap, setMinGap] = useState(10);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [runsOf, setRunsOf] = useState<CronJob | null>(null);
  const [runs, setRuns] = useState<CronRun[] | null>(null);
  const [runsError, setRunsError] = useState('');
  const [confirmDel, setConfirmDel] = useState<CronJob | null>(null);
  const [showSystem, setShowSystem] = useState(false);

  // 定时刷新和操作后的刷新可能交错返回：只认最后发出的那次，旧结果不覆盖新状态
  const loadSeq = useRef(0);
  const load = useCallback(() => {
    const seq = ++loadSeq.current;
    fetchCronJobs()
      .then((r) => {
        if (seq !== loadSeq.current) return;
        setJobs(r.jobs); setMinGap(r.minIntervalMinutes); setLoadError('');
      })
      .catch((e: Error) => { if (seq === loadSeq.current) setLoadError(e.message); });
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const mine = useMemo(() => (jobs ?? []).filter((j) => !j.readonly), [jobs]);
  const system = useMemo(() => (jobs ?? []).filter((j) => j.readonly), [jobs]);

  const openNew = () => { setDraft(emptyDraft()); setFormError(''); };

  // 运行记录同理：关掉再开别的任务、或连点刷新时，晚到的旧结果不能显示在新标题下
  const runsSeq = useRef(0);
  const openRuns = (job: CronJob) => {
    const seq = ++runsSeq.current;
    setRunsOf(job); setRuns(null); setRunsError('');
    fetchCronRuns(job.id)
      .then((r) => { if (seq === runsSeq.current) setRuns(r.runs); })
      .catch((e: Error) => { if (seq === runsSeq.current) setRunsError(e.message); });
  };

  const act = async (job: CronJob, action: 'pause' | 'resume' | 'run') => {
    setBusy(job.id);
    try {
      await cronAction(job.id, action);
      const text = action === 'run' ? `「${job.name}」已开始运行，结果稍后在运行记录里看`
        : action === 'pause' ? `已暂停「${job.name}」` : `已恢复「${job.name}」`;
      setNotice({ tone: 'ok', text });
      load();
    } catch (e) {
      setNotice({ tone: 'error', text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!confirmDel) return;
    const job = confirmDel;
    setBusy(job.id);
    try {
      await deleteCronJob(job.id);
      setNotice({ tone: 'ok', text: `已删除「${job.name}」` });
      load();
    } catch (e) {
      setNotice({ tone: 'error', text: `没能删除「${job.name}」：${(e as Error).message}` });
    } finally {
      setConfirmDel(null);   // 成功失败都关弹窗，提示才看得见
      setBusy(null);
    }
  };

  const save = async () => {
    if (!draft) return;
    const spec = toSpec(draft.schedule);
    if (typeof spec === 'string') { setFormError(spec); return; }
    setSaving(true); setFormError('');
    try {
      const r = await createCronJob({ name: draft.name.trim(), message: draft.message.trim(), schedule: spec });
      setDraft(null);
      setNotice(r.warning
        ? { tone: 'warn', text: `已创建「${r.job.name}」。${r.warning}` }
        : { tone: 'ok', text: `已创建「${r.job.name}」` });
      load();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const setSched = (patch: Partial<ScheduleForm>) => {
    if (draft) setDraft({ ...draft, schedule: { ...draft.schedule, ...patch } });
  };
  const previewSpec = draft ? toSpec(draft.schedule) : '';
  const preview = typeof previewSpec === 'string' ? ''
    : previewSpec.mode === 'cron' ? describeSchedule({ kind: 'cron', expr: previewSpec.expr })
      : previewSpec.mode === 'every' ? describeSchedule({ kind: 'every', everyMs: previewSpec.minutes * 60000 })
        : describeSchedule({ kind: 'at', at: previewSpec.at });
  const publishHit = draft ? PUBLISH_WORDS.filter((w) => draft.message.includes(w)) : [];

  const renderJob = (job: CronJob) => {
    const st = statusOf(job);
    const disabled = busy === job.id;
    const detail = job.kind === 'agentTurn' ? job.message : job.description;
    return (
      <article key={job.id} className={`cron-job${job.enabled ? '' : ' paused'}`}>
        <div className="cron-job-main">
          <div className="cron-job-head">
            <h3 className="cron-job-name" title={job.name}>{job.name}</h3>
            <Tag tone={st.tone}>{st.label}</Tag>
          </div>
          <div className="cron-job-sched">{describeSchedule(job.schedule)}</div>
          {detail && <p className="cron-job-msg" title={detail}>{detail}</p>}
          <div className="cron-job-meta">
            <span>下次：{job.enabled ? fmtDateTime(job.nextRunAtMs) : '—'}</span>
            <span>上次：{fmtDateTime(job.lastRunAtMs)}{job.lastDurationMs ? `（${fmtDuration(job.lastDurationMs)}）` : ''}</span>
          </div>
          {job.lastRunStatus === 'error' && job.lastError && <p className="cron-job-err">{job.lastError}</p>}
        </div>
        <div className="cron-job-actions">
          <Button size="sm" variant="ghost" onClick={() => openRuns(job)}>运行记录</Button>
          {!job.readonly && (
            <>
              <Button size="sm" variant="ghost" disabled={disabled || !!job.runningAtMs} onClick={() => act(job, 'run')}>立即运行</Button>
              <Button size="sm" disabled={disabled} onClick={() => act(job, job.enabled ? 'pause' : 'resume')}>
                {job.enabled ? '暂停' : '恢复'}
              </Button>
              <Button size="sm" variant="ghost" className="cron-del" aria-label={`删除「${job.name}」`} title="删除"
                icon={<IconTrash size={13} />} disabled={disabled} onClick={() => setConfirmDel(job)} />
            </>
          )}
        </div>
      </article>
    );
  };

  return (
    <div className="page-scroll cron-page">
      <PageHeader
        layer="plan"
        title="定时任务"
        description="到点让 agent 自动做一件事：追热点、整理选题、汇总数据。每次运行是一个独立会话，结果在运行记录里看。"
        actions={<Button variant="primary" size="sm" icon={<IconPlus size={14} />} onClick={openNew}>新建任务</Button>}
      />
      <p className="cron-note">
        定时运行时没人在场确认，agent 只会准备好内容、不会替你真正发布。小红书不要定时自动发帖或互动，会被判成 AI 托管。
      </p>

      {notice && (
        <div className={notice.tone === 'error' ? 'notice-error cron-notice' : `cron-notice ${notice.tone}`} role="status">
          {notice.tone === 'ok' && <IconCheck size={14} />}
          <span>{notice.text}</span>
          <button type="button" className="cron-notice-close" aria-label="关闭提示" onClick={() => setNotice(null)}>×</button>
        </div>
      )}

      {loadError && (
        <div className="notice-error cron-load-error" role="alert">
          <span>{loadError}</span>
          <Button size="sm" onClick={load}>重试</Button>
        </div>
      )}

      {jobs === null && !loadError && <p className="cron-loading">正在读取定时任务…</p>}

      {jobs !== null && (
        <>
          <section className="cron-section">
            <h2 className="cron-section-title">我的任务 <span className="cron-count">{mine.length}</span></h2>
            {mine.length === 0
              ? <EmptyState text="还没有定时任务。比如每天早上 9 点让 agent 收集热点、整理成选题。" action={{ label: '新建任务', onClick: openNew }} />
              : <div className="cron-list">{mine.map(renderJob)}</div>}
          </section>

          {system.length > 0 && (
            <section className="cron-section">
              <button type="button" className="cron-sys-toggle" aria-expanded={showSystem} onClick={() => setShowSystem((v) => !v)}>
                <span className={`cron-chevron${showSystem ? ' open' : ''}`}><IconChevron size={12} /></span>
                系统和命令行任务 <span className="cron-count">{system.length}</span>
                <span className="cron-sys-hint">只能查看</span>
              </button>
              {showSystem && <div className="cron-list">{system.map(renderJob)}</div>}
            </section>
          )}
        </>
      )}

      {draft && (
        <Modal title="新建定时任务" width={560} onClose={() => setDraft(null)} closeOnBackdrop={false}
          footer={<>
            <Button size="sm" onClick={() => setDraft(null)}>取消</Button>
            <Button variant="primary" size="sm" loading={saving}
              disabled={!draft.name.trim() || !draft.message.trim()} onClick={save}>创建</Button>
          </>}>
          <label className="field-label" htmlFor="cron-name">名称</label>
          <Input id="cron-name" value={draft.name} maxLength={60} autoFocus placeholder="比如：每日热点选题"
            onChange={(e) => setDraft({ ...draft, name: e.target.value })} />

          <label className="field-label" htmlFor="cron-msg">让 agent 做什么</label>
          <Textarea id="cron-msg" className="cron-msg-input" value={draft.message} maxLength={4000}
            placeholder="像在对话里一样写清楚要做的事"
            onChange={(e) => setDraft({ ...draft, message: e.target.value })} />
          {!draft.message && (
            <div className="cron-examples">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="cron-example" onClick={() => setDraft({ ...draft, message: ex })}>{ex}</button>
              ))}
            </div>
          )}
          {publishHit.length > 0 && (
            <p className="cron-warn">
              提到了「{publishHit.join('、')}」：定时运行时没人确认，agent 不会替你真正发出去，只会把内容准备好。
            </p>
          )}

          <label className="field-label">什么时候运行</label>
          <Tabs<RepeatMode> size="sm" ariaLabel="重复方式" value={draft.schedule.mode}
            onChange={(mode) => setSched({ mode })} items={MODES} />
          <div className="cron-sched-fields">
            {(draft.schedule.mode === 'daily' || draft.schedule.mode === 'weekly') && (
              <div className="cron-row">
                {draft.schedule.mode === 'weekly' && (
                  <div className="cron-weekdays" role="group" aria-label="星期">
                    {WEEKDAY_NAMES.map((n, i) => {
                      const d = i + 1;
                      const on = draft.schedule.weekdays.includes(d);
                      return (
                        <button key={d} type="button" className={`cron-day${on ? ' on' : ''}`} aria-pressed={on}
                          onClick={() => setSched({ weekdays: on ? draft.schedule.weekdays.filter((x) => x !== d) : [...draft.schedule.weekdays, d] })}>
                          周{n}
                        </button>
                      );
                    })}
                  </div>
                )}
                <Input type="time" aria-label="时间" className="cron-time" value={draft.schedule.time}
                  onChange={(e) => setSched({ time: e.target.value })} />
              </div>
            )}
            {draft.schedule.mode === 'every' && (
              <div className="cron-row">
                <span>每隔</span>
                <Input type="number" aria-label="间隔" className="cron-num" min={1} value={draft.schedule.everyValue}
                  onChange={(e) => setSched({ everyValue: Number(e.target.value) })} />
                <SelectMenu ariaLabel="单位" className="cron-unit" value={draft.schedule.everyUnit} options={UNITS}
                  onChange={(v) => setSched({ everyUnit: v as ScheduleForm['everyUnit'] })} />
              </div>
            )}
            {draft.schedule.mode === 'once' && (
              <Input type="datetime-local" aria-label="运行时间" value={draft.schedule.at}
                onChange={(e) => setSched({ at: e.target.value })} />
            )}
            {draft.schedule.mode === 'cron' && (
              <>
                <Input aria-label="cron 表达式" className="cron-expr" value={draft.schedule.expr} spellCheck={false}
                  placeholder="分 时 日 月 周，如 0 9 * * 1-5" onChange={(e) => setSched({ expr: e.target.value })} />
                <p className="cron-help">5 段：分 时 日 月 周（0 或 7 是周日）。「分」要写具体数字，例如 0 9 * * 1-5 是工作日早上 9 点。</p>
              </>
            )}
            <p className="cron-help">
              {preview ? <>将会：<strong>{preview}</strong>。</> : null}两次运行至少间隔 {minGap} 分钟。
              {draft.schedule.mode === 'once' ? '按你现在这台电脑的时间。' : '按运行 Easel 的电脑的时区。'}
            </p>
          </div>
          {formError && <p className="notice-error cron-form-error" role="alert">{formError}</p>}
        </Modal>
      )}

      {runsOf && (
        <Modal title={`运行记录：${runsOf.name}`} width={620} onClose={() => setRunsOf(null)}
          footer={<Button size="sm" onClick={() => openRuns(runsOf)}>刷新</Button>}>
          {runsError && <p className="notice-error">{runsError}</p>}
          {!runsError && runs === null && <p className="cron-loading">正在读取…</p>}
          {runs !== null && runs.length === 0 && <EmptyState text="还没有运行过。可以点「立即运行」先试一次。" />}
          {runs !== null && runs.length > 0 && (
            <ol className="cron-runs">
              {runs.map((r, i) => {
                const st = RUN_STATUS[r.status] ?? { tone: 'neutral' as const, label: r.status || '未知' };
                const text = r.summary && r.summary !== 'NO_REPLY' ? r.summary : '';
                return (
                  <li key={`${r.runAtMs}-${i}`} className="cron-run">
                    <div className="cron-run-head">
                      <span className="cron-run-time">{fmtDateTime(r.runAtMs)}</span>
                      <Tag tone={st.tone}>{st.label}</Tag>
                      {r.durationMs != null && <span className="cron-run-dur">{fmtDuration(r.durationMs)}</span>}
                    </div>
                    {r.error && <p className="cron-job-err">{r.error}</p>}
                    {text && <div className="cron-run-summary">{text}</div>}
                    {!r.error && !text && <p className="cron-run-empty">没有输出文字</p>}
                  </li>
                );
              })}
            </ol>
          )}
        </Modal>
      )}

      {confirmDel && (
        <Modal title="删除定时任务" width={420} onClose={() => setConfirmDel(null)}
          footer={<>
            <Button size="sm" onClick={() => setConfirmDel(null)}>取消</Button>
            <Button variant="danger" size="sm" loading={busy === confirmDel.id} onClick={remove}>删除</Button>
          </>}>
          <p>删除「{confirmDel.name}」后它就不会再运行了。只是想停一阵，可以用「暂停」。</p>
        </Modal>
      )}
    </div>
  );
}
