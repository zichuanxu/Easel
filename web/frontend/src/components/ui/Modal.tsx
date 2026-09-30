import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export interface ModalProps {
  title?: ReactNode;
  onClose: () => void;
  width?: number;
  footer?: ReactNode;
  className?: string;
  closeOnBackdrop?: boolean;
  children: ReactNode;
}

const FOCUSABLE = 'input, select, textarea, button, [href], [tabindex]:not([tabindex="-1"])';

/** 通用弹窗：挂载即打开（调用方条件渲染）；Esc 关闭；焦点移入，卸载后还给打开前的元素。 */
export default function Modal({
  title, onClose, width = 480, footer, className, closeOnBackdrop = true, children,
}: ModalProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // 首次渲染时（提交前）记下打开前的焦点，关闭后还回去
  const [returnTo] = useState(() => document.activeElement as HTMLElement | null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });

  useEffect(() => {
    const box = boxRef.current;
    if (box && !box.contains(document.activeElement)) {
      (box.querySelector<HTMLElement>(FOCUSABLE) ?? box).focus();
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      returnTo?.focus?.();
    };
  }, [returnTo]);

  return (
    <div
      className="overlay"
      onMouseDown={(e) => { if (closeOnBackdrop && e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={boxRef}
        className={['modal', className].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        style={{ width, maxWidth: '100%' }}
      >
        {title && <h2 id={titleId} className="modal-title">{title}</h2>}
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
