import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SelectMenu from './ui/SelectMenu';

/** 设置里的单选下拉：套用设计系统的 SelectMenu（键盘导航、浮层 Esc 只收浮层），触发器撑满字段宽度。 */
export default function SettingsSelect({ value, options, disabled = false, label, onChange }: {
  value: string;
  options: { value: string; label: string }[];
  disabled?: boolean;
  label: string;
  onChange: (value: string) => void;
}) {
  return (
    <SelectMenu ariaLabel={label} placeholder={value}
      value={value} options={options} disabled={disabled} onChange={onChange} />
  );
}

/** 锚在输入框/触发器上的浮层选项列表（模型清单用）：portal 到 body，Esc 只关浮层、不连带关设置弹窗。 */
export function OptionsDropdown({ anchor, items, current, emptyHint, onPull, pulling, focusOptions = false, onPick, onClose }: {
  anchor: HTMLElement | null;
  items: { value: string; label: string }[];
  current: string;
  emptyHint?: string;
  onPull?: () => void;
  pulling?: boolean;
  focusOptions?: boolean;
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const positioned = pos !== null;
  useEffect(() => {
    if (!anchor) return;
    const measure = () => {
      const rect = anchor.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 240), 380, window.innerWidth - 16);
      const below = window.innerHeight - rect.bottom;
      const estimate = Math.min(items.length, 8) * 30 + 10;
      const openUp = below < Math.min(estimate, 240) && rect.top > estimate;
      setPos({
        top: openUp ? rect.top - Math.min(estimate, 240) - 4 : rect.bottom + 4,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
        width,
      });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [anchor, items.length]);

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)
          && !(anchor && anchor.contains(event.target as Node))) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        anchor?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey, true);
    };
  }, [anchor, onClose]);

  useEffect(() => {
    if (!positioned || !focusOptions) return;
    const selected = ref.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    const first = ref.current?.querySelector<HTMLElement>('[role="option"]');
    (selected || first)?.focus();
  }, [positioned, focusOptions]);

  if (!pos) return null;
  return createPortal(
    <div ref={ref} className="model-dd" role="listbox" onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        event.stopPropagation();
        const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
        if (!keys.includes(event.key)) return;
        event.preventDefault();
        const options = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role="option"]') || []);
        if (!options.length) return;
        const currentIndex = options.indexOf(document.activeElement as HTMLElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
        options[next].focus();
      }}
      style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width }}>
      {items.length === 0 && (
        <div className="dd-empty">
          <span>{emptyHint || '该端点没有返回模型'}</span>
          {onPull && (
            <button className="dd-pull" onMouseDown={(event) => { event.preventDefault(); onPull(); }} disabled={pulling}>
              {pulling ? <><span className="spin" />拉取中</> : '立即拉取'}
            </button>
          )}
        </div>
      )}
      {items.map((item) => (
        <div key={item.value} role="option" aria-selected={item.value === current} tabIndex={0}
          className={`dd-item${item.value === current ? ' active' : ''}`}
          onMouseDown={(event) => { event.preventDefault(); onPick(item.value); }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onPick(item.value);
            }
          }}>
          <span>{item.label}</span>
          {item.value === current && <small>当前</small>}
        </div>
      ))}
    </div>,
    document.body,
  );
}
