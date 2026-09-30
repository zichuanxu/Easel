import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/noto-serif-sc/600.css'
import '@fontsource/bodoni-moda/latin-600-italic.css'
import './index.css'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'

export const BUILD_ID = 'subnav-1';
// 打到控制台，便于确认浏览器加载的是最新前端（排查缓存旧包）
console.log(`%cEasel build: ${BUILD_ID}`, 'color:#8b5cf6;font-weight:bold');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
