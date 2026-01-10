import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Trigger, PaginatedResponse } from '../types';
import { ArrowLeft, Zap } from 'lucide-react';
import TriggerImage from '../components/TriggerImage';

const ChatTriggers: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchTriggers = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<Trigger>>(`/chats/${id}/triggers`, {
        params: { page: currentPage, limit: 20 },
      });

      if (reset) {
        setTriggers(res.data.items);
      } else {
        setTriggers((prev) => [...prev, ...res.data.items]);
      }

      setHasMore(currentPage < res.data.pagination.total_pages);
      setPage(currentPage + 1);
    } catch (error: any) {
      console.error(error);
      setError(error.response?.data?.detail || error.message || 'Failed to load triggers');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTriggers(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', color: 'var(--link-color)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}>
        <ArrowLeft size={20} style={{ marginRight: '4px' }} /> Back
      </button>

      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '20px' }}>
        <Zap size={24} style={{ marginRight: '10px', color: 'var(--link-color)' }} />
        <h1 style={{ fontSize: '24px', fontWeight: 'bold', margin: 0 }}>Chat Triggers</h1>
      </div>

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

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {triggers.map((trigger) => (
          <div
            key={trigger.id}
            style={{
              backgroundColor: 'var(--section-bg-color)',
              padding: '16px',
              borderRadius: '12px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
              <div style={{ fontWeight: 'bold', fontSize: '16px' }}>
                {trigger.key_phrase}
              </div>
              <span style={{
                fontSize: '12px',
                backgroundColor: 'var(--secondary-bg-color)',
                padding: '4px 8px',
                borderRadius: '6px',
                textTransform: 'uppercase'
              }}>
                {trigger.match_type}
              </span>
            </div>

            <div style={{ color: 'var(--hint-color)', fontSize: '14px', marginBottom: '8px' }}>
              Uses: {trigger.usage_count} • Access: {trigger.access_level}
            </div>

            <div style={{ fontSize: '14px', wordBreak: 'break-word' }}>
               {/* Display content summary */}
               {trigger.content.text && <div style={{ marginBottom: '8px' }}>{trigger.content.text}</div>}

               {trigger.content.photo && (
                 <TriggerImage chatId={trigger.chat_id} triggerId={trigger.id} alt="Trigger photo" />
               )}

               {trigger.content.sticker && (
                 <TriggerImage chatId={trigger.chat_id} triggerId={trigger.id} alt="Trigger sticker" />
               )}

               {trigger.content.video && <div>[Video]</div>}
               {trigger.content.animation && <div>[Animation]</div>}
               {trigger.content.document && <div>[Document]</div>}
               {trigger.content.voice && <div>[Voice]</div>}
               {trigger.content.audio && <div>[Audio]</div>}
            </div>
          </div>
        ))}

        {triggers.length === 0 && !loading && !error && (
            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--hint-color)' }}>
                No triggers found for this chat.
            </div>
        )}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchTriggers(false)}
            disabled={loading}
            style={{ width: '100%', padding: '12px', marginTop: '16px', color: 'var(--link-color)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default ChatTriggers;
