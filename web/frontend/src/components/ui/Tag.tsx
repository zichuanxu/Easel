import type { ReactNode } from 'react';
import type { LayerKey } from '../../lib/layers';

export type TagTone = 'neutral' | 'ok' | 'warn' | 'danger' | LayerKey;

export default function Tag({ tone = 'neutral', title, children }: { tone?: TagTone; title?: string; children: ReactNode }) {
  return <span className="ui-tag" data-tone={tone} title={title}>{children}</span>;
}
