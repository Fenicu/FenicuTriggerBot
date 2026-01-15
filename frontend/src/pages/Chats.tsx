import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat, PaginatedResponse } from '../types';
import { Search, Filter, ArrowUpDown } from 'lucide-react';

const ChatsPage: React.FC = () => {
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const [sortBy, setSortBy] = useState<string>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const [includePrivate, setIncludePrivate] = useState(false);
  const [filterActive, setFilterActive] = useState<boolean | null>(null);
  const [filterTrusted, setFilterTrusted] = useState<boolean | null>(null);
  const [filterBanned, setFilterBanned] = useState<boolean | null>(null);
  const [filterType, setFilterType] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

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

  const toggleSortOrder = () => {
    setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
  };

  return (
    <div className="p-4">
      {error && (
        <div className="bg-red-500/10 text-red-500 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-2 mb-4">
        <div className="flex gap-2">
          <div className="bg-section-bg rounded-[10px] p-2 px-3 flex items-center flex-1">
            <Search size={20} className="text-hint mr-2" />
            <input
              type="text"
              placeholder="Search chats..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="border-none bg-transparent w-full text-base text-text outline-none"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`bg-section-bg rounded-[10px] px-3 flex items-center justify-center ${showFilters ? 'text-link' : 'text-text'}`}
          >
            <Filter size={20} />
          </button>
        </div>

        {showFilters && (
          <div className="bg-section-bg rounded-[10px] p-3 flex flex-col gap-3 animate-in fade-in slide-in-from-top-2">
            <div className="flex gap-2 items-center justify-between">
              <span className="text-sm text-hint">Sort by:</span>
              <div className="flex gap-2 items-center">
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="bg-bg rounded px-2 py-1 text-sm outline-none border-none"
                >
                  <option value="created_at">Created Date</option>
                  <option value="updated_at">Activity</option>
                  <option value="title">Title</option>
                  <option value="id">ID</option>
                </select>
                <button onClick={toggleSortOrder} className="p-1">
                  <ArrowUpDown size={16} className={sortOrder === 'asc' ? 'transform rotate-180' : ''} />
                </button>
              </div>
            </div>

            <div className="h-px bg-bg w-full" />

            <div className="grid grid-cols-2 gap-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={includePrivate} onChange={(e) => setIncludePrivate(e.target.checked)} />
                Show Private
              </label>
              <label className="flex items-center gap-2">
                <select
                  value={filterActive === null ? '' : filterActive.toString()}
                  onChange={(e) => setFilterActive(e.target.value === '' ? null : e.target.value === 'true')}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Status</option>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </select>
              </label>
              <label className="flex items-center gap-2">
                <select
                  value={filterTrusted === null ? '' : filterTrusted.toString()}
                  onChange={(e) => setFilterTrusted(e.target.value === '' ? null : e.target.value === 'true')}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Trust</option>
                  <option value="true">Trusted</option>
                  <option value="false">Untrusted</option>
                </select>
              </label>
              <label className="flex items-center gap-2">
                <select
                  value={filterBanned === null ? '' : filterBanned.toString()}
                  onChange={(e) => setFilterBanned(e.target.value === '' ? null : e.target.value === 'true')}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Ban</option>
                  <option value="true">Banned</option>
                  <option value="false">Not Banned</option>
                </select>
              </label>
              <label className="flex items-center gap-2 col-span-2">
                <select
                  value={filterType || ''}
                  onChange={(e) => setFilterType(e.target.value || null)}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Types</option>
                  <option value="private">Private</option>
                  <option value="group">Group</option>
                  <option value="supergroup">Supergroup</option>
                  <option value="channel">Channel</option>
                </select>
              </label>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        {chats.map((chat) => (
          <div
            key={chat.id}
            onClick={() => navigate(`/chats/${chat.id}`)}
            className="bg-section-bg p-3 rounded-xl cursor-pointer"
          >
            <div className="font-bold">
              {chat.title || chat.username || `Chat ${chat.id}`}
            </div>
            <div className="text-hint text-sm">
              {chat.type && <span className="capitalize">{chat.type} • </span>}
              Lang: {chat.language_code} • Warns: {chat.warn_limit}
            </div>
            <div className="mt-1 flex gap-1 flex-wrap">
                {chat.is_trusted && <span className="text-xs bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded">Trusted</span>}
                {chat.is_banned && <span className="text-xs bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded">Banned</span>}
                {!chat.is_active && <span className="text-xs bg-gray-500/10 text-gray-500 px-1.5 py-0.5 rounded">Inactive</span>}
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchChats(false)}
            disabled={loading}
            className="w-full p-3 mt-4 text-link"
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default ChatsPage;
