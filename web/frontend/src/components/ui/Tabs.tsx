import type { KeyboardEvent, ReactNode } from 'react';

export interface TabItem<K extends string> { key: K; label: ReactNode; }

interface TabsProps<K extends string> {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  size?: 'sm' | 'md';
  ariaLabel?: string;
}

export default function Tabs<K extends string>({ items, value, onChange, size = 'md', ariaLabel }: TabsProps<K>) {
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const step = e.key === 'ArrowRight' ? 1 : -1;
    onChange(items[(i + step + items.length) % items.length].key);
  };
  return (
    <div className={`ui-tabs${size === 'sm' ? ' ui-tabs-sm' : ''}`} role="tablist" aria-label={ariaLabel}>
      {items.map((t, i) => {
        const active = t.key === value;
        return (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={`ui-tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
