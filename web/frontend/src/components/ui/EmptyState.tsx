import type { ReactNode } from 'react';
import Button from './Button';

interface EmptyStateProps {
  text: ReactNode;
  action?: { label: string; onClick: () => void };
}

/** 空状态：文案要写清楚下一步做什么。 */
export default function EmptyState({ text, action }: EmptyStateProps) {
  return (
    <div className="ui-empty">
      <p>{text}</p>
      {action && <Button size="sm" onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}
