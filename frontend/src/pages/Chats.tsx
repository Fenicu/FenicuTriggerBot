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
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchChats = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<Chat>>('/chats', {
        params: { page: currentPage, limit: 20, query },
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
  }, [query]);

  return (
    <div style={{ padding: '16px' }}>
      {error && (
        <div style={{
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          color: '#ef4444',
          padding: '12px',
          borderRadius: '8px',
          marginBottom: '16px'
        }}>
          {error}
        </div>
      )}
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
          placeholder="Search chats..."
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
        {chats.map((chat) => (
          <div
            key={chat.id}
            onClick={() => navigate(`/chats/${chat.id}`)}
            style={{
              backgroundColor: 'var(--section-bg-color)',
              padding: '12px',
              borderRadius: '12px',
              cursor: 'pointer'
            }}
          >
            <div style={{ fontWeight: 'bold' }}>
              Chat ID: {chat.id}
            </div>
            <div style={{ color: 'var(--hint-color)', fontSize: '14px' }}>
              Lang: {chat.language_code} • Warns: {chat.warn_limit}
            </div>
            <div style={{ marginTop: '4px', display: 'flex', gap: '4px' }}>
                {chat.is_trusted && <span style={{ fontSize: '12px', backgroundColor: 'rgba(34, 197, 94, 0.1)', color: '#22c55e', padding: '2px 6px', borderRadius: '4px' }}>Trusted</span>}
                {chat.is_banned && <span style={{ fontSize: '12px', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', padding: '2px 6px', borderRadius: '4px' }}>Banned</span>}
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchChats(false)}
            disabled={loading}
            style={{ width: '100%', padding: '12px', marginTop: '16px', color: 'var(--link-color)' }}
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default ChatsPage;
