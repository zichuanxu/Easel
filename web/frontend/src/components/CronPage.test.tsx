import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchCronJobs: vi.fn(),
  createCronJob: vi.fn(),
  cronAction: vi.fn(() => Promise.resolve({ ok: true })),
  deleteCronJob: vi.fn(() => Promise.resolve({ ok: true })),
  fetchCronRuns: vi.fn(),
}));

import * as api from '../lib/api';
import type { CronJob } from '../lib/api';
import CronPage from './CronPage';

const job = (patch: Partial<CronJob>): CronJob => ({
  id: 'j1', name: '每日热点', description: '由 Easel 网页创建', enabled: true, system: false, readonly: false, kind: 'agentTurn',
  message: '收集今天的 AI 热点', schedule: { kind: 'cron', expr: '0 9 * * *' }, nextRunAtMs: Date.now() + 3600000,
  lastRunAtMs: null, lastRunStatus: '', lastError: '', lastDurationMs: null, runningAtMs: null, createdAtMs: 1,
  ...patch,
});
const SYS = job({ id: 's1', name: 'Heartbeat (main)', system: true, readonly: true, kind: 'heartbeat', message: '', description: '',
  schedule: { kind: 'every', everyMs: 1800000 } });

beforeEach(() => {
  vi.mocked(api.fetchCronJobs).mockReset();
  vi.mocked(api.createCronJob).mockReset();
  vi.mocked(api.cronAction).mockClear();
  vi.mocked(api.deleteCronJob).mockClear();
  vi.mocked(api.fetchCronRuns).mockReset();
});

describe('CronPage', () => {
  it('列出我的任务（中文时间），系统任务折叠且只能看', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({}), SYS], minIntervalMinutes: 10 });
    render(<CronPage />);
    expect(await screen.findByText('每日热点')).toBeTruthy();
    expect(screen.getByText('每天 09:00')).toBeTruthy();
    expect(screen.queryByText('Heartbeat (main)')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /系统和命令行任务/ }));
    expect(await screen.findByText('Heartbeat (main)')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: '暂停' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: '运行记录' })).toHaveLength(2);
  });

  it('暂停调后端并给出提示', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({})], minIntervalMinutes: 10 });
    render(<CronPage />);
    fireEvent.click(await screen.findByRole('button', { name: '暂停' }));
    await waitFor(() => expect(api.cronAction).toHaveBeenCalledWith('j1', 'pause'));
    expect(await screen.findByText('已暂停「每日热点」')).toBeTruthy();
  });

  it('暂停中的任务显示「已暂停」和「恢复」', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({ enabled: false })], minIntervalMinutes: 10 });
    render(<CronPage />);
    expect(await screen.findByText('已暂停')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '恢复' }));
    await waitFor(() => expect(api.cronAction).toHaveBeenCalledWith('j1', 'resume'));
  });

  it('新建：每周一 08:30 → cron 表达式；提到发布时提醒', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [], minIntervalMinutes: 10 });
    vi.mocked(api.createCronJob).mockResolvedValue({ job: job({ name: '周报' }), warning: '' });
    render(<CronPage />);
    fireEvent.click((await screen.findAllByRole('button', { name: '新建任务' }))[0]);
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: '周报' } });
    fireEvent.change(screen.getByLabelText('让 agent 做什么'), { target: { value: '写周报，然后发布到小红书' } });
    expect(screen.getByText(/提到了「发布」/)).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: '每周' }));
    fireEvent.change(screen.getByLabelText('时间'), { target: { value: '08:30' } });
    expect(screen.getByText('每周一 08:30')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '创建' }));
    await waitFor(() => expect(api.createCronJob).toHaveBeenCalledWith({
      name: '周报', message: '写周报，然后发布到小红书', schedule: { mode: 'cron', expr: '30 8 * * 1' },
    }));
  });

  it('后端拒绝时弹窗里显示原因，不关弹窗', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [], minIntervalMinutes: 10 });
    vi.mocked(api.createCronJob).mockRejectedValue(new Error('两次运行间隔不能短于 10 分钟'));
    render(<CronPage />);
    fireEvent.click((await screen.findAllByRole('button', { name: '新建任务' }))[0]);
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('让 agent 做什么'), { target: { value: 'y' } });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));
    expect(await screen.findByText('两次运行间隔不能短于 10 分钟')).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('运行记录：显示结果文字和失败原因', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({})], minIntervalMinutes: 10 });
    vi.mocked(api.fetchCronRuns).mockResolvedValue({ runs: [
      { runAtMs: Date.now(), status: 'ok', durationMs: 2000, summary: '整理好了 3 个选题', error: '', model: '' },
      { runAtMs: Date.now() - 86400000, status: 'error', durationMs: 500, summary: '', error: 'model timeout', model: '' },
    ] });
    render(<CronPage />);
    fireEvent.click(await screen.findByRole('button', { name: '运行记录' }));
    expect(await screen.findByText('整理好了 3 个选题')).toBeTruthy();
    expect(screen.getByText('model timeout')).toBeTruthy();
    expect(api.fetchCronRuns).toHaveBeenCalledWith('j1');
  });

  it('连不上 gateway 时给出原因和重试', async () => {
    vi.mocked(api.fetchCronJobs).mockRejectedValue(new Error('连不上 gateway，定时任务要靠它运行。'));
    render(<CronPage />);
    expect(await screen.findByText(/连不上 gateway/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
  });

  it('命令行建的命令任务也只能看，没有立即运行', async () => {
    const cmd = job({ id: 'c1', name: '备份脚本', kind: 'command', readonly: true, message: '', description: 'nightly' });
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [cmd], minIntervalMinutes: 10 });
    render(<CronPage />);
    fireEvent.click(await screen.findByRole('button', { name: /系统和命令行任务/ }));
    expect(await screen.findByText('备份脚本')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '立即运行' })).toBeNull();
  });

  it('删除失败：关掉确认框，把原因显示在页面上', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({})], minIntervalMinutes: 10 });
    vi.mocked(api.deleteCronJob).mockRejectedValueOnce(new Error('连不上 gateway'));
    render(<CronPage />);
    fireEvent.click(await screen.findByRole('button', { name: '删除「每日热点」' }));
    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    expect(await screen.findByText(/没能删除「每日热点」：连不上 gateway/)).toBeTruthy();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('删除要先确认', async () => {
    vi.mocked(api.fetchCronJobs).mockResolvedValue({ jobs: [job({})], minIntervalMinutes: 10 });
    render(<CronPage />);
    fireEvent.click(await screen.findByRole('button', { name: '删除「每日热点」' }));
    expect(api.deleteCronJob).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() => expect(api.deleteCronJob).toHaveBeenCalledWith('j1'));
  });
});
