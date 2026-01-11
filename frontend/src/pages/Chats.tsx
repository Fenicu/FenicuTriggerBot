import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Chat, PaginatedResponse } from '../types';
import { Search } from 'lucide-react';

const ChatsPage: React.FC = () => {
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'trusted' | 'banned'>('newest');
  const [includePrivate, setIncludePrivate] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const sortedChats = React.useMemo(() => {
    return [...chats].sort((a, b) => {
      if (sortBy === 'newest') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sortBy === 'oldest') {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      if (sortBy === 'trusted') {
        if (a.is_trusted === b.is_trusted) {
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        return (b.is_trusted ? 1 : 0) - (a.is_trusted ? 1 : 0);
      }
      if (sortBy === 'banned') {
        if (a.is_banned === b.is_banned) {
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        return (b.is_banned ? 1 : 0) - (a.is_banned ? 1 : 0);
      }
      return 0;
    });
  }, [chats, sortBy]);

  const fetchChats = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<Chat>>('/chats', {
        params: { page: currentPage, limit: 20, query, include_private: includePrivate },
      });

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
  }, [query, includePrivate]);

  return (
    <div className="p-4">
      {error && (
        <div className="bg-red-500/10 text-red-500 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}
      <div className="flex gap-2 mb-4">
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
        <div className="bg-section-bg rounded-[10px] px-3 flex items-center justify-center">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-transparent outline-none text-text border-none py-2 cursor-pointer"
          >
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="trusted">Trusted</option>
            <option value="banned">Banned</option>
          </select>
        </div>
      </div>

      <div className="mb-4 flex items-center">
        <label className="flex items-center cursor-pointer text-text">
          <input
            type="checkbox"
            checked={includePrivate}
            onChange={(e) => setIncludePrivate(e.target.checked)}
            className="mr-2 w-4.5 h-4.5"
          />
          Show private chats
        </label>
      </div>

      <div className="flex flex-col gap-2">
        {sortedChats.map((chat) => (
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
            <div className="mt-1 flex gap-1">
                {chat.is_trusted && <span className="text-xs bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded">Trusted</span>}
                {chat.is_banned && <span className="text-xs bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded">Banned</span>}
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
