import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('./api', () => ({
  fetchAccountAnalytics: vi.fn(),
  fetchCachedAnalytics: vi.fn(),
}));

import * as api from './api';
import type { AccountAnalytics } from './api';
import { useAnalyticsData, ANALYTICS_TTL_MS } from './useAnalyticsData';

const NOW = 1_800_000_000_000;
const mk = (platform: string, ageMs: number, followers = 1): AccountAnalytics => ({
  platform, name: platform, nickname: '', loggedIn: true, followers, likes: 0, following: 0, posts: 0,
  metrics: [], notes: [], growth: { last: null, day: null, week: null, month: null, year: null },
  fetched_at: Math.floor((NOW - ageMs) / 1000),
});
const fetchA = vi.mocked(api.fetchAccountAnalytics);
const fetchC = vi.mocked(api.fetchCachedAnalytics);
const seed = (v: unknown) => localStorage.setItem('easel_analytics', JSON.stringify(v));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
  localStorage.clear();
  fetchA.mockReset();
  fetchC.mockReset();
  fetchC.mockResolvedValue(null);
});
afterEach(() => vi.useRealTimers());

describe('useAnalyticsData', () => {
  it('小红书只读缓存：过期也不自动抓，点刷新才抓', async () => {
    seed({ xiaohongshu: mk('xiaohongshu', ANALYTICS_TTL_MS + 60_000, 3) });
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('xiaohongshu', true));
    act(() => result.current.ensure('xiaohongshu', true, true));
    expect(result.current.entry('xiaohongshu').data?.followers).toBe(3);
    expect(result.current.entry('xiaohongshu').updating).toBe(false);
    expect(fetchA).not.toHaveBeenCalled();
    act(() => result.current.refresh('xiaohongshu'));
    expect(fetchA).toHaveBeenCalledTimes(1);
  });

  it('小红书本地没有：只读后端落盘结果，没有也不抓', async () => {
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('xiaohongshu', true));
    await waitFor(() => expect(fetchC).toHaveBeenCalledWith('xiaohongshu'));
    await act(async () => {});
    expect(fetchA).not.toHaveBeenCalled();
    expect(result.current.entry('xiaohongshu').updating).toBe(false);
  });

  it('新鲜缓存：立即有数据，不抓取', () => {
    seed({ douyin: mk('douyin', 60_000) });
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    expect(result.current.entry('douyin').data?.followers).toBe(1);
    expect(result.current.entry('douyin').updating).toBe(false);
    expect(fetchA).not.toHaveBeenCalled();
    expect(fetchC).not.toHaveBeenCalled();
  });

  it('过期缓存：保留旧数据，后台抓一次，完成后替换', async () => {
    seed({ douyin: mk('douyin', ANALYTICS_TTL_MS + 60_000, 1) });
    let resolve!: (v: AccountAnalytics) => void;
    fetchA.mockReturnValue(new Promise((r) => { resolve = r; }));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    expect(result.current.entry('douyin').data?.followers).toBe(1);
    expect(result.current.entry('douyin').updating).toBe(true);
    expect(fetchA).toHaveBeenCalledTimes(1);
    await act(async () => { resolve(mk('douyin', 0, 2)); });
    expect(result.current.entry('douyin').data?.followers).toBe(2);
    expect(result.current.entry('douyin').updating).toBe(false);
  });

  it('本地无缓存：后端落盘结果新鲜则不抓取', async () => {
    fetchC.mockResolvedValue(mk('douyin', 1000, 5));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    await waitFor(() => expect(result.current.entry('douyin').data?.followers).toBe(5));
    expect(result.current.entry('douyin').updating).toBe(false);
    expect(fetchA).not.toHaveBeenCalled();
  });

  it('本地无缓存：落盘结果过期则先显示再后台刷新', async () => {
    fetchC.mockResolvedValue(mk('douyin', ANALYTICS_TTL_MS + 1000, 5));
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    await waitFor(() => expect(fetchA).toHaveBeenCalledTimes(1));
    expect(result.current.entry('douyin').data?.followers).toBe(5);
    expect(result.current.entry('douyin').updating).toBe(true);
  });

  it('本地和后端都没有：真抓取', async () => {
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    await waitFor(() => expect(fetchA).toHaveBeenCalledWith('douyin'));
    expect(result.current.entry('douyin').data).toBeUndefined();
    expect(result.current.entry('douyin').updating).toBe(true);
  });

  it("旧 localStorage 里的 'loading' / 'error' 被忽略并正常抓取", async () => {
    seed({ douyin: 'loading', zhihu: 'error' });
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    expect(result.current.entry('douyin').data).toBeUndefined();
    act(() => { result.current.ensure('douyin', true); result.current.ensure('zhihu'); });
    await waitFor(() => expect(fetchA).toHaveBeenCalledTimes(2));
  });

  it('只把成功结果写进 localStorage', async () => {
    fetchA.mockImplementation((p) => (p === 'douyin' ? Promise.resolve(mk('douyin', 0)) : Promise.reject(new Error('x'))));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => { result.current.ensure('douyin', true); result.current.ensure('zhihu'); });
    await waitFor(() => expect(result.current.entry('zhihu').failed).toBe(true));
    const stored = JSON.parse(localStorage.getItem('easel_analytics') || '{}');
    expect(Object.keys(stored)).toEqual(['douyin']);
    expect(stored.douyin.followers).toBe(1);
  });

  it('去重：A -> B -> A，A 只抓一次', async () => {
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => { result.current.ensure('a', true); result.current.ensure('b', true); result.current.ensure('a', true); });
    await waitFor(() => expect(fetchA).toHaveBeenCalledTimes(2));
    act(() => result.current.refresh('a'));
    expect(fetchA.mock.calls.filter((c) => c[0] === 'a')).toHaveLength(1);
  });

  it('并发上限 2，选中的平台插到队首', async () => {
    const pending: Record<string, (v: AccountAnalytics) => void> = {};
    fetchA.mockImplementation((p) => new Promise((r) => { pending[p] = r; }));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => { ['a', 'b', 'c', 'd'].forEach((p) => result.current.ensure(p)); });
    await waitFor(() => expect(fetchA).toHaveBeenCalledTimes(2));
    act(() => result.current.ensure('d', true));
    await act(async () => { pending.a(mk('a', 0)); });
    await waitFor(() => expect(fetchA).toHaveBeenCalledTimes(3));
    expect(fetchA.mock.calls[2][0]).toBe('d');
  });

  it('失败但有旧数据：保留旧数据并标记 failed', async () => {
    seed({ douyin: mk('douyin', ANALYTICS_TTL_MS + 1000, 7) });
    fetchA.mockRejectedValue(new Error('x'));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    await waitFor(() => expect(result.current.entry('douyin').failed).toBe(true));
    expect(result.current.entry('douyin').data?.followers).toBe(7);
    expect(result.current.entry('douyin').updating).toBe(false);
  });

  it('卸载后不再 setState / 起抓取', async () => {
    let resolve!: (v: AccountAnalytics | null) => void;
    fetchC.mockReturnValue(new Promise((r) => { resolve = r; }));
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    unmount();
    await act(async () => { resolve(null); });
    expect(fetchA).not.toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });

  it('fetched_at 不是数字（如日期字符串）：按过期处理，后台刷新', async () => {
    const bad = { ...mk('douyin', 0, 3), fetched_at: '2026-09-30 12:00:00' as unknown as number };
    seed({ douyin: bad });
    fetchA.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAnalyticsData());
    act(() => result.current.ensure('douyin', true));
    expect(fetchA).toHaveBeenCalledTimes(1);
    expect(result.current.entry('douyin').data?.followers).toBe(3);
  });
});
