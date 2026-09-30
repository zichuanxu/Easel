import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchEnvTools: vi.fn(() => Promise.resolve({ tools: [], python: '' })),
  startEnvInstall: vi.fn(), fetchEnvJob: vi.fn(),
  fetchModelChannels: vi.fn(() => Promise.resolve({ channels: { chat: { rows: [] }, transcribe: { rows: [] } }, primary: '' })),
  runChannelSelftest: vi.fn(), saveModelConfig: vi.fn(),
}));

import SettingsPanel from './SettingsPanel';

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
