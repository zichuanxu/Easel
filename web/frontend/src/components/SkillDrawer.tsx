import { useState, useEffect, useMemo, useRef } from 'react';
import { fetchSkillDetail, executeSkill, saveEnv } from '../lib/api';
import type { SkillDetail } from '../lib/api';
import { renderMarkdown } from '../lib/sanitize';
import { displayName } from '../lib/skillDisplayNames';
import { isLayerKey, layerInfo } from '../lib/layers';
import Button from './ui/Button';
import Tag from './ui/Tag';
import Panel from './ui/Panel';
import { Input, Textarea } from './ui/Field';
import SelectMenu from './ui/SelectMenu';

interface SkillDrawerProps {
  skillName: string;
  persona: string;
  onClose: () => void;
  onConfigured: () => void;   // 保存 API 后通知父组件刷新卡片状态
}

export default function SkillDrawer({ skillName, persona, onClose, onConfigured }: SkillDrawerProps) {
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loadErr, setLoadErr] = useState('');

  // API 配置输入（env -> 明文，只提交非空项）
  const [envInputs, setEnvInputs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  // 执行区
  const [input, setInput] = useState('');
  const [result, setResult] = useState('');
  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState('');
  const reqSeq = useRef(0);

  const loadDetail = () => {
    let ignore = false;
    fetchSkillDetail(skillName)
      .then((d) => { if (!ignore) { setDetail(d); setLoadErr(''); } })
      .catch(() => { if (!ignore) setLoadErr('加载 SKILL 详情失败'); });
    return () => { ignore = true; };
  };

  useEffect(loadDetail, [skillName]);

  const bodyHtml = useMemo(() => renderMarkdown(detail?.body || ''), [detail?.body]);
  const resultHtml = useMemo(() => renderMarkdown(result), [result]);

  const handleSaveEnv = async () => {
    const updates = Object.fromEntries(
      Object.entries(envInputs).filter(([, v]) => v.trim() !== '')
    );
    if (Object.keys(updates).length === 0) { setSavedMsg('没有填写新值'); return; }
    setSaving(true);
    setSavedMsg('');
    try {
      await saveEnv(updates);
      setEnvInputs({});
      const seq = ++reqSeq.current;
      const fresh = await fetchSkillDetail(skillName);
      if (seq === reqSeq.current) setDetail(fresh);
      setSavedMsg('已保存');
      onConfigured();
      setTimeout(() => setSavedMsg(''), 2500);
    } catch (e) {
      setSavedMsg(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (!input.trim()) return;
    const seq = ++reqSeq.current;
    setRunning(true);
    setRunErr('');
    setResult('');
    try {
      const res = await executeSkill(skillName, input.trim(), persona || undefined);
      if (seq === reqSeq.current) setResult(res.response);
    } catch (e) {
      if (seq === reqSeq.current) setRunErr(e instanceof Error ? e.message : '执行失败');
    } finally {
      if (seq === reqSeq.current) setRunning(false);
    }
  };

  const blocked = detail?.needsApi && !detail.apiConfigured;
  const layerKey = detail?.layer && isLayerKey(detail.layer) ? detail.layer : null;

  const renderKeyField = (k: { env: string; secret: boolean; choices: string[]; configured: boolean; masked?: string }) => (
    k.choices.length > 0 ? (
      <SelectMenu
        ariaLabel={k.env}
        value={envInputs[k.env] ?? ''}
        placeholder={k.configured ? `当前：${k.masked}` : `请选择 ${k.env}`}
        options={[
          { value: '', label: k.configured ? '保持当前' : '不设置' },
          ...k.choices.map((choice) => ({ value: choice, label: choice })),
        ]}
        onChange={(v) => setEnvInputs((p) => ({ ...p, [k.env]: v }))}
      />
    ) : (
      <Input
        type={k.secret ? 'password' : 'text'}
        placeholder={k.configured ? '留空则保持不变，输入以覆盖' : `请输入 ${k.env}`}
        value={envInputs[k.env] || ''}
        onChange={(e) => setEnvInputs((p) => ({ ...p, [k.env]: e.target.value }))}
      />
    )
  );

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="skill-detail-head">
            <div>
              <h2 className="skill-detail-title">{displayName(skillName)}</h2>
              <div className="skill-detail-rawname">{skillName}</div>
              <div className="skill-detail-meta">
                {detail?.layer && (layerKey
                  ? <Tag tone={layerKey}>{layerInfo(layerKey).name}</Tag>
                  : <Tag>{detail.layer}</Tag>)}
                {detail?.needsApi && (
                  detail.apiConfigured
                    ? <Tag tone="ok">已配置</Tag>
                    : <Tag tone="warn">需配置 API</Tag>
                )}
              </div>
            </div>
            <button type="button" className="icon-btn" onClick={onClose} title="关闭" aria-label="关闭">×</button>
          </div>
        </div>

        <div className="drawer-body">
          {loadErr && <div className="skill-error">{loadErr}</div>}

          {/* API 配置 */}
          {detail?.needsApi && detail.apiSpec && (
            <Panel title={<>{detail.apiSpec.label} · API 配置<span className="skill-panel-hint">（任选一个服务商填齐即可用）</span></>}>
              {detail.apiSpec.settings.length > 0 && (
                <div className="skill-provider">
                  <div className="skill-provider-head"><strong>默认选择与能力</strong></div>
                  {detail.apiSpec.settings.map((k) => (
                    <div key={k.env}>
                      <label className="field-label">
                        {k.label} · 可选
                        {k.configured && <span className="skill-configured">
                          已配置{k.masked ? `：${k.masked}` : ''}
                        </span>}
                      </label>
                      {renderKeyField(k)}
                    </div>
                  ))}
                </div>
              )}
              {detail.apiSpec.providers.map((prov) => {
                const provOk = prov.keys.filter(k => k.required).every(k => k.configured);
                return (
                  <div key={prov.id} className={`skill-provider${provOk ? ' configured' : ''}`}>
                    <div className="skill-provider-head">
                      <strong>{prov.name}</strong>
                      {provOk ? <Tag tone="ok">就绪</Tag> : <Tag>未配置</Tag>}
                    </div>
                    {prov.keys.map((k) => (
                      <div key={k.env}>
                        <label className="field-label">
                          {k.label}{k.required ? '' : ' · 可选'}
                          {k.configured && <span className="skill-configured">
                            已配置{k.secret && k.masked ? `（${k.masked}）` : k.masked ? `：${k.masked}` : ''}
                          </span>}
                        </label>
                        {renderKeyField(k)}
                      </div>
                    ))}
                  </div>
                );
              })}
              <div className="skill-save-row">
                <Button variant="primary" size="sm" onClick={handleSaveEnv} loading={saving}>
                  {saving ? '保存中…' : '保存到 .env'}
                </Button>
                {savedMsg && <span className={`skill-saved${savedMsg.includes('已保存') ? ' ok' : ''}`}>{savedMsg}</span>}
              </div>
            </Panel>
          )}

          {/* 执行 */}
          <Panel title="运行">
            {blocked && (
              <div className="skill-blocked">该技能需要先配置上面的 API 才能运行。</div>
            )}
            <Textarea
              className="skill-input"
              placeholder="输入内容，例如主题 / 素材 / 要求…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
            <div className="skill-run-row">
              <Button variant="primary" onClick={handleRun} loading={running} disabled={!input.trim() || blocked}>
                {running ? '执行中…' : '执行'}
              </Button>
            </div>
            {runErr && <div className="skill-error">{runErr}</div>}
            {resultHtml && (
              <div className="skill-result" dangerouslySetInnerHTML={{ __html: resultHtml }} />
            )}
          </Panel>

          {/* 描述 */}
          <Panel title="说明">
            {detail
              ? <div className="skill-body-md" dangerouslySetInnerHTML={{ __html: bodyHtml }} />
              : !loadErr && <div className="loading"><div className="spinner" />加载中…</div>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
