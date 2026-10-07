import { useEffect, useMemo, useState } from 'react';
import type { ChatQuestion, ChatQuestionItem } from '../lib/api';
import { answerQuestion, questionStatus } from '../lib/api';
import Button from './ui/Button';
import Tag from './ui/Tag';
import { Input } from './ui/Field';

/**
 * ask_user 问答题卡片。
 *
 * OpenClaw 的 ask_user 一次可带 1-3 个问题（question.questions[]）。gateway 的
 * question.resolve 要求 answers 里**每个问题都有答案**（单个缺失即报
 * QUESTION_INVALID_ANSWER: "question 'xxx' requires an answer"）。
 * 因此多问题时渲染全部题目，用户每问答完一项，全部选齐后自动提交一次。
 *
 * 多选：问题对象带 multiSelect: true 时，answers[qid] 可携带多个 label
 * （gateway 对 multiSelect=false 的多值直接报 "does not allow multiple answers"，
 * 前端只按数据渲染，不绕过校验）。
 *
 * 失效：ask_user 等待有时限（expiresAtMs），超时后 gateway 取消并清理这道题，
 * Agent 往往换个 id 重新提问。旧卡片到点或提交时后端回 gone，就转成失效态，
 * 不再能提交——否则用户对着一张死卡片反复提交，只会收到 QUESTION_NOT_FOUND。
 */
const EXPIRED_HINT = '这道题已超时失效，Agent 收不到这个答案。如果 Agent 重新提问会出现新卡片；也可以直接在输入框里用文字回复。';

function QuestionCard({ question, onAnswered }: { question: ChatQuestion; onAnswered: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [customVals, setCustomVals] = useState<Record<string, string[]>>({});
  const [showCustom, setShowCustom] = useState<Record<string, boolean>>({});
  const [expired, setExpired] = useState('');   // 非空 = 失效提示文案

  useEffect(() => {
    const at = question.expiresAtMs;
    if (typeof at !== 'number' || !(at > 0)) return;
    // 到点只是提示该查了：浏览器时钟可能与网关不一致（远程打开时），以网关状态为准。
    // 仍 pending / 查询失败 → 过一会儿再查，绝不凭本机时钟锁死一张还能答的卡片。
    let t: ReturnType<typeof setTimeout>;
    let stopped = false;
    const check = () => {
      void questionStatus([question.id]).then((st) => {
        if (stopped) return;
        const s = st[question.id]?.status;
        if (s && s !== 'pending' && s !== 'unknown') setExpired(EXPIRED_HINT);
        else t = setTimeout(check, 15_000);
      });
    };
    // setTimeout 上限约 24.8 天，超出会立即触发；有效期不会这么长，夹一下防误判
    t = setTimeout(check, Math.min(Math.max(at - Date.now(), 0), 2 ** 31 - 1));
    return () => { stopped = true; clearTimeout(t); };
  }, [question.id, question.expiresAtMs]);
  const locked = busy || !!expired;

  const items: ChatQuestionItem[] = question.questions || [];
  const valsOf = (it: ChatQuestionItem): string[] => selected[it.questionId] || [];
  const allAnswered = items.length > 0 && items.every((it) => valsOf(it).length > 0);

  const pick = (it: ChatQuestionItem, label: string) => {
    setSelected((s) => {
      const cur = s[it.questionId] || [];
      const next = it.multiSelect
        ? (cur.includes(label) ? cur.filter((v) => v !== label) : [...cur, label])
        : [label];
      return { ...s, [it.questionId]: next };
    });
  };

  const fillCustom = (it: ChatQuestionItem) => {
    const v = (custom[it.questionId] || '').trim();
    if (!v) return;
    setSelected((s) => {
      const cur = s[it.questionId] || [];
      return { ...s, [it.questionId]: it.multiSelect && !cur.includes(v) ? [...cur, v] : [v] };
    });
    setCustomVals((c) => {
      const cur = c[it.questionId] || [];
      return { ...c, [it.questionId]: cur.includes(v) ? cur : [...cur, v] };
    });
  };

  const removeCustom = (it: ChatQuestionItem, v: string) => {
    setSelected((s) => ({ ...s, [it.questionId]: (s[it.questionId] || []).filter((x) => x !== v) }));
    setCustomVals((c) => ({ ...c, [it.questionId]: (c[it.questionId] || []).filter((x) => x !== v) }));
  };

  const submit = async () => {
    if (locked || !allAnswered) return;
    setBusy(true); setError('');
    const answers: Record<string, string[]> = {};
    for (const it of items) answers[it.questionId] = valsOf(it);
    try {
      const res = await answerQuestion({ questionId: question.id, answers });
      if (res.gone) setExpired(res.error || EXPIRED_HINT);
      else if (!res.ok) setError(res.error || '提交失败');
      else onAnswered();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="message-row assistant">
      <div className="msg-col assistant question-col">
        <div className={`question-card${expired ? ' question-card--expired' : ''}`}>
          {items.map((it, idx) => {
            const options: { label: string; description?: string }[] = it.options || [];
            const vals = valsOf(it);
            const ctl = showCustom[it.questionId];
            const cvals = customVals[it.questionId] || [];
            return (
              <div key={it.questionId} className="question-card__item">
                {idx > 0 && <div className="question-card__divider" />}
                {it.header && <div className="question-card__chip"><Tag>{it.header}</Tag></div>}
                <div className="question-card__title">
                  {it.question || '请选择'}
                  {it.multiSelect && <span className="question-card__multi"><Tag>可多选</Tag></span>}
                </div>
                <div className="question-card__options">
                  {options.map((opt) => (
                    <button key={opt.label}
                      className={`question-card__option${vals.includes(opt.label) ? ' question-card__option--selected' : ''}`}
                      disabled={locked}
                      onClick={() => pick(it, opt.label)}>
                      <strong>{opt.label}</strong>
                      {opt.description && <span>{opt.description}</span>}
                    </button>
                  ))}
                  {cvals.map((v) => (
                    <button key={`custom-${v}`}
                      className="question-card__option question-card__option--selected"
                      disabled={locked}
                      title="点击移除"
                      onClick={() => removeCustom(it, v)}>
                      <strong>{v}</strong>
                      <span>自定义 · 点击移除</span>
                    </button>
                  ))}
                  {!expired && <Button variant="ghost" size="sm" className="question-card__other" disabled={busy}
                    onClick={() => setShowCustom((s) => ({ ...s, [it.questionId]: !s[it.questionId] }))}>
                    {ctl ? '收起自定义输入' : '自行输入'}
                  </Button>}
                </div>
                {ctl && !expired && (
                  <div className="question-card__custom">
                    <Input
                      type="text"
                      value={custom[it.questionId] || ''}
                      placeholder="输入你的答案"
                      onChange={(e) => setCustom((c) => ({ ...c, [it.questionId]: e.target.value }))}
                    />
                    <Button variant="secondary" disabled={busy || !(custom[it.questionId] || '').trim()}
                      onClick={() => fillCustom(it)}>
                      填入
                    </Button>
                  </div>
                )}
              </div>
            );
          })}

          {/* 单选题：选完点提交；多题：全部选齐后提交（单选/多选同一规则） */}
          {expired ? (
            <div className="question-card__actions">
              <Button variant="secondary" onClick={onAnswered}>关闭</Button>
            </div>
          ) : items.length === 1 ? (
            <div className="question-card__actions">
              <Button variant="primary" disabled={busy || !allAnswered}
                onClick={() => void submit()}>
                提交
              </Button>
            </div>
          ) : (
            allAnswered && !busy && (
              <div className="question-card__actions">
                <Button variant="primary" disabled={busy} onClick={() => void submit()}>
                  全部已选，提交
                </Button>
              </div>
            )
          )}
          {busy && <div className="question-card__hint">已提交，Agent 继续处理中…</div>}
          {expired && <div className="question-card__hint">{expired}</div>}
          {!expired && error && <div className="question-card__hint question-card__error">{error}</div>}
        </div>
      </div>
    </div>
  );
}

/** 流式中的 ask_user 问答题列表（一次性卡片，答完即从当前流移除）。 */
export default function QuestionCards({ questions, onDone }: { questions: ChatQuestion[]; onDone?: (questionId: string) => void }) {
  const [answered, setAnswered] = useState<Record<string, boolean>>({});
  const visible = useMemo(
    () => questions.filter((q) => !answered[q.id]),
    [questions, answered],
  );
  if (!visible.length) return null;
  return (
    <>
      {visible.map((q) => (
        <QuestionCard key={q.id} question={q} onAnswered={() => {
          setAnswered((a) => ({ ...a, [q.id]: true }));
          onDone?.(q.id);   // 通知 App：此题已答，重放/恢复不再出现
        }} />
      ))}
    </>
  );
}
