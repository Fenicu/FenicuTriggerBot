import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User, PaginatedResponse } from '../types';
import { Search, Filter, ArrowUpDown } from 'lucide-react';

const STORAGE_KEY = 'users_filters';

const UsersPage: React.FC = () => {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
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
      sortBy: 'created_at',
      sortOrder: 'desc',
      filterPremium: null,
      filterTrusted: null,
      filterModerator: null
    };
  };

  const [initialState] = useState(getInitialState);

  const [sortBy, setSortBy] = useState<string>(initialState.sortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialState.sortOrder);

  const [filterPremium, setFilterPremium] = useState<boolean | null>(initialState.filterPremium);
  const [filterTrusted, setFilterTrusted] = useState<boolean | null>(initialState.filterTrusted);
  const [filterModerator, setFilterModerator] = useState<boolean | null>(initialState.filterModerator);

  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    const state = {
      sortBy,
      sortOrder,
      filterPremium,
      filterTrusted,
      filterModerator
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [sortBy, sortOrder, filterPremium, filterTrusted, filterModerator]);

  const resetFilters = () => {
    setSortBy('created_at');
    setSortOrder('desc');
    setFilterPremium(null);
    setFilterTrusted(null);
    setFilterModerator(null);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const fetchUsers = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const params: any = {
        page: currentPage,
        limit: 20,
        query,
        sort_by: sortBy,
        sort_order: sortOrder,
      };

      if (filterPremium !== null) params.is_premium = filterPremium;
      if (filterTrusted !== null) params.is_trusted = filterTrusted;
      if (filterModerator !== null) params.is_bot_moderator = filterModerator;

      const res = await apiClient.get<PaginatedResponse<User>>('/users', { params });

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, sortBy, sortOrder, filterPremium, filterTrusted, filterModerator]);

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
              placeholder="Search users..."
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
                  <option value="username">Username</option>
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
                <select
                  value={filterPremium === null ? '' : filterPremium.toString()}
                  onChange={(e) => setFilterPremium(e.target.value === '' ? null : e.target.value === 'true')}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Premium</option>
                  <option value="true">Premium</option>
                  <option value="false">Standard</option>
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
              <label className="flex items-center gap-2 col-span-2">
                <select
                  value={filterModerator === null ? '' : filterModerator.toString()}
                  onChange={(e) => setFilterModerator(e.target.value === '' ? null : e.target.value === 'true')}
                  className="bg-bg rounded px-1 py-0.5 w-full"
                >
                  <option value="">All Roles</option>
                  <option value="true">Moderator</option>
                  <option value="false">User</option>
                </select>
              </label>
            </div>

            <button onClick={resetFilters} className="w-full p-2 bg-red-500/10 text-red-500 rounded text-sm mt-2 cursor-pointer border-none">
                Reset Filters
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        {users.map((user) => (
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
                {user.is_premium && <span className="text-xs bg-purple-500/10 text-purple-500 px-1.5 py-0.5 rounded">Premium</span>}
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
