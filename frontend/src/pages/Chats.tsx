import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  DEFAULT_CHATS_FILTERS,
  parseStoredChatsFilters,
  trustFilterToParam,
  type ChatsFiltersState,
  type TrustFilter,
} from '../lib/chatsFilters';

const STORAGE_KEY = 'chats_filters';

const CHAT_TYPE_LABELS: Record<string, string> = {
  supergroup: 'Супергруппа',
  group: 'Группа',
  channel: 'Канал',
  private: 'Личный',
};

/** Короткая версия -- полная фраза "Бот удалён из чата" плохо влезает в чип/бейдж на мобильной ширине. */
const BOT_REMOVED_LABEL = 'Бот удалён';
const BOT_REMOVED_TOOLTIP =
  'Бот исключён, вышел или потерял права -- модерация и триггеры в чате не работают';

const ChatsPage: React.FC = () => {
  const navigate = useNavigate();
  // Корневая вкладка -- нативную кнопку "Назад" Telegram прячем
  useTelegramBackButton(false);
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const getInitialFilters = (): ChatsFiltersState => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) return parseStoredChatsFilters(JSON.parse(saved));
    } catch (e) {
      console.error('Failed to parse saved filters', e);
    }
    return { ...DEFAULT_CHATS_FILTERS };
  };

  const [initialFilters] = useState(getInitialFilters);

  const [sortBy, setSortBy] = useState<string>(initialFilters.sortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialFilters.sortOrder);

  const [includePrivate, setIncludePrivate] = useState(initialFilters.includePrivate);
  const [filterActive, setFilterActive] = useState<boolean | null>(initialFilters.filterActive);
  const [trustFilter, setTrustFilter] = useState<TrustFilter>(initialFilters.trustFilter);
  const [filterBanned, setFilterBanned] = useState<boolean | null>(initialFilters.filterBanned);
  const [filterType, setFilterType] = useState<string | null>(initialFilters.filterType);

  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

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

  const resetFilters = () => {
    setSortBy(DEFAULT_CHATS_FILTERS.sortBy);
    setSortOrder(DEFAULT_CHATS_FILTERS.sortOrder);
    setIncludePrivate(DEFAULT_CHATS_FILTERS.includePrivate);
    setFilterActive(DEFAULT_CHATS_FILTERS.filterActive);
    setTrustFilter(DEFAULT_CHATS_FILTERS.trustFilter);
    setFilterBanned(DEFAULT_CHATS_FILTERS.filterBanned);
    setFilterType(DEFAULT_CHATS_FILTERS.filterType);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const requestIdRef = useRef(0);

  const fetchChats = async (reset = false) => {
    if (loading && !reset) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const params: any = {
        page: currentPage,
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

      const res = await apiClient.get<PaginatedResponse<Chat>>('/chats', { params });

      // Игнорируем устаревший ответ, если за время запроса ушёл более новый
      if (requestIdRef.current !== requestId) return;

      if (reset) {
        setChats(res.data.items);
      } else {
        setChats((prev) => [...prev, ...res.data.items]);
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

  useEffect(() => {
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
                            onClick={() => navigate(`/chats/${chat.id}`)}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/chats/${chat.id}`); } }}
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
                onClick={() => navigate(`/chats/${chat.id}`)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/chats/${chat.id}`); } }}
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
