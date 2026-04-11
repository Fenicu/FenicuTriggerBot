import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat, PaginatedResponse } from '../types';
import Breadcrumbs from '../components/Breadcrumbs';
import Skeleton from '../components/Skeleton';
import ChatAvatar from '../components/ChatAvatar';
import FilterBar from '../components/ui/FilterBar';
import FilterChip from '../components/ui/FilterChip';
import Badge from '../components/ui/Badge';

const STORAGE_KEY = 'chats_filters';

const ChatsPage: React.FC = () => {
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const getInitialState = () => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch (e) {
      console.error('Failed to parse saved filters', e);
    }
    return {
      sortBy: 'updated_at',
      sortOrder: 'desc',
      includePrivate: false,
      filterActive: null,
      filterTrusted: null,
      filterBanned: null,
      filterType: null
    };
  };

  const [initialState] = useState(getInitialState);

  const [sortBy, setSortBy] = useState<string>(initialState.sortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialState.sortOrder);

  const [includePrivate, setIncludePrivate] = useState(initialState.includePrivate);
  const [filterActive, setFilterActive] = useState<boolean | null>(initialState.filterActive);
  const [filterTrusted, setFilterTrusted] = useState<boolean | null>(initialState.filterTrusted);
  const [filterBanned, setFilterBanned] = useState<boolean | null>(initialState.filterBanned);
  const [filterType, setFilterType] = useState<string | null>(initialState.filterType);

  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  useEffect(() => {
    const state = {
      sortBy,
      sortOrder,
      includePrivate,
      filterActive,
      filterTrusted,
      filterBanned,
      filterType
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [sortBy, sortOrder, includePrivate, filterActive, filterTrusted, filterBanned, filterType]);

  const resetFilters = () => {
    setSortBy('updated_at');
    setSortOrder('desc');
    setIncludePrivate(false);
    setFilterActive(null);
    setFilterTrusted(null);
    setFilterBanned(null);
    setFilterType(null);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const fetchChats = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const params: any = {
        page: currentPage,
        limit: 20,
        query,
        include_private: includePrivate,
        sort_by: sortBy,
        sort_order: sortOrder,
      };

      if (filterActive !== null) params.is_active = filterActive;
      if (filterTrusted !== null) params.is_trusted = filterTrusted;
      if (filterBanned !== null) params.is_banned = filterBanned;
      if (filterType) params.chat_type = filterType;

      const res = await apiClient.get<PaginatedResponse<Chat>>('/chats', { params });

      if (reset) {
        setChats(res.data.items);
      } else {
        setChats((prev) => [...prev, ...res.data.items]);
      }

      setHasMore(currentPage < res.data.pagination.total_pages);
      setPage(currentPage + 1);
    } catch (error: any) {
      console.error(error);
      setError(error.response?.data?.detail || error.message || 'Failed to load chats');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChats(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, includePrivate, sortBy, sortOrder, filterActive, filterTrusted, filterBanned, filterType]);

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <Breadcrumbs />
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Chats</h1>
      </div>

      {error && (
        <div className="bg-red-500/10 text-red-500 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <FilterBar
        search={query}
        onSearchChange={setQuery}
        searchPlaceholder="Search chats..."
        sortOrder={sortOrder}
        onSortOrderChange={(v) => setSortOrder(v)}
      >
        <FilterChip active={!filterType && filterActive === null && filterTrusted === null && filterBanned === null && !includePrivate} onClick={resetFilters}>All</FilterChip>
        <FilterChip active={filterType === 'supergroup'} onClick={() => setFilterType(filterType === 'supergroup' ? null : 'supergroup')}>Supergroup</FilterChip>
        <FilterChip active={filterType === 'group'} onClick={() => setFilterType(filterType === 'group' ? null : 'group')}>Group</FilterChip>
        <FilterChip active={filterType === 'channel'} onClick={() => setFilterType(filterType === 'channel' ? null : 'channel')}>Channel</FilterChip>
        <FilterChip active={filterTrusted === true} onClick={() => setFilterTrusted(filterTrusted === true ? null : true)}>Trusted</FilterChip>
        <FilterChip active={filterBanned === true} onClick={() => setFilterBanned(filterBanned === true ? null : true)}>Banned</FilterChip>
        <FilterChip active={includePrivate} onClick={() => setIncludePrivate(!includePrivate)}>Private</FilterChip>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="ml-auto px-2.5 py-1.5 rounded-full text-xs font-medium bg-elevated text-hint border border-[#3f3f46] appearance-none cursor-pointer"
        >
          <option value="updated_at">By Activity</option>
          <option value="created_at">By Date</option>
          <option value="users_count">By Users</option>
          <option value="triggers_count">By Triggers</option>
          <option value="title">By Title</option>
        </select>
      </FilterBar>

      {/* Desktop Table View */}
      <div className="hidden md:block bg-surface rounded-[14px] border border-border overflow-hidden">
        <table className="w-full text-left border-collapse">
            <thead>
                <tr className="border-b border-border text-hint text-sm">
                    <th className="p-4 font-medium">Chat</th>
                    <th className="p-4 font-medium">ID</th>
                    <th className="p-4 font-medium">Type</th>
                    <th className="p-4 font-medium">Stats</th>
                    <th className="p-4 font-medium">Status</th>
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
                                        <div className="font-bold">{chat.title || chat.username || `Chat ${chat.id}`}</div>
                                        <div className="text-xs text-hint">
                                            {chat.username ? `@${chat.username}` : ''}
                                        </div>
                                    </div>
                                </div>
                            </td>
                            <td className="p-4 text-sm font-mono text-hint">{chat.id}</td>
                            <td className="p-4 capitalize text-sm">{chat.type}</td>
                            <td className="p-4 text-sm">
                                <div className="flex gap-3">
                                    <span title="Triggers">{chat.triggers_count} ⚡</span>
                                    <span title="Users">{chat.users_count} 👥</span>
                                </div>
                            </td>
                            <td className="p-4">
                                <div className="flex gap-1 flex-wrap">
                                    {chat.is_trusted && <Badge variant="green">Trusted</Badge>}
                                    {chat.is_banned && <Badge variant="red">Banned</Badge>}
                                    {!chat.is_active && <Badge variant="gray">Inactive</Badge>}
                                </div>
                            </td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
        {chats.length === 0 && !loading && (
            <div className="p-8 text-center text-hint">No chats found</div>
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
                        {chat.title || chat.username || `Chat ${chat.id}`}
                        </div>
                        <div className="text-hint text-sm">
                        {chat.type && <span className="capitalize">{chat.type} • </span>}
                        Lang: {chat.language_code}
                        </div>
                    </div>
                </div>
                <div className="text-hint text-sm mb-2">
                    Triggers: {chat.triggers_count} • Users: {chat.users_count}
                </div>
                <div className="mt-1 flex gap-1 flex-wrap">
                    {chat.is_trusted && <Badge variant="green">Trusted</Badge>}
                    {chat.is_banned && <Badge variant="red">Banned</Badge>}
                    {!chat.is_active && <Badge variant="gray">Inactive</Badge>}
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
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default ChatsPage;
