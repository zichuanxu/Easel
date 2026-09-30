import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({ fetchSkills: vi.fn() }));
vi.mock('./SkillDrawer', () => ({ default: ({ skillName }: { skillName: string }) => <div role="dialog">{skillName}</div> }));

import * as api from '../lib/api';
import SkillPage from './SkillPage';

const SKILLS = [
  { name: 'skill-trending-topics', description: '抓取实时热搜', layer: 'discover', needsApi: false, apiConfigured: false },
  { name: 'skill-news-intelligence', description: '行业情报', layer: 'discover', needsApi: true, apiConfigured: false },
  { name: 'copywriting', description: '营销文案', layer: 'produce', needsApi: false, apiConfigured: false },
  { name: 'ai-video-gen', description: '生成视频', layer: 'produce', needsApi: true, apiConfigured: true },
];

describe('SkillPage', () => {
  it('左侧索引显示各层真实数量，层名用「生产」不用「制作」', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    const { container } = render(<SkillPage persona="" />);
    await screen.findAllByText('营销 / 带货文案');
    const idx = [...container.querySelectorAll('.skill-index-item')].map((n) => n.textContent);
    expect(idx).toEqual(['发现2', '生产2']);
    expect(container.textContent).not.toContain('制作');
  });

  it('只有「需要 key 且未配置」的技能挂「需 key」，不显示英文代号', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    const { container } = render(<SkillPage persona="" />);
    await screen.findAllByText('营销 / 带货文案');
    expect(screen.getAllByText('需 key').length).toBe(1);
    expect(container.textContent).not.toContain('skill-news-intelligence');
  });

  it('点技能打开详情抽屉', async () => {
    vi.mocked(api.fetchSkills).mockResolvedValue(SKILLS);
    render(<SkillPage persona="" />);
    fireEvent.click(await screen.findByText('营销 / 带货文案'));
    expect(screen.getByRole('dialog').textContent).toBe('copywriting');
  });

  it('加载失败时给出提示和重试', async () => {
    vi.mocked(api.fetchSkills).mockRejectedValue(new Error('x'));
    render(<SkillPage persona="" />);
    expect(await screen.findByText(/技能列表加载失败/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();
  });
});
