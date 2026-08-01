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
 * Заменить telegram-параметры в hash на маршрут приложения.
 *
 * Telegram кладёт параметры запуска в hash, а HashRouter принимает их за путь: маршрут
 * не находится, срабатывает `path="*"` и пользователя уводит на главную. Вызывать ДО
 * монтирования роутера и ПОСЛЕ того, как SDK прочитал параметры запуска из URL.
 * Возвращает маршрут, на который переписан hash, либо null если трогать было нечего.
 */
export function normalizeTelegramHash(location: Location): string | null {
  const rawHash = location.hash.replace(/^#/, '');
  if (!rawHash.includes('tgWebApp')) return null;

  const route = routeForStartParam(startParamFromHash(rawHash)) ?? '/';
  location.hash = route;
  return route;
}
