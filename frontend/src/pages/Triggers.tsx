import React, { useState, useEffect, useCallback } from 'react';
import {
  Search,
  RefreshCw,
  Trash2,
  AlertTriangle,
  ShieldCheck,
  Filter,
  Loader2,
  X,
  MessageSquare
} from 'lucide-react';
import {
  getTriggers,
  approveTrigger,
  requeueTrigger,
  deleteTrigger,
  getTriggerQueueStatus
} from '../api/client';
import type { Trigger } from '../types';
import TriggerImage from '../components/TriggerImage';
import Breadcrumbs from '../components/Breadcrumbs';
import Skeleton from '../components/Skeleton';

const TriggerCard: React.FC<{
  trigger: Trigger;
  onApprove: (id: number) => void;
  onRequeue: (id: number) => void;
  onDelete: (id: number) => void;
  onChatClick: (chatId: number) => void;
}> = ({ trigger, onApprove, onRequeue, onDelete, onChatClick }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const checkQueue = async () => {
      try {
        const status = await getTriggerQueueStatus(trigger.id);
        if (mounted) setIsProcessing(status.is_processing);
      } catch (e) {
        console.error('Failed to check queue status', e);
      }
    };
    checkQueue();
    return () => { mounted = false; };
  }, [trigger.id]);

  const handleAction = async (action: 'approve' | 'requeue' | 'delete') => {
    setLoadingAction(action);
    try {
      if (action === 'approve') await onApprove(trigger.id);
      if (action === 'requeue') await onRequeue(trigger.id);
      if (action === 'delete') await onDelete(trigger.id);
    } finally {
      setLoadingAction(null);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'safe': return 'bg-green-500/20 text-green-500 border-green-500/30';
      case 'flagged': return 'bg-red-500/20 text-red-500 border-red-500/30';
      default: return 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30';
    }
  };

  return (
    <div className="bg-secondary-bg rounded-xl p-4 border border-black/5 shadow-sm space-y-3">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-bold text-text text-lg">{trigger.key_phrase}</h3>
          <div className="text-xs text-hint flex gap-2 mt-1">
            <span>ID: {trigger.id}</span>
            <span
              onClick={() => onChatClick(trigger.chat_id)}
              className="cursor-pointer hover:text-button hover:underline transition-colors"
              title="Filter by this chat"
            >
              Chat: {trigger.chat_id}
            </span>
          </div>
        </div>
        <div className={`px-2 py-1 rounded-full text-xs border ${getStatusColor(trigger.moderation_status)}`}>
          {trigger.moderation_status.toUpperCase()}
        </div>
      </div>

      <div className="bg-bg/50 p-3 rounded-lg text-sm text-text/90 wrap-break-word">
        {trigger.content?.text && <p>{trigger.content.text}</p>}
        {(trigger.content?.photo || trigger.content?.video || trigger.content?.animation || trigger.content?.sticker || trigger.content?.document || trigger.content?.voice || trigger.content?.audio) && (
           <div className="mt-2">
             <TriggerImage trigger={trigger} />
           </div>
        )}
        {!trigger.content?.text && !(trigger.content?.photo || trigger.content?.video || trigger.content?.animation || trigger.content?.sticker || trigger.content?.document || trigger.content?.voice || trigger.content?.audio) && (
          <span className="italic text-hint">No preview available</span>
        )}
      </div>

      {(trigger.moderation_reason) && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/5 p-2 rounded">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold">AI Flag:</span> {trigger.moderation_reason}
          </div>
        </div>
      )}

      {isProcessing && (
        <div className="flex items-center gap-2 text-xs text-blue-400 bg-blue-500/5 p-2 rounded">
          <Loader2 size={14} className="animate-spin" />
          <span>Processing in Queue...</span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 text-xs text-hint border-t border-black/5 pt-2">
        <div>
            <span className="block opacity-50 mb-0.5">Created</span>
            <span className="font-medium">{new Date(trigger.created_at).toLocaleDateString()}</span>
        </div>
        <div>
            <span className="block opacity-50 mb-0.5">Updated</span>
            <span className="font-medium">{new Date(trigger.updated_at).toLocaleDateString()}</span>
        </div>
        <div>
            <span className="block opacity-50 mb-0.5">Uses</span>
            <span className="font-medium">{trigger.usage_count}</span>
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-black/5">
        <button
          onClick={() => handleAction('approve')}
          disabled={!!loadingAction || trigger.moderation_status === 'safe'}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-green-500/10 text-green-500 hover:bg-green-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
        >
          {loadingAction === 'approve' ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
          Approve
        </button>
        <button
          onClick={() => handleAction('requeue')}
          disabled={!!loadingAction}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
        >
          {loadingAction === 'requeue' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          Re-Queue
        </button>
        <button
          onClick={() => handleAction('delete')}
          disabled={!!loadingAction}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
        >
          {loadingAction === 'delete' ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
          Delete
        </button>
      </div>
    </div>
  );
};

const Triggers: React.FC = () => {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);

  // Filters
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<string>('pending');
  const [chatId, setChatId] = useState<string>('');
  const [sortBy, setSortBy] = useState<'created_at' | 'key_phrase'>('created_at');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');

  const fetchTriggersData = useCallback(async (reset = false) => {
    if (loading) return;
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
        order: order,
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
  }, [page, status, search, chatId, sortBy, order]);

  useEffect(() => {
    fetchTriggersData(true);
  }, [status, search, chatId, sortBy, order]);

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
    try {
      await deleteTrigger(id);
      setTriggers(prev => prev.filter(t => t.id !== id));
    } catch (e) {
      console.error('Failed to delete', e);
    }
  };

  return (
    <div className="p-4 space-y-4 max-w-7xl mx-auto">
      <Breadcrumbs />
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-text">Triggers Manager</h1>
        <div className="text-sm text-hint">{total} total</div>
      </div>

      {/* Filters */}
      <div className="space-y-3 bg-secondary-bg p-4 rounded-xl border border-black/5">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="relative col-span-1 md:col-span-2 lg:col-span-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-hint" size={18} />
                <input
                    type="text"
                    placeholder="Search key phrases..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full bg-bg pl-10 pr-4 py-2 rounded-lg border border-black/10 focus:outline-none focus:border-button text-text placeholder:text-hint"
                />
            </div>

            <div className="flex gap-2 overflow-x-auto pb-1 md:pb-0 lg:col-span-1">
                {['pending', 'flagged', 'safe', 'all'].map((s) => (
                    <button
                    key={s}
                    onClick={() => setStatus(s)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors border border-transparent ${
                        status === s
                        ? 'bg-button text-white'
                        : 'bg-bg text-hint hover:bg-black/5 border-black/5'
                    }`}
                    >
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-2 lg:col-span-1">
                <Filter size={16} className="text-hint shrink-0" />
                <div className="relative flex-1">
                <input
                    type="number"
                    placeholder="Filter by Chat ID"
                    value={chatId}
                    onChange={(e) => setChatId(e.target.value)}
                    className="w-full bg-bg px-3 py-2 rounded-lg border border-black/10 focus:outline-none focus:border-button text-text text-sm placeholder:text-hint pr-8"
                />
                {chatId && (
                    <button
                    onClick={() => setChatId('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-hint hover:text-text p-0.5"
                    >
                    <X size={14} />
                    </button>
                )}
                </div>
            </div>

            <div className="lg:col-span-1">
                <select
                    value={`${sortBy}-${order}`}
                    onChange={(e) => {
                    const [newSort, newOrder] = e.target.value.split('-');
                    setSortBy(newSort as any);
                    setOrder(newOrder as any);
                    }}
                    className="w-full bg-bg px-3 py-2 rounded-lg border border-black/10 focus:outline-none focus:border-button text-text text-sm"
                >
                    <option value="created_at-desc">Newest First</option>
                    <option value="created_at-asc">Oldest First</option>
                    <option value="key_phrase-asc">Phrase (A-Z)</option>
                    <option value="key_phrase-desc">Phrase (Z-A)</option>
                </select>
            </div>
        </div>
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:block bg-section-bg rounded-xl border border-black/5 overflow-hidden">
        <table className="w-full text-left border-collapse">
            <thead>
                <tr className="border-b border-black/5 text-hint text-sm">
                    <th className="p-4 font-medium w-1/4">Phrase</th>
                    <th className="p-4 font-medium w-1/4">Content</th>
                    <th className="p-4 font-medium">Chat</th>
                    <th className="p-4 font-medium">Created</th>
                    <th className="p-4 font-medium">Updated</th>
                    <th className="p-4 font-medium">Uses</th>
                    <th className="p-4 font-medium">Status</th>
                    <th className="p-4 font-medium text-right">Actions</th>
                </tr>
            </thead>
            <tbody>
                {loading && triggers.length === 0 ? (
                    Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i} className="border-b border-black/5 last:border-none">
                            <td className="p-4"><Skeleton className="w-32 h-5" /></td>
                            <td className="p-4"><Skeleton className="w-48 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-20 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-24 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-24 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-10 h-4" /></td>
                            <td className="p-4"><Skeleton className="w-24 h-6 rounded-full" /></td>
                            <td className="p-4"><div className="flex justify-end gap-2"><Skeleton className="w-8 h-8 rounded" /><Skeleton className="w-8 h-8 rounded" /></div></td>
                        </tr>
                    ))
                ) : (
                    triggers.map((trigger) => (
                        <tr key={trigger.id} className="border-b border-black/5 last:border-none hover:bg-black/5 transition-colors">
                            <td className="p-4 font-bold">{trigger.key_phrase}</td>
                            <td className="p-4 text-sm text-hint max-w-xs">
                                {trigger.content?.text && <div className="truncate mb-1">{trigger.content.text}</div>}
                                {(trigger.content?.photo || trigger.content?.sticker || trigger.content?.animation || trigger.content?.video || trigger.content?.voice || trigger.content?.audio || trigger.content?.document) ? (
                                    <TriggerImage
                                        trigger={trigger}
                                        compact={true}
                                    />
                                ) : (
                                    !trigger.content?.text && <span className="italic">[No Content]</span>
                                )}
                            </td>
                            <td className="p-4">
                                <button
                                    onClick={() => setChatId(trigger.chat_id.toString())}
                                    className="flex items-center gap-1 text-sm text-link hover:underline bg-transparent border-none cursor-pointer"
                                >
                                    <MessageSquare size={14} /> {trigger.chat_id}
                                </button>
                            </td>
                            <td className="p-4 text-sm text-hint whitespace-nowrap">
                                {new Date(trigger.created_at).toLocaleDateString()}
                                <div className="text-xs opacity-50">{new Date(trigger.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
                            </td>
                            <td className="p-4 text-sm text-hint whitespace-nowrap">
                                {new Date(trigger.updated_at).toLocaleDateString()}
                                <div className="text-xs opacity-50">{new Date(trigger.updated_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
                            </td>
                            <td className="p-4 text-sm text-hint font-mono">
                                {trigger.usage_count}
                            </td>
                            <td className="p-4">
                                <span className={`px-2 py-1 rounded-full text-xs border ${
                                    trigger.moderation_status === 'safe' ? 'bg-green-500/20 text-green-500 border-green-500/30' :
                                    trigger.moderation_status === 'flagged' ? 'bg-red-500/20 text-red-500 border-red-500/30' :
                                    'bg-yellow-500/20 text-yellow-500 border-yellow-500/30'
                                }`}>
                                    {trigger.moderation_status.toUpperCase()}
                                </span>
                            </td>
                            <td className="p-4">
                                <div className="flex justify-end gap-2">
                                    <button
                                        onClick={() => handleApprove(trigger.id)}
                                        disabled={trigger.moderation_status === 'safe'}
                                        className="p-2 rounded hover:bg-green-500/10 text-green-500 disabled:opacity-30 transition-colors"
                                        title="Approve"
                                    >
                                        <ShieldCheck size={18} />
                                    </button>
                                    <button
                                        onClick={() => handleRequeue(trigger.id)}
                                        className="p-2 rounded hover:bg-blue-500/10 text-blue-500 transition-colors"
                                        title="Requeue"
                                    >
                                        <RefreshCw size={18} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(trigger.id)}
                                        className="p-2 rounded hover:bg-red-500/10 text-red-500 transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 size={18} />
                                    </button>
                                </div>
                            </td>
                        </tr>
                    ))
                )}
            </tbody>
        </table>
        {triggers.length === 0 && !loading && (
            <div className="p-8 text-center text-hint">No triggers found</div>
        )}
      </div>

      {/* Mobile List View */}
      <div className="md:hidden space-y-4">
        {loading && triggers.length === 0 ? (
             Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-section-bg p-4 rounded-xl space-y-3">
                    <div className="flex justify-between">
                        <Skeleton className="w-32 h-6" />
                        <Skeleton className="w-16 h-5 rounded-full" />
                    </div>
                    <Skeleton className="w-full h-12" />
                    <div className="flex gap-2 pt-2">
                        <Skeleton className="flex-1 h-8 rounded" />
                        <Skeleton className="flex-1 h-8 rounded" />
                    </div>
                </div>
             ))
        ) : (
            triggers.map((trigger) => (
            <TriggerCard
                key={trigger.id}
                trigger={trigger}
                onApprove={handleApprove}
                onRequeue={handleRequeue}
                onDelete={handleDelete}
                onChatClick={(id) => setChatId(id.toString())}
            />
            ))
        )}
      </div>

      {hasMore && (
        <button
          onClick={() => fetchTriggersData(false)}
          disabled={loading}
          className="w-full py-3 text-button font-medium hover:bg-button/5 rounded-xl transition-colors disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Load More'}
        </button>
      )}
    </div>
  );
};

export default Triggers;
