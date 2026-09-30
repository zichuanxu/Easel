import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// vitest 不开 globals 时 RTL 不会自动清理，这里手动注册
afterEach(() => cleanup());
Element.prototype.scrollIntoView = () => {};
