import { describe, expect, it } from 'vitest';

import { DEFAULT_CHATS_FILTERS, type ChatsFiltersState } from './chatsFilters';
import {
  buildChatsListSnapshot,
  invalidateChatsListSnapshot,
  loadValidChatsListSnapshot,
  readChatsListSnapshot,
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
const LOCATION_KEY = 'abc123';

function makeSnapshot(overrides: Partial<ChatsListSnapshot> = {}): ChatsListSnapshot {
  return {
    items: [chat(1), chat(2)],
    page: 2,
    hasMore: true,
    query: 'alpha',
    persistedFilters: filters,
    scrollTop: 340,
    timestamp: Date.now(),
    pageInstanceId: PAGE_ID,
    listLocationKey: LOCATION_KEY,
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
  it('валидный, свежий, с совпадающими фильтрами/документом/локацией -- возвращается', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + 1000, filters, PAGE_ID, LOCATION_KEY, storage);
    expect(loaded).toEqual(snapshot);
  });

  it('устаревший (старше 5 минут) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + SNAPSHOT_MAX_AGE_MS + 1, filters, PAGE_ID, LOCATION_KEY, storage);
    expect(loaded).toBeNull();
  });

  it('ровно на границе возраста -- ещё валиден', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000 });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000 + SNAPSHOT_MAX_AGE_MS, filters, PAGE_ID, LOCATION_KEY, storage);
    expect(loaded).toEqual(snapshot);
  });

  it('несовпадающие фильтры (сменили фильтр в другой вкладке/сессии) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000, persistedFilters: filters });
    saveChatsListSnapshot(snapshot, storage);

    const otherFilters: ChatsFiltersState = { ...DEFAULT_CHATS_FILTERS, filterType: 'channel' };
    const loaded = loadValidChatsListSnapshot(1000, otherFilters, PAGE_ID, LOCATION_KEY, storage);
    expect(loaded).toBeNull();
  });

  it('снэпшот из другого документа (между сохранением и загрузкой был жёсткий reload) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000, pageInstanceId: PAGE_ID });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000, filters, PAGE_ID + 1, LOCATION_KEY, storage);
    expect(loaded).toBeNull();
  });

  it('снэпшот от другой записи истории (пришли не назад, а вперёд/другим путём) -- игнорируется', () => {
    const storage = fakeStorage();
    const snapshot = makeSnapshot({ timestamp: 1000, listLocationKey: LOCATION_KEY });
    saveChatsListSnapshot(snapshot, storage);

    const loaded = loadValidChatsListSnapshot(1000, filters, PAGE_ID, 'different-key', storage);
    expect(loaded).toBeNull();
  });

  it('нет снэпшота -- null', () => {
    expect(loadValidChatsListSnapshot(Date.now(), filters, PAGE_ID, LOCATION_KEY, fakeStorage())).toBeNull();
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

describe('buildChatsListSnapshot', () => {
  it('проставляет текущую метку времени, переданный pageInstanceId и сохраняет остальные поля как есть', () => {
    const input = {
      items: [chat(1)],
      page: 1,
      hasMore: false,
      query: '',
      persistedFilters: filters,
      scrollTop: 0,
      listLocationKey: LOCATION_KEY,
    };
    const before = Date.now();
    const result = buildChatsListSnapshot(input, PAGE_ID);
    const after = Date.now();

    expect(result.items).toBe(input.items);
    expect(result.pageInstanceId).toBe(PAGE_ID);
    expect(result.listLocationKey).toBe(LOCATION_KEY);
    expect(result.timestamp).toBeGreaterThanOrEqual(before);
    expect(result.timestamp).toBeLessThanOrEqual(after);
  });

  it('без явного pageInstanceId берёт его из performance.timeOrigin', () => {
    const input = {
      items: [],
      page: 1,
      hasMore: false,
      query: '',
      persistedFilters: filters,
      scrollTop: 0,
      listLocationKey: LOCATION_KEY,
    };
    const result = buildChatsListSnapshot(input);
    expect(result.pageInstanceId).toBe(performance.timeOrigin);
  });
});
