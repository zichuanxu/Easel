import type { LayerKey } from '../../lib/layers';

/** 层色小方块：颜色由 CSS 按 data-layer 取 --layer-<key>。 */
export default function Swatch({ layer, size = 'md' }: { layer: LayerKey; size?: 'sm' | 'md' }) {
  return <span className={`ui-swatch${size === 'sm' ? ' ui-swatch-sm' : ''}`} data-layer={layer} aria-hidden="true" />;
}
