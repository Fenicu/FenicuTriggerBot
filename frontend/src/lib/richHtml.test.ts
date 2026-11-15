// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { findUnknownTags } from './richHtml';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('findUnknownTags', () => {
  it('возвращает теги вне контракта rich-HTML', () => {
    expect(findUnknownTags('<p>ок</p><div><span>x</span></div>').sort()).toEqual(['div', 'span']);
  });

  it('возвращает пустой список для допустимой разметки', () => {
    expect(findUnknownTags('<h1>a</h1><p><b>b</b> <tg-spoiler>c</tg-spoiler></p>')).toEqual([]);
  });

  it('не вставляет проверяемый html в живой документ', () => {
    const assigned: string[] = [];
    const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML')!;
    vi.spyOn(Element.prototype, 'innerHTML', 'set').mockImplementation(function (this: Element, value: string) {
      if (this.ownerDocument === document) assigned.push(value);
      descriptor.set!.call(this, value);
    });

    findUnknownTags('<img src="https://example.com/x.png" onerror="window.__xss = 1">');

    expect(assigned).toEqual([]);
  });
});
