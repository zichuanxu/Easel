/** 更新时间的相对写法：刚刚 / N 分钟前 / N 小时前 / M 月 D 日 HH:mm。ms 是毫秒时间戳。 */
export function fmtAgo(ms: number, now: number): string {
  if (!Number.isFinite(ms) || !Number.isFinite(now)) return '';
  const min = Math.floor((now - ms) / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  if (min < 60 * 24) return `${Math.floor(min / 60)} 小时前`;
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
