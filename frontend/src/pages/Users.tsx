import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { usersApi } from '../api/client';
import type { User } from '../types';
import { ShieldAlert, Bot } from 'lucide-react';
import Breadcrumbs from '../components/Breadcrumbs';
import Skeleton from '../components/Skeleton';
import UserAvatar from '../components/UserAvatar';
import FilterBar from '../components/ui/FilterBar';
import FilterChip from '../components/ui/FilterChip';
import Badge from '../components/ui/Badge';

const STORAGE_KEY = 'users_filters';

const UsersPage: React.FC = () => {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');

  const getInitialState = () => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      // Ignore parse errors
    }
    return {
      sortBy: 'updated_at',
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
    setSortBy('updated_at');
    setSortOrder('desc');
    setFilterPremium(null);
    setFilterTrusted(null);
    setFilterModerator(null);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  const requestIdRef = useRef(0);

  const fetchUsers = useCallback(async (reset = false) => {
    if (loading && !reset) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    try {
      const currentPage = reset ? 1 : page;
      const params: Parameters<typeof usersApi.getAll>[0] = {
        page: currentPage,
        limit: 20,
        query: query || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      };

      if (filterPremium !== null) params.is_premium = filterPremium;
      if (filterTrusted !== null) params.is_trusted = filterTrusted;
      if (filterModerator !== null) params.is_bot_moderator = filterModerator;

      const res = await usersApi.getAll(params);

      // Игнорируем устаревший ответ, если за время запроса ушёл более новый
      if (requestIdRef.current !== requestId) return;

      if (reset) {
        setUsers(res.items);
      } else {
        setUsers((prev) => [...prev, ...res.items]);
      }

      setHasMore(currentPage < res.pagination.total_pages);
      setPage(currentPage + 1);
    } catch {
      // Error handled by interceptor
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [page, query, sortBy, sortOrder, filterPremium, filterTrusted, filterModerator, loading]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchUsers(true);
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, sortBy, sortOrder, filterPremium, filterTrusted, filterModerator]);

  const UserBadges = ({ user }: { user: User }) => (
    <div className="flex gap-1 flex-wrap">
      {user.is_bot && <Badge variant="gray" icon={Bot}>Bot</Badge>}
      {user.is_gban && <Badge variant="red" icon={ShieldAlert}>GBAN</Badge>}
      {user.is_premium && <Badge variant="purple">Premium</Badge>}
      {user.is_trusted && <Badge variant="green">Trusted</Badge>}
      {user.is_bot_moderator && <Badge variant="blue">Mod</Badge>}
    </div>
  );

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <Breadcrumbs />

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Users</h1>
      </div>

      <FilterBar
        search={query}
        onSearchChange={setQuery}
        searchPlaceholder="Search users..."
        sortOrder={sortOrder}
        onSortOrderChange={(v) => setSortOrder(v)}
      >
        <FilterChip active={filterPremium === null && filterTrusted === null && filterModerator === null} onClick={resetFilters}>All</FilterChip>
        <FilterChip active={filterPremium === true} onClick={() => setFilterPremium(filterPremium === true ? null : true)}>Premium</FilterChip>
        <FilterChip active={filterModerator === true} onClick={() => setFilterModerator(filterModerator === true ? null : true)}>Moderator</FilterChip>
        <FilterChip active={filterTrusted === true} onClick={() => setFilterTrusted(filterTrusted === true ? null : true)}>Trusted</FilterChip>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="ml-auto px-2.5 py-1.5 rounded-full text-xs font-medium bg-elevated text-hint border border-border appearance-none cursor-pointer"
        >
          <option value="updated_at">By Activity</option>
          <option value="created_at">By Date</option>
          <option value="badges">By Badges</option>
          <option value="username">By Username</option>
        </select>
      </FilterBar>

      {/* Desktop Table View */}
      <div className="hidden md:block bg-surface rounded-[14px] border border-border overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-hint text-sm">
              <th className="p-4 font-medium">User</th>
              <th className="p-4 font-medium">ID</th>
              <th className="p-4 font-medium">Badges</th>
              <th className="p-4 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody>
            {loading && users.length === 0 ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border last:border-none">
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
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/users/${user.id}`); } }}
                  tabIndex={0}
                  className="border-b border-border last:border-none hover:bg-elevated/50 cursor-pointer transition-colors"
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
                    {new Date(user.created_at).toLocaleDateString(navigator.language)}
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
          users.map((user) => (
            <div
              key={user.id}
              onClick={() => navigate(`/users/${user.id}`)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/users/${user.id}`); } }}
              role="button"
              tabIndex={0}
              className="bg-surface p-3 rounded-[14px] cursor-pointer border border-border"
            >
              <div className="flex items-center gap-3 mb-2">
                <UserAvatar userId={user.id} photoId={user.photo_id} />
                <div>
                  <div className="font-bold">
                    {user.first_name} {user.last_name}
                  </div>
                  <div className="text-hint text-sm">
                    @{user.username || 'No username'} | ID: {user.id}
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
          className="w-full p-3 mt-4 text-button font-medium hover:bg-elevated/50 rounded-lg transition-colors"
        >
          {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default UsersPage;
