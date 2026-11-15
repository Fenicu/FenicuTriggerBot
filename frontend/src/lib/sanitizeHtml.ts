// Очистка пользовательского HTML перед вставкой в предпросмотр.

import createDOMPurify from 'dompurify';

import { RICH_ALL_TAGS } from './richHtml';

const BASIC_TAGS = ['b', 'i', 'u', 's', 'code', 'pre', 'tg-spoiler', 'a'];
const ALLOWED_ATTRS: Record<string, string[]> = { a: ['href'], img: ['src', 'alt'], video: ['src'], audio: ['src'] };
const URL_ATTRS = ['href', 'src'];
const HTTP_URL_RE = /^https?:\/\//i;

// Отдельный экземпляр, чтобы хук не задевал другие вызовы DOMPurify.
const purifier = createDOMPurify(window);

// Список атрибутов у DOMPurify общий на все теги, а data: в src медиа он пропускает сам,
// поэтому привязку атрибута к тегу и схему ссылки проверяем здесь.
purifier.addHook('uponSanitizeAttribute', (node, data) => {
  const allowed = ALLOWED_ATTRS[node.nodeName.toLowerCase()] ?? [];
  if (!allowed.includes(data.attrName)) {
    data.keepAttr = false;
    return;
  }
  if (URL_ATTRS.includes(data.attrName) && !HTTP_URL_RE.test(data.attrValue.trim())) {
    data.keepAttr = false;
  }
});

/**
 * Оставляет в html только разрешённые теги и атрибуты, ссылки -- только http/https.
 * DOMPurify разбирает строку в неактивном документе: обработчики событий не срабатывают.
 */
export function sanitizeHtml(html: string, richMode: boolean): string {
  return purifier.sanitize(html, {
    ALLOWED_TAGS: richMode ? RICH_ALL_TAGS : BASIC_TAGS,
    ALLOWED_ATTR: ['href', 'src', 'alt'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
    ALLOWED_URI_REGEXP: HTTP_URL_RE,
  });
}
