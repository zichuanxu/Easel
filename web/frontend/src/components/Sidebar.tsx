import { useEffect, useRef } from 'react';
import type { ComponentType } from 'react';
import type { PersonaItem } from '../lib/api';
import { NAV_GROUPS, layerInfo } from '../lib/layers';
import type { Page } from '../lib/layers';
import {
  IconDashboard, IconChat, IconFire, IconLayers, IconIdea, IconCalendar, IconClock,
  IconOutputs, IconPublish, IconAccounts, IconChart, IconSkills, IconProfile,
} from './icons';
import { IconGear } from './settingsIcons';
import Swatch from './ui/Swatch';
import SelectMenu from './ui/SelectMenu';
import ThemeToggle from './ThemeToggle';

export type { Page } from '../lib/layers';

interface SidebarProps {
  currentPage: Page;
  onPageChange: (page: Page) => void;
  personas: PersonaItem[];
  selectedPersona: string;
  onPersonaChange: (persona: string) => void;
  onNewProfile: () => void;
  activeChatTitle?: string;
  gatewayStatus: string;
  apiDirect: boolean;
  agentRuntime: string;
  onOpenSettings: () => void;
}

const PAGE_ICON: Record<Page, ComponentType<{ size?: number }>> = {
  dashboard: IconDashboard, chat: IconChat,
  trends: IconFire, breakdown: IconLayers,
  ideas: IconIdea, calendar: IconCalendar, cron: IconClock,
  outputs: IconOutputs,
  publish: IconPublish, accounts: IconAccounts,
  analytics: IconChart,
  skills: IconSkills, profile: IconProfile,
};

export default function Sidebar({
  currentPage, onPageChange, personas, selectedPersona, onPersonaChange, onNewProfile,
  activeChatTitle, gatewayStatus, apiDirect, agentRuntime, onOpenSettings,
}: SidebarProps) {
  // 连接状态按当前执行引擎换说法：仅聊天模式看 API 配置，其余 CLI 引擎看本机命令行是否就绪
  const statusText = gatewayStatus === 'connected'
    ? (apiDirect ? '仅聊天模式已配置' : agentRuntime !== 'openclaw' ? `${agentRuntime} CLI 已安装` : '网关已连接')
    : gatewayStatus === 'disconnected'
      ? (apiDirect ? 'API 配置不完整' : agentRuntime !== 'openclaw' ? `${agentRuntime} CLI 未配置` : '网关离线')
      : '连接中…';
  // 选中项不在可视区时（矮窗口下导航可滚动）才滚进来，避免每次切页都跳
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    navRef.current?.querySelector<HTMLElement>('.nav-item.active')?.scrollIntoView?.({ block: 'nearest' });
  }, [currentPage]);
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img className="sidebar-logo-icon" src="./static/easel-icon-transparent.png" alt="" />
        <span className="sidebar-wordmark">Easel</span>
        <ThemeToggle />
      </div>

      <SelectMenu
        className="persona-select"
        ariaLabel="画像"
        placeholder="选择画像"
        value={selectedPersona}
        options={[{ value: '', label: '通用模式' }, ...personas.map((p) => ({ value: p.name, label: p.name }))]}
        onChange={onPersonaChange}
        action={{ label: '新建画像', onSelect: onNewProfile }}
        title="选择用户画像（一个对话对应一个画像：切换会新建一个对话）"
      />

      <nav className="sidebar-nav" aria-label="主导航" ref={navRef}>
        {NAV_GROUPS.map((g, gi) => (
          <div key={gi} className="nav-group">
            {g.layer && (
              <div className="nav-group-title"><Swatch layer={g.layer} />{layerInfo(g.layer).name}</div>
            )}
            {g.items.map(({ page, label }) => {
              const Icon = PAGE_ICON[page];
              const active = currentPage === page;
              return (
                <button
                  key={page}
                  type="button"
                  className={`nav-item${active ? ' active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                  title={label}
                  onClick={() => onPageChange(page)}
                >
                  <span className="nav-icon"><Icon size={16} /></span>
                  <span className="nav-label">{label}</span>
                  {page === 'chat' && activeChatTitle && (
                    <span className="nav-sub" title={activeChatTitle}>{activeChatTitle}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-status">
        <span className={`status-dot${gatewayStatus === 'connected' ? '' : ' offline'}`} aria-hidden="true" />
        <span className="sidebar-status-text">{statusText}</span>
        <button type="button" className="settings-gear" onClick={onOpenSettings} title="设置（模型 · 环境 · 更多）">
          <IconGear size={14} /><span className="nav-label">设置</span>
        </button>
      </div>
    </aside>
  );
}
