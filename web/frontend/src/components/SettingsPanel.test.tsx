import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchEnvTools: vi.fn(() => Promise.resolve({ tools: [], python: '' })),
  startEnvInstall: vi.fn(), fetchEnvJob: vi.fn(),
  fetchModelChannels: vi.fn(() => Promise.resolve({ channels: { chat: { rows: [] }, transcribe: { rows: [] } }, primary: '' })),
  runChannelSelftest: vi.fn(), saveModelConfig: vi.fn(),
  fetchLocalAgents: vi.fn(() => Promise.resolve({ agents: [], installedCount: 0, usableWithoutKeyCount: 0, usableWithoutKey: [] })),
  enableLocalAgent: vi.fn(() => Promise.resolve({ note: '已接入 Claude Code' })),
  fetchAvailableModels: vi.fn(() => Promise.resolve({ models: [] })),
}));

import * as api from '../lib/api';
import SettingsPanel from './SettingsPanel';

const speechRows = [
  { slot: 'dashscope', order: 0, name: '阿里 CosyVoice', sub: 'voice', type: 'dashscope', model: '', baseUrl: '',
    keyMasked: '', role: '备', result: '未配置' },
  { order: 0, name: 'edge-tts', sub: '微软在线 · 免 key', type: 'edge', model: '晓晓（默认音色）', baseUrl: '—',
    keyMasked: '免 key', role: '主', result: '已就绪' },
];

describe('SettingsPanel 配音通道', () => {
  it('没配云端时显示 edge-tts 可用；把云端设为主后 edge-tts 退为兜底', async () => {
    vi.mocked(api.fetchModelChannels).mockResolvedValueOnce({
      channels: { chat: { rows: [] }, transcribe: { rows: [] }, speech: { rows: speechRows } }, primary: '',
    } as Awaited<ReturnType<typeof api.fetchModelChannels>>);
    render(<SettingsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('tab', { name: '配音' }));
    expect(await screen.findByText('edge-tts 可用（免 Key）')).toBeTruthy();
    const edgeRow = screen.getByText('edge-tts').closest('.prow') as HTMLElement;
    expect(edgeRow.textContent).toContain('主');
    fireEvent.click(screen.getByTitle('设为主通道'));
    expect(edgeRow.textContent).toContain('兜底');
  });
});

const imageRows = [
  { slot: 'openai', order: 0, name: 'OpenAI 兼容 / apimart / 小红书 MaaS', sub: 'image', type: 'openai', model: '',
    baseUrl: '', keyMasked: '', role: '主', result: '未配置' },
  { slot: 'codex-cli', order: 0, name: 'Codex CLI（ChatGPT 登录）', sub: 'image', type: 'codex-cli', model: '',
    baseUrl: '本机', keyMasked: '免 key', role: '备', result: '已配置', keyless: true, modelHint: 'gpt-6.1-sol（默认）' },
];

describe('SettingsPanel 生图通道', () => {
  it('Codex 行免 Key、显示默认模型；设为主后状态显示 Codex 生效', async () => {
    vi.mocked(api.fetchModelChannels).mockResolvedValueOnce({
      channels: { chat: { rows: [] }, transcribe: { rows: [] }, image: { rows: imageRows } }, primary: '',
    } as Awaited<ReturnType<typeof api.fetchModelChannels>>);
    render(<SettingsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('tab', { name: '生图' }));
    const codexRow = (await screen.findByText('Codex CLI（ChatGPT 登录）')).closest('.prow') as HTMLElement;
    expect(codexRow.querySelector('input[type="password"]')).toBeNull();
    expect(codexRow.textContent).toContain('免 key');
    expect(codexRow.textContent).toContain('gpt-6.1-sol（默认）');
    const top = () => document.querySelector('.st-panel.active .panel-top')?.textContent || '';
    expect(top()).toContain('未配置');      // 主仍是没填 Key 的 API
    fireEvent.click(codexRow.querySelector('.role-btn') as HTMLElement);
    expect(top()).toContain('Codex CLI（ChatGPT 登录） 生效');
  });
});

describe('SettingsPanel', () => {
  it('是对话框，六个模型通道是标签页，Esc 关闭', async () => {
    const onClose = vi.fn();
    render(<SettingsPanel onClose={onClose} />);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(await screen.findAllByRole('tab')).toHaveLength(6);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

const claudeAgent = {
  id: 'claude-code', label: 'Claude Code', installed: true, command: 'claude', path: '/usr/local/bin/claude',
  openclawProvider: 'claude-cli', supported: true, configured: false, usableWithoutKey: true,
  loginHint: '已用 Claude Code 登录即可', models: [{ id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6' }],
};

describe('SettingsPanel 对话通道（上游合并：本机 Agent、拉取模型）', () => {
  it('装了 Claude Code：显示本机 Agent 区块，一键接入后标成已接入', async () => {
    vi.mocked(api.fetchLocalAgents).mockResolvedValueOnce({
      agents: [claudeAgent], installedCount: 1, usableWithoutKeyCount: 1, usableWithoutKey: ['claude-code'],
    } as Awaited<ReturnType<typeof api.fetchLocalAgents>>);
    render(<SettingsPanel onClose={() => {}} />);
    expect(await screen.findByText('本机 Agent')).toBeTruthy();
    expect(screen.getByText('检测到可免 API Key 使用：Claude Code')).toBeTruthy();
    expect(screen.getByLabelText('Claude Code 使用的模型')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '一键接入' }));
    expect(await screen.findByText('已接入 Claude Code')).toBeTruthy();
    expect(vi.mocked(api.enableLocalAgent).mock.calls[0]).toEqual(['claude-code', '']);
    expect(document.querySelector('.la-row')?.textContent).toContain('已接入');
  });

  it('可改模型的行有「拉取」按钮，拉到的模型名进输入框的补全列表', async () => {
    vi.mocked(api.fetchModelChannels).mockResolvedValueOnce({
      channels: { chat: { rows: [{ slot: 'openai', order: 0, name: 'OpenAI 兼容', sub: 'chat', type: 'openai',
        model: 'gpt-4o', baseUrl: 'https://api.example.com/v1', keyMasked: 'sk-***', role: '主', result: '已配置' }] },
      transcribe: { rows: [] } }, primary: 'openai/gpt-4o',
    } as Awaited<ReturnType<typeof api.fetchModelChannels>>);
    vi.mocked(api.fetchAvailableModels).mockResolvedValueOnce({ models: ['gpt-4o', 'gpt-4.1'] } as Awaited<ReturnType<typeof api.fetchAvailableModels>>);
    render(<SettingsPanel onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '拉取' }));
    await screen.findByRole('button', { name: '拉取' });
    const options = [...document.querySelectorAll('datalist option')].map((o) => (o as HTMLOptionElement).value);
    expect(options).toEqual(['gpt-4o', 'gpt-4.1']);
    expect(vi.mocked(api.fetchAvailableModels).mock.calls[0].slice(0, 3)).toEqual(['https://api.example.com/v1', '', 'openai']);
  });
});

