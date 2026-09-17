// Фильтры списка чатов: три состояния доверия (все / доверенные / без доверия) и
// разбор сохранённого в sessionStorage состояния, включая старый бинарный формат.

/** Доверие как фильтр, а не сортировка -- владелец продукта явно исключил вариант сортировки. */
export type TrustFilter = 'all' | 'trusted' | 'untrusted';

export interface ChatsFiltersState {
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  includePrivate: boolean;
  filterActive: boolean | null;
  trustFilter: TrustFilter;
  filterBanned: boolean | null;
  filterType: string | null;
}

export const DEFAULT_CHATS_FILTERS: ChatsFiltersState = {
  sortBy: 'updated_at',
  sortOrder: 'desc',
  includePrivate: false,
  filterActive: null,
  trustFilter: 'all',
  filterBanned: null,
  filterType: null,
};

/** Короткая версия -- полная фраза "Бот удалён из чата" плохо влезает в чип/бейдж на мобильной ширине. */
export const BOT_REMOVED_LABEL = 'Бот удалён';
export const BOT_REMOVED_TOOLTIP =
  'Бот исключён, вышел или потерял права -- модерация и триггеры в чате не работают';

/**
 * Разобрать значение доверия в tri-state.
 *
 * Принимает как новый строковый формат ('all'/'trusted'/'untrusted'), так и старый
 * бинарный (`true`/`null` -- до этой фичи чипа "без доверия" не было, `false` в сторадже
 * никогда не оказывалось, но на всякий случай тоже маппим). Всё незнакомое -- 'all'.
 */
export function parseTrustFilter(value: unknown): TrustFilter {
  if (value === 'trusted' || value === true) return 'trusted';
  if (value === 'untrusted' || value === false) return 'untrusted';
  return 'all';
}

/** Значение query-параметра `is_trusted` для запроса к API, либо undefined -- фильтр не применять. */
export function trustFilterToParam(filter: TrustFilter): boolean | undefined {
  if (filter === 'trusted') return true;
  if (filter === 'untrusted') return false;
  return undefined;
}

/**
 * Разобрать сырое значение из `sessionStorage['chats_filters']` (уже прошедшее JSON.parse).
 *
 * Читает новое поле `trustFilter`, а если его нет -- старое `filterTrusted` (boolean|null),
 * чтобы сессия, сохранённая до этой фичи, не сбрасывала остальные фильтры при догрузке.
 */
export function parseStoredChatsFilters(raw: unknown): ChatsFiltersState {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_CHATS_FILTERS };
  const obj = raw as Record<string, unknown>;

  return {
    sortBy: typeof obj.sortBy === 'string' ? obj.sortBy : DEFAULT_CHATS_FILTERS.sortBy,
    sortOrder: obj.sortOrder === 'asc' ? 'asc' : DEFAULT_CHATS_FILTERS.sortOrder,
    includePrivate: obj.includePrivate === true,
    filterActive: obj.filterActive === true ? true : obj.filterActive === false ? false : null,
    trustFilter: parseTrustFilter('trustFilter' in obj ? obj.trustFilter : obj.filterTrusted),
    filterBanned: obj.filterBanned === true ? true : null,
    filterType: typeof obj.filterType === 'string' ? obj.filterType : null,
  };
}

/** Стабильная строковая подпись фильтров (без строки поиска) -- для сравнения "тот же набор фильтров или нет". */
export function chatsFiltersSignature(filters: ChatsFiltersState): string {
  return JSON.stringify([
    filters.sortBy,
    filters.sortOrder,
    filters.includePrivate,
    filters.filterActive,
    filters.trustFilter,
    filters.filterBanned,
    filters.filterType,
  ]);
}

/**
 * Подпись поиска+фильтров вместе -- "что сейчас должно быть загружено в списке".
 *
 * В отличие от `chatsFiltersSignature` включает строку поиска: нужна там, где важно
 * само значение chats (совпадает ли оно с текущим query+фильтрами прямо сейчас), а не
 * только идентичность набора фильтров как таковых (см. loadedSignatureRef в Chats.tsx).
 */
export function chatsListSignature(query: string, filters: ChatsFiltersState): string {
  return JSON.stringify([
    query,
    filters.sortBy,
    filters.sortOrder,
    filters.includePrivate,
    filters.filterActive,
    filters.trustFilter,
    filters.filterBanned,
    filters.filterType,
  ]);
}
