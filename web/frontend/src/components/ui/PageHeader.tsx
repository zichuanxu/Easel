import type { ReactNode } from 'react';
import type { LayerKey } from '../../lib/layers';
import LayerMark from './LayerMark';

interface PageHeaderProps {
  layer?: LayerKey;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export default function PageHeader({ layer, title, description, actions }: PageHeaderProps) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header-main">
        {layer && <LayerMark layer={layer} />}
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-subtitle">{description}</p>}
      </div>
      {actions && <div className="ui-page-header-actions">{actions}</div>}
    </header>
  );
}
