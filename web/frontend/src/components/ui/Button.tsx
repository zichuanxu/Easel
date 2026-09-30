import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  loading?: boolean;
  block?: boolean;
}

/** 规范类名：页面里还没换成组件的按钮也可以直接用这个函数拼类名。 */
// oxlint-disable-next-line react/only-export-components -- 规范类名函数需与组件同处导出（brief 约定）
export function buttonClass(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', block = false): string {
  return [
    'btn',
    variant === 'secondary' ? '' : `btn-${variant}`,
    size === 'sm' ? 'btn-sm' : '',
    block ? 'btn-block' : '',
  ].filter(Boolean).join(' ');
}

export default function Button({
  variant = 'secondary', size = 'md', icon, loading = false, block = false,
  className, children, disabled, type = 'button', ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[buttonClass(variant, size, block), className].filter(Boolean).join(' ')}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="btn-spinner" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}
