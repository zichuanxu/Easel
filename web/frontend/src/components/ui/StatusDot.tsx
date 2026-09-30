import type { ReactNode } from 'react';

export type DotTone = 'ok' | 'idle' | 'warn' | 'danger';

export default function StatusDot({ tone, children }: { tone: DotTone; children: ReactNode }) {
  return <span className="ui-dot" data-tone={tone}><i aria-hidden="true" />{children}</span>;
}
