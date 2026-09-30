import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import Modal from './Modal';

function Harness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>打开</button>
      {open && (
        <Modal title="登录 小红书" onClose={() => { onClose(); setOpen(false); }}>
          <button type="button">里面的按钮</button>
        </Modal>
      )}
    </div>
  );
}

describe('Modal', () => {
  it('打开时焦点移入，关闭后回到触发按钮', () => {
    render(<Harness onClose={() => {}} />);
    const trigger = screen.getByRole('button', { name: '打开' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '登录 小红书' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('Esc 调用 onClose', () => {
    const onClose = vi.fn();
    render(<Modal title="设置" onClose={onClose}><p>内容</p></Modal>);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('点遮罩关闭，点弹窗内部不关闭', () => {
    const onClose = vi.fn();
    const { container } = render(<Modal title="设置" onClose={onClose}><p>内容</p></Modal>);
    fireEvent.mouseDown(screen.getByText('内容'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(container.querySelector('.overlay')!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closeOnBackdrop=false 时点遮罩不关闭', () => {
    const onClose = vi.fn();
    const { container } = render(<Modal title="向导" closeOnBackdrop={false} onClose={onClose}><p>内容</p></Modal>);
    fireEvent.mouseDown(container.querySelector('.overlay')!);
    expect(onClose).not.toHaveBeenCalled();
  });
});
