import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from './ErrorBoundary';

function Boom(): never { throw new Error('渲染炸了'); }

describe('ErrorBoundary', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it('出错时显示中文说明、错误详情和刷新按钮', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole('heading', { name: '页面出错了' })).toBeTruthy();
    expect(screen.getByText(/渲染炸了/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '刷新页面' })).toBeTruthy();
    expect(screen.getByText(/刷新页面通常能恢复/)).toBeTruthy();
    expect(screen.getByText(/渲染炸了/).tagName).toBe('PRE');
  });
});
