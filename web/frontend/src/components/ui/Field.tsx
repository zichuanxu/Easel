import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';

const cls = (extra?: string) => ['field', extra].filter(Boolean).join(' ');

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cls(className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cls(className)} {...rest} />;
}
