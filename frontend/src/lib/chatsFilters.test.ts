import { describe, expect, it } from 'vitest';

import {
  chatsFiltersSignature,
  DEFAULT_CHATS_FILTERS,
  parseStoredChatsFilters,
  parseTrustFilter,
  trustFilterToParam,
  type ChatsFiltersState,
} from './chatsFilters';

describe('parseTrustFilter', () => {
  it('распознаёт новый строковый формат', () => {
    expect(parseTrustFilter('trusted')).toBe('trusted');
    expect(parseTrustFilter('untrusted')).toBe('untrusted');
    expect(parseTrustFilter('all')).toBe('all');
  });

  it('распознаёт старый бинарный формат (true/false/null)', () => {
    expect(parseTrustFilter(true)).toBe('trusted');
    expect(parseTrustFilter(false)).toBe('untrusted');
    expect(parseTrustFilter(null)).toBe('all');
  });

  it('незнакомое значение -- "all"', () => {
    expect(parseTrustFilter(undefined)).toBe('all');
    expect(parseTrustFilter('garbage')).toBe('all');
    expect(parseTrustFilter(42)).toBe('all');
  });
});

describe('trustFilterToParam', () => {
  it('trusted -> true, untrusted -> false, all -> undefined', () => {
    expect(trustFilterToParam('trusted')).toBe(true);
    expect(trustFilterToParam('untrusted')).toBe(false);
    expect(trustFilterToParam('all')).toBeUndefined();
  });
});

describe('parseStoredChatsFilters', () => {
  it('возвращает дефолты для пустого/некорректного значения', () => {
    expect(parseStoredChatsFilters(null)).toEqual(DEFAULT_CHATS_FILTERS);
    expect(parseStoredChatsFilters(undefined)).toEqual(DEFAULT_CHATS_FILTERS);
    expect(parseStoredChatsFilters('garbage')).toEqual(DEFAULT_CHATS_FILTERS);
    expect(parseStoredChatsFilters(42)).toEqual(DEFAULT_CHATS_FILTERS);
  });

  it('читает новый формат с полем trustFilter', () => {
    const stored = {
      sortBy: 'title',
      sortOrder: 'asc',
      includePrivate: true,
      filterActive: false,
      trustFilter: 'untrusted',
      filterBanned: true,
      filterType: 'group',
    };
    expect(parseStoredChatsFilters(stored)).toEqual<ChatsFiltersState>({
      sortBy: 'title',
      sortOrder: 'asc',
      includePrivate: true,
      filterActive: false,
      trustFilter: 'untrusted',
      filterBanned: true,
      filterType: 'group',
    });
  });

  it('старая сессия с filterTrusted: true (до фичи "без доверия") читается как trusted', () => {
    const oldShape = {
      sortBy: 'updated_at',
      sortOrder: 'desc',
      includePrivate: false,
      filterActive: null,
      filterTrusted: true,
      filterBanned: null,
      filterType: null,
    };
    expect(parseStoredChatsFilters(oldShape).trustFilter).toBe('trusted');
  });

  it('старая сессия с filterTrusted: null читается как all', () => {
    const oldShape = { filterTrusted: null };
    expect(parseStoredChatsFilters(oldShape).trustFilter).toBe('all');
  });

  it('новое поле trustFilter имеет приоритет над старым filterTrusted, если оба есть', () => {
    const mixed = { trustFilter: 'trusted', filterTrusted: false };
    expect(parseStoredChatsFilters(mixed).trustFilter).toBe('trusted');
  });

  it('подставляет дефолты для отсутствующих полей', () => {
    const partial = { filterType: 'channel' };
    expect(parseStoredChatsFilters(partial)).toEqual<ChatsFiltersState>({
      ...DEFAULT_CHATS_FILTERS,
      filterType: 'channel',
    });
  });
});

describe('chatsFiltersSignature', () => {
  it('одинаковые фильтры дают одинаковую подпись', () => {
    const a: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, filterType: 'group' };
    const b: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, filterType: 'group' };
    expect(chatsFiltersSignature(a)).toBe(chatsFiltersSignature(b));
  });

  it('разные фильтры дают разную подпись', () => {
    const a: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, trustFilter: 'trusted' };
    const b: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, trustFilter: 'untrusted' };
    expect(chatsFiltersSignature(a)).not.toBe(chatsFiltersSignature(b));
  });
});
