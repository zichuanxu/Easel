import { describe, it, expect } from 'vitest';
import { defaultScheduleForm, describeSchedule, fmtDuration, toSpec } from './cronSchedule';

const form = (patch: Partial<ReturnType<typeof defaultScheduleForm>>) => ({ ...defaultScheduleForm(), ...patch });

describe('toSpec：表单 → 后端时间设置', () => {
  it('每天 / 每周转成 cron，周日是 0、按周一到周日排序', () => {
    expect(toSpec(form({ mode: 'daily', time: '09:05' }))).toEqual({ mode: 'cron', expr: '5 9 * * *' });
    expect(toSpec(form({ mode: 'weekly', time: '20:30', weekdays: [7, 3, 1, 3] })))
      .toEqual({ mode: 'cron', expr: '30 20 * * 1,3,0' });
  });
  it('每隔按单位换算成分钟', () => {
    expect(toSpec(form({ mode: 'every', everyValue: 2, everyUnit: 'hours' }))).toEqual({ mode: 'every', minutes: 120 });
    expect(toSpec(form({ mode: 'every', everyValue: 1, everyUnit: 'days' }))).toEqual({ mode: 'every', minutes: 1440 });
  });
  it('没填完给提示文字，不发请求', () => {
    expect(toSpec(form({ mode: 'daily', time: '' }))).toBe('请填写时间');
    expect(toSpec(form({ mode: 'daily', time: '25:00' }))).toBe('请填写时间');
    expect(toSpec(form({ mode: 'weekly', weekdays: [] }))).toBe('请至少选一天');
    expect(toSpec(form({ mode: 'every', everyValue: 0 }))).toBe('请填写间隔');
    expect(toSpec(form({ mode: 'once', at: '' }))).toBe('请选择运行时间');
    expect(toSpec(form({ mode: 'cron', expr: '  ' }))).toBe('请填写 cron 表达式');
  });
  it('只运行一次 / 自定义原样带过去', () => {
    // 浏览器本地时间 → 带时区的绝对时间
    expect(toSpec(form({ mode: 'once', at: '2026-10-03T09:00' })))
      .toEqual({ mode: 'at', at: new Date('2026-10-03T09:00').toISOString() });
    expect(toSpec(form({ mode: 'once', at: 'garbage' }))).toBe('请选择运行时间');
    expect(toSpec(form({ mode: 'cron', expr: ' 0 9 * * 1-5 ' }))).toEqual({ mode: 'cron', expr: '0 9 * * 1-5' });
  });
});

describe('describeSchedule：说成中文', () => {
  it.each([
    [{ kind: 'cron', expr: '0 9 * * *' }, '每天 09:00'],
    [{ kind: 'cron', expr: '30 8,20 * * *' }, '每天 08:30、20:30'],
    [{ kind: 'cron', expr: '0 9 * * 1-5' }, '工作日 09:00'],
    [{ kind: 'cron', expr: '0 20 * * 1,3,0' }, '每周一、三、日 20:00'],
    [{ kind: 'cron', expr: '15 10 1 * *' }, '每月 1 号 10:15'],
    [{ kind: 'cron', expr: '0 */2 * * *' }, '每天从 0 点起每 2 小时（第 0 分）'],
    [{ kind: 'cron', expr: '0 9 * * 1,2,3,4,5' }, '工作日 09:00'],
    [{ kind: 'cron', expr: '0 3 * * *', tz: 'Asia/Tokyo' }, '每天 03:00（Asia/Tokyo）'],
    [{ kind: 'cron', expr: '0 9 1-7 * 1' }, 'cron 0 9 1-7 * 1'],
    [{ kind: 'every', everyMs: 1800000 }, '每隔 30 分钟'],
    [{ kind: 'every', everyMs: 7200000 }, '每隔 2 小时'],
    [{ kind: 'every', everyMs: 7 * 86400000 }, '每隔 7 天'],
    [undefined, '—'],
  ])('%j → %s', (s, text) => {
    expect(describeSchedule(s)).toBe(text);
  });
  it('只运行一次带上日期', () => {
    expect(describeSchedule({ kind: 'at', at: '2026-10-03T09:00:00+09:00' })).toMatch(/^只运行一次：/);
  });
});

describe('fmtDuration', () => {
  it('毫秒 / 秒 / 分秒', () => {
    expect(fmtDuration(800)).toBe('800 毫秒');
    expect(fmtDuration(1876)).toBe('2 秒');
    expect(fmtDuration(125000)).toBe('2 分 5 秒');
    expect(fmtDuration(null)).toBe('');
  });
});
