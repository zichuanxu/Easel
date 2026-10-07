import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent, act } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  createSchedule: vi.fn(), executeSkill: vi.fn(), runAgent: vi.fn(), streamChat: vi.fn(),
  fetchAccounts: vi.fn(() => Promise.resolve([])), publishNow: vi.fn(), publishStatus: vi.fn(),
  submitPublishSms: vi.fn(), fetchOutputs: vi.fn(() => Promise.resolve([])), mediaUrl: (p: string) => p,
}));

import * as api from '../lib/api';
import PublishPage from './PublishPage';

describe('PublishPage 海外平台', () => {
  beforeEach(() => localStorage.clear());

  it('平台分国内、海外两组', () => {
    render(<PublishPage persona="" />);
    const overseas = screen.getByRole('group', { name: '海外平台' });
    expect(within(overseas).getByRole('button', { name: 'TikTok' })).toBeTruthy();
    const domestic = screen.getByRole('group', { name: '国内平台' });
    expect(within(domestic).getByRole('button', { name: '小红书' })).toBeTruthy();
  });

  it('选了 TikTok：卡片里有可见范围选择', () => {
    render(<PublishPage persona="" />);
    fireEvent.click(screen.getByRole('button', { name: 'TikTok' }));
    const select = screen.getByRole('combobox', { name: 'TikTok 可见范围' }) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['', 'everyone', 'friends', 'only_me']);
  });
});

// 国内浏览器平台半自动发布：异步轮询 awaiting_user_click → 终态；重复可确认重发，冷却不可绕过
describe('PublishPage 半自动发布', () => {
  const mocked = api as unknown as {
    fetchAccounts: ReturnType<typeof vi.fn>; publishNow: ReturnType<typeof vi.fn>;
    publishStatus: ReturnType<typeof vi.fn>; runAgent: ReturnType<typeof vi.fn>;
  };

  async function startPublish() {
    mocked.fetchAccounts.mockResolvedValue([{ platform: 'zhihu', name: '知乎', backend: 'web', supported: true, loggedIn: true }]);
    mocked.runAgent.mockResolvedValue({ response: '未见明显风险' });
    render(<PublishPage persona="" />);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole('button', { name: '知乎' }));
    fireEvent.change(screen.getByPlaceholderText(/写下你的内容/), { target: { value: '正文内容' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '一键发布' })); });
    await act(async () => { await Promise.resolve(); });
  }

  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('awaiting_user_click 时醒目提示并继续轮询，直到 success', async () => {
    mocked.publishNow.mockResolvedValue({ async: true, pending: true, message: '发布已启动' });
    mocked.publishStatus
      .mockResolvedValueOnce({ mode: 'publish', state: 'awaiting_user_click', message: '已在窗口里填好，请检查后亲自点击『发布』' })
      .mockResolvedValue({ mode: 'publish', state: 'success', message: '检测到已发布。' });
    await startPublish();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText('请在弹出的浏览器窗口里点击『发布』')).toBeTruthy();
    expect(screen.getByText(/已在窗口里填好/)).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText('已发布')).toBeTruthy();
  });

  it('verifying（已检测到发布，正在核对）是非终态：显示消息、不弹短信窗、继续轮询到 success', async () => {
    mocked.publishNow.mockResolvedValue({ async: true, pending: true, message: '发布已启动' });
    mocked.publishStatus
      .mockResolvedValueOnce({ mode: 'publish', state: 'verifying', message: '已检测到发布，正在核对…' })
      .mockResolvedValue({ mode: 'publish', state: 'success', message: '发布成功' });
    await startPublish();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText(/已检测到发布，正在核对/)).toBeTruthy();
    expect(screen.queryByText('提交验证码')).toBeNull();
    expect(screen.queryByText('已发布')).toBeNull();   // 还没到终态，不能显示成功
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText('已发布')).toBeTruthy();
  });

  it('verifying 后脚本写 error：显示失败而非成功', async () => {
    mocked.publishNow.mockResolvedValue({ async: true, pending: true, message: '' });
    mocked.publishStatus
      .mockResolvedValueOnce({ mode: 'publish', state: 'verifying', message: '已检测到发布，正在核对…' })
      .mockResolvedValue({ mode: 'publish', state: 'error', message: '发布未确认：读回未见本次内容' });
    await startPublish();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText(/发布未确认/)).toBeTruthy();
    expect(screen.queryByText('已发布')).toBeNull();
  });

  it('重复被拦：确认后带 allowRepost 重发', async () => {
    mocked.publishNow.mockResolvedValue({ async: true, pending: true, message: '' });
    mocked.publishStatus
      .mockResolvedValueOnce({ mode: 'publish', state: 'duplicate', message: '检测到重复发布：知乎 已发过' })
      .mockResolvedValue({ mode: 'publish', state: 'success', message: '' });
    await startPublish();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(window.confirm).toHaveBeenLastCalledWith(expect.stringContaining('仍要重发同一内容？'));
    expect(mocked.publishNow).toHaveBeenCalledTimes(2);
    expect(mocked.publishNow.mock.calls[0][1].allowRepost).toBe(false);
    expect(mocked.publishNow.mock.calls[1][1].allowRepost).toBe(true);
  });

  it('平台冷却：只显示说明，不再询问重发', async () => {
    mocked.publishNow.mockResolvedValue({ async: true, pending: true, message: '' });
    mocked.publishStatus.mockResolvedValue({ mode: 'publish', state: 'cooldown', message: '知乎 当前处于冷却期，已停止发布。' });
    await startPublish();
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(screen.getByText(/当前处于冷却期/)).toBeTruthy();
    expect(mocked.publishNow).toHaveBeenCalledTimes(1);
    expect(window.confirm).toHaveBeenCalledTimes(1);   // 只有发布前那次确认
  });
});
