import { describe, expect, it } from 'vitest';

import { normalizeTelegramHash, routeForStartParam, startParamFromHash } from './startParam';

/** Минимальная замена Location: normalizeTelegramHash читает и пишет только hash. */
const fakeLocation = (hash: string) => ({ hash }) as Location;

describe('routeForStartParam', () => {
  it('строит маршрут карточки чата', () => {
    expect(routeForStartParam('chat_123')).toBe('/chats/123');
  });

  it('сохраняет отрицательный id супергруппы', () => {
    expect(routeForStartParam('chat_-1002467107234')).toBe('/chats/-1002467107234');
  });

  it('возвращает null на незнакомом параметре', () => {
    expect(routeForStartParam('promo_summer')).toBeNull();
    expect(routeForStartParam('chat_abc')).toBeNull();
    expect(routeForStartParam(undefined)).toBeNull();
  });
});

describe('startParamFromHash', () => {
  it('достаёт параметр из строки запуска Telegram', () => {
    const hash = 'tgWebAppData=user%3D%257B%2522id%2522%253A1%257D&tgWebAppStartParam=chat_-100500&tgWebAppVersion=8.0';
    expect(startParamFromHash(hash)).toBe('chat_-100500');
  });

  it('не путает параметр с похожим именем', () => {
    expect(startParamFromHash('tgWebAppStartParamExtra=nope')).toBeUndefined();
  });

  it('возвращает undefined, когда параметра нет', () => {
    expect(startParamFromHash('tgWebAppVersion=8.0')).toBeUndefined();
  });
});

describe('normalizeTelegramHash', () => {
  it('переписывает hash Telegram в маршрут карточки чата', () => {
    const location = fakeLocation('#tgWebAppData=abc&tgWebAppStartParam=chat_-1002467107234&tgWebAppVersion=8.0');

    expect(normalizeTelegramHash(location)).toBe('/chats/-1002467107234');
    expect(location.hash).toBe('/chats/-1002467107234');
  });

  it('уводит на главную, если параметра запуска нет', () => {
    const location = fakeLocation('#tgWebAppData=abc&tgWebAppVersion=8.0');

    expect(normalizeTelegramHash(location)).toBe('/');
    expect(location.hash).toBe('/');
  });

  it('не трогает обычный маршрут приложения', () => {
    const location = fakeLocation('#/triggers');

    expect(normalizeTelegramHash(location)).toBeNull();
    expect(location.hash).toBe('#/triggers');
  });
});
