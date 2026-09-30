import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import Button from './ui/Button';

interface Props { children: ReactNode }
interface State { hasError: boolean; message: string }

/** 全局错误边界：任一渲染期异常不再白屏整个应用。 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Easel UI error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-page">
          <h2>页面出错了</h2>
          <p>刷新页面通常能恢复。如果反复出现，把下面的错误信息发给维护者。</p>
          <pre>{this.state.message}</pre>
          <Button variant="primary" onClick={() => window.location.reload()}>刷新页面</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
