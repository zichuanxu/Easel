import { describe, it, expect } from 'vitest';
import {
  OVERSEAS_PLATFORMS, OVERSEAS_MEDIA_REQUIRED, OVERSEAS_VIDEO_ONLY, VISIBILITY_OPTIONS,
  isOverseas, overseasPayload, overseasAdaptRule,
} from './overseasPublish';

describe('overseasPublish', () => {
  it('五个海外平台，限额与后端一致', () => {
    expect(OVERSEAS_PLATFORMS.map((p) => p.key)).toEqual(['tiktok', 'youtube', 'instagram', 'x', 'threads']);
    const yt = OVERSEAS_PLATFORMS.find((p) => p.key === 'youtube')!;
    expect(yt.titleLimit).toBe(100);
    expect(OVERSEAS_PLATFORMS.find((p) => p.key === 'x')!.bodyLimit).toBe(280);
    expect(isOverseas('x')).toBe(true);
    expect(isOverseas('douyin')).toBe(false);
  });

  it('媒体要求与后端一致：X / Threads 可纯文字，只有 YouTube 只收视频', () => {
    expect(OVERSEAS_MEDIA_REQUIRED).toEqual(['tiktok', 'youtube', 'instagram']);
    expect(OVERSEAS_VIDEO_ONLY).toEqual(['youtube']);
    expect(OVERSEAS_PLATFORMS.find((p) => p.key === 'x')!.hint).toContain('纯文字');
    expect(OVERSEAS_PLATFORMS.find((p) => p.key === 'instagram')!.hint).toContain('≤10 张图');
  });

  it('非 YouTube 平台：整段卡片文字作正文，标题和母版标签留空（Review Focus 3）', () => {
    expect(overseasPayload('tiktok', 'Hello world #ai')).toEqual({ title: '', body: 'Hello world #ai', tags: '' });
  });

  it('YouTube：第一行作标题，其余作描述', () => {
    expect(overseasPayload('youtube', 'My Short\n\nAbout this video #ai')).toEqual(
      { title: 'My Short', body: 'About this video #ai', tags: '' });
    expect(overseasPayload('youtube', 'Only title')).toEqual({ title: 'Only title', body: '', tags: '' });
  });

  it('可见范围选项只给 YouTube 和 TikTok', () => {
    expect(Object.keys(VISIBILITY_OPTIONS).sort()).toEqual(['tiktok', 'youtube']);
    expect(VISIBILITY_OPTIONS.tiktok.map((o) => o.value)).toEqual(['everyone', 'friends', 'only_me']);
  });

  it('适配提示：选了海外平台才要求英文', () => {
    expect(overseasAdaptRule(['xiaohongshu'])).toBe('');
    const rule = overseasAdaptRule(['xiaohongshu', 'x', 'youtube']);
    expect(rule).toContain('YouTube、X');
    expect(rule).toContain('英文');
    expect(rule).toContain('第一行');
  });
});
