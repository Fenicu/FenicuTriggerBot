import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { User, PaginatedResponse } from '../types';
import { Search } from 'lucide-react';

const UsersPage: React.FC = () => {
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchUsers = async (reset = false) => {
    if (loading) return;
    setLoading(true);
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
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(true);
  }, [query]);

  return (
    <div style={{ padding: '16px' }}>
      <div style={{
        backgroundColor: 'var(--section-bg-color)',
        borderRadius: '10px',
        padding: '8px 12px',
        display: 'flex',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        <Search size={20} style={{ color: 'var(--hint-color)', marginRight: '8px' }} />
        <input
          type="text"
          placeholder="Search users..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            border: 'none',
            background: 'transparent',
            width: '100%',
            fontSize: '16px',
            color: 'var(--text-color)',
            outline: 'none'
          }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {users.map((user) => (
          <div
            key={user.id}
            onClick={() => navigate(`/users/${user.id}`)}
            style={{
              backgroundColor: 'var(--section-bg-color)',
              padding: '12px',
              borderRadius: '12px',
              cursor: 'pointer'
            }}
          >
            <div style={{ fontWeight: 'bold' }}>
              {user.first_name} {user.last_name}
            </div>
            <div style={{ color: 'var(--hint-color)', fontSize: '14px' }}>
              @{user.username || 'No username'} • ID: {user.id}
            </div>
            <div style={{ marginTop: '4px', display: 'flex', gap: '4px' }}>
                {user.is_trusted && <span style={{ fontSize: '12px', backgroundColor: 'rgba(34, 197, 94, 0.1)', color: '#22c55e', padding: '2px 6px', borderRadius: '4px' }}>Trusted</span>}
                {user.is_bot_moderator && <span style={{ fontSize: '12px', backgroundColor: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6', padding: '2px 6px', borderRadius: '4px' }}>Mod</span>}
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchUsers(false)}
            disabled={loading}
            style={{ width: '100%', padding: '12px', marginTop: '16px', color: 'var(--link-color)' }}
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default UsersPage;
