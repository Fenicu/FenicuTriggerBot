// Теги из контракта Bot API 10.1 (должны совпадать с rich_html.py)

export const RICH_INLINE_TAGS: string[] = [
  'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
  'code', 'mark', 'sub', 'sup', 'tg-spoiler', 'a', 'tg-reference',
  'tg-emoji', 'tg-time', 'tg-math', 'br', 'cite',
];

export const RICH_BLOCK_TAGS: string[] = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'pre', 'footer', 'hr', 'ul', 'ol', 'li', 'input',
  'blockquote', 'aside', 'img', 'video', 'audio',
  'figure', 'figcaption', 'tg-map', 'tg-collage', 'tg-slideshow',
  'table', 'caption', 'tr', 'th', 'td', 'details', 'summary', 'tg-math-block',
];

export const RICH_ALL_TAGS: string[] = [...RICH_INLINE_TAGS, ...RICH_BLOCK_TAGS];

/**
 * Строит абсолютный URL для media proxy.
 * VITE_API_URL может быть абсолютным (https://...) или относительным (/api/v1).
 * Ссылка без токена: она сохраняется в тексте, а токен живёт час. Для показа в
 * предпросмотре её подписывает applySignedMediaUrls.
 */
export function buildMediaUrl(fileId: string): string {
  const rawBase = import.meta.env.VITE_API_URL || '/api/v1';
  const base = rawBase.startsWith('http')
    ? rawBase
    : `${window.location.origin}${rawBase}`;
  // Убираем trailing slash перед добавлением пути
  return `${base.replace(/\/+$/, '')}/media/proxy?file_id=${encodeURIComponent(fileId)}`;
}

/**
 * Возвращает теги, встречающиеся в html, которых нет в RICH_ALL_TAGS.
 */
export function findUnknownTags(html: string): string[] {
  const doc = parseInert(html);
  const unknown = new Set<string>();
  doc.body.querySelectorAll('*').forEach((el) => {
    const tag = el.tagName.toLowerCase();
    if (!RICH_ALL_TAGS.includes(tag)) {
      unknown.add(tag);
    }
  });
  return Array.from(unknown);
}

const MEDIA_SELECTOR = 'img[src], video[src], audio[src]';

/** Разбор в неактивном документе: обработчики событий и загрузка медиа не срабатывают. */
function parseInert(html: string): Document {
  return new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
}

/**
 * file_id из ссылки на media proxy без токена (такие ссылки хранятся в rich-HTML),
 * либо null для любой другой ссылки.
 */
export function proxyFileId(src: string): string | null {
  let url: URL;
  try {
    url = new URL(src, window.location.origin);
  } catch {
    return null;
  }
  if (!url.pathname.endsWith('/media/proxy') || url.searchParams.has('token')) return null;
  return url.searchParams.get('file_id') || null;
}

/** Уникальные file_id медиа, которые в html ссылаются на media proxy без токена. */
export function collectProxyFileIds(html: string): string[] {
  if (!html.includes('/media/proxy')) return [];
  const ids = new Set<string>();
  parseInert(html).body.querySelectorAll(MEDIA_SELECTOR).forEach((el) => {
    const fileId = proxyFileId(el.getAttribute('src') || '');
    if (fileId) ids.add(fileId);
  });
  return Array.from(ids);
}

/**
 * Заменяет ссылки на media proxy подписанными (signed: file_id -> URL с токеном).
 * Proxy требует токен, поэтому без подписанной ссылки src убирается -- иначе браузер
 * сделает заведомо неудачный запрос. Вызывать после очистки html.
 */
export function applySignedMediaUrls(html: string, signed: Record<string, string>): string {
  if (!html.includes('/media/proxy')) return html;
  const doc = parseInert(html);
  let changed = false;
  doc.body.querySelectorAll(MEDIA_SELECTOR).forEach((el) => {
    const fileId = proxyFileId(el.getAttribute('src') || '');
    if (!fileId) return;
    changed = true;
    const url = signed[fileId];
    if (url) {
      el.setAttribute('src', url);
    } else {
      el.removeAttribute('src');
    }
  });
  return changed ? doc.body.innerHTML : html;
}

// Токен живёт час (MEDIA_TOKEN_TTL_SECONDS в media.py) -- держим ссылку вдвое меньше
const SIGNED_URL_TTL_MS = 30 * 60 * 1000;
// После ошибки (нет прав, сеть) не дёргаем бэкенд на каждое нажатие клавиши
const FAILED_URL_TTL_MS = 60 * 1000;

const signedUrlCache = new Map<string, { promise: Promise<string | null>; expiresAt: number }>();

/**
 * Подписанная ссылка на media proxy для file_id; null если получить её не удалось.
 * fetcher делает авторизованный запрос токена (mediaApi.getProxyUrl).
 */
export function getSignedMediaUrl(
  fileId: string,
  fetcher: (fileId: string) => Promise<string>,
): Promise<string | null> {
  const cached = signedUrlCache.get(fileId);
  if (cached && cached.expiresAt > Date.now()) return cached.promise;

  const entry = { promise: Promise.resolve<string | null>(null), expiresAt: Date.now() + SIGNED_URL_TTL_MS };
  entry.promise = fetcher(fileId).catch(() => {
    entry.expiresAt = Date.now() + FAILED_URL_TTL_MS;
    return null;
  });
  signedUrlCache.set(fileId, entry);
  return entry.promise;
}

/** Сброс кэша подписанных ссылок (для тестов). */
export function resetSignedMediaUrlCache(): void {
  signedUrlCache.clear();
}
