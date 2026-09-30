import type { ReactNode } from 'react';

interface PanelProps {
  title?: ReactNode;
  action?: { label: string; onClick: () => void };
  className?: string;
  children: ReactNode;
}

export default function Panel({ title, action, className, children }: PanelProps) {
  return (
    <section className={['ui-panel', className].filter(Boolean).join(' ')}>
      {(title || action) && (
        <header className="ui-panel-head">
          {title && <h3 className="ui-panel-title">{title}</h3>}
          {action && <button type="button" className="ui-panel-action" onClick={action.onClick}>{action.label}</button>}
        </header>
      )}
      {children}
    </section>
  );
}
