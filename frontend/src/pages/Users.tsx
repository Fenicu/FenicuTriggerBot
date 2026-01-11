import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User, PaginatedResponse } from '../types';
import { Search } from 'lucide-react';

const UsersPage: React.FC = () => {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'trusted'>('newest');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const sortedUsers = React.useMemo(() => {
    return [...users].sort((a, b) => {
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
      return 0;
    });
  }, [users, sortBy]);

  const fetchUsers = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<User>>('/users', {
        params: { page: currentPage, limit: 20, query },
      });

      if (reset) {
        setUsers(res.data.items);
      } else {
        setUsers((prev) => [...prev, ...res.data.items]);
      }

      setHasMore(currentPage < res.data.pagination.total_pages);
      setPage(currentPage + 1);
    } catch (error: any) {
      console.error(error);
      setError(error.response?.data?.detail || error.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(true);
  }, [query]);

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
            placeholder="Search users..."
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
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {sortedUsers.map((user) => (
          <div
            key={user.id}
            onClick={() => navigate(`/users/${user.id}`)}
            className="bg-section-bg p-3 rounded-xl cursor-pointer"
          >
            <div className="font-bold">
              {user.first_name} {user.last_name}
            </div>
            <div className="text-hint text-sm">
              @{user.username || 'No username'} • ID: {user.id}
            </div>
            <div className="mt-1 flex gap-1">
                {user.is_trusted && <span className="text-xs bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded">Trusted</span>}
                {user.is_bot_moderator && <span className="text-xs bg-blue-500/10 text-blue-500 px-1.5 py-0.5 rounded">Mod</span>}
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchUsers(false)}
            disabled={loading}
            className="w-full p-3 mt-4 text-link"
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default UsersPage;
