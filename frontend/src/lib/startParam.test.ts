import { describe, expect, it } from 'vitest';

import { parseCaptchaToken } from './captchaToken';
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

  it('уводит на главную при незнакомом параметре запуска', () => {
    const location = fakeLocation('#tgWebAppData=abc&tgWebAppStartParam=promo_summer');

    expect(normalizeTelegramHash(location)).toBe('/');
  });

  it('не трогает обычный маршрут приложения', () => {
    const location = fakeLocation('#/triggers');

    expect(normalizeTelegramHash(location)).toBeNull();
    expect(location.hash).toBe('#/triggers');
  });

  it('не трогает маршрут капчи без параметров Telegram', () => {
    const location = fakeLocation('#/captcha?token=abc');

    expect(normalizeTelegramHash(location)).toBeNull();
    expect(location.hash).toBe('#/captcha?token=abc');
  });

  it('не трогает диплинк настроек чата', () => {
    const location = fakeLocation('#/settings/-1002467107234');

    expect(normalizeTelegramHash(location)).toBeNull();
    expect(location.hash).toBe('#/settings/-1002467107234');
  });

  it('сохраняет маршрут капчи и token, убирая параметры Telegram', () => {
    const location = fakeLocation(
      '#/captcha?token=abc&tgWebAppData=user%3D1%26hash%3Dff&tgWebAppVersion=8.0&tgWebAppPlatform=ios',
    );

    expect(normalizeTelegramHash(location)).toBe('/captcha?token=abc');
    expect(location.hash).toBe('/captcha?token=abc');
    expect(parseCaptchaToken(location.hash)).toBe('abc');
  });

  it('сохраняет свои параметры маршрута в любом месте строки', () => {
    const location = fakeLocation('#/captcha?tgWebAppVersion=8.0&token=a%2Bb&tgWebAppData=x&lang=ru');

    expect(normalizeTelegramHash(location)).toBe('/captcha?token=a%2Bb&lang=ru');
  });

  it('сохраняет диплинк настроек, к которому Telegram дописал параметры', () => {
    const location = fakeLocation('#/settings/-1002467107234&tgWebAppData=abc&tgWebAppVersion=8.0');

    expect(normalizeTelegramHash(location)).toBe('/settings/-1002467107234');
    expect(location.hash).toBe('/settings/-1002467107234');
  });

  it('оставляет маршрут, даже если есть параметр запуска', () => {
    const location = fakeLocation('#/captcha?token=abc&tgWebAppData=x&tgWebAppStartParam=chat_42');

    expect(normalizeTelegramHash(location)).toBe('/captcha?token=abc');
  });

  it('считает корневой путь отсутствием маршрута', () => {
    const location = fakeLocation('#/&tgWebAppData=x&tgWebAppStartParam=chat_42');

    expect(normalizeTelegramHash(location)).toBe('/chats/42');
  });
});
