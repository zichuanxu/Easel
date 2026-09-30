/** 预检结论：只看最后一个非空行（prompt 要求末行给「可发 / 建议修改」）。只影响展示。 */
export function precheckVerdict(text: string): 'ok' | 'warn' | null {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const last = lines[lines.length - 1];
  if (!last) return null;
  if (/建议修改|不可发|不建议/.test(last)) return 'warn';
  if (/(^|[^不])可发/.test(last)) return 'ok';
  return null;
}
