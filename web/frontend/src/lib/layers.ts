/**
 * 流水线层与页面的唯一定义：侧栏分组、页头层标、工作台色条、技能库分段都从这里取。
 * 颜色不在这里——CSS 变量 `--layer-<key>` / `-text` / `-soft` 见 styles/tokens.css。
 */
export type LayerKey = 'discover' | 'plan' | 'produce' | 'publish' | 'attribute' | 'general';

export type Page =
  | 'dashboard' | 'chat' | 'trends' | 'ideas' | 'calendar' | 'publish' | 'breakdown'
  | 'skills' | 'outputs' | 'accounts' | 'profile' | 'analytics';

export const ALL_PAGES: Page[] = [
  'dashboard', 'chat', 'trends', 'ideas', 'calendar', 'publish', 'breakdown',
  'skills', 'outputs', 'accounts', 'profile', 'analytics',
];

export interface LayerInfo {
  key: LayerKey;
  name: string;      // 中文层名
  pigment: string;   // 矿物色名
  desc: string;      // 一句话说明（技能库分段、提示用）
}

export const LAYERS: LayerInfo[] = [
  { key: 'discover', name: '发现', pigment: '群青', desc: '找热点、看同行、盯平台规则' },
  { key: 'plan', name: '策划', pigment: '赭石', desc: '定选题、排日程、做规划' },
  { key: 'produce', name: '生产', pigment: '朱砂', desc: '写文案、做图、剪视频、配音' },
  { key: 'publish', name: '发布', pigment: '石绿', desc: '多平台发布与账号管理' },
  { key: 'attribute', name: '归因', pigment: '藤黄', desc: '看数据、做复盘' },
  { key: 'general', name: '通用', pigment: '墨灰', desc: '画像、素材、模板等基础能力' },
];

/** 五层流水线（不含通用），按流程先后。 */
export const PIPELINE: LayerKey[] = ['discover', 'plan', 'produce', 'publish', 'attribute'];

const BY_KEY: Record<LayerKey, LayerInfo> = Object.fromEntries(
  LAYERS.map((l) => [l.key, l]),
) as Record<LayerKey, LayerInfo>;

export function layerInfo(key: LayerKey): LayerInfo {
  return BY_KEY[key];
}

export function isLayerKey(v: string): v is LayerKey {
  return Object.hasOwn(BY_KEY, v);
}

/** 页面所属层：决定页头层标。技能库横跨所有层，不配。 */
export const PAGE_LAYER: Partial<Record<Page, LayerKey>> = {
  trends: 'discover',
  breakdown: 'discover',
  ideas: 'plan',
  calendar: 'plan',
  outputs: 'produce',
  publish: 'publish',
  accounts: 'publish',
  analytics: 'attribute',
  profile: 'general',
};

export interface NavItem { page: Page; label: string; }
export interface NavGroup { layer?: LayerKey; items: NavItem[]; }

/** 侧栏导航：无 layer 的组不显示组名。 */
export const NAV_GROUPS: NavGroup[] = [
  { items: [{ page: 'dashboard', label: '工作台' }, { page: 'chat', label: '对话' }] },
  { layer: 'discover', items: [{ page: 'trends', label: '热点雷达' }, { page: 'breakdown', label: '爆款拆解' }] },
  { layer: 'plan', items: [{ page: 'ideas', label: '选题库' }, { page: 'calendar', label: '内容日历' }] },
  { layer: 'produce', items: [{ page: 'outputs', label: '内容库' }] },
  { layer: 'publish', items: [{ page: 'publish', label: '发布中心' }, { page: 'accounts', label: '账号' }] },
  { layer: 'attribute', items: [{ page: 'analytics', label: '创作数据' }] },
  { items: [{ page: 'skills', label: '技能库' }, { page: 'profile', label: '画像' }] },
];
