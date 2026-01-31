import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { chatsApi, triggersApi } from '../api/client';
import { toast, confirm } from '../store/store';
import type { Trigger } from '../types/index';
import { ArrowLeft, Zap, X, CheckCircle, Clock, Ban } from 'lucide-react';
import Breadcrumbs from '../components/Breadcrumbs';
import TriggerFilters from '../components/TriggerFilters';
import TriggersList from '../components/TriggersList';
import StatusBadge from '../components/StatusBadge';
import ModerationTimeline from '../components/ModerationTimeline';

// Type for trigger content with optional reply markup
interface TriggerContent {
  text?: string;
  buttons?: Array<Array<{ text?: string }> | { text?: string }>;
  reply_markup?: {
    inline_keyboard?: Array<Array<{ text?: string }>>;
    keyboard?: Array<Array<{ text?: string }>>;
  };
  [key: string]: unknown;
}

const ChatTriggers: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [selectedTrigger, setSelectedTrigger] = useState<Trigger | null>(null);
  const [scrollToTimeline, setScrollToTimeline] = useState(false);

  // Filters state
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');

  const fetchTriggers = async (reset = false) => {
    if (loading && !reset) return;
    if (!id) return;
    setLoading(true);
    try {
      const currentPage = reset ? 1 : page;
      const res = await chatsApi.getTriggers(parseInt(id), {
        page: currentPage,
        limit: 20,
        search: search || undefined,
        status: status !== 'all' ? status : undefined,
        sort_by: sortBy as 'created_at' | 'key_phrase',
        order: sortOrder as 'asc' | 'desc',
      });

      if (reset) {
        setTriggers(res.items);
      } else {
        setTriggers((prev) => [...prev, ...res.items]);
      }

      setHasMore(res.items.length === 20);
      setPage(currentPage + 1);
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTriggers(true);
    }, 500);
    return () => clearTimeout(timer);
  }, [search, status, sortBy, sortOrder, id]);

  const handleApprove = async (id: number) => {
    try {
      const updated = await triggersApi.approve(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
      if (selectedTrigger?.id === id) {
        setSelectedTrigger(updated);
      }
      toast.success('Trigger approved');
    } catch {
      // Error handled by interceptor
    }
  };

  const handleRequeue = async (id: number) => {
    try {
      const updated = await triggersApi.requeue(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
      if (selectedTrigger?.id === id) {
        setSelectedTrigger(updated);
      }
      toast.info('Trigger requeued for moderation');
    } catch {
      // Error handled by interceptor
    }
  };

  const handleTriggerUpdate = async (id: number) => {
    try {
      const updated = await triggersApi.getById(id);
      setTriggers((prev) => prev.map((t) => (t.id === id ? updated : t)));
      if (selectedTrigger?.id === id) {
        setSelectedTrigger(updated);
      }
    } catch (error) {
      console.error('Failed to update trigger:', error);
    }
  };

  const handleDelete = async (triggerId: number) => {
    const confirmed = await confirm({
      title: 'Delete Trigger',
      message: 'Are you sure you want to delete this trigger?',
      confirmText: 'Delete',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await triggersApi.delete(triggerId);
      setTriggers((prev) => prev.filter((t) => t.id !== triggerId));
      if (selectedTrigger?.id === triggerId) {
        setSelectedTrigger(null);
      }
      toast.success('Trigger deleted');
    } catch {
      // Error handled by interceptor
    }
  };

  const getContent = (trigger: Trigger): TriggerContent => {
    return trigger.content as TriggerContent;
  };

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <Breadcrumbs />
      <button onClick={() => navigate(-1)} className="md:hidden mb-4 flex items-center text-link bg-transparent border-none cursor-pointer text-base">
        <ArrowLeft size={20} className="mr-1" /> Back
      </button>

      <div className="flex items-center mb-5">
        <Zap size={24} className="mr-2.5 text-link" />
        <h1 className="text-2xl font-bold m-0">Chat Triggers</h1>
      </div>

      <TriggerFilters
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
        sortBy={sortBy}
        onSortByChange={setSortBy}
        sortOrder={sortOrder}
        onSortOrderChange={setSortOrder}
      />

      <TriggersList
        triggers={triggers}
        onDelete={handleDelete}
        onViewDetails={(trigger) => {
          setSelectedTrigger(trigger);
          setScrollToTimeline(false);
        }}
        onApprove={handleApprove}
        onRequeue={handleRequeue}
        onStatusClick={(trigger) => {
          setSelectedTrigger(trigger);
          setScrollToTimeline(true);
        }}
      />

      {hasMore && (
        <button
          onClick={() => fetchTriggers(false)}
          disabled={loading}
          className="w-full p-3 mt-4 text-link bg-transparent border-none cursor-pointer hover:bg-black/5 rounded-lg"
        >
          {loading ? 'Loading...' : 'Load More'}
        </button>
      )}

      {/* Details Modal */}
      {selectedTrigger && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setSelectedTrigger(null)}>
          <div className="bg-section-bg p-6 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto relative shadow-2xl border border-secondary-bg" onClick={e => e.stopPropagation()}>
            <button onClick={() => setSelectedTrigger(null)} className="absolute top-4 right-4 text-hint hover:text-text transition-colors">
              <X size={24} />
            </button>

            <h2 className="text-xl font-bold mb-6 pr-8">Trigger Details</h2>

            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-hint uppercase mb-2">Moderation</h3>
                <div className="flex items-center gap-3 mb-2">
                  <StatusBadge status={selectedTrigger.moderation_status} size="md" />
                </div>
                {selectedTrigger.moderation_reason && (
                  <div className="bg-secondary-bg p-3 rounded-lg text-sm border border-black/5">
                    <span className="font-semibold block mb-1 text-hint">Reasoning:</span>
                    <div className="whitespace-pre-wrap">{selectedTrigger.moderation_reason}</div>
                  </div>
                )}

                <div className="flex gap-3 mt-3">
                  {selectedTrigger.moderation_status !== 'safe' && (
                    <button
                      onClick={() => handleApprove(selectedTrigger.id)}
                      className="flex-1 bg-green-500/10 text-green-500 py-2 rounded-lg font-medium hover:bg-green-500/20 transition-colors flex items-center justify-center gap-2"
                    >
                      <CheckCircle size={18} /> Approve
                    </button>
                  )}
                  <button
                    onClick={() => handleRequeue(selectedTrigger.id)}
                    className="flex-1 bg-blue-500/10 text-blue-500 py-2 rounded-lg font-medium hover:bg-blue-500/20 transition-colors flex items-center justify-center gap-2"
                  >
                    <Clock size={18} /> Requeue
                  </button>
                  <button
                    onClick={() => handleDelete(selectedTrigger.id)}
                    className="flex-1 bg-red-500/10 text-red-500 py-2 rounded-lg font-medium hover:bg-red-500/20 transition-colors flex items-center justify-center gap-2"
                  >
                    <Ban size={18} /> Delete
                  </button>
                </div>

                {/* Moderation Timeline */}
                <div className="mt-4 pt-4 border-t border-secondary-bg">
                  <ModerationTimeline
                    triggerId={selectedTrigger.id}
                    scrollToTimeline={scrollToTimeline}
                    onModerationComplete={() => handleTriggerUpdate(selectedTrigger.id)}
                  />
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-hint uppercase mb-2">Content</h3>
                <div className="bg-secondary-bg p-4 rounded-lg overflow-x-auto border border-black/5">
                  <pre className="text-xs font-mono whitespace-pre-wrap">
                    {JSON.stringify(selectedTrigger.content, null, 2)}
                  </pre>
                </div>
              </div>

              {/* Buttons Visualization */}
              {(() => {
                const content = getContent(selectedTrigger);
                if (!content.buttons && !content.reply_markup) return null;

                const buttons = content.buttons ||
                  content.reply_markup?.inline_keyboard ||
                  content.reply_markup?.keyboard;

                if (!Array.isArray(buttons)) return null;

                return (
                  <div>
                    <h3 className="text-sm font-semibold text-hint uppercase mb-2">Buttons</h3>
                    <div className="flex flex-col gap-2">
                      {buttons.map((row, i: number) => (
                        <div key={i} className="flex gap-2 justify-center">
                          {Array.isArray(row) ? row.map((btn, j: number) => (
                            <div key={j} className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                              {btn.text || 'Button'}
                            </div>
                          )) : (
                            <div className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                              {(row as { text?: string }).text || 'Button'}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ChatTriggers;
