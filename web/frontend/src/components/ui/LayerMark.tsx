import type { LayerKey } from '../../lib/layers';
import { layerInfo } from '../../lib/layers';
import Swatch from './Swatch';

export default function LayerMark({ layer }: { layer: LayerKey }) {
  return <span className="ui-layer-mark"><Swatch layer={layer} />{layerInfo(layer).name}</span>;
}
