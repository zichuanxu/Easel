import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { useState } from 'react';
import SelectMenu from './SelectMenu';

afterEach(cleanup);

const OPTIONS = [
  { value: '', label: '通用模式' },
  { value: 'a', label: '画像甲' },
  { value: 'b', label: '画像乙' },
];

function setup(props: Partial<React.ComponentProps<typeof SelectMenu>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <SelectMenu value="a" options={OPTIONS} onChange={onChange} ariaLabel="画像" placeholder="请选择" {...props} />,
  );
  const trigger = screen.getByRole('button', { name: '画像' });
  return { onChange, trigger, ...utils };
}
const listbox = () => screen.queryByRole('listbox');
const active = () => {
  const lb = listbox()!;
  return document.getElementById(lb.getAttribute('aria-activedescendant') || '');
};

describe('SelectMenu', () => {
  it('触发器显示当前项文字；value 不在 options 里时显示 placeholder', () => {
    const { trigger, rerender } = setup();
    expect(trigger.textContent).toContain('画像甲');
    rerender(<SelectMenu value="zzz" options={OPTIONS} onChange={() => {}} ariaLabel="画像" placeholder="请选择" />);
    expect(screen.getByRole('button', { name: '画像' }).textContent).toContain('请选择');
  });

  it('点击触发器展开，再点一次收起，aria-expanded 跟随', () => {
    const { trigger } = setup();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(trigger.getAttribute('aria-controls')).toBeNull();
    fireEvent.click(trigger);
    expect(listbox()).toBeTruthy();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(trigger.getAttribute('aria-controls')).toBe(listbox()!.id);
    fireEvent.click(trigger);
    expect(listbox()).toBeNull();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('选中项带 aria-selected=true', () => {
    const { trigger } = setup();
    fireEvent.click(trigger);
    const opts = screen.getAllByRole('option');
    expect(opts.map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false']);
  });

  it('点选项：调用 onChange、收起、焦点回触发器', () => {
    const { trigger, onChange } = setup();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('option', { name: '画像乙' }));
    expect(onChange).toHaveBeenCalledWith('b');
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('点当前已选项只收起，不调用 onChange', () => {
    const { trigger, onChange } = setup();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('option', { name: '画像甲' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(listbox()).toBeNull();
  });

  it.each(['ArrowDown', 'ArrowUp', 'Enter', ' '])('触发器上按 %s 展开并高亮当前项，焦点到 listbox', (key) => {
    const { trigger } = setup();
    trigger.focus();
    fireEvent.keyDown(trigger, { key });
    expect(listbox()).toBeTruthy();
    expect(document.activeElement).toBe(listbox());
    expect(active()?.textContent).toContain('画像甲');
  });

  it('没有选中项时高亮第一项', () => {
    const { trigger } = setup({ value: 'nope' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(active()?.textContent).toContain('通用模式');
  });

  it('方向键移动高亮，到头不循环；Home/End 跳首末', () => {
    const { trigger } = setup();
    fireEvent.keyDown(trigger, { key: 'Enter' });
    const lb = listbox()!;
    fireEvent.keyDown(lb, { key: 'ArrowDown' });
    expect(active()?.textContent).toContain('画像乙');
    fireEvent.keyDown(lb, { key: 'ArrowDown' });
    expect(active()?.textContent).toContain('画像乙');
    fireEvent.keyDown(lb, { key: 'Home' });
    expect(active()?.textContent).toContain('通用模式');
    fireEvent.keyDown(lb, { key: 'ArrowUp' });
    expect(active()?.textContent).toContain('通用模式');
    fireEvent.keyDown(lb, { key: 'End' });
    expect(active()?.textContent).toContain('画像乙');
  });

  it('Enter / Space 选中高亮项', () => {
    const { trigger, onChange } = setup();
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(listbox()!, { key: 'ArrowDown' });
    fireEvent.keyDown(listbox()!, { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('b');
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger);
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(listbox()!, { key: 'Home' });
    fireEvent.keyDown(listbox()!, { key: ' ' });
    expect(onChange).toHaveBeenLastCalledWith('');
  });

  it('Escape 收起并把焦点还给触发器；Tab 收起且不抢焦点', () => {
    const { trigger } = setup();
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(listbox()!, { key: 'Escape' });
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger);
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(listbox()!, { key: 'Tab' });
    expect(listbox()).toBeNull();
  });

  it('点击浮层外部、resize、外部滚动都会收起；浮层自身滚动不收起', () => {
    const { trigger } = setup();
    fireEvent.click(trigger);
    fireEvent.mouseDown(document.body);
    expect(listbox()).toBeNull();

    fireEvent.click(trigger);
    fireEvent(window, new Event('resize'));
    expect(listbox()).toBeNull();

    fireEvent.click(trigger);
    fireEvent.scroll(listbox()!);
    expect(listbox()).toBeTruthy();
    fireEvent.scroll(document.body);
    expect(listbox()).toBeNull();
  });

  it('点触发器自身不会先被外部点击关掉再重开', () => {
    const { trigger } = setup();
    fireEvent.click(trigger);
    fireEvent.mouseDown(trigger);
    expect(listbox()).toBeTruthy();
    fireEvent.click(trigger);
    expect(listbox()).toBeNull();
  });

  it('disabled 时点击和键盘都不展开', () => {
    const { trigger } = setup({ disabled: true });
    fireEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(listbox()).toBeNull();
  });

  it('title 透传到触发器', () => {
    const { trigger } = setup({ title: '选择用户画像' });
    expect(trigger.getAttribute('title')).toBe('选择用户画像');
  });

  it('操作项：点击调用 onSelect、收起、不调 onChange', () => {
    const onSelect = vi.fn();
    const { trigger, onChange } = setup({ action: { label: '新建画像', onSelect } });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: /新建画像/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
    expect(listbox()).toBeNull();
  });

  it('操作项是最后一个可高亮项，键盘可达并用 Enter 触发', () => {
    const onSelect = vi.fn();
    const { trigger, onChange } = setup({ action: { label: '新建画像', onSelect } });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(listbox()!, { key: 'End' });
    expect(active()?.textContent).toContain('新建画像');
    fireEvent.keyDown(listbox()!, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
    expect(listbox()).toBeNull();
  });

  it('高亮项用 scrollIntoView({ block: nearest }) 滚入可见区', () => {
    const spy = vi.fn();
    const orig = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = spy;
    try {
      const { trigger } = setup();
      fireEvent.keyDown(trigger, { key: 'Enter' });
      expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
    } finally {
      Element.prototype.scrollIntoView = orig;
    }
  });

  it('受控使用：选中后触发器文字更新', () => {
    function Host() {
      const [v, setV] = useState('a');
      return <SelectMenu value={v} options={OPTIONS} onChange={setV} ariaLabel="画像" />;
    }
    render(<Host />);
    const t = screen.getByRole('button', { name: '画像' });
    fireEvent.click(t);
    fireEvent.click(screen.getByRole('option', { name: '画像乙' }));
    expect(t.textContent).toContain('画像乙');
  });
});
