import { useState, useEffect } from 'react';
import { buildProfile, profileBuildStatus } from '../lib/api';
import Modal from './ui/Modal';
import Button from './ui/Button';
import { Input, Textarea } from './ui/Field';

const PLATFORMS = ['小红书', '抖音', 'B站', '视频号', '公众号', '微博', '知乎'];
const TONES = ['专业严谨', '轻松幽默', '亲切日常', '犀利吐槽', '治愈温暖', '干货实用'];

interface OnboardingWizardProps {
  onClose: () => void;
  onCreated: (name: string) => void;
}

interface FormState {
  name: string;
  platforms: string[];
  accountStage: string;
  links: Record<string, string>;
  direction: string;
  reason: string;
  goal: string;
  formats: string;
  likes: string;
  tone: string;
  avoid: string;
}

const EMPTY: FormState = {
  name: '', platforms: [], accountStage: '全新起号', links: {},
  direction: '', reason: '', goal: '', formats: '', likes: '', tone: '', avoid: '',
};

const STEPS = ['基础信息', '社媒链接', '运营意图', '偏好与红线'];

export default function OnboardingWizard({ onClose, onCreated }: OnboardingWizardProps) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [phase, setPhase] = useState<'form' | 'enhancing'>('form');
  const [error, setError] = useState('');

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const togglePlatform = (p: string) =>
    setForm((f) => ({
      ...f,
      platforms: f.platforms.includes(p)
        ? f.platforms.filter((x) => x !== p)
        : [...f.platforms, p],
    }));

  const canNext =
    (step === 0 && form.name.trim() !== '') ||
    (step === 2 && form.direction.trim() !== '') ||
    step === 1 || step === 3;

  const submit = async () => {
    setSubmitting(true);
    setError('');
    try {
      // 后端异步：立即返回（基线已写、画像可用），不再长阻塞被代理超时掐断
      const res = await buildProfile(form.name.trim(), form as unknown as Record<string, unknown>);
      if (res.created) {
        setSubmitting(false);
        setPhase('enhancing'); // 进入后台增强等待（可跳过）
      } else {
        setError('画像创建失败，请重试');
        setSubmitting(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败');
      setSubmitting(false);
    }
  };

  // 增强阶段：轮询后台 AI 增强进度；完成/失败即进入画像（基线已可用）
  useEffect(() => {
    if (phase !== 'enhancing') return;
    let alive = true;
    const name = form.name.trim();
    const tick = async () => {
      try {
        const st = await profileBuildStatus(name);
        if (!alive) return;
        if (st.state === 'done' || st.state === 'failed' || st.state === 'unknown') {
          onCreated(name);
          return;
        }
      } catch {
        /* 轮询失败忽略，继续 */
      }
      if (alive) setTimeout(tick, 5000);
    };
    const t = setTimeout(tick, 4000);
    return () => { alive = false; clearTimeout(t); };
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const footer = phase === 'form' && !submitting ? (
    <>
      <Button onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>
        {step === 0 ? '取消' : '上一步'}
      </Button>
      {step < STEPS.length - 1 ? (
        <Button variant="primary" onClick={() => canNext && setStep(step + 1)} disabled={!canNext}>
          下一步
        </Button>
      ) : (
        <Button variant="primary" onClick={submit} disabled={!form.name.trim() || !form.direction.trim()}>
          生成画像
        </Button>
      )}
    </>
  ) : undefined;

  const chip = (active: boolean, label: string, onClick: () => void) => (
    <button key={label} type="button" className="wiz-chip" aria-pressed={active} onClick={onClick}>{label}</button>
  );

  return (
    <Modal title="配置账号画像" width={560} closeOnBackdrop={false} onClose={() => { if (!submitting) onClose(); }} footer={footer} className="wizard-modal">
      <ol className="wiz-steps" aria-label="步骤">
        {STEPS.map((s, i) => (
          <li key={s} className="wiz-step" data-done={i <= step} data-current={i === step} aria-current={i === step ? 'step' : undefined}>
            <span className="wiz-step-bar" />
            <span className="wiz-step-name">{s}</span>
          </li>
        ))}
      </ol>

      {submitting ? (
        <div className="wiz-wait">
          <div className="spinner" />
          正在创建画像基线…
        </div>
      ) : phase === 'enhancing' ? (
        <div className="wiz-wait">
          <div className="spinner" />
          <div className="wiz-wait-title">画像已创建，AI 正在后台增强…</div>
          <span className="wiz-hint">
            正在尝试抓取社媒链接并完善各维度，可能需要 1-2 分钟。<br />
            也可以现在就进去用，增强会在后台继续。
          </span>
          <div className="wiz-wait-action">
            <Button variant="primary" onClick={() => onCreated(form.name.trim())}>先进去用</Button>
          </div>
        </div>
      ) : (
        <div className="wiz-form">
          {step === 0 && (
            <>
              <label className="wiz-label">画像名 *（一个人设 = 一个画像，可跨多平台）</label>
              <Input value={form.name} placeholder="如：科技数码达人"
                onChange={(e) => set('name', e.target.value)} />
              <label className="wiz-label">运营平台（可多选）</label>
              <div className="wiz-chips">
                {PLATFORMS.map((p) => chip(form.platforms.includes(p), p, () => togglePlatform(p)))}
              </div>
              <label className="wiz-label">起号状态</label>
              <div className="wiz-chips">
                {['全新起号', '已有账号'].map((s) => chip(form.accountStage === s, s, () => set('accountStage', s)))}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <p className="wiz-hint">
                贴上各平台主页链接，AI 会尽力分析你已发的内容和风格（抓不到会跳过，可留空）。
              </p>
              {form.platforms.length === 0 && (
                <p className="wiz-hint">（未选平台，可直接下一步）</p>
              )}
              {form.platforms.map((p) => (
                <div key={p}>
                  <label className="wiz-label">{p} 主页链接</label>
                  <Input value={form.links[p] || ''} placeholder="https://…"
                    onChange={(e) => set('links', { ...form.links, [p]: e.target.value })} />
                </div>
              ))}
            </>
          )}

          {step === 2 && (
            <>
              <label className="wiz-label">想做什么方向的内容 *（越具体越好）</label>
              <Input value={form.direction} placeholder="如：平价护肤测评"
                onChange={(e) => set('direction', e.target.value)} />
              <label className="wiz-label">为什么做这个 / 你的优势·独特经历</label>
              <Textarea value={form.reason} onChange={(e) => set('reason', e.target.value)} />
              <label className="wiz-label">运营目标</label>
              <Input value={form.goal} placeholder="涨粉 / 变现 / 个人品牌 / 引流私域"
                onChange={(e) => set('goal', e.target.value)} />
              <label className="wiz-label">想产出的形式</label>
              <Input value={form.formats} placeholder="图文 / 短视频 / 中长视频 / 长文"
                onChange={(e) => set('formats', e.target.value)} />
            </>
          )}

          {step === 3 && (
            <>
              <label className="wiz-label">喜欢看的内容 / 对标账号</label>
              <Textarea value={form.likes} onChange={(e) => set('likes', e.target.value)} />
              <label className="wiz-label">期望调性</label>
              <div className="wiz-chips">
                {TONES.map((t) => chip(form.tone === t, t, () => set('tone', form.tone === t ? '' : t)))}
              </div>
              <label className="wiz-label">不做的内容 / 合规红线</label>
              <Textarea value={form.avoid} placeholder="如：不接医疗功效、不做虚假宣传"
                onChange={(e) => set('avoid', e.target.value)} />
            </>
          )}

          {error && <div className="wiz-error">{error}</div>}
        </div>
      )}
    </Modal>
  );
}
