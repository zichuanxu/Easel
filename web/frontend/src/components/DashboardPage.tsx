import { useState, useEffect } from 'react';
import { fetchTrends, fetchSchedule, fetchOutputs, fetchAccounts, fetchIdeas } from '../lib/api';
import type { TrendGroup, ScheduleItem, OutputNode, AccountItem, Idea } from '../lib/api';
import { layerInfo } from '../lib/layers';
import type { LayerKey, Page } from '../lib/layers';
import { useAnalyticsPlatforms } from '../lib/useAnalyticsPlatforms';
import Button from './ui/Button';
import Panel from './ui/Panel';
import EmptyState from './ui/EmptyState';
import Tag from './ui/Tag';

interface DashboardProps {
  persona: string;
  gatewayStatus: string;
  onNavigate: (page: Page) => void;
  onUseTopic: (title: string) => void;
}

const STATUS_LABEL: Record<string, string> = { idea: '选题', draft: '草稿', scheduled: '待发', published: '已发' };
const WEEK = ['日', '一', '二', '三', '四', '五', '六'];

interface Stage { layer: LayerKey; num: string; label: string; link: { label: string; page: Page } }

export default function DashboardPage({ persona, gatewayStatus, onNavigate, onUseTopic }: DashboardProps) {
  const [trends, setTrends] = useState<TrendGroup[]>([]);
  const [trendsFailed, setTrendsFailed] = useState(false);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [outputs, setOutputs] = useState<OutputNode[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const { logged: anaLogged } = useAnalyticsPlatforms();

  useEffect(() => {
    fetchTrends('weibo,douyin', 6).then((d) => setTrends(d.trends)).catch(() => setTrendsFailed(true));
    fetchSchedule().then(setSchedule).catch(() => {});
    fetchOutputs().then(setOutputs).catch(() => {});
    fetchAccounts().then(setAccounts).catch(() => {});
    fetchIdeas().then(setIdeas).catch(() => {});
  }, []);

  const now = new Date();
  const hour = now.getHours();
  const greet = hour < 6 ? '夜深了' : hour < 12 ? '上午好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
  const dateLine = `${now.getMonth() + 1}月${now.getDate()}日 周${WEEK[now.getDay()]}`;
  const todayStr = now.toISOString().slice(0, 10);
  const upcoming = [...schedule]
    .filter((s) => s.date >= todayStr && s.status !== 'published')
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time)).slice(0, 5);
  const recent = outputs.slice(0, 5);
  const pendingIdeas = ideas.filter((i) => i.status === 'pending');
  const loggedIn = accounts.filter((a) => a.loggedIn).length;
  const trendCount = trends.reduce((n, g) => n + g.items.length, 0);

  const stages: Stage[] = [
    { layer: 'discover', num: String(trendCount), label: '条今日热点', link: { label: '热点雷达', page: 'trends' } },
    { layer: 'plan', num: String(pendingIdeas.length), label: '个待做选题', link: { label: '选题库', page: 'ideas' } },
    { layer: 'produce', num: String(outputs.length), label: '个内容项目', link: { label: '内容库', page: 'outputs' } },
    { layer: 'publish', num: accounts.length ? `${loggedIn}/${accounts.length}` : '—', label: '个账号已登录', link: { label: '账号', page: 'accounts' } },
    { layer: 'attribute', num: anaLogged.length ? String(anaLogged.length) : '—', label: anaLogged.length ? '个平台可看数据' : '暂无可看数据的平台', link: { label: '创作数据', page: 'analytics' } },
  ];

  return (
    <div className="page-scroll dash-page">
      <header className="dash-head">
        <div>
          <h1 className="dash-greet">{greet}</h1>
          <p className="dash-date">
            {dateLine}。{persona ? `当前画像：${persona}。` : '通用模式，选一个画像生成的内容会更贴合你。'}
            {gatewayStatus !== 'connected' && <Tag tone="danger">网关未连接，对话暂不可用</Tag>}
          </p>
        </div>
        <div className="dash-actions">
          <Button onClick={() => onNavigate('breakdown')}>拆一条爆款</Button>
          <Button variant="primary" onClick={() => onNavigate('chat')}>开始对话</Button>
        </div>
      </header>

      <section className="pipe" aria-label="内容流水线">
        {stages.map((s) => (
          <div key={s.layer} className="pipe-stage" data-stage={s.layer}>
            <span className="pipe-band" aria-hidden="true" />
            <span className="pipe-stage-name">{layerInfo(s.layer).name}</span>
            <span className="pipe-stage-num">{s.num}</span>
            <span className="pipe-stage-label">{s.label}</span>
            <button type="button" className="pipe-stage-link" onClick={() => onNavigate(s.link.page)}>{s.link.label}</button>
          </div>
        ))}
      </section>

      <div className="dash-cols">
        <Panel title="今日热点" action={{ label: '热点雷达', onClick: () => onNavigate('trends') }}>
          {trends.length === 0 && (
            <EmptyState text={trendsFailed
              ? '热点暂时拉不到。检查网络，或在设置里配置代理后刷新。'
              : '正在拉取微博和抖音的热搜…'} />
          )}
          {trends.map((g) => (
            <div key={g.platform} className="hot-group">
              <div className="hot-plat">{g.label}</div>
              {g.items.slice(0, 5).map((it, i) => (
                <button key={i} type="button" className="hot-row" title={`${it.title}（点击做成内容）`} onClick={() => onUseTopic(it.title)}>
                  <span className="hot-rank">{i + 1}</span>
                  <span className="hot-title">{it.title}</span>
                  <span className="hot-act">做选题</span>
                </button>
              ))}
            </div>
          ))}
        </Panel>

        <div className="dash-stack">
          <Panel title="选题 · 待做" action={{ label: '选题库', onClick: () => onNavigate('ideas') }}>
            {pendingIdeas.length === 0
              ? <EmptyState text="还没有待做的选题。在热点雷达里收藏几个，会出现在这里。" />
              : pendingIdeas.slice(0, 5).map((it) => (
                <button key={it.id} type="button" className="dash-row" title="点击做成内容" onClick={() => onUseTopic(it.title)}>
                  <span className="dash-row-title">{it.title}</span>
                  {it.source && <Tag>{it.source}</Tag>}
                </button>
              ))}
          </Panel>
          <Panel title="近期排期" action={{ label: '内容日历', onClick: () => onNavigate('calendar') }}>
            {upcoming.length === 0
              ? <EmptyState text="还没有排期。从选题库挑一条排进日历。" action={{ label: '去排期', onClick: () => onNavigate('calendar') }} />
              : upcoming.map((s) => (
                <button key={s.id} type="button" className="dash-row" onClick={() => onNavigate('calendar')}>
                  <span className="dash-row-date">{s.date.slice(5)}</span>
                  <span className="dash-row-title">{s.platform ? `[${s.platform}] ` : ''}{s.title}</span>
                  <Tag>{STATUS_LABEL[s.status] || s.status}</Tag>
                </button>
              ))}
          </Panel>
          <Panel title="最近产物" action={{ label: '内容库', onClick: () => onNavigate('outputs') }}>
            {recent.length === 0
              ? <EmptyState text="还没有产物。在对话里让 Easel 写一篇，成品会出现在这里。" />
              : recent.map((g) => (
                <button key={g.name} type="button" className="dash-row" onClick={() => onNavigate('outputs')}>
                  <span className="dash-row-title">{g.meta?.title || g.name}</span>
                  <Tag>{g.meta?.platform || (g.type === 'dir' ? `${g.fileCount ?? 0} 个文件` : '单文件')}</Tag>
                </button>
              ))}
          </Panel>
        </div>
      </div>
    </div>
  );
}
