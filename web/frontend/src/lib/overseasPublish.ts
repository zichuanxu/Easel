// 发布中心的海外平台（与 skills/shared/scripts/overseas/<平台>.py 的 LIMITS / VISIBILITY 对齐）。
// 海外平台的卡片正文就是完整英文文案（话题标签写在正文里），所以发送时不再拼中文母版的标题和标签。

export interface OverseasPlatform {
  key: string;
  label: string;
  titleLimit?: number;
  bodyLimit: number;
  hint: string;
  region: 'overseas';
  mediaRequired: boolean;   // 要带图片或视频（X / Threads 可以纯文字）
  videoOnly: boolean;       // 只收视频（目前只有 YouTube）
}

export const OVERSEAS_PLATFORMS: OverseasPlatform[] = [
  { key: 'tiktok', label: 'TikTok', bodyLimit: 2200, hint: '英文说明≤2200，附 1 个视频或 ≤35 张图',
    region: 'overseas', mediaRequired: true, videoOnly: false },
  { key: 'youtube', label: 'YouTube', titleLimit: 100, bodyLimit: 5000,
    hint: '第一行是英文标题（≤100），空一行后写描述；需附视频；账号要先有频道',
    region: 'overseas', mediaRequired: true, videoOnly: true },
  { key: 'instagram', label: 'Instagram', bodyLimit: 2200, hint: '英文说明≤2200、话题≤30，视频发成 Reels，或 ≤10 张图',
    region: 'overseas', mediaRequired: true, videoOnly: false },
  { key: 'x', label: 'X', bodyLimit: 280, hint: '英文≤280（中日韩文字算 2），可附 1 个视频或 ≤4 张图，也可纯文字',
    region: 'overseas', mediaRequired: false, videoOnly: false },
  { key: 'threads', label: 'Threads', bodyLimit: 500, hint: '英文≤500，话题只能 1 个，可附 1 个视频或 ≤10 张图，也可纯文字',
    region: 'overseas', mediaRequired: false, videoOnly: false },
];

// 与后端 web/app.py 的 MEDIA_REQUIRED / VIDEO_ONLY_PUBLISH 的海外部分一致
export const OVERSEAS_MEDIA_REQUIRED = OVERSEAS_PLATFORMS.filter((p) => p.mediaRequired).map((p) => p.key);
export const OVERSEAS_VIDEO_ONLY = OVERSEAS_PLATFORMS.filter((p) => p.videoOnly).map((p) => p.key);

const KEYS = new Set(OVERSEAS_PLATFORMS.map((p) => p.key));

export const VISIBILITY_OPTIONS: Record<string, { value: string; label: string }[]> = {
  youtube: [
    { value: 'public', label: '公开' },
    { value: 'unlisted', label: '不公开（有链接可看）' },
    { value: 'private', label: '私享' },
  ],
  tiktok: [
    { value: 'everyone', label: '所有人' },
    { value: 'friends', label: '好友' },
    { value: 'only_me', label: '仅自己' },
  ],
};

export function isOverseas(key: string): boolean {
  return KEYS.has(key);
}

/** 发给 /api/publish 的标题 / 正文 / 标签：YouTube 第一行是标题，其余平台整段都是正文。 */
export function overseasPayload(key: string, text: string): { title: string; body: string; tags: string } {
  if (key !== 'youtube') return { title: '', body: text.trim(), tags: '' };
  const [first, ...rest] = text.trim().split('\n');
  return { title: first.trim(), body: rest.join('\n').trim(), tags: '' };
}

/** 一键适配的附加要求：选了海外平台时，这些平台的版本要写英文。 */
export function overseasAdaptRule(keys: string[]): string {
  const labels = OVERSEAS_PLATFORMS.filter((p) => keys.includes(p.key)).map((p) => p.label);
  if (labels.length === 0) return '';
  return `【海外平台】${labels.join('、')} 的版本一律用英文，话题标签用英文写在正文末尾（如 #AI #productivity），` +
    `遵守各平台字数上限；YouTube 版本第一行写英文标题（≤100 字符），空一行后写描述。\n`;
}
