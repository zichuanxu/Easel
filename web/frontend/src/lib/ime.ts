import type { KeyboardEvent } from 'react';

/**
 * 输入法（IME）组字期间的按键：中文输入法里敲英文按回车上屏、按回车选词等。
 * 这类回车只是在确认输入法里的字，不能当成「发送 / 提交」。
 * - Chrome / Firefox：组字期间 keydown 的 isComposing 为 true。
 * - Safari：上屏那一下先触发 compositionend，keydown 的 isComposing 已是 false，但 keyCode 仍是 229。
 */
export function isImeComposing(e: KeyboardEvent): boolean {
  // keyCode 已标为弃用，但识别 Safari 的上屏回车没有替代写法
  return e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229;
}

/** 真正的回车提交：按的是 Enter，且不在输入法组字中。 */
export function isSubmitEnter(e: KeyboardEvent): boolean {
  return e.key === 'Enter' && !isImeComposing(e);
}
