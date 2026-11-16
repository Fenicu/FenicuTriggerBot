// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  applySignedMediaUrls,
  collectProxyFileIds,
  getSignedMediaUrl,
  proxyFileId,
  resetSignedMediaUrlCache,
} from './richHtml';
import { findUnknownTags } from './richHtml';

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  resetSignedMediaUrlCache();
});

const PROXY = 'https://bot.example.com/api/v1/media/proxy';

describe('proxyFileId', () => {
  it('достаёт file_id из ссылки на media proxy без токена', () => {
    expect(proxyFileId(`${PROXY}?file_id=AgAC%2Bx`)).toBe('AgAC+x');
  });

  it('пропускает уже подписанную ссылку', () => {
    expect(proxyFileId(`${PROXY}?file_id=AgAC&token=abc.def`)).toBeNull();
  });

  it('пропускает посторонние ссылки', () => {
    expect(proxyFileId('https://example.com/cat.png')).toBeNull();
    expect(proxyFileId('https://example.com/media/proxy')).toBeNull();
    expect(proxyFileId('https://example.com/other?file_id=AgAC')).toBeNull();
    expect(proxyFileId('не ссылка')).toBeNull();
  });
});

describe('collectProxyFileIds', () => {
  it('собирает file_id медиа без повторов', () => {
    const html =
      `<img src="${PROXY}?file_id=one"><video src="${PROXY}?file_id=two"></video>` +
      `<audio src="${PROXY}?file_id=one"></audio><img src="https://example.com/cat.png">`;

    expect(collectProxyFileIds(html)).toEqual(['one', 'two']);
  });

  it('не смотрит на ссылки вне медиа-тегов', () => {
    expect(collectProxyFileIds(`<a href="${PROXY}?file_id=one">x</a><p>текст</p>`)).toEqual([]);
  });
});

describe('applySignedMediaUrls', () => {
  it('подставляет подписанную ссылку', () => {
    const html = `<p>до</p><img src="${PROXY}?file_id=one" alt="x">`;

    expect(applySignedMediaUrls(html, { one: '/api/v1/media/proxy?file_id=one&token=t' })).toBe(
      '<p>до</p><img src="/api/v1/media/proxy?file_id=one&amp;token=t" alt="x">',
    );
  });

  it('убирает src, пока подписанной ссылки нет', () => {
    expect(applySignedMediaUrls(`<video src="${PROXY}?file_id=one"></video>`, {})).toBe('<video></video>');
  });

  it('не меняет html без ссылок на media proxy', () => {
    const html = '<p>текст</p><img src="https://example.com/cat.png">';

    expect(applySignedMediaUrls(html, { one: 'x' })).toBe(html);
  });
});

describe('getSignedMediaUrl', () => {
  it('запрашивает ссылку один раз на file_id', async () => {
    const fetcher = vi.fn(async (fileId: string) => `signed:${fileId}`);

    expect(await getSignedMediaUrl('one', fetcher)).toBe('signed:one');
    expect(await getSignedMediaUrl('one', fetcher)).toBe('signed:one');
    expect(await getSignedMediaUrl('two', fetcher)).toBe('signed:two');
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('запрашивает ссылку заново, когда токен устарел', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(async (fileId: string) => `signed:${fileId}`);

    await getSignedMediaUrl('one', fetcher);
    vi.advanceTimersByTime(31 * 60 * 1000);
    await getSignedMediaUrl('one', fetcher);

    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('возвращает null при ошибке и не повторяет запрос сразу', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(async (): Promise<string> => {
      throw new Error('403');
    });

    expect(await getSignedMediaUrl('one', fetcher)).toBeNull();
    expect(await getSignedMediaUrl('one', fetcher)).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(61 * 1000);
    await getSignedMediaUrl('one', fetcher);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
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
