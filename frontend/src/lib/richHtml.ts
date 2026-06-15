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
  const div = document.createElement('div');
  div.innerHTML = html;
  const unknown = new Set<string>();
  div.querySelectorAll('*').forEach((el) => {
    const tag = el.tagName.toLowerCase();
    if (!RICH_ALL_TAGS.includes(tag)) {
      unknown.add(tag);
    }
  });
  return Array.from(unknown);
}
