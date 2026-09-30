import { useEffect, useRef, useState } from 'react';
import { fetchAnalyticsPlatforms } from './api';
import type { AccountWhoami, AnalyticsPlatform } from './api';
import { getWhoamiCache, verifyStale } from './whoami';

/**
 * 归因层平台加载 + whoami 自愈（工作台与创作数据页共用，行为与原工作台卡片一致）。
 * onLoggedIn：发现第一个已登录平台 / 自愈确认某平台已登录时回调（创作数据页用来默认选中）。
 */
export function useAnalyticsPlatforms(onLoggedIn?: (platform: string) => void) {
  const [plats, setPlats] = useState<AnalyticsPlatform[]>([]);
  const [whoamiMap, setWhoamiMap] = useState<Record<string, AccountWhoami>>(() => getWhoamiCache());
  const cb = useRef(onLoggedIn);
  useEffect(() => { cb.current = onLoggedIn; });

  useEffect(() => {
    fetchAnalyticsPlatforms().then((ps) => {
      setPlats(ps);
      const cache = getWhoamiCache();
      const first = ps.find((p) => p.loggedIn || !!cache[p.platform]?.loggedIn);
      if (first) cb.current?.(first.platform);
      // 开页后台自愈：对非 API 式的归因平台真校验（whoami），刷新登录态；
      // B 站走 cookie、公众号走凭证/官方 API 判定，都不起浏览器。
      const API_BASED = new Set(['bilibili', 'wechat-oa']);
      verifyStale(ps.filter((p) => !API_BASED.has(p.platform)).map((p) => p.platform), {
        onUpdate: (platform, r) => {
          setWhoamiMap((m) => ({ ...m, [platform]: r }));
          if (r.loggedIn) cb.current?.(platform);
        },
      });
    }).catch(() => {});
  }, []);

  const logged = plats.filter((p) => p.loggedIn || whoamiMap[p.platform]?.loggedIn);
  return { plats, logged };
}
