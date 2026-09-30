import { useState } from 'react';
import { fetchAccountAnalytics } from '../lib/api';
import type { AccountAnalytics } from '../lib/api';
import type { Page } from '../lib/layers';
import { useAnalyticsPlatforms } from '../lib/useAnalyticsPlatforms';
import PageHeader from './ui/PageHeader';
import Panel from './ui/Panel';
import EmptyState from './ui/EmptyState';
import Tabs from './ui/Tabs';
import Button from './ui/Button';

/** 大数格式化：12000 → 1.2万。 */
function fmtNum(n: number | null): string {
  if (n == null) return '—';
  const a = Math.abs(n);
  if (a >= 10000) return (n / 10000).toFixed(a >= 100000 ? 0 : 1) + '万';
  return String(n);
}
/** 增长量渲染信息：正=石绿↑，负=深朱砂↓，0/缺失=不显示。 */
function growthInfo(n: number | null): { text: string; color: string } | null {
  if (n == null || n === 0) return null;
  return n > 0
    ? { text: `▲+${fmtNum(n)}`, color: 'var(--c-ok)' }
    : { text: `▼${fmtNum(Math.abs(n))}`, color: 'var(--c-danger)' };
}

type Win = 'last' | 'day' | 'week' | 'month' | 'year';
const WIN: { key: Win; label: string }[] = [
  { key: 'last', label: '较上次' }, { key: 'day', label: '较昨日' }, { key: 'week', label: '较上周' },
  { key: 'month', label: '较上月' }, { key: 'year', label: '较去年' },
];

export default function AnalyticsPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const [anaSel, setAnaSel] = useState('');
  const [anaData, setAnaData] = useState<Record<string, AccountAnalytics | 'loading' | 'error'>>(() => {
    try { return JSON.parse(localStorage.getItem('easel_analytics') || '{}'); } catch { return {}; }
  });
  const [anaWin, setAnaWin] = useState<Win>('week');
  const { plats, logged } = useAnalyticsPlatforms((p) => setAnaSel((s) => s || p));

  const runAna = (platform: string) => {
    setAnaSel(platform);
    setAnaData((d) => ({ ...d, [platform]: 'loading' }));
    fetchAccountAnalytics(platform)
      .then((r) => setAnaData((d) => {
        const next = { ...d, [platform]: r };
        try { localStorage.setItem('easel_analytics', JSON.stringify(next)); } catch { /* quota */ }
        return next;
      }))
      .catch(() => setAnaData((d) => ({ ...d, [platform]: 'error' as const })));
  };

  const d = anaSel ? anaData[anaSel] : undefined;

  return (
    <div className="page-scroll analytics-page">
      <PageHeader
        layer="attribute"
        title="创作数据"
        description="各平台已登录账号的粉丝、获赞、关注，增长趋势和最新作品。"
        actions={anaSel && d && d !== 'loading'
          ? <Button size="sm" onClick={() => runAna(anaSel)}>刷新数据</Button>
          : undefined}
      />
      {plats.length === 0 ? (
        <EmptyState text="正在加载平台列表。如果一直没有内容，检查网络或代理设置。" />
      ) : logged.length === 0 ? (
        <EmptyState
          text="还没有能拉取数据的账号。先去账号页扫码登录，这里就能看到各平台的粉丝、获赞和最新作品。"
          action={{ label: '去账号页', onClick: () => onNavigate('accounts') }}
        />
      ) : (
        <>
          <Tabs
            ariaLabel="平台"
            items={logged.map((p) => ({ key: p.platform, label: p.name }))}
            value={anaSel}
            onChange={runAna}
          />
          <div className="analytics-body">
            {!d && <EmptyState text="点上方的平台，拉取这个账号的数据。" />}
            {d === 'loading' && (
              <div className="loading"><div className="spinner" />正在拉取数据，需要启动浏览器，约数秒…</div>
            )}
            {d === 'error' && (
              <EmptyState text="拉取失败：可能是登录失效，或平台页面改版了。点上方平台重试。" />
            )}
            {d && d !== 'loading' && d !== 'error' && (!d.loggedIn ? (
              <EmptyState
                text="该平台登录态已失效，去账号页重新登录后再来看。"
                action={{ label: '去账号页', onClick: () => onNavigate('accounts') }}
              />
            ) : (
              <>
                <div className="ana-col ana-col-main">
                  <Panel title="概览">
                    <div className="ana-id">{d.nickname ? `@${d.nickname}` : d.name}</div>
                    <div className="ana-overview">
                      {([['粉丝', 'followers'], ['获赞', 'likes'], ['关注', 'following']] as const).map(([label, key]) => {
                        const w = d.growth?.[anaWin] ?? null;
                        const g = w ? growthInfo(w[key as 'followers' | 'likes']) : null;
                        return (
                          <div key={key} className="ana-stat">
                            <div className="ana-stat-val">{fmtNum(d[key])}</div>
                            <div className="ana-stat-label">{label}</div>
                            {g ? <div className="ana-stat-delta" style={{ color: g.color }}>{g.text}</div>
                               : <div className="ana-stat-delta ana-muted">—</div>}
                          </div>
                        );
                      })}
                    </div>
                    <Tabs size="sm" items={WIN} value={anaWin} onChange={setAnaWin} ariaLabel="对比时段" />
                    <div className="ana-wins-note">
                      {d.growth?.[anaWin]?.since_days != null
                        ? `对比 ${d.growth[anaWin]!.since_days} 天前的快照`
                        : '暂无该时段历史快照，多刷新几次即可积累对比'}
                    </div>
                  </Panel>
                </div>

                <div className="ana-col ana-col-metrics">
                  <Panel title="近 7 日环比">
                    {(d.metrics ?? []).length === 0 ? (
                      <EmptyState text="该平台未提供近 7 日指标" />
                    ) : (
                      <div className="ana-metrics">
                        {(d.metrics ?? []).map((m) => {
                          const vs = m.vs ?? '';
                          const up = vs.startsWith('+');
                          const has = vs && vs !== '-';
                          return (
                            <div key={m.label} className="ana-metric">
                              <div className="ana-metric-val">{m.value}</div>
                              <div className="ana-metric-label">{m.label}</div>
                              {has && <div className="ana-metric-vs" style={{ color: up ? 'var(--c-ok)' : 'var(--c-danger)' }}>环比{vs}</div>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </Panel>
                </div>

                <div className="ana-col ana-col-notes">
                  <Panel title="最新作品">
                    {(d.notes ?? []).length === 0 ? (
                      <EmptyState text="该账号暂无可读取的已发布作品" />
                    ) : (
                      <div className="ana-notes">
                        {(d.notes ?? []).slice(0, 6).map((n, i) => (
                          <a key={i} className="ana-note" href={n.url} target="_blank" rel="noreferrer" title={n.title}>
                            {n.cover
                              ? <img className="ana-note-cover" src={n.cover} alt="" referrerPolicy="no-referrer" />
                              : <span className="ana-note-cover ana-note-cover-ph" aria-hidden="true" />}
                            <span className="ana-note-main">
                              <span className="ana-note-title">{n.title || '(无标题)'}</span>
                              {n.stat && <span className="ana-note-stat">{n.stat}</span>}
                            </span>
                            <span className="ana-note-go">↗</span>
                          </a>
                        ))}
                      </div>
                    )}
                  </Panel>
                </div>
              </>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
