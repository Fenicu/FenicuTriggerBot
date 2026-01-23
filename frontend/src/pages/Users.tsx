import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User, PaginatedResponse } from '../types';
import { Search, Filter, ArrowUpDown, ShieldAlert, Bot } from 'lucide-react';
import Breadcrumbs from '../components/Breadcrumbs';
import Skeleton from '../components/Skeleton';
import UserAvatar from '../components/UserAvatar';

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

  const UserBadges = ({ user }: { user: User }) => (
    <div className="flex gap-1 flex-wrap">
        {user.is_bot && <span className="text-xs bg-gray-500/10 text-gray-500 px-1.5 py-0.5 rounded flex items-center gap-1"><Bot size={12} /> Bot</span>}
        {user.is_gban && <span className="text-xs bg-red-500/10 text-red-500 px-1.5 py-0.5 rounded flex items-center gap-1"><ShieldAlert size={12} /> GBAN</span>}
        {user.is_premium && <span className="text-xs bg-purple-500/10 text-purple-500 px-1.5 py-0.5 rounded">Premium</span>}
        {user.is_trusted && <span className="text-xs bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded">Trusted</span>}
        {user.is_bot_moderator && <span className="text-xs bg-blue-500/10 text-blue-500 px-1.5 py-0.5 rounded">Mod</span>}
    </div>
  );

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <Breadcrumbs />

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Users</h1>
      </div>

      {error && (
        <div className="bg-red-500/10 text-red-500 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-4 mb-6">
        <div className="flex gap-2">
          <div className="bg-section-bg rounded-[10px] p-2 px-3 flex items-center flex-1 border border-black/5">
            <Search size={20} className="text-hint mr-2" />
            <input
              type="text"
              placeholder="Search users..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="border-none bg-transparent w-full text-base text-text outline-none placeholder:text-hint"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`bg-section-bg rounded-[10px] px-3 flex items-center justify-center border border-black/5 hover:bg-black/5 transition-colors ${showFilters ? 'text-link' : 'text-text'}`}
          >
            <Filter size={20} />
          </button>
        </div>

        {showFilters && (
          <div className="bg-section-bg rounded-[10px] p-4 border border-black/5 animate-in fade-in slide-in-from-top-2">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="flex flex-col gap-1">
                    <span className="text-xs text-hint uppercase font-semibold">Sort By</span>
                    <div className="flex gap-2">
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="bg-bg rounded px-2 py-1.5 text-sm outline-none border border-black/10 w-full"
                        >
                            <option value="created_at">Created Date</option>
                            <option value="updated_at">Activity</option>
                            <option value="username">Username</option>
                            <option value="id">ID</option>
                        </select>
                        <button onClick={toggleSortOrder} className="p-1.5 bg-bg rounded border border-black/10 hover:bg-black/5">
                            <ArrowUpDown size={16} className={sortOrder === 'asc' ? 'transform rotate-180' : ''} />
                        </button>
                    </div>
                </div>

                <div className="flex flex-col gap-1">
                    <span className="text-xs text-hint uppercase font-semibold">Premium</span>
                    <select
                        value={filterPremium === null ? '' : filterPremium.toString()}
                        onChange={(e) => setFilterPremium(e.target.value === '' ? null : e.target.value === 'true')}
                        className="bg-bg rounded px-2 py-1.5 text-sm outline-none border border-black/10 w-full"
                    >
                        <option value="">All</option>
                        <option value="true">Premium</option>
                        <option value="false">Standard</option>
                    </select>
                </div>

                <div className="flex flex-col gap-1">
                    <span className="text-xs text-hint uppercase font-semibold">Trust</span>
                    <select
                        value={filterTrusted === null ? '' : filterTrusted.toString()}
                        onChange={(e) => setFilterTrusted(e.target.value === '' ? null : e.target.value === 'true')}
                        className="bg-bg rounded px-2 py-1.5 text-sm outline-none border border-black/10 w-full"
                    >
                        <option value="">All</option>
                        <option value="true">Trusted</option>
                        <option value="false">Untrusted</option>
                    </select>
                </div>

                <div className="flex flex-col gap-1">
                    <span className="text-xs text-hint uppercase font-semibold">Role</span>
                    <select
                        value={filterModerator === null ? '' : filterModerator.toString()}
                        onChange={(e) => setFilterModerator(e.target.value === '' ? null : e.target.value === 'true')}
                        className="bg-bg rounded px-2 py-1.5 text-sm outline-none border border-black/10 w-full"
                    >
                        <option value="">All</option>
                        <option value="true">Moderator</option>
                        <option value="false">User</option>
                    </select>
                </div>
            </div>

            <div className="mt-4 flex justify-end">
                <button onClick={resetFilters} className="text-red-500 text-sm hover:underline cursor-pointer bg-transparent border-none">
                    Reset Filters
                </button>
            </div>
          </div>
        )}
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:block bg-section-bg rounded-xl border border-black/5 overflow-hidden">
        <table className="w-full text-left border-collapse">
            <thead>
                <tr className="border-b border-black/5 text-hint text-sm">
                    <th className="p-4 font-medium">User</th>
                    <th className="p-4 font-medium">ID</th>
                    <th className="p-4 font-medium">Badges</th>
                    <th className="p-4 font-medium">Joined</th>
                </tr>
            </thead>
            <tbody>
                {loading && users.length === 0 ? (
                    Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="border-b border-black/5 last:border-none">
                            <td className="p-4"><div className="flex items-center gap-3"><Skeleton className="w-10 h-10 rounded-full" /><div className="space-y-2"><Skeleton className="w-32 h-4" /><Skeleton className="w-20 h-3" /></div></div></td>
                            <td className="p-4"><Skeleton className="w-20 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-40 h-6" /></td>
                            <td className="p-4"><Skeleton className="w-24 h-4" /></td>
                        </tr>
                    ))
                ) : (
                    users.map((user) => (
                        <tr
                            key={user.id}
                            onClick={() => navigate(`/users/${user.id}`)}
                            className="border-b border-black/5 last:border-none hover:bg-black/5 cursor-pointer transition-colors"
                        >
                            <td className="p-4">
                                <div className="flex items-center gap-3">
                                    <UserAvatar userId={user.id} photoId={user.photo_id} />
                                    <div>
                                        <div className="font-bold">{user.first_name} {user.last_name}</div>
                                        <div className="text-xs text-hint">@{user.username || 'No username'}</div>
                                    </div>
                                </div>
                            </td>
                            <td className="p-4 text-sm font-mono text-hint">{user.id}</td>
                            <td className="p-4">
                                <UserBadges user={user} />
                            </td>
                            <td className="p-4 text-sm text-hint">
                                {new Date(user.created_at).toLocaleDateString()}
                            </td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
        {users.length === 0 && !loading && (
            <div className="p-8 text-center text-hint">No users found</div>
        )}
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden flex flex-col gap-2">
        {loading && users.length === 0 ? (
             Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-section-bg p-3 rounded-xl space-y-3">
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
            users.map((user) => (
            <div
                key={user.id}
                onClick={() => navigate(`/users/${user.id}`)}
                className="bg-section-bg p-3 rounded-xl cursor-pointer border border-black/5"
            >
                <div className="flex items-center gap-3 mb-2">
                    <UserAvatar userId={user.id} photoId={user.photo_id} />
                    <div>
                        <div className="font-bold">
                        {user.first_name} {user.last_name}
                        </div>
                        <div className="text-hint text-sm">
                        @{user.username || 'No username'} • ID: {user.id}
                        </div>
                    </div>
                </div>
                <div className="mt-2">
                    <UserBadges user={user} />
                </div>
            </div>
            ))
        )}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchUsers(false)}
            disabled={loading}
            className="w-full p-3 mt-4 text-link hover:bg-black/5 rounded-lg transition-colors"
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default UsersPage;
