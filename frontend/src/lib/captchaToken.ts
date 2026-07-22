/**
 * Извлекает token сессии капчи из URL-фрагмента Mini App вида `#/captcha?token=<token>`.
 *
 * HashRouter кладёт путь и query-строку в один fragment после `#` (см. backend
 * `webapp_captcha_url`), поэтому здесь парсим вручную, а не через `useSearchParams()`
 * из react-router — функция должна оставаться чистой и не тянуть роутер в тесты.
 */
export function parseCaptchaToken(hash: string): string | null {
  const queryIndex = hash.indexOf('?');
  if (queryIndex === -1) return null;

  const token = new URLSearchParams(hash.slice(queryIndex + 1)).get('token');
  return token ? token : null;
}
