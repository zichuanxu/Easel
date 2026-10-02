/**
 * 定时任务的时间设置：表单 ⇄ 后端 schedule spec，以及把 OpenClaw 的 schedule 说成中文。
 * 规则（最短间隔、分钟位必须写死数字）由后端 easel/gateway_cron.py 把关，这里只负责好填、好读。
 */

export type RepeatMode = 'daily' | 'weekly' | 'every' | 'once' | 'cron';

export interface ScheduleForm {
  mode: RepeatMode;
  time: string;          // HH:MM（每天 / 每周）
  weekdays: number[];    // 1=周一 … 7=周日（每周）
  everyValue: number;    // 每隔 N …
  everyUnit: 'minutes' | 'hours' | 'days';
  at: string;            // YYYY-MM-DDTHH:MM（只运行一次，本机时区）
  expr: string;          // 自定义 cron 表达式
}

export type ScheduleSpec =
  | { mode: 'cron'; expr: string }
  | { mode: 'every'; minutes: number }
  | { mode: 'at'; at: string };

export const WEEKDAY_NAMES = ['一', '二', '三', '四', '五', '六', '日'];
const UNIT_MIN = { minutes: 1, hours: 60, days: 1440 } as const;

export function defaultScheduleForm(): ScheduleForm {
  return { mode: 'daily', time: '09:00', weekdays: [1], everyValue: 2, everyUnit: 'hours', at: '', expr: '0 9 * * *' };
}

function hm(time: string): [number, number] | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  return h <= 23 && min <= 59 ? [h, min] : null;
}

/** 表单 → 后端 spec；填得不完整返回提示文字。cron 的「周」用 0=周日（周日在表单里是 7）。 */
export function toSpec(f: ScheduleForm): ScheduleSpec | string {
  if (f.mode === 'daily' || f.mode === 'weekly') {
    const t = hm(f.time);
    if (!t) return '请填写时间';
    if (f.mode === 'daily') return { mode: 'cron', expr: `${t[1]} ${t[0]} * * *` };
    if (!f.weekdays.length) return '请至少选一天';
    const days = [...new Set(f.weekdays)].sort((a, b) => a - b).map((d) => (d === 7 ? 0 : d));
    return { mode: 'cron', expr: `${t[1]} ${t[0]} * * ${days.join(',')}` };
  }
  if (f.mode === 'every') {
    const minutes = Math.round(f.everyValue * UNIT_MIN[f.everyUnit]);
    return Number.isFinite(minutes) && minutes > 0 ? { mode: 'every', minutes } : '请填写间隔';
  }
  if (f.mode === 'once') {
    // datetime-local 是浏览器这边的本地时间：带上时区发过去，别让服务器按它自己的时区理解
    const ms = f.at ? new Date(f.at).getTime() : NaN;
    return Number.isFinite(ms) ? { mode: 'at', at: new Date(ms).toISOString() } : '请选择运行时间';
  }
  return f.expr.trim() ? { mode: 'cron', expr: f.expr.trim() } : '请填写 cron 表达式';
}

export interface CronScheduleData {
  kind?: string;
  expr?: string;
  everyMs?: number;
  at?: string;
  tz?: string;
}

const pad = (n: number) => String(n).padStart(2, '0');

function describeEvery(ms: number): string {
  const min = Math.round(ms / 60000);
  if (min % 1440 === 0) return `每隔 ${min / 1440} 天`;
  if (min % 60 === 0) return `每隔 ${min / 60} 小时`;
  return `每隔 ${min} 分钟`;
}

/** 常见 cron 表达式说成中文（每天 / 工作日 / 每周几 / 每月几号），说不清的原样给出。 */
function describeCron(expr: string): string {
  const f = expr.trim().split(/\s+/);
  if (f.length !== 5) return `cron ${expr}`;
  const [min, hour, dom, mon, dow] = f;
  const num = /^\d+$/;
  if (!num.test(min) || mon !== '*') return `cron ${expr}`;
  if (hour.startsWith('*/') && dom === '*' && dow === '*') return `每天从 0 点起每 ${hour.slice(2)} 小时（第 ${min} 分）`;
  if (hour === '*' && dom === '*' && dow === '*') return `每小时第 ${min} 分`;
  const hours = hour.split(',');
  if (!hours.every((h) => num.test(h))) return `cron ${expr}`;
  const times = hours.map((h) => `${pad(Number(h))}:${pad(Number(min))}`).join('、');
  if (dom === '*' && dow === '*') return `每天 ${times}`;
  if (dom === '*' && (dow === '1-5' || dow === '1,2,3,4,5')) return `工作日 ${times}`;
  if (dom === '*' && /^[0-7](,[0-7])*$/.test(dow)) {
    const days = [...new Set(dow.split(',').map((d) => (d === '0' ? 7 : Number(d))))].sort((a, b) => a - b);
    return `每周${days.map((d) => WEEKDAY_NAMES[d - 1]).join('、')} ${times}`;
  }
  if (num.test(dom) && dow === '*') return `每月 ${dom} 号 ${times}`;
  return `cron ${expr}`;
}

export function describeSchedule(s: CronScheduleData | undefined): string {
  if (!s || !s.kind) return '—';
  if (s.kind === 'every' && s.everyMs) return describeEvery(s.everyMs);
  if (s.kind === 'at' && s.at) return `只运行一次：${fmtDateTime(Date.parse(s.at))}`;
  if (s.kind === 'cron' && s.expr) return describeCron(s.expr) + (s.tz ? `（${s.tz}）` : '');
  return s.kind;
}

/** M 月 D 日 HH:mm；跨年时带上年份。 */
export function fmtDateTime(ms: number | null | undefined, now = Date.now()): string {
  if (ms == null || !Number.isFinite(ms)) return '—';
  const d = new Date(ms);
  const y = d.getFullYear() !== new Date(now).getFullYear() ? `${d.getFullYear()} 年 ` : '';
  return `${y}${d.getMonth() + 1} 月 ${d.getDate()} 日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '';
  if (ms < 1000) return `${ms} 毫秒`;
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
}
