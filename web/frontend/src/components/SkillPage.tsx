import { useState, useEffect, useMemo, useRef } from 'react';
import { fetchSkills } from '../lib/api';
import type { SkillItem } from '../lib/api';
import SkillDrawer from './SkillDrawer';
import { displayName } from '../lib/skillDisplayNames';
import { LAYERS, isLayerKey } from '../lib/layers';
import type { LayerKey } from '../lib/layers';
import PageHeader from './ui/PageHeader';
import Swatch from './ui/Swatch';
import Tag from './ui/Tag';
import EmptyState from './ui/EmptyState';
import { Input } from './ui/Field';

interface SkillPageProps { persona: string; }

type GroupKey = LayerKey | 'other';

export default function SkillPage({ persona }: SkillPageProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [activeLayer, setActiveLayer] = useState<GroupKey | ''>('');
  const bodyRef = useRef<HTMLDivElement>(null);

  const load = () => {
    setError('');
    fetchSkills().then(setSkills).catch(() => setError('技能列表加载失败'));
  };
  useEffect(load, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter((s) =>
      s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q) || displayName(s.name).toLowerCase().includes(q));
  }, [skills, query]);

  const grouped = useMemo(() => {
    const g: Partial<Record<GroupKey, SkillItem[]>> = {};
    for (const s of filtered) {
      const key: GroupKey = isLayerKey(s.layer) ? s.layer : 'other';
      (g[key] ||= []).push(s);
    }
    return g;
  }, [filtered]);

  const sections: { key: GroupKey; name: string; desc: string }[] = [
    ...LAYERS.map((l) => ({ key: l.key as GroupKey, name: l.name, desc: l.desc })),
    { key: 'other' as GroupKey, name: '其他', desc: '未标注层的技能' },
  ].filter((sec) => grouped[sec.key]?.length);

  const needKeyCount = skills.filter((s) => s.needsApi && !s.apiConfigured).length;

  // 滚动时高亮当前层（jsdom 无 IntersectionObserver，跳过）
  useEffect(() => {
    const root = bodyRef.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver((entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (top) setActiveLayer((top.target as HTMLElement).dataset.layer as GroupKey);
    }, { root, rootMargin: '0px 0px -70% 0px' });
    root.querySelectorAll('section[data-layer]').forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [sections.length]);

  const jump = (key: GroupKey) => {
    setActiveLayer(key);
    document.getElementById(`skill-layer-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const current = activeLayer || sections[0]?.key || '';

  return (
    <div className="skills-page">
      <div className="skills-top">
        <PageHeader
          title="技能库"
          description={`共 ${skills.length} 个技能${needKeyCount ? `，其中 ${needKeyCount} 个要先配 key 才能用` : ''}。点一项看说明，就地运行。`}
        />
      </div>
      <div className="skills-grid">
        <nav className="skill-index" aria-label="按层浏览">
          {sections.map((sec) => (
            <button key={sec.key} type="button"
              className={`skill-index-item${current === sec.key ? ' active' : ''}`}
              onClick={() => jump(sec.key)}>
              <Swatch layer={sec.key === 'other' ? 'general' : sec.key} />
              <span className="skill-index-name">{sec.name}</span>
              <span className="skill-index-count">{grouped[sec.key]?.length ?? 0}</span>
            </button>
          ))}
        </nav>
        <div className="skills-body" ref={bodyRef}>
          <div className="skill-search">
            <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索技能名或说明" aria-label="搜索技能" />
          </div>
          {error && <EmptyState text={`${error}。检查网关是否在运行，然后重试。`} action={{ label: '重试', onClick: load }} />}
          {!error && skills.length > 0 && sections.length === 0 && (
            <EmptyState text={`没有找到和「${query}」相关的技能。换个关键词试试。`} action={{ label: '清除搜索', onClick: () => setQuery('') }} />
          )}
          {sections.map((sec) => (
            <section key={sec.key} id={`skill-layer-${sec.key}`} data-layer={sec.key} className="skill-section">
              <header className="skill-section-head">
                <h2>{sec.name}</h2>
                <span>{sec.desc}</span>
              </header>
              <div className="skill-list">
                {(grouped[sec.key] || []).map((s) => (
                  <button key={s.name} type="button" className="skill-row" onClick={() => setSelected(s.name)}>
                    <span className="skill-row-name">{displayName(s.name)}</span>
                    {s.needsApi && !s.apiConfigured && <Tag tone="warn" title="需要先在详情里配置 API key">需 key</Tag>}
                    <span className="skill-row-desc">{s.description?.trim() || '点开查看说明'}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      {selected && (
        <SkillDrawer
          skillName={selected}
          persona={persona}
          onClose={() => setSelected(null)}
          onConfigured={load}
        />
      )}
    </div>
  );
}
