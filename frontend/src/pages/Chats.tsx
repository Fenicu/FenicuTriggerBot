import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat, PaginatedResponse } from '../types';
import Breadcrumbs from '../components/Breadcrumbs';
import Skeleton from '../components/Skeleton';
import ChatAvatar from '../components/ChatAvatar';
import FilterBar from '../components/ui/FilterBar';
import FilterChip from '../components/ui/FilterChip';
import Badge from '../components/ui/Badge';
import { useTelegramBackButton } from '../hooks/useTelegramBackButton';
import {
  BOT_REMOVED_LABEL,
  BOT_REMOVED_TOOLTIP,
  chatsListSignature,
  DEFAULT_CHATS_FILTERS,
  parseStoredChatsFilters,
  trustFilterToParam,
  type ChatsFiltersState,
  type TrustFilter,
} from '../lib/chatsFilters';
import {
  buildChatsListSnapshot,
  getCurrentPageInstanceId,
  invalidateChatsListSnapshot,
  loadValidChatsListSnapshot,
  MAIN_SCROLL_ELEMENT_ID,
  saveChatsListSnapshot,
} from '../lib/chatsListSnapshot';

const STORAGE_KEY = 'chats_filters';

const CHAT_TYPE_LABELS: Record<string, string> = {
  supergroup: 'Супергруппа',
  group: 'Группа',
  channel: 'Канал',
  private: 'Личный',
};

const getInitialFilters = (): ChatsFiltersState => {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) return parseStoredChatsFilters(JSON.parse(saved));
  } catch (e) {
    console.error('Failed to parse saved filters', e);
  }
  return { ...DEFAULT_CHATS_FILTERS };
};

const ChatsPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  // Корневая вкладка -- нативную кнопку "Назад" Telegram прячем
  useTelegramBackButton(false);
  const [error, setError] = useState<string | null>(null);

  // Решение "восстанавливаем список или грузим с нуля" принимается один раз при монтировании.
  // pageInstanceId сам решает "не было ли жёсткой перезагрузки", location.key -- "вернулись ли
  // именно на эту запись истории, а не пришли на /chats каким-то другим путём" (см. chatsListSnapshot.ts).
  const [restore] = useState(() => {
    const filters = getInitialFilters();
    const snapshot = loadValidChatsListSnapshot(Date.now(), filters, getCurrentPageInstanceId(), location.key);
    return { filters, snapshot };
  });

  const [chats, setChats] = useState<Chat[]>(restore.snapshot?.items ?? []);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState(restore.snapshot?.query ?? '');

  const [sortBy, setSortBy] = useState<string>(restore.filters.sortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(restore.filters.sortOrder);

  const [includePrivate, setIncludePrivate] = useState(restore.filters.includePrivate);
  const [filterActive, setFilterActive] = useState<boolean | null>(restore.filters.filterActive);
  const [trustFilter, setTrustFilter] = useState<TrustFilter>(restore.filters.trustFilter);
  const [filterBanned, setFilterBanned] = useState<boolean | null>(restore.filters.filterBanned);
  const [filterType, setFilterType] = useState<string | null>(restore.filters.filterType);

  const [page, setPage] = useState(restore.snapshot?.page ?? 1);
  const [hasMore, setHasMore] = useState(restore.snapshot?.hasMore ?? true);

  const requestIdRef = useRef(0);
  // Пока не null -- эффект ниже должен пропустить очередной fetch (данные уже восстановлены из снэпшота).
  // Как только реально меняется что-то из поиска/фильтров/сортировки, флаг гасится безвозвратно.
  const suppressNextFetchRef = useRef(restore.snapshot !== null);
  // Какому query+фильтрам сейчас реально соответствует chats -- обновляется только на успешном
  // fetchChats(true). Пока не обновился (идёт debounce/сеть, либо последний fetch упал), chats может
  // не совпадать с текущими query/фильтрами -- openChat не должен в этот момент сохранять снэпшот
  // с рассинхроном между items и заявленными в нём фильтрами.
  const loadedSignatureRef = useRef(chatsListSignature(restore.snapshot?.query ?? '', restore.filters));
  // Скролл восстанавливаем один раз, после того как восстановленные items реально отрисуются.
  const pendingScrollRestoreRef = useRef<number | null>(restore.snapshot?.scrollTop ?? null);

  useEffect(() => {
    const state: ChatsFiltersState = {
      sortBy,
      sortOrder,
      includePrivate,
      filterActive,
      trustFilter,
      filterBanned,
      filterType,
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [sortBy, sortOrder, includePrivate, filterActive, trustFilter, filterBanned, filterType]);

  // Восстановление скролла ждёт, пока восстановленные из снэпшота items реально попадут в DOM.
  useLayoutEffect(() => {
    if (pendingScrollRestoreRef.current === null) return;
    const target = pendingScrollRestoreRef.current;
    pendingScrollRestoreRef.current = null;
    const el = document.getElementById(MAIN_SCROLL_ELEMENT_ID);
    if (el) el.scrollTop = target;
  }, [chats]);

  const resetFilters = () => {
    setSortBy(DEFAULT_CHATS_FILTERS.sortBy);
    setSortOrder(DEFAULT_CHATS_FILTERS.sortOrder);
    setIncludePrivate(DEFAULT_CHATS_FILTERS.includePrivate);
    setFilterActive(DEFAULT_CHATS_FILTERS.filterActive);
    setTrustFilter(DEFAULT_CHATS_FILTERS.trustFilter);
    setFilterBanned(DEFAULT_CHATS_FILTERS.filterBanned);
    setFilterType(DEFAULT_CHATS_FILTERS.filterType);
    sessionStorage.removeItem(STORAGE_KEY);
    invalidateChatsListSnapshot();
  };

  const currentFilters = (): ChatsFiltersState => ({
    sortBy, sortOrder, includePrivate, filterActive, trustFilter, filterBanned, filterType,
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const buildParams = (page: number): any => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const params: any = {
      page,
      limit: 20,
      query,
      include_private: includePrivate,
      sort_by: sortBy,
      sort_order: sortOrder,
    };
    if (filterActive !== null) params.is_active = filterActive;
    const isTrustedParam = trustFilterToParam(trustFilter);
    if (isTrustedParam !== undefined) params.is_trusted = isTrustedParam;
    if (filterBanned !== null) params.is_banned = filterBanned;
    if (filterType) params.chat_type = filterType;
    return params;
  };

  const openChat = (chatId: number) => {
    const filters = currentFilters();
    const currentSignature = chatsListSignature(query, filters);

    if (currentSignature === loadedSignatureRef.current) {
      saveChatsListSnapshot(
        buildChatsListSnapshot({
          items: chats,
          page,
          hasMore,
          query,
          persistedFilters: filters,
          // Читаем DOM напрямую, а не ref, обновляемый листенером скролла -- надёжнее
          // на случай, если листенер почему-то не успел/не был навешен к этому моменту.
          scrollTop: document.getElementById(MAIN_SCROLL_ELEMENT_ID)?.scrollTop ?? 0,
          listLocationKey: location.key,
        }),
      );
    } else {
      // chats ещё не догнал debounce/сеть под новые query/фильтры (или последний fetch
      // упал) -- сохранить сейчас значило бы записать снэпшот с рассинхроном между items
      // и заявленными в нём фильтрами. Лучше без снэпшота вовсе, чем с неверным.
      invalidateChatsListSnapshot();
    }
    navigate(`/chats/${chatId}`);
  };

  const fetchChats = async (reset = false) => {
    if (loading && !reset) return;
    const requestId = ++requestIdRef.current;
    const requestSignature = chatsListSignature(query, currentFilters());
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<Chat>>('/chats', { params: buildParams(currentPage) });

      // Игнорируем устаревший ответ, если за время запроса ушёл более новый
      if (requestIdRef.current !== requestId) return;

      if (reset) {
        setChats(res.data.items);
        loadedSignatureRef.current = requestSignature;
      } else {
        setChats((prev) => {
          const seen = new Set(prev.map((c) => c.id));
          return [...prev, ...res.data.items.filter((c) => !seen.has(c.id))];
        });
      }

      setHasMore(currentPage < res.data.pagination.total_pages);
      setPage(currentPage + 1);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      if (requestIdRef.current !== requestId) return;
      console.error(error);
      setError(error.response?.data?.detail || error.message || 'Не удалось загрузить чаты');
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  };

  // Сразу после восстановления список показываем мгновенно (items+скролл из снэпшота), но данные
  // могли устареть, пока пользователь был на странице чата: доверие/бан/счётчики поменялись, либо
  // сортировка "По активности" уже отдаёт чаты в другом порядке (updated_at обновляется при любой
  // правке настроек чата). Тихо перезапрашиваем уже загруженные страницы 1..N и подменяем items
  // без лоадера и без прыжка скролла; при ошибке просто оставляем восстановленный список как есть.
  useEffect(() => {
    if (!restore.snapshot) return;
    const loadedPages = restore.snapshot.page - 1;
    if (loadedPages < 1) return;

    const requestId = ++requestIdRef.current;
    (async () => {
      try {
        const responses = await Promise.all(
          Array.from({ length: loadedPages }, (_, i) =>
            apiClient.get<PaginatedResponse<Chat>>('/chats', { params: buildParams(i + 1) }),
          ),
        );
        // Конкурирующее действие (смена фильтра, "Показать ещё") уже победило -- наш результат не нужен
        if (requestIdRef.current !== requestId) return;

        const seen = new Set<number>();
        const merged: Chat[] = [];
        for (const res of responses) {
          for (const item of res.data.items) {
            if (!seen.has(item.id)) {
              seen.add(item.id);
              merged.push(item);
            }
          }
        }
        const lastPagination = responses[responses.length - 1].data.pagination;
        setChats(merged);
        setHasMore(loadedPages < lastPagination.total_pages);
      } catch {
        // сеть моргнула -- оставляем восстановленный (пусть местами и устаревший) список как есть
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const signature = chatsListSignature(query, currentFilters());

    // Первый рендер после восстановления снэпшота: набор фильтров и поиск ещё те же, что были
    // сохранены -- значит, это не пользовательское изменение, а сам факт монтирования. Не бьём
    // fetch'ем page=1 по уже восстановленному списку (его свежесть чинит фоновый рефреш выше).
    // Как только signature разойдётся с loadedSignatureRef (реальное изменение фильтра/поиска),
    // флаг гасится навсегда -- см. suppressNextFetchRef.
    if (suppressNextFetchRef.current && signature === loadedSignatureRef.current) {
      return;
    }
    suppressNextFetchRef.current = false;
    invalidateChatsListSnapshot();

    const timer = setTimeout(() => {
      fetchChats(true);
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, includePrivate, sortBy, sortOrder, filterActive, trustFilter, filterBanned, filterType]);

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <Breadcrumbs />
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Чаты</h1>
      </div>

      {error && (
        <div className="bg-danger-soft text-danger p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <FilterBar
        search={query}
        onSearchChange={setQuery}
        searchPlaceholder="Поиск чатов…"
        sortOrder={sortOrder}
        onSortOrderChange={(v) => setSortOrder(v)}
      >
        <FilterChip active={!filterType && filterActive === null && trustFilter === 'all' && filterBanned === null && !includePrivate} onClick={resetFilters}>Все чаты</FilterChip>
        <FilterChip active={filterType === 'supergroup'} onClick={() => setFilterType(filterType === 'supergroup' ? null : 'supergroup')}>Супергруппа</FilterChip>
        <FilterChip active={filterType === 'group'} onClick={() => setFilterType(filterType === 'group' ? null : 'group')}>Группа</FilterChip>
        <FilterChip active={filterType === 'channel'} onClick={() => setFilterType(filterType === 'channel' ? null : 'channel')}>Канал</FilterChip>
        <FilterChip active={trustFilter === 'trusted'} onClick={() => setTrustFilter(trustFilter === 'trusted' ? 'all' : 'trusted')}>Доверенные</FilterChip>
        <FilterChip active={trustFilter === 'untrusted'} onClick={() => setTrustFilter(trustFilter === 'untrusted' ? 'all' : 'untrusted')}>Без доверия</FilterChip>
        <FilterChip active={filterBanned === true} onClick={() => setFilterBanned(filterBanned === true ? null : true)}>Забанен</FilterChip>
        <FilterChip active={filterActive === false} onClick={() => setFilterActive(filterActive === false ? null : false)}>{BOT_REMOVED_LABEL}</FilterChip>
        <FilterChip active={includePrivate} onClick={() => setIncludePrivate(!includePrivate)}>Личный</FilterChip>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="ml-auto px-2.5 py-1.5 rounded-full text-xs font-medium bg-elevated text-hint border border-border appearance-none cursor-pointer"
        >
          <option value="updated_at">По активности</option>
          <option value="created_at">По дате</option>
          <option value="users_count">По участникам</option>
          <option value="triggers_count">По триггерам</option>
          <option value="title">По названию</option>
        </select>
      </FilterBar>

      {/* Desktop Table View */}
      <div className="hidden md:block bg-surface rounded-[14px] border border-border overflow-hidden">
        <table className="w-full text-left border-collapse">
            <thead>
                <tr className="border-b border-border text-hint text-sm">
                    <th className="p-4 font-medium">Чат</th>
                    <th className="p-4 font-medium">ID</th>
                    <th className="p-4 font-medium">Тип</th>
                    <th className="p-4 font-medium">Статистика</th>
                    <th className="p-4 font-medium">Статус</th>
                </tr>
            </thead>
            <tbody>
                {loading && chats.length === 0 ? (
                    Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="border-b border-border last:border-none">
                            <td className="p-4"><div className="flex items-center gap-3"><Skeleton className="w-10 h-10 rounded-full" /><div className="space-y-2"><Skeleton className="w-32 h-4" /><Skeleton className="w-20 h-3" /></div></div></td>
                            <td className="p-4"><Skeleton className="w-20 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-16 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-24 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-20 h-4" /></td>
                        </tr>
                    ))
                ) : (
                    chats.map((chat) => (
                        <tr
                            key={chat.id}
                            onClick={() => openChat(chat.id)}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openChat(chat.id); } }}
                            tabIndex={0}
                            className="border-b border-border last:border-none hover:bg-elevated/50 cursor-pointer transition-colors"
                        >
                            <td className="p-4">
                                <div className="flex items-center gap-3">
                                    <ChatAvatar chatId={chat.id} photoId={chat.photo_id} />
                                    <div>
                                        <div className="font-bold">{chat.title || chat.username || `Чат ${chat.id}`}</div>
                                        <div className="text-xs text-hint">
                                            {chat.username ? `@${chat.username}` : ''}
                                        </div>
                                    </div>
                                </div>
                            </td>
                            <td className="p-4 text-sm font-mono text-hint">{chat.id}</td>
                            <td className="p-4 text-sm">{chat.type ? (CHAT_TYPE_LABELS[chat.type] ?? chat.type) : ''}</td>
                            <td className="p-4 text-sm">
                                <div className="flex gap-3">
                                    <span title="Триггеры">{chat.triggers_count} ⚡</span>
                                    <span title="Пользователи">{chat.users_count} 👥</span>
                                </div>
                            </td>
                            <td className="p-4">
                                <div className="flex gap-1 flex-wrap">
                                    {chat.is_trusted && <Badge variant="green">Доверенный</Badge>}
                                    {chat.is_banned && <Badge variant="red">Забанен</Badge>}
                                    {!chat.is_active && (
                                        <Badge variant="gray" title={BOT_REMOVED_TOOLTIP}>{BOT_REMOVED_LABEL}</Badge>
                                    )}
                                </div>
                            </td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
        {chats.length === 0 && !loading && (
            <div className="p-8 text-center text-hint">Чаты не найдены</div>
        )}
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden flex flex-col gap-2">
        {loading && chats.length === 0 ? (
             Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-surface border border-border p-3 rounded-[14px] space-y-3">
                    <div className="flex items-center gap-3">
                        <Skeleton className="w-10 h-10 rounded-full" />
                        <div className="flex-1 space-y-2">
                            <Skeleton className="w-3/4 h-4" />
                            <Skeleton className="w-1/2 h-3" />
                        </div>
                    </div>
                    <Skeleton className="w-full h-6" />
                </div>
             ))
        ) : (
            chats.map((chat) => (
            <div
                key={chat.id}
                onClick={() => openChat(chat.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openChat(chat.id); } }}
                role="button"
                tabIndex={0}
                className="bg-surface p-3 rounded-[14px] cursor-pointer border border-border"
            >
                <div className="flex items-center gap-3 mb-2">
                    <ChatAvatar chatId={chat.id} photoId={chat.photo_id} />
                    <div>
                        <div className="font-bold">
                        {chat.title || chat.username || `Чат ${chat.id}`}
                        </div>
                        <div className="text-hint text-sm">
                        {chat.type && <span>{CHAT_TYPE_LABELS[chat.type] ?? chat.type} • </span>}
                        Язык: {chat.language_code}
                        </div>
                    </div>
                </div>
                <div className="text-hint text-sm mb-2">
                    Триггеры: {chat.triggers_count} • Пользователи: {chat.users_count}
                </div>
                <div className="mt-1 flex gap-1 flex-wrap">
                    {chat.is_trusted && <Badge variant="green">Доверенный</Badge>}
                    {chat.is_banned && <Badge variant="red">Забанен</Badge>}
                    {!chat.is_active && (
                        <Badge variant="gray" title={BOT_REMOVED_TOOLTIP}>{BOT_REMOVED_LABEL}</Badge>
                    )}
                </div>
            </div>
            ))
        )}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchChats(false)}
            disabled={loading}
            className="w-full p-3 mt-4 text-button font-medium hover:bg-elevated/50 rounded-lg transition-colors"
        >
            {loading ? 'Загрузка…' : 'Показать ещё'}
        </button>
      )}
    </div>
  );
};

export default ChatsPage;
