// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { sanitizeHtml } from './sanitizeHtml';

/**
 * Следит за присваиванием innerHTML элементам живого документа: именно в этот момент
 * браузер запускает загрузку <img> и срабатывает onerror, ещё до любой очистки.
 */
function spyOnLiveInnerHtml(): string[] {
  const assigned: string[] = [];
  const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML')!;
  vi.spyOn(Element.prototype, 'innerHTML', 'set').mockImplementation(function (this: Element, value: string) {
    if (this.ownerDocument === document) assigned.push(value);
    descriptor.set!.call(this, value);
  });
  return assigned;
}

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as Record<string, unknown>).__xss;
});

describe('sanitizeHtml', () => {
  it('не исполняет и вырезает обработчик события', () => {
    const assigned = spyOnLiveInnerHtml();
    const payload = '<img src="https://example.com/x.png" onerror="window.__xss = 1" onload="window.__xss = 1">';

    const result = sanitizeHtml(payload, true);

    expect(assigned).toEqual([]);
    expect((window as unknown as Record<string, unknown>).__xss).toBeUndefined();
    expect(result).not.toMatch(/onerror|onload|__xss/);
    expect(result).toBe('<img src="https://example.com/x.png">');
  });

  it('вырезает обработчики и у разрешённых тегов обычного режима', () => {
    const result = sanitizeHtml('<b onclick="window.__xss = 1" style="color:red">жирный</b>', false);

    expect(result).toBe('<b>жирный</b>');
  });

  it('оставляет базовую разметку Telegram', () => {
    const html = '<b>a</b><i>b</i><u>c</u><s>d</s><code>e</code><pre>f</pre><tg-spoiler>g</tg-spoiler>';

    expect(sanitizeHtml(html, false)).toBe(html);
  });

  it('заменяет запрещённый тег его текстом', () => {
    expect(sanitizeHtml('<div>привет <b>мир</b></div>', false)).toBe('привет <b>мир</b>');
    expect(sanitizeHtml('<img src="https://example.com/x.png">текст', false)).toBe('текст');
  });

  it('не пропускает script и его содержимое', () => {
    const result = sanitizeHtml('до<script>window.__xss = 1</script>после', true);

    expect(result).toBe('допосле');
  });

  it('оставляет в ссылке только http и https', () => {
    expect(sanitizeHtml('<a href="https://example.com/a?b=1">ссылка</a>', false)).toBe(
      '<a href="https://example.com/a?b=1">ссылка</a>',
    );
    expect(sanitizeHtml('<a href="javascript:alert(1)">ссылка</a>', false)).toBe('<a>ссылка</a>');
    expect(sanitizeHtml('<a href="tg://user?id=1">ссылка</a>', false)).toBe('<a>ссылка</a>');
  });

  it('оставляет в медиа только http и https', () => {
    expect(sanitizeHtml('<img src="data:image/svg+xml;base64,AAAA" alt="x">', true)).toBe('<img alt="x">');
    expect(sanitizeHtml('<video src="javascript:alert(1)"></video>', true)).toBe('<video></video>');
    expect(sanitizeHtml('<audio src="http://example.com/a.ogg"></audio>', true)).toBe(
      '<audio src="http://example.com/a.ogg"></audio>',
    );
  });

  it('разрешает атрибут только у своего тега', () => {
    expect(sanitizeHtml('<b href="https://example.com">a</b>', true)).toBe('<b>a</b>');
    expect(sanitizeHtml('<img href="https://example.com" data-x="1" aria-label="y">', true)).toBe('<img>');
  });

  it('оставляет блочные теги rich-режима', () => {
    const html = '<h1>Заголовок</h1><ul><li>пункт</li></ul><blockquote>цитата</blockquote>';

    expect(sanitizeHtml(html, true)).toBe(html);
  });
});
