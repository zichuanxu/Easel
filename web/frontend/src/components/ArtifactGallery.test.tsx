import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../lib/api', () => ({
  fetchArtifactArchive: vi.fn(() => Promise.resolve({ paths: [] })),
  mediaUrl: (p: string) => `/api/media/${p}`,
}));

import ArtifactGallery from './ArtifactGallery';
import type { Artifact } from '../lib/artifacts';

const img = (name: string): Artifact => ({ url: `/api/media/p/${name}`, name, kind: 'image' });

describe('ArtifactGallery', () => {
  it('单个产物：没有翻页箭头，页脚给出打开和下载', () => {
    render(<ArtifactGallery artifacts={[img('a.png')]} />);
    expect(screen.queryByRole('button', { name: '下一个产物' })).toBeNull();
    expect(screen.getByText('1 / 1')).toBeTruthy();
    expect(screen.getByRole('link', { name: /打开/ }).getAttribute('href')).toBe('/api/media/p/a.png');
    expect(screen.getByRole('link', { name: '下载' }).getAttribute('download')).toBe('a.png');
  });

  it('多个产物：箭头循环翻页，页脚跟着显示当前文件名', () => {
    render(<ArtifactGallery artifacts={[img('a.png'), img('b.png')]} />);
    expect(screen.getByText('1 / 2')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '下一个产物' }));
    expect(screen.getByText('2 / 2')).toBeTruthy();
    expect(document.querySelector('.artifact-name')?.textContent).toBe('b.png');
    fireEvent.click(screen.getByRole('button', { name: '下一个产物' }));
    expect(screen.getByText('1 / 2')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '上一个产物' }));
    expect(screen.getByText('2 / 2')).toBeTruthy();
  });

  it('画廊获得焦点后左右方向键翻页', () => {
    const { container } = render(<ArtifactGallery artifacts={[img('a.png'), img('b.png')]} />);
    const gallery = container.querySelector('.artifact-gallery') as HTMLElement;
    fireEvent.keyDown(gallery, { key: 'ArrowRight' });
    expect(screen.getByText('2 / 2')).toBeTruthy();
    fireEvent.keyDown(gallery, { key: 'ArrowLeft' });
    expect(screen.getByText('1 / 2')).toBeTruthy();
  });

  it('没有产物时什么都不渲染', () => {
    const { container } = render(<ArtifactGallery artifacts={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
