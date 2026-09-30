import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchEnvTools: vi.fn(() => Promise.resolve({ tools: [], python: '' })),
  startEnvInstall: vi.fn(), fetchEnvJob: vi.fn(),
  fetchModelChannels: vi.fn(() => Promise.resolve({ channels: { chat: { rows: [] }, transcribe: { rows: [] } }, primary: '' })),
  runChannelSelftest: vi.fn(), saveModelConfig: vi.fn(),
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
