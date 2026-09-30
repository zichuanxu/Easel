import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchAccountAnalytics, fetchCachedAnalytics } from './api';
import type { AccountAnalytics } from './api';

/** 缓存超过这么久算过期，切到该平台/打开页面时在后台刷新。 */
export const ANALYTICS_TTL_MS = 30 * 60 * 1000;
/** 同时最多几个平台在抓取（每个都会起一个浏览器）。 */
const CONCURRENCY = 2;
const STORE_KEY = 'easel_analytics';

export interface AnalyticsEntry {
  data?: AccountAnalytics;
  /** 正在抓取或排队中（有旧数据时旧数据照常显示）。 */
  updating: boolean;
  /** 最近一次抓取失败。 */
  failed: boolean;
}

const EMPTY: AnalyticsEntry = { updating: false, failed: false };

function isFresh(d: AccountAnalytics | undefined, now = Date.now()): boolean {
  // fetched_at 不是有限数字（如公众号出错时的日期字符串）一律按过期处理
  return !!d && Number.isFinite(d.fetched_at) && now - d.fetched_at * 1000 <= ANALYTICS_TTL_MS;
}

/** 只接受对象值：旧版本会把 'loading' / 'error' 字符串一起写进来，直接丢掉。 */
function loadStored(): Record<string, AccountAnalytics> {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    const out: Record<string, AccountAnalytics> = {};
    for (const [k, v] of Object.entries(raw ?? {})) {
      if (v && typeof v === 'object') out[k] = v as AccountAnalytics;
    }
    return out;
  } catch { return {}; }
}

/**
 * 创作数据：先显示缓存、过期则后台刷新。
 * - ensure(p, priority)：有新鲜缓存不动；过期则后台抓，旧数据保留；本地没有则先读后端落盘结果，仍没有才真抓。
 * - refresh(p)：强制抓取，期间保留旧数据。
 * - 同平台已在抓取时不重复发请求；最多 2 个平台同时抓，priority（当前选中的平台）插队首。
 */
export function useAnalyticsData() {
  const store = useRef<Record<string, AnalyticsEntry>>({});
  const [entries, setEntries] = useState<Record<string, AnalyticsEntry>>(() => {
    const init: Record<string, AnalyticsEntry> = {};
    for (const [k, data] of Object.entries(loadStored())) init[k] = { data, updating: false, failed: false };
    store.current = init;
    return init;
  });
  const inflight = useRef(new Set<string>());   // 排队中 + 抓取中 + 读落盘缓存中
  const queue = useRef<string[]>([]);           // 等待抓取的平台，队首先跑
  const running = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const patch = useCallback((p: string, part: Partial<AnalyticsEntry>) => {
    store.current = { ...store.current, [p]: { ...(store.current[p] ?? EMPTY), ...part } };
    if (alive.current) setEntries(store.current);
  }, []);

  const persist = useCallback(() => {
    const out: Record<string, AccountAnalytics> = {};
    for (const [k, e] of Object.entries(store.current)) if (e.data) out[k] = e.data;
    try { localStorage.setItem(STORE_KEY, JSON.stringify(out)); } catch { /* 配额 / 隐私模式：忽略 */ }
  }, []);

  const pump = useCallback(() => {
    while (running.current < CONCURRENCY && queue.current.length) {
      const p = queue.current.shift()!;
      running.current++;
      fetchAccountAnalytics(p)
        .then((r) => {
          patch(p, { data: r, updating: false, failed: false });
          persist();
        })
        .catch(() => patch(p, { updating: false, failed: true }))
        .finally(() => {
          running.current--;
          inflight.current.delete(p);
          pump();
        });
    }
  }, [patch, persist]);

  /** 排进抓取队列；已在队列里的只调整位置。 */
  const schedule = useCallback((p: string, priority: boolean) => {
    inflight.current.add(p);
    patch(p, { updating: true, failed: false });
    queue.current = queue.current.filter((x) => x !== p);
    if (priority) queue.current.unshift(p); else queue.current.push(p);
    pump();
  }, [patch, pump]);

  // auto：页面定时器发起的检查。上次抓取失败的平台不再自动重抓——否则失效账号或改版平台
  // 会每分钟起一次 headless 浏览器；留给「重试」按钮、切页签或下次打开页面。
  const ensure = useCallback((p: string, priority = false, auto = false) => {
    if (auto && store.current[p]?.failed) return;
    if (inflight.current.has(p)) {
      // 还在排队（没开跑）的，被选中时提到队首
      if (priority && queue.current.includes(p)) {
        queue.current = [p, ...queue.current.filter((x) => x !== p)];
      }
      return;
    }
    const cur = store.current[p]?.data;
    if (isFresh(cur)) return;
    if (cur) { schedule(p, priority); return; }
    // 本地没有：先读后端落盘结果（毫秒级），比起浏览器抓取快得多
    inflight.current.add(p);
    patch(p, { updating: true, failed: false });
    fetchCachedAnalytics(p)
      .catch(() => null)
      .then((r) => {
        if (!alive.current) { inflight.current.delete(p); return; }   // 已卸载：不再起抓取
        if (r) {
          patch(p, { data: r });
          persist();
          if (isFresh(r)) {
            patch(p, { updating: false });
            inflight.current.delete(p);
            return;
          }
        }
        schedule(p, priority);
      });
  }, [patch, persist, schedule]);

  const refresh = useCallback((p: string) => {
    if (inflight.current.has(p)) {
      if (queue.current.includes(p)) queue.current = [p, ...queue.current.filter((x) => x !== p)];
      return;
    }
    schedule(p, true);
  }, [schedule]);

  return { entries, entry: (p: string): AnalyticsEntry => entries[p] ?? EMPTY, ensure, refresh };
}
