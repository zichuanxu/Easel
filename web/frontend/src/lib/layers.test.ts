import { describe, it, expect } from 'vitest';
import { ALL_PAGES, LAYERS, NAV_GROUPS, PAGE_LAYER, PIPELINE, isLayerKey, layerInfo } from './layers';

describe('layers', () => {
  it('五层流水线按顺序：发现、策划、生产、发布、归因', () => {
    expect(PIPELINE.map((k) => layerInfo(k).name)).toEqual(['发现', '策划', '生产', '发布', '归因']);
  });

  it('不再出现「制作」', () => {
    expect(LAYERS.map((l) => l.name)).not.toContain('制作');
  });

  it('每个页面恰好出现在一个导航分组里', () => {
    const seen = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.page));
    expect([...seen].sort()).toEqual([...ALL_PAGES].sort());
    expect(new Set(seen).size).toBe(seen.length);
  });

  it('带层的分组里，每一页的 PAGE_LAYER 都等于这一组的层', () => {
    for (const g of NAV_GROUPS) {
      if (!g.layer) continue;
      for (const it of g.items) expect(PAGE_LAYER[it.page]).toBe(g.layer);
    }
  });

  it('五层流水线每层都有导航分组', () => {
    const grouped = NAV_GROUPS.map((g) => g.layer).filter(Boolean);
    expect(grouped).toEqual(PIPELINE);
  });

  it('技能库不配层标，画像是通用层', () => {
    expect(PAGE_LAYER.skills).toBeUndefined();
    expect(PAGE_LAYER.profile).toBe('general');
  });

  it('isLayerKey 能识别合法和非法的 key', () => {
    expect(isLayerKey('produce')).toBe(true);
    expect(isLayerKey('other')).toBe(false);
    expect(isLayerKey('toString')).toBe(false);
    expect(isLayerKey('__proto__')).toBe(false);
  });
});
