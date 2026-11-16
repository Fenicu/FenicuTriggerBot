// Разбор параметра запуска Mini App (?startapp=...) и приведение telegram-hash к маршруту.

/** start_param вида chat_<id>, в т.ч. отрицательные id супергрупп и каналов. */
export const START_PARAM_CHAT_RE = /^chat_(-?\d+)$/;

/** Маршрут, соответствующий параметру запуска, либо null если параметр нам незнаком. */
export function routeForStartParam(startParam: string | undefined | null): string | null {
  if (!startParam) return null;
  const match = START_PARAM_CHAT_RE.exec(startParam);
  return match ? `/chats/${match[1]}` : null;
}

/** Достать tgWebAppStartParam из строки параметров запуска (hash без ведущего '#'). */
export function startParamFromHash(rawHash: string): string | undefined {
  const match = /(?:^|&)tgWebAppStartParam=([^&]*)/.exec(rawHash);
  if (!match) return undefined;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

/**
 * Убрать telegram-параметры из hash, оставив маршрут приложения.
 *
 * Telegram кладёт параметры запуска в hash, а HashRouter принимает их за путь: маршрут
 * не находится, срабатывает `path="*"` и пользователя уводит на главную. Если в hash уже
 * был маршрут (`#/captcha?token=...`), Telegram дописывает параметры к нему через `&` --
 * тогда маршрут и его собственные параметры остаются, уходят только tgWebApp*.
 * Параметр запуска превращается в маршрут, только когда своего маршрута в hash нет.
 * Вызывать ДО монтирования роутера и ПОСЛЕ того, как SDK прочитал параметры запуска из URL.
 * Возвращает маршрут, на который переписан hash, либо null если трогать было нечего.
 */
export function normalizeTelegramHash(location: Location): string | null {
  const rawHash = location.hash.replace(/^#/, '');
  if (!rawHash.includes('tgWebApp')) return null;

  const route = routeFromHash(rawHash) ?? routeForStartParam(startParamFromHash(rawHash)) ?? '/';
  location.hash = route;
  return route;
}

/** Маршрут приложения из hash без tgWebApp-параметров, либо null если маршрута в нём нет. */
function routeFromHash(rawHash: string): string | null {
  if (!rawHash.startsWith('/')) return null;

  // Параметры отделены от пути через '?', а дописанные Telegram к пути без query -- через '&'
  const pathEnd = rawHash.search(/[?&]/);
  const path = pathEnd === -1 ? rawHash : rawHash.slice(0, pathEnd);
  const ownParams = (pathEnd === -1 ? '' : rawHash.slice(pathEnd + 1))
    .split('&')
    .filter((param) => param && !param.startsWith('tgWebApp'));

  // Голый корень -- не маршрут: пусть решает параметр запуска
  if (path === '/' && ownParams.length === 0) return null;
  return ownParams.length > 0 ? `${path}?${ownParams.join('&')}` : path;
}
