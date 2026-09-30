import type { SelectOption } from '../components/ui/SelectMenu';

/** 技能抽屉里带 choices 的 env 选择项：首项 value 为空，表示「保持当前 / 不设置」。
 *  已配置时首项显示掩码值（k.masked），不出现其他与 key 相关的字段。 */
export function skillKeyOptions(k: { choices: string[]; configured: boolean; masked?: string }): SelectOption[] {
  return [
    { value: '', label: k.configured ? `当前：${k.masked || '已配置'}` : '不设置' },
    ...k.choices.map((c) => ({ value: c, label: c })),
  ];
}
