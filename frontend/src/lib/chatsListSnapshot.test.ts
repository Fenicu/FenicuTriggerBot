import { describe, expect, it } from 'vitest';

import { DEFAULT_CHATS_FILTERS, type ChatsFiltersState } from './chatsFilters';
import {
  buildChatsListSnapshot,
  invalidateChatsListSnapshot,
  loadValidChatsListSnapshot,
  readChatsListSnapshot,
  removeChatFromSnapshot,
  removeChatFromStoredSnapshot,
  saveChatsListSnapshot,
  SNAPSHOT_MAX_AGE_MS,
  type ChatsListSnapshot,
  type SnapshotStorage,
} from './chatsListSnapshot';
import type { Chat } from '../types';

/** Storage-заглушка -- модуль принимает её через DI, чтобы не тянуть jsdom в тесты. */
function fakeStorage(): SnapshotStorage {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

const chat = (id: number, overrides: Partial<Chat> = {}): Chat =>
  ({
    id,
    admins_only_add: false,
    language_code: 'ru',
    warn_limit: 3,
    warn_punishment: 'mute',
    warn_duration: 3600,
    is_trusted: false,
    is_active: true,
    timezone: 'UTC',
    module_triggers: true,
    module_moderation: true,
    captcha_enabled: false,
    captcha_type: 'emoji',
    captcha_timeout: 60,
    gban_enabled: true,
    welcome_enabled: false,
    tags_enabled: false,
    created_at: '2026-01-01T00:00:00Z',
    is_banned: false,
    triggers_count: 0,
    users_count: 0,
    ...overrides,
  }) as Chat;

const filters: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, filterType: 'group' };
const PAGE_ID = 111;

function makeSnapshot(overrides: Partial<ChatsListSnapshot> = {}): ChatsListSnapshot {
  return {
    items: [chat(1), chat(2)],
    page: 2,
    hasMore: true,
    pagination: { page: 1, limit: 20, total: 5, total_pages: 1 },
    query: 'alpha',
    persistedFilters: filters,
    scrollTop: 340,
    timestamp: Date.now(),
    pageInstanceId: PAGE_ID,
    ...overrides,
  };
}

describe('save/read raw snapshot', () => {
  it('сохранённый снэпшот читается обратно без изменений', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot();
    saveChatsListSnapshot(snapshot, storage);
    expect(readChatsListSnapshot(storage)).toEqual(snapshot);
  });

  it('пустое хранилище -- null', () => {
    expect(readChatsListSnapshot(fakeStorage())).toBeNull();
  });

  it('битый JSON в хранилище -- null, без исключения', () => {
    const storage = fakeStorage();
    storage.setItem('chats_list_snapshot', '{not json');
    expect(readChatsListSnapshot(storage)).toBeNull();
  });
});

describe('loadValidChatsListSnapshot', () => {
  it('валидный, свежий, с совпадающими фильтрами и документом -- возвращается', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + 1000, filters, PAGE_ID, storage);
    expect(loaded).toEqual(snapshot);
  });

  it('устаревший (старше 5 минут) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + SNAPSHOT_MAX_AGE_MS + 1, filters, PAGE_ID, storage);
    expect(loaded).toBeNull();
  });

  it('ровно на границе возраста -- ещё валиден', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + SNAPSHOT_MAX_AGE_MS, filters, PAGE_ID, storage);
    expect(loaded).toEqual(snapshot);
  });

  it('несовпадающие фильтры (сменили фильтр в другой вкладке/сессии) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000, persistedFilters: filters });
    saveChatsListSnapshot(snapshot, storage);

    const otherFilters: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, filterType: 'channel' };
    const loaded = loadValidChatsListSnapshot(1000, otherFilters, PAGE_ID, storage);
    expect(loaded).toBeNull();
  });

  it('снэпшот из другого документа (между сохранением и загрузкой был жёсткий reload) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000, pageInstanceId: PAGE_ID });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000, filters, PAGE_ID + 1, storage);
    expect(loaded).toBeNull();
  });

  it('нет снэпшота -- null', () => {
    expect(loadValidChatsListSnapshot(Date.now(), filters, PAGE_ID, fakeStorage())).toBeNull();
  });
});

describe('invalidateChatsListSnapshot', () => {
  it('удаляет снэпшот из хранилища', () => {
    const storage = fakeStorage();
    saveChatsListSnapshot(makeSnapshot(), storage);
    invalidateChatsListSnapshot(storage);
    expect(readChatsListSnapshot(storage)).toBeNull();
  });

  it('на пустом хранилище не падает', () => {
    expect(() => invalidateChatsListSnapshot(fakeStorage())).not.toThrow();
  });
});

describe('removeChatFromSnapshot', () => {
  it('убирает чат по id из items и уменьшает total', () => {
    const snapshot = makeSnapshot({
      items: [chat(1), chat(2), chat(3)],
      pagination: { page: 1, limit: 20, total: 3, total_pages: 1 },
    });
    const result = removeChatFromSnapshot(snapshot, 2);
    expect(result.items.map((c) => c.id)).toEqual([1, 3]);
    expect(result.pagination?.total).toBe(2);
  });

  it('не трогает total, если чата с таким id нет', () => {
    const snapshot = makeSnapshot({
      items: [chat(1), chat(2)],
      pagination: { page: 1, limit: 20, total: 2, total_pages: 1 },
    });
    const result = removeChatFromSnapshot(snapshot, 999);
    expect(result.items.map((c) => c.id)).toEqual([1, 2]);
    expect(result.pagination?.total).toBe(2);
  });

  it('total не уходит в минус, если pagination уже некорректна', () => {
    const snapshot = makeSnapshot({
      items: [chat(1)],
      pagination: { page: 1, limit: 20, total: 0, total_pages: 1 },
    });
    const result = removeChatFromSnapshot(snapshot, 1);
    expect(result.pagination?.total).toBe(0);
  });

  it('является чистой функцией -- не мутирует исходный снэпшот', () => {
    const snapshot = makeSnapshot({ items: [chat(1), chat(2)] });
    const original = JSON.parse(JSON.stringify(snapshot));
    removeChatFromSnapshot(snapshot, 1);
    expect(snapshot).toEqual(original);
  });

  it('без pagination (null) -- просто убирает из items', () => {
    const snapshot = makeSnapshot({ items: [chat(1), chat(2)], pagination: null });
    const result = removeChatFromSnapshot(snapshot, 1);
    expect(result.items.map((c) => c.id)).toEqual([2]);
    expect(result.pagination).toBeNull();
  });
});

describe('removeChatFromStoredSnapshot', () => {
  it('обновляет снэпшот в хранилище без учёта срока годности', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({
      items: [chat(1), chat(2)],
      pagination: { page: 1, limit: 20, total: 2, total_pages: 1 },
      timestamp: Date.now() - SNAPSHOT_MAX_AGE_MS * 10, // давно просрочен, но чат всё равно должен уйти
    });
    saveChatsListSnapshot(snapshot, storage);

    removeChatFromStoredSnapshot(1, storage);

    const raw = readChatsListSnapshot(storage);
    expect(raw?.items.map((c) => c.id)).toEqual([2]);
  });

  it('нет снэпшота -- no-op, без исключения', () => {
    expect(() => removeChatFromStoredSnapshot(1, fakeStorage())).not.toThrow();
  });
});

describe('buildChatsListSnapshot', () => {
  it('проставляет текущую метку времени, переданный pageInstanceId и сохраняет остальные поля как есть', () => {
    const input = {
      items: [chat(1)],
      page: 1,
      hasMore: false,
      pagination: null,
      query: '',
      persistedFilters: filters,
      scrollTop: 0,
    };
    const before = Date.now();
    const result = buildChatsListSnapshot(input, PAGE_ID);
    const after = Date.now();

    expect(result.items).toBe(input.items);
    expect(result.pageInstanceId).toBe(PAGE_ID);
    expect(result.timestamp).toBeGreaterThanOrEqual(before);
    expect(result.timestamp).toBeLessThanOrEqual(after);
  });

  it('без явного pageInstanceId берёт его из performance.timeOrigin', () => {
    const input = {
      items: [],
      page: 1,
      hasMore: false,
      pagination: null,
      query: '',
      persistedFilters: filters,
      scrollTop: 0,
    };
    const result = buildChatsListSnapshot(input);
    expect(result.pageInstanceId).toBe(performance.timeOrigin);
  });
});
