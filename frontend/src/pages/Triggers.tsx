import React, { useState, useEffect, useCallback } from 'react';
import { X, Zap, CheckCircle, Ban, Clock, AlertTriangle } from 'lucide-react';
import {
  getTriggers,
  approveTrigger,
  requeueTrigger,
  deleteTrigger
} from '../api/client';
import type { Trigger } from '../types/index';
import Breadcrumbs from '../components/Breadcrumbs';
import TriggerFilters from '../components/TriggerFilters';
import TriggersList from '../components/TriggersList';

const Triggers: React.FC = () => {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [selectedTrigger, setSelectedTrigger] = useState<Trigger | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>('pending');
  const [chatId, setChatId] = useState<string>('');
  const [sortBy, setSortBy] = useState<'created_at' | 'key_phrase'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const fetchTriggersData = useCallback(async (reset = false) => {
    if (loading && !reset) return;
    setLoading(true);
    try {
      const currentPage = reset ? 1 : page;
      const res = await getTriggers({
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
      console.error('Failed to fetch triggers', error);
    } finally {
      setLoading(false);
    }
  }, [page, status, search, chatId, sortBy, sortOrder]);

  useEffect(() => {
    const timer = setTimeout(() => {
        fetchTriggersData(true);
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, search, chatId, sortBy, sortOrder]);

  const handleApprove = async (id: number) => {
    try {
      const updated = await approveTrigger(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
    } catch (e) {
      console.error('Failed to approve', e);
    }
  };

  const handleRequeue = async (id: number) => {
    try {
      const updated = await requeueTrigger(id);
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
    } catch (e) {
      console.error('Failed to requeue', e);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this trigger?')) return;
    try {
      await deleteTrigger(id);
      setTriggers(prev => prev.filter(t => t.id !== id));
    } catch (e) {
      console.error('Failed to delete', e);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'safe':
        return (
          <span className="flex items-center text-green-500 bg-green-500/10 px-2 py-1 rounded text-xs font-medium">
            <CheckCircle size={12} className="mr-1" /> Safe
          </span>
        );
      case 'banned':
        return (
          <span className="flex items-center text-red-500 bg-red-500/10 px-2 py-1 rounded text-xs font-medium">
            <Ban size={12} className="mr-1" /> Banned
          </span>
        );
      case 'pending':
        return (
          <span className="flex items-center text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded text-xs font-medium">
            <Clock size={12} className="mr-1" /> Pending
          </span>
        );
      case 'flagged':
        return (
          <span className="flex items-center text-orange-500 bg-orange-500/10 px-2 py-1 rounded text-xs font-medium">
            <AlertTriangle size={12} className="mr-1" /> Flagged
          </span>
        );
      default:
        return (
          <span className="flex items-center text-gray-500 bg-gray-500/10 px-2 py-1 rounded text-xs font-medium">
            {status}
          </span>
        );
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
        onSortByChange={(val) => setSortBy(val as any)}
        sortOrder={sortOrder}
        onSortOrderChange={(val) => setSortOrder(val as any)}
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
                            {getStatusBadge(selectedTrigger.moderation_status)}
                        </div>
                        {selectedTrigger.moderation_reason && (
                            <div className="bg-secondary-bg p-3 rounded-lg text-sm border border-black/5">
                                <span className="font-semibold block mb-1 text-hint">Reasoning:</span>
                                <div className="whitespace-pre-wrap">{selectedTrigger.moderation_reason}</div>
                            </div>
                        )}
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
                    {(selectedTrigger.content.buttons || selectedTrigger.content.reply_markup) && (
                        <div>
                            <h3 className="text-sm font-semibold text-hint uppercase mb-2">Buttons</h3>
                            <div className="flex flex-col gap-2">
                                {(() => {
                                    const buttons = selectedTrigger.content.buttons ||
                                                   selectedTrigger.content.reply_markup?.inline_keyboard ||
                                                   selectedTrigger.content.reply_markup?.keyboard;

                                    if (Array.isArray(buttons)) {
                                        return buttons.map((row: any, i: number) => (
                                            <div key={i} className="flex gap-2 justify-center">
                                                {Array.isArray(row) ? row.map((btn: any, j: number) => (
                                                    <div key={j} className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                                                                {btn.text || 'Button'}
                                                            </div>
                                                        )) : (
                                                            <div className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                                                                {row.text || 'Button'}
                                                            </div>
                                                        )}
                                            </div>
                                        ));
                                    }
                                    return <div className="text-sm text-hint italic">Complex button structure</div>;
                                })()}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
      )}
    </div>
  );
};

export default Triggers;
