import React, { useState, useEffect, useCallback } from 'react';
import { X, Zap, Clock, Ban, CheckCircle } from 'lucide-react';
import {
  triggersApi,
} from '../api/client';
import { toast, confirm } from '../store/store';
import type { Trigger } from '../types/index';
import Breadcrumbs from '../components/Breadcrumbs';
import TriggerFilters from '../components/TriggerFilters';
import TriggersList from '../components/TriggersList';
import StatusBadge from '../components/StatusBadge';

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

const Triggers: React.FC = () => {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [selectedTrigger, setSelectedTrigger] = useState<Trigger | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>('all');
  const [chatId, setChatId] = useState<string>('');
  const [sortBy, setSortBy] = useState<'created_at' | 'key_phrase'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const fetchTriggersData = useCallback(async (reset = false) => {
    if (loading && !reset) return;
    setLoading(true);
    try {
      const currentPage = reset ? 1 : page;
      const res = await triggersApi.getAll({
        page: currentPage,
        limit: 20,
        status: status === 'all' ? undefined : status,
        search: search || undefined,
        chat_id: chatId ? parseInt(chatId) : undefined,
        sort_by: sortBy,
        order: sortOrder,
      });

      if (reset) {
        setTriggers(res.items);
        setPage(2);
      } else {
        setTriggers(prev => [...prev, ...res.items]);
        setPage(prev => prev + 1);
      }

      setHasMore(res.items.length === 20);
      setTotal(res.total);
    } catch (error) {
      // Error is handled by API interceptor
    } finally {
      setLoading(false);
    }
  }, [page, status, search, chatId, sortBy, sortOrder, loading]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTriggersData(true);
    }, 500);
    return () => clearTimeout(timer);
  }, [status, search, chatId, sortBy, sortOrder]);

  const handleApprove = async (id: number) => {
    try {
      const updated = await triggersApi.approve(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
      toast.success('Trigger approved');
    } catch {
      // Error handled by interceptor
    }
  };

  const handleRequeue = async (id: number) => {
    try {
      const updated = await triggersApi.requeue(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
      toast.info('Trigger requeued for moderation');
    } catch {
      // Error handled by interceptor
    }
  };

  const handleDelete = async (id: number) => {
    const confirmed = await confirm({
      title: 'Delete Trigger',
      message: 'Are you sure you want to delete this trigger? This action cannot be undone.',
      confirmText: 'Delete',
      cancelText: 'Cancel',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await triggersApi.delete(id);
      setTriggers(prev => prev.filter(t => t.id !== id));
      toast.success('Trigger deleted');
    } catch {
      // Error handled by interceptor
    }
  };

  return (
    <div className="p-4 space-y-4 max-w-7xl mx-auto">
      <Breadcrumbs />
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center">
          <Zap size={24} className="mr-2.5 text-link" />
          <h1 className="text-2xl font-bold m-0">Triggers Manager</h1>
        </div>
        <div className="text-sm text-hint">{total} total</div>
      </div>

      <TriggerFilters
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
        sortBy={sortBy}
        onSortByChange={(val) => setSortBy(val as 'created_at' | 'key_phrase')}
        sortOrder={sortOrder}
        onSortOrderChange={(val) => setSortOrder(val as 'asc' | 'desc')}
      >
        <div className="relative min-w-32">
          <input
            type="number"
            placeholder="Chat ID"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            className="w-full px-3 py-2 bg-bg rounded-lg border border-secondary-bg focus:border-link focus:outline-none transition-colors"
          />
          {chatId && (
            <button
              onClick={() => setChatId('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-hint hover:text-text"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </TriggerFilters>

      <TriggersList
        triggers={triggers}
        onDelete={handleDelete}
        onViewDetails={setSelectedTrigger}
        onApprove={handleApprove}
        onRequeue={handleRequeue}
        onChatClick={(id) => setChatId(id.toString())}
      />

      {hasMore && (
        <button
          onClick={() => fetchTriggersData(false)}
          disabled={loading}
          className="w-full py-3 text-button font-medium hover:bg-button/5 rounded-xl transition-colors disabled:opacity-50"
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
                      onClick={() => {
                        handleApprove(selectedTrigger.id);
                        setSelectedTrigger(null);
                      }}
                      className="flex-1 bg-green-500/10 text-green-500 py-2 rounded-lg font-medium hover:bg-green-500/20 transition-colors flex items-center justify-center gap-2"
                    >
                      <CheckCircle size={18} /> Approve
                    </button>
                  )}
                  <button
                    onClick={() => {
                      handleRequeue(selectedTrigger.id);
                      setSelectedTrigger(null);
                    }}
                    className="flex-1 bg-blue-500/10 text-blue-500 py-2 rounded-lg font-medium hover:bg-blue-500/20 transition-colors flex items-center justify-center gap-2"
                  >
                    <Clock size={18} /> Requeue
                  </button>
                  <button
                    onClick={() => {
                      handleDelete(selectedTrigger.id);
                      setSelectedTrigger(null);
                    }}
                    className="flex-1 bg-red-500/10 text-red-500 py-2 rounded-lg font-medium hover:bg-red-500/20 transition-colors flex items-center justify-center gap-2"
                  >
                    <Ban size={18} /> Delete
                  </button>
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
                const content = selectedTrigger.content as TriggerContent;
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

export default Triggers;
