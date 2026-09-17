// Снэпшот списка чатов для восстановления при возврате со страницы конкретного чата:
// загруженные страницы, поиск, фильтры и позиция скролла контейнера `<main>` Layout'а.
//
// sessionStorage вместо zustand-стора: список и так уже хранит фильтры напрямую в
// sessionStorage (см. Chats.tsx), а снэпшот нужен ровно на один "туда и обратно" --
// заводить отдельный persist-стор ради одного среза состояния было бы избыточно.

import type { Chat } from '../types';
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
  query: string;
  persistedFilters: ChatsFiltersState;
  scrollTop: number;
  timestamp: number;
  /**
   * `performance.timeOrigin` документа, в котором снэпшот был сохранён.
   *
   * Заменяет собой отдельное "было ли F5" -- та проверка держится на
   * `performance.getEntriesByType('navigation')[0].type`, который не меняется до
   * следующей реальной навигации, поэтому единственный ре-релоуд где угодно в
   * приложении навсегда выключал восстановление до конца вкладки. timeOrigin же
   * меняется РОВНО на реальном reload/переходе и не трогается SPA-навигацией внутри
   * него, так что сравнение "текущий timeOrigin == сохранённый" само по себе даёт
   * нужную семантику без отдельного стейта.
   */
  pageInstanceId: number;
  /**
   * `useLocation().key` записи истории списка чатов на момент сохранения.
   *
   * Без этого снэпшот подхватывался при ЛЮБОМ монтировании ChatsPage в течение 5 минут
   * -- список → чат → вкладка "Пользователи" → вкладка "Чаты" тоже восстанавливал(ся)бы,
   * хотя пользователь не возвращался "назад". React Router выдаёт entry.key заново на
   * каждый push (в т.ч. `navigate('/chats')` после leave-chat) и сохраняет тот же key
   * при переходе назад/вперёд по истории -- то, что нужно для "именно вернулись".
   */
  listLocationKey: string;
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
    typeof obj.pageInstanceId === 'number' &&
    typeof obj.listLocationKey === 'string' &&
    !!obj.persistedFilters &&
    typeof obj.persistedFilters === 'object'
  );
}

/**
 * `performance.timeOrigin` текущего документа -- id "экземпляра страницы" для снэпшота.
 *
 * Отдельная экспортируемая функция, а не `performance.timeOrigin`/`Date.now()` прямо в
 * компоненте -- react-hooks/purity не пропускает вызов нечистой функции внутри тела
 * компонента (см. openChat и восстановление снэпшота в Chats.tsx).
 */
export function getCurrentPageInstanceId(): number {
  return performance.timeOrigin;
}

/** Собрать снэпшот с текущей меткой времени и id текущего документа. */
export function buildChatsListSnapshot(
  input: Omit<ChatsListSnapshot, 'timestamp' | 'pageInstanceId'>,
  pageInstanceId: number = getCurrentPageInstanceId(),
): ChatsListSnapshot {
  return { ...input, timestamp: Date.now(), pageInstanceId };
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
 * Отклоняется, если: снэпшота нет, он старше SNAPSHOT_MAX_AGE_MS, набор фильтров (без
 * строки поиска -- она в снэпшоте своя) с тех пор поменялся, снэпшот сохранён в ДРУГОМ
 * документе (жёсткая перезагрузка страницы между сохранением и восстановлением -- см.
 * pageInstanceId), либо текущая запись истории -- не та, с которой снэпшот сохранён (см.
 * listLocationKey: восстанавливаем только при возврате именно на неё, а не при любом
 * монтировании списка).
 */
export function loadValidChatsListSnapshot(
  now: number,
  currentPersistedFilters: ChatsFiltersState,
  currentPageInstanceId: number,
  currentLocationKey: string,
  storage: SnapshotStorage = defaultStorage(),
): ChatsListSnapshot | null {
  const snapshot = readChatsListSnapshot(storage);
  if (!snapshot) return null;
  if (now - snapshot.timestamp > SNAPSHOT_MAX_AGE_MS) return null;
  if (snapshot.pageInstanceId !== currentPageInstanceId) return null;
  if (snapshot.listLocationKey !== currentLocationKey) return null;
  if (chatsFiltersSignature(snapshot.persistedFilters) !== chatsFiltersSignature(currentPersistedFilters)) return null;
  return snapshot;
}

export function invalidateChatsListSnapshot(storage: SnapshotStorage = defaultStorage()): void {
  storage.removeItem(CHATS_LIST_SNAPSHOT_KEY);
}
