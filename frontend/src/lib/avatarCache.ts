// Модульный кэш аватарок пользователей/чатов.
//
// /users/{id}/photo и /chats/{id}/photo требуют авторизации (Depends(get_current_admin)),
// поэтому обычный <img src="..."> не сработает -- браузер не приложит заголовок
// Authorization. В отличие от /media/proxy (без авторизации, StickerPreview/LazyVideo
// используют его как обычный <img src>) и SSE-эндпоинтов (авторизация из query
// параметров через get_current_admin_from_query) для /photo такого query-механизма
// в бэкенде ещё нет -- поэтому оставляем blob-запрос через apiClient, но кэшируем
// результат на весь сеанс вкладки: при смене фильтров/перерендере компонент
// пересоздаётся с теми же id, и повторный blob-запрос за той же фотографией не нужен.
//
// Ключ кэша -- сущность+id+photo_id: если фото обновится (сменится photo_id),
// закэшированный URL не переиспользуется.
//
// objectURL намеренно не отзываются: одна и та же аватарка может быть отрендерена
// в нескольких местах одновременно (список + модалка), и нет дешёвого способа
// отследить, что все потребители размонтировались. Для админки на десятки/сотни
// аватарок за сессию это не проблема памяти.

const cache = new Map<string, Promise<string | null>>();

/**
 * Возвращает objectURL картинки по ключу, кэшируя результат fetcher() на весь сеанс.
 * Повторный вызов с тем же ключом (даже из другого компонента) переиспользует уже
 * идущий или завершённый запрос вместо нового blob-запроса.
 */
export function getCachedAvatarUrl(key: string, fetcher: () => Promise<Blob>): Promise<string | null> {
  const cached = cache.get(key);
  if (cached) return cached;

  const promise = fetcher()
    .then((blob) => URL.createObjectURL(blob))
    .catch(() => null);

  cache.set(key, promise);
  return promise;
}
