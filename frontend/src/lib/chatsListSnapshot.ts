// Снэпшот списка чатов для восстановления при возврате со страницы конкретного чата:
// загруженные страницы, поиск, фильтры и позиция скролла контейнера `<main>` Layout'а.
//
// sessionStorage вместо zustand-стора: список и так уже хранит фильтры напрямую в
// sessionStorage (см. Chats.tsx), а снэпшот нужен ровно на один "туда и обратно" --
// заводить отдельный persist-стор ради одного среза состояния было бы избыточно.

import type { Chat, Pagination } from '../types';
import { chatsFiltersSignature, type ChatsFiltersState } from './chatsFilters';

export const CHATS_LIST_SNAPSHOT_KEY = 'chats_list_snapshot';
/** Снэпшот старше 5 минут считается протухшим -- показываем свежую загрузку вместо него. */
export const SNAPSHOT_MAX_AGE_MS = 5 * 60 * 1000;
/** id элемента `<main>` в Layout -- единственный скроллящийся контейнер страниц. */
export const MAIN_SCROLL_ELEMENT_ID = 'app-main-scroll';

export interface ChatsListSnapshot {
  items: Chat[];
  page: number;
  hasMore: boolean;
  pagination: Pagination | null;
  query: string;
  persistedFilters: ChatsFiltersState;
  scrollTop: number;
  timestamp: number;
}

/** Минимальный интерфейс Storage -- позволяет тестировать модуль без jsdom/sessionStorage. */
export interface SnapshotStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function defaultStorage(): SnapshotStorage {
  return sessionStorage;
}

function isChatsListSnapshot(value: unknown): value is ChatsListSnapshot {
  if (!value || typeof value !== 'object') return false;
  const obj = value as Record<string, unknown>;
  return (
    Array.isArray(obj.items) &&
    typeof obj.page === 'number' &&
    typeof obj.hasMore === 'boolean' &&
    typeof obj.query === 'string' &&
    typeof obj.timestamp === 'number' &&
    !!obj.persistedFilters &&
    typeof obj.persistedFilters === 'object'
  );
}

/**
 * Собрать снэпшот с текущей меткой времени.
 *
 * Отдельная функция, а не `Date.now()` прямо в компоненте -- react-hooks/purity не
 * пропускает вызов нечистой функции внутри тела компонента (см. openChat в Chats.tsx).
 */
export function buildChatsListSnapshot(input: Omit<ChatsListSnapshot, 'timestamp'>): ChatsListSnapshot {
  return { ...input, timestamp: Date.now() };
}

export function saveChatsListSnapshot(snapshot: ChatsListSnapshot, storage: SnapshotStorage = defaultStorage()): void {
  storage.setItem(CHATS_LIST_SNAPSHOT_KEY, JSON.stringify(snapshot));
}

/** Прочитать снэпшот как есть -- без проверки срока годности и совпадения фильтров. */
export function readChatsListSnapshot(storage: SnapshotStorage = defaultStorage()): ChatsListSnapshot | null {
  const raw = storage.getItem(CHATS_LIST_SNAPSHOT_KEY);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isChatsListSnapshot(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Прочитать снэпшот, пригодный для восстановления списка прямо сейчас.
 *
 * Отклоняется, если: снэпшота нет, он старше SNAPSHOT_MAX_AGE_MS, либо набор фильтров
 * (без строки поиска -- она в снэпшоте своя) с тех пор поменялся, и показывать под
 * текущими чипами старую выдачу было бы неверно.
 */
export function loadValidChatsListSnapshot(
  now: number,
  currentPersistedFilters: ChatsFiltersState,
  storage: SnapshotStorage = defaultStorage(),
): ChatsListSnapshot | null {
  const snapshot = readChatsListSnapshot(storage);
  if (!snapshot) return null;
  if (now - snapshot.timestamp > SNAPSHOT_MAX_AGE_MS) return null;
  if (chatsFiltersSignature(snapshot.persistedFilters) !== chatsFiltersSignature(currentPersistedFilters)) return null;
  return snapshot;
}

export function invalidateChatsListSnapshot(storage: SnapshotStorage = defaultStorage()): void {
  storage.removeItem(CHATS_LIST_SNAPSHOT_KEY);
}

/**
 * Убрать чат из снэпшота (чистая функция, снэпшот не мутируется).
 *
 * Нужно после "Выйти из чата": если не почистить, чат из которого бот только что вышел
 * будет мгновенно "воскресать" при возврате на список из восстановленного снэпшота.
 */
export function removeChatFromSnapshot(snapshot: ChatsListSnapshot, chatId: number): ChatsListSnapshot {
  const hadChat = snapshot.items.some((c) => c.id === chatId);
  const items = snapshot.items.filter((c) => c.id !== chatId);
  const pagination =
    snapshot.pagination && hadChat
      ? { ...snapshot.pagination, total: Math.max(0, snapshot.pagination.total - 1) }
      : snapshot.pagination;

  return { ...snapshot, items, pagination };
}

/** Side-effect обёртка над removeChatFromSnapshot: читает, чистит и сохраняет обратно (или no-op, если снэпшота нет). */
export function removeChatFromStoredSnapshot(chatId: number, storage: SnapshotStorage = defaultStorage()): void {
  const snapshot = readChatsListSnapshot(storage);
  if (!snapshot) return;
  saveChatsListSnapshot(removeChatFromSnapshot(snapshot, chatId), storage);
}

/** Реальная перезагрузка страницы (F5/Ctrl+R) -- в отличие от SPA-навигации "назад", должна начинать со свежей загрузки. */
export function isHardReload(navigationType: string | undefined): boolean {
  return navigationType === 'reload';
}
