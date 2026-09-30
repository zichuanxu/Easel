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
