import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { IconCheck, IconChevron, IconPlus } from '../icons';

export interface SelectOption { value: string; label: string; }

interface SelectMenuProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  disabled?: boolean;
  title?: string;
  action?: { label: string; onSelect: () => void };
  className?: string;
}

interface Pos { left: number; top: number; width: number; maxHeight: number; }

const GAP = 4;
const EDGE = 8;
const MIN_WIDTH = 180;

export default function SelectMenu({
  value, options, onChange, ariaLabel, placeholder, disabled, title, action, className,
}: SelectMenuProps) {
  const uid = useId();
  const listId = `${uid}-list`;
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const [pos, setPos] = useState<Pos | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selectedIdx = options.findIndex((o) => o.value === value);
  const selected = selectedIdx >= 0 ? options[selectedIdx] : null;
  const actionIdx = action ? options.length : -1;
  const lastIdx = options.length + (action ? 1 : 0) - 1;
  const itemId = (i: number) => (i === actionIdx ? `${uid}-action` : `${uid}-opt-${i}`);

  const close = useCallback((refocus: boolean) => {
    setOpen(false);
    setPos(null);
    if (refocus) triggerRef.current?.focus();
  }, []);

  const openMenu = () => {
    if (disabled) return;
    setActiveIdx(selectedIdx >= 0 ? selectedIdx : 0);
    setOpen(true);
  };

  // 在绘制前量出浮层高度并定位，首帧即在最终位置
  useLayoutEffect(() => {
    if (!open || !triggerRef.current || !listRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const below = window.innerHeight - EDGE - (rect.bottom + GAP);
    const above = rect.top - GAP - EDGE;
    const maxHeight = Math.max(0, Math.min(280, Math.max(below, above)));
    const h = Math.min(listRef.current.offsetHeight, maxHeight);
    const flip = h > below && above > below;
    const width = Math.max(rect.width, MIN_WIDTH);
    setPos({
      left: Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE)),
      width,
      top: Math.max(0, flip ? rect.top - GAP - h : rect.bottom + GAP),
      maxHeight,
    });
  }, [open]);

  // visibility:hidden 的元素不能聚焦，所以等定位完成后再把焦点交给 listbox
  useEffect(() => {
    if (open && pos) listRef.current?.focus({ preventScroll: true });
  }, [open, pos]);

  useEffect(() => {
    if (!open) return;
    document.getElementById(itemId(activeIdx))?.scrollIntoView?.({ block: 'nearest' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeIdx, pos]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || listRef.current?.contains(t)) return;
      close(false);
    };
    const onScroll = (e: Event) => {
      if (listRef.current && e.target instanceof Node && listRef.current.contains(e.target)) return;
      close(false);
    };
    const onResize = () => close(false);
    document.addEventListener('mousedown', onDown);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('mousedown', onDown);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
    };
  }, [open, close]);

  // 打开期间禁用状态变化（例如会话产生消息）时收起
  useEffect(() => { if (disabled) close(false); }, [disabled, close]);

  const commit = (idx: number) => {
    if (idx === actionIdx) {
      close(true);
      action?.onSelect();
      return;
    }
    const opt = options[idx];
    close(true);
    if (opt && opt.value !== value) onChange(opt.value);
  };

  const onTriggerKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault();
      if (!open) openMenu();
    }
  };

  const onListKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); setActiveIdx((i) => Math.min(i + 1, lastIdx)); break;
      case 'ArrowUp': e.preventDefault(); setActiveIdx((i) => Math.max(i - 1, 0)); break;
      case 'Home': e.preventDefault(); setActiveIdx(0); break;
      case 'End': e.preventDefault(); setActiveIdx(lastIdx); break;
      case 'Enter':
      case ' ': e.preventDefault(); commit(activeIdx); break;
      case 'Escape': e.preventDefault(); e.stopPropagation(); close(true); break;
      case 'Tab':
        // 浮层挂在 body 末尾：先把焦点还给触发器，浏览器才会从触发器位置继续 Tab / Shift+Tab
        triggerRef.current?.focus();
        close(false);
        break;
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={['ui-select', className].filter(Boolean).join(' ')}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        title={title}
        disabled={disabled}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={`ui-select__text${selected ? '' : ' ui-select__text--placeholder'}`} title={selected?.label}>
          {selected ? selected.label : placeholder}
        </span>
        <IconChevron size={14} className="ui-select__chevron" />
      </button>
      {open && createPortal(
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-label={ariaLabel}
          aria-activedescendant={itemId(activeIdx)}
          className="ui-select__list"
          style={pos
            ? { left: pos.left, top: pos.top, width: pos.width, maxHeight: pos.maxHeight }
            : { left: 0, top: 0, visibility: 'hidden' }}
          onKeyDown={onListKeyDown}
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={itemId(i)}
              role="option"
              aria-selected={i === selectedIdx}
              className={`ui-select__option${i === activeIdx ? ' is-active' : ''}`}
              onMouseMove={() => setActiveIdx(i)}
              onClick={() => commit(i)}
            >
              <span className="ui-select__label">{o.label}</span>
              <span className="ui-select__mark">{i === selectedIdx && <IconCheck size={14} />}</span>
            </li>
          ))}
          {action && (
            <>
              <li role="separator" className="ui-select__sep" />
              <li role="presentation">
                <button
                  type="button"
                  id={itemId(actionIdx)}
                  tabIndex={-1}
                  className={`ui-select__action${activeIdx === actionIdx ? ' is-active' : ''}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseMove={() => setActiveIdx(actionIdx)}
                  onClick={() => commit(actionIdx)}
                >
                  <IconPlus size={14} />
                  <span className="ui-select__label">{action.label}</span>
                </button>
              </li>
            </>
          )}
        </ul>,
        document.body,
      )}
    </>
  );
}
