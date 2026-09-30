import { describe, it, expect } from 'vitest';
import fieldCss from './ui/field.css?raw';
import chatCss from './pages/chat.css?raw';
import accountsCss from './pages/accounts.css?raw';
import publishCss from './pages/publish.css?raw';
import overlayCss from './ui/overlay.css?raw';
import settingsCss from './pages/settings.css?raw';

describe('控件定高不压过单类覆盖，弹窗不留多余滚动槽', () => {
  it('input/select 定高用 :where 零特异性', () => {
    expect(fieldCss).toMatch(/:where\(input\.field, select\.field\)\s*\{[^}]*height: var\(--h-ctl\)/);
    expect(fieldCss).not.toMatch(/^input\.field, select\.field/m);
  });
  it('改名框与验证码框显式声明自己的高度', () => {
    expect(chatCss).toMatch(/\.session-rename-input\s*\{[^}]*height: calc\(/);
    expect(accountsCss).toMatch(/\.sms-input\s*\{[^}]*height: auto/);
    expect(publishCss).toMatch(/\.publish-sms-input\s*\{[^}]*height: auto/);
  });
  it('.modal 不写 scrollbar-gutter，设置弹窗写 auto', () => {
    const modal = /\.modal\s*\{[^}]*\}/.exec(overlayCss)![0];
    expect(modal).not.toMatch(/scrollbar-gutter/);
    expect(settingsCss).toMatch(/\.settings-modal\s*\{[^}]*scrollbar-gutter: auto/);
  });
});
