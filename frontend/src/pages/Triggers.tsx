import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ArrowLeft, Zap, ArrowUpDown, Search, RefreshCw, CheckCircle, Clock, Trash2, ShieldBan, X, CheckSquare, Plus } from 'lucide-react';
import { triggersApi, chatsApi } from '../api/client';
import { toast, confirm } from '../store/store';
import type { Trigger, TriggerStatsResponse } from '../types/index';
import Breadcrumbs from '../components/Breadcrumbs';
import TriggerCardList from '../components/TriggerCardList';
import TriggerDetailPanel from '../components/TriggerDetailPanel';
import TriggerEditor from '../components/TriggerEditor';
import FilterChip from '../components/ui/FilterChip';

const STORAGE_KEY = 'triggers_filters';

type ModerationStatus = 'safe' | 'pending' | 'flagged' | 'deleted' | 'banned_chat';
type StatusFilter = 'all' | ModerationStatus;

const statusColors: Record<StatusFilter, string> = {
  all: '',
  safe: 'text-success',
  pending: 'text-[#fbbf24]',
  flagged: 'text-[#fbbf24]',
  deleted: 'text-hint',
  banned_chat: 'text-[#f87171]',
};

const getInitialState = () => {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved);
  } catch {
    // Ignore parse errors
  }
  return {
    status: 'all' as StatusFilter,
    sortBy: 'created_at',
    sortOrder: 'desc',
    activeOnly: true,
    search: '',
  };
};

const Triggers: React.FC = () => {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [selectedTrigger, setSelectedTrigger] = useState<Trigger | null>(null);
  const [stats, setStats] = useState<TriggerStatsResponse | null>(null);

  // Редактор триггера
  type EditorMode = 'view' | 'create' | 'edit';
  const [editorMode, setEditorMode] = useState<EditorMode>('view');
  const [editorChatId, setEditorChatId] = useState<number>(0);
  const [editingTrigger, setEditingTrigger] = useState<Trigger | null>(null);

  // Mobile detail view
  const [showMobileDetail, setShowMobileDetail] = useState(false);

  // Bulk remoderation state
  const [bulkProgress, setBulkProgress] = useState<{
    status: string; total: number; processed: number; flagged: number; safe: number;
  } | null>(null);
  const bulkPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bulkStartTimeRef = useRef<number>(0);

  const startBulkRemoderate = async () => {
    const ok = await confirm({
      title: 'Перемодерация',
      message: 'Все триггеры со статусом Safe будут отправлены на повторную проверку AI. Уведомления модераторам отправляться не будут. Продолжить?',
      confirmText: 'Запустить',
      variant: 'warning',
    });
    if (!ok) return;

    try {
      const res = await triggersApi.startBulkRemoderate();
      toast.success(`Перемодерация запущена: ${res.total} триггеров`);
      bulkStartTimeRef.current = Date.now();
      setBulkProgress({ status: 'running', total: res.total, processed: 0, flagged: 0, safe: 0 });
      bulkPollRef.current = setInterval(async () => {
        try {
          const p = await triggersApi.getBulkRemodProgress();
          setBulkProgress(p);
          if (p.status === 'completed' || p.processed >= p.total) {
            if (bulkPollRef.current) clearInterval(bulkPollRef.current);
            toast.success(`Перемодерация завершена: ${p.safe} Safe, ${p.flagged} Flagged`);
            fetchTriggers(true);
          }
        } catch { /* ignore */ }
      }, 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка';
      toast.error(msg);
    }
  };

  // Check if bulk remoderation is already running on page load
  useEffect(() => {
    const checkBulkProgress = async () => {
      try {
        const p = await triggersApi.getBulkRemodProgress();
        if (p.status === 'running' && p.processed < p.total) {
          setBulkProgress(p);
          bulkStartTimeRef.current = Date.now();
          bulkPollRef.current = setInterval(async () => {
            try {
              const progress = await triggersApi.getBulkRemodProgress();
              setBulkProgress(progress);
              if (progress.status === 'completed' || progress.processed >= progress.total) {
                if (bulkPollRef.current) clearInterval(bulkPollRef.current);
                toast.success(`Перемодерация завершена: ${progress.safe} Safe, ${progress.flagged} Flagged`);
                fetchTriggers(true);
              }
            } catch { /* ignore */ }
          }, 3000);
        }
      } catch { /* ignore */ }
    };
    checkBulkProgress();
    return () => { if (bulkPollRef.current) clearInterval(bulkPollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filters
  const [initialState] = useState(getInitialState);
  const [search, setSearch] = useState(initialState.search);
  const [status, setStatus] = useState<StatusFilter>(initialState.status);
  const [sortBy, setSortBy] = useState(initialState.sortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialState.sortOrder);
  const [activeOnly, setActiveOnly] = useState(initialState.activeOnly);

  // Persist filters
  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ status, sortBy, sortOrder, activeOnly, search }));
  }, [status, sortBy, sortOrder, activeOnly, search]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const data = await triggersApi.getStats(activeOnly);
      setStats(data);
    } catch {
      // Stats are non-critical
    }
  }, [activeOnly]);

  // Fetch triggers
  const fetchTriggers = useCallback(async (reset = false) => {
    if (loading && !reset) return;
    setLoading(true);
    try {
      const currentPage = reset ? 1 : page;
      const res = await triggersApi.getAll({
        page: currentPage,
        limit: 20,
        status: status === 'all' ? undefined : status,
        search: search || undefined,
        sort_by: sortBy as 'created_at' | 'key_phrase' | 'usage_count',
        order: sortOrder,
        active_only: activeOnly,
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
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  }, [page, status, search, sortBy, sortOrder, activeOnly, loading]);

  // Refetch on filter change
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchTriggers(true);
      fetchStats();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, search, sortBy, sortOrder, activeOnly]);

  const matchesCurrentFilter = (trigger: Trigger) => {
    return status === 'all' || trigger.moderation_status === status;
  };

  const updateTriggerInList = (id: number, updated: Trigger) => {
    if (matchesCurrentFilter(updated)) {
      setTriggers(prev => prev.map(t => t.id === id ? updated : t));
    } else {
      setTriggers(prev => prev.filter(t => t.id !== id));
      setTotal(prev => Math.max(0, prev - 1));
    }
    if (selectedTrigger?.id === id) setSelectedTrigger(updated);
  };

  const handleApprove = async (id: number) => {
    try {
      const updated = await triggersApi.approve(id);
      updateTriggerInList(id, updated);
      toast.success('Trigger approved');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  const handleRequeue = async (id: number) => {
    try {
      const updated = await triggersApi.requeue(id);
      updateTriggerInList(id, updated);
      toast.info('Trigger requeued');
      fetchStats();
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
      setTotal(prev => Math.max(0, prev - 1));
      if (selectedTrigger?.id === id) {
        setSelectedTrigger(null);
        setShowMobileDetail(false);
      }
      toast.success('Trigger deleted');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  const handleTriggerUpdate = async (id: number) => {
    try {
      const updated = await triggersApi.getById(id);
      updateTriggerInList(id, updated);
      fetchStats();
    } catch {
      console.error('Failed to update trigger');
    }
  };

  const handleBanChat = async (chatId: number, triggerId: number) => {
    const confirmed = await confirm({
      title: 'Ban Chat',
      message: `Ban chat ${selectedTrigger?.chat_title || `#${chatId}`} and delete this trigger? The bot will leave the chat.`,
      confirmText: 'Ban',
      cancelText: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await chatsApi.ban(chatId, { reason: `Banned via trigger #${triggerId} moderation` });
      await triggersApi.delete(triggerId);
      setTriggers(prev => prev.filter(t => t.id !== triggerId));
      setTotal(prev => Math.max(0, prev - 1));
      if (selectedTrigger?.id === triggerId) {
        setSelectedTrigger(null);
        setShowMobileDetail(false);
      }
      toast.success('Chat banned, trigger deleted');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  // Bulk selection
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const lastCheckedRef = useRef<number | null>(null);

  // Clear selection when filters change
  useEffect(() => {
    setCheckedIds(new Set());
  }, [status, search, sortBy, sortOrder, activeOnly]);

  const handleToggleCheck = useCallback((id: number, shiftKey: boolean) => {
    setCheckedIds(prev => {
      const next = new Set(prev);

      if (shiftKey && lastCheckedRef.current !== null) {
        const lastIdx = triggers.findIndex(t => t.id === lastCheckedRef.current);
        const currIdx = triggers.findIndex(t => t.id === id);
        if (lastIdx !== -1 && currIdx !== -1) {
          const [from, to] = lastIdx < currIdx ? [lastIdx, currIdx] : [currIdx, lastIdx];
          for (let i = from; i <= to; i++) {
            next.add(triggers[i].id);
          }
          return next;
        }
      }

      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      lastCheckedRef.current = id;
      return next;
    });
  }, [triggers]);

  const handleSelectAll = () => {
    if (checkedIds.size === triggers.length) {
      setCheckedIds(new Set());
    } else {
      setCheckedIds(new Set(triggers.map(t => t.id)));
    }
  };

  const getCheckedTriggers = () => triggers.filter(t => checkedIds.has(t.id));

  const handleBulkApprove = async () => {
    const items = getCheckedTriggers();
    if (!items.length) return;
    setBulkLoading(true);
    const results = await Promise.allSettled(items.map(t => triggersApi.approve(t.id)));
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') updateTriggerInList(items[i].id, r.value);
    });
    setCheckedIds(new Set());
    toast.success(`Approved: ${succeeded}/${items.length}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleBulkRequeue = async () => {
    const items = getCheckedTriggers();
    if (!items.length) return;
    setBulkLoading(true);
    const results = await Promise.allSettled(items.map(t => triggersApi.requeue(t.id)));
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') updateTriggerInList(items[i].id, r.value);
    });
    setCheckedIds(new Set());
    toast.info(`Requeued: ${succeeded}/${items.length}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleBulkDelete = async () => {
    const items = getCheckedTriggers();
    if (!items.length) return;
    const confirmed = await confirm({
      title: 'Delete Triggers',
      message: `Delete ${items.length} trigger(s)? This cannot be undone.`,
      confirmText: 'Delete All',
      cancelText: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    setBulkLoading(true);
    const results = await Promise.allSettled(items.map(t => triggersApi.delete(t.id)));
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const deletedIds = new Set(items.filter((_, i) => results[i].status === 'fulfilled').map(t => t.id));
    setTriggers(prev => prev.filter(t => !deletedIds.has(t.id)));
    setTotal(prev => Math.max(0, prev - succeeded));
    if (selectedTrigger && deletedIds.has(selectedTrigger.id)) {
      setSelectedTrigger(null);
      setShowMobileDetail(false);
    }
    setCheckedIds(new Set());
    toast.success(`Deleted: ${succeeded}/${items.length}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleBulkBan = async () => {
    const items = getCheckedTriggers();
    const uniqueChats = [...new Set(items.map(t => t.chat_id))];
    if (!uniqueChats.length) return;
    const confirmed = await confirm({
      title: 'Ban Chats',
      message: `Ban ${uniqueChats.length} chat(s) and delete ${items.length} trigger(s)? The bot will leave these chats.`,
      confirmText: 'Ban All',
      cancelText: 'Cancel',
      variant: 'danger',
    });
    if (!confirmed) return;
    setBulkLoading(true);
    await Promise.allSettled(uniqueChats.map(cid =>
      chatsApi.ban(cid, { reason: 'Banned via bulk moderation' })
    ));
    const deleteResults = await Promise.allSettled(items.map(t => triggersApi.delete(t.id)));
    const succeeded = deleteResults.filter(r => r.status === 'fulfilled').length;
    const deletedIds = new Set(items.filter((_, i) => deleteResults[i].status === 'fulfilled').map(t => t.id));
    setTriggers(prev => prev.filter(t => !deletedIds.has(t.id)));
    setTotal(prev => Math.max(0, prev - succeeded));
    if (selectedTrigger && deletedIds.has(selectedTrigger.id)) {
      setSelectedTrigger(null);
      setShowMobileDetail(false);
    }
    setCheckedIds(new Set());
    toast.success(`Banned ${uniqueChats.length} chat(s), deleted ${succeeded} trigger(s)`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleSelect = (trigger: Trigger) => {
    setSelectedTrigger(trigger);
    setEditorMode('view');
    setShowMobileDetail(true);
  };

  const handleOpenCreate = () => {
    // chat_id берём из выбранного триггера, если есть; иначе 0 (пользователь выберет)
    setEditorChatId(selectedTrigger?.chat_id ?? 0);
    setEditingTrigger(null);
    setEditorMode('create');
    setShowMobileDetail(false);
  };

  const handleOpenEdit = (trigger: Trigger) => {
    setEditorChatId(trigger.chat_id);
    setEditingTrigger(trigger);
    setEditorMode('edit');
  };

  const handleEditorSaved = (saved: Trigger) => {
    if (editorMode === 'create') {
      // Добавляем в начало списка
      setTriggers(prev => [saved, ...prev]);
      setTotal(prev => prev + 1);
    } else {
      updateTriggerInList(saved.id, saved);
    }
    setEditorMode('view');
    setSelectedTrigger(saved);
    fetchStats();
  };

  const handleEditorCancel = () => {
    setEditorMode('view');
  };

  const handleStatusClick = (s: StatusFilter) => {
    setStatus(prev => prev === s ? 'all' : s);
  };

  const statEntries: { key: ModerationStatus; label: string }[] = [
    { key: 'safe', label: 'Safe' },
    { key: 'pending', label: 'Pending' },
    { key: 'flagged', label: 'Flagged' },
    { key: 'deleted', label: 'Deleted' },
    { key: 'banned_chat', label: 'Banned' },
  ];

  return (
    <div className="p-4 max-w-7xl mx-auto h-[calc(100vh-2rem)]">
      <Breadcrumbs />

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center">
          <Zap size={24} className="mr-2.5 text-link" />
          <h1 className="text-2xl font-bold m-0">Triggers</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-hint">{total} total</div>
          <button
            onClick={handleOpenCreate}
            disabled={!selectedTrigger}
            title={!selectedTrigger ? 'Выберите триггер (чат), чтобы создать новый' : undefined}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-button text-button-text hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={14} />
            Создать
          </button>
          <button
            onClick={startBulkRemoderate}
            disabled={bulkProgress?.status === 'running'}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-section-bg text-text hover:bg-secondary-bg transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={bulkProgress?.status === 'running' ? 'animate-spin' : ''} />
            Перемодерация
          </button>
        </div>
      </div>

      {/* Bulk remoderation progress */}
      {bulkProgress && bulkProgress.status === 'running' && (() => {
        const pct = bulkProgress.total ? Math.round(bulkProgress.processed / bulkProgress.total * 100) : 0;
        const elapsed = bulkStartTimeRef.current ? (Date.now() - bulkStartTimeRef.current) / 1000 : 0;
        const speed = elapsed > 0 && bulkProgress.processed > 0 ? bulkProgress.processed / elapsed : 0;
        const remaining = speed > 0 ? Math.round((bulkProgress.total - bulkProgress.processed) / speed) : 0;
        const etaMin = Math.floor(remaining / 60);
        const etaHours = Math.floor(etaMin / 60);
        const etaStr = remaining > 0
          ? etaHours > 0 ? `~${etaHours}ч ${etaMin % 60}мин` : `~${etaMin}мин`
          : '';

        return (
          <div className="mb-4 p-4 rounded-[14px] bg-surface border border-border">
            <div className="flex justify-between items-center text-sm mb-2">
              <span className="font-medium">Перемодерация: {bulkProgress.processed}/{bulkProgress.total} ({pct}%)</span>
              {etaStr && <span className="text-hint">{etaStr}</span>}
            </div>
            <div className="h-2 bg-elevated rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-button rounded-full transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex gap-4 text-xs">
              <span className="text-success">Safe: {bulkProgress.safe}</span>
              <span className={bulkProgress.flagged > 0 ? 'text-[#fbbf24]' : 'text-hint'}>Flagged: {bulkProgress.flagged}</span>
              {speed > 0 && <span className="text-hint">{speed.toFixed(1)} триг/сек</span>}
            </div>
          </div>
        );
      })()}

      {/* Status counters */}
      {stats && (
        <div className="flex gap-1.5 flex-wrap mb-4">
          {statEntries.map(({ key, label }) => (
            <FilterChip
              key={key}
              active={status === key}
              onClick={() => handleStatusClick(key)}
            >
              <span className={statusColors[key]}>{label}: {stats[key]}</span>
            </FilterChip>
          ))}
        </div>
      )}

      {/* Mobile: detail view */}
      {showMobileDetail && selectedTrigger && editorMode === 'view' && (
        <div className="md:hidden fixed inset-0 z-50 bg-bg">
          <div className="flex items-center p-3 border-b border-border">
            <button onClick={() => setShowMobileDetail(false)} className="flex items-center text-link mr-3">
              <ArrowLeft size={20} />
            </button>
            <span className="font-bold truncate">{selectedTrigger.key_phrase}</span>
          </div>
          <TriggerDetailPanel
            trigger={selectedTrigger}
            onApprove={handleApprove}
            onRequeue={handleRequeue}
            onDelete={handleDelete}
            onBanChat={handleBanChat}
            onTriggerUpdate={handleTriggerUpdate}
            onEdit={handleOpenEdit}
          />
        </div>
      )}

      {/* Mobile: editor */}
      {(editorMode === 'create' || editorMode === 'edit') && (
        <div className="md:hidden fixed inset-0 z-50 bg-bg overflow-y-auto">
          <div className="flex items-center p-3 border-b border-border">
            <button onClick={handleEditorCancel} className="flex items-center text-link mr-3">
              <ArrowLeft size={20} />
            </button>
            <span className="font-bold">
              {editorMode === 'create' ? 'Новый триггер' : `Редактирование #${editingTrigger?.id}`}
            </span>
          </div>
          <div className="p-4">
            <TriggerEditor
              chatId={editorChatId}
              trigger={editorMode === 'edit' ? editingTrigger : null}
              onSaved={handleEditorSaved}
              onCancel={handleEditorCancel}
            />
          </div>
        </div>
      )}

      {/* Split panel */}
      <div className="flex gap-4 h-[calc(100%-8rem)]">
        {/* Left panel — list */}
        <div className="w-full md:w-[45%] flex flex-col min-h-0">
          {/* Filters */}
          <div className="bg-surface border border-border rounded-[14px] p-3 mb-3">
            <div className="flex gap-2 mb-2.5">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#52525b]" size={16} />
                <input
                  type="text"
                  placeholder="Search triggers..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-elevated text-text border border-border rounded-[10px] text-sm outline-none focus:border-button transition-colors placeholder:text-[#52525b]"
                />
              </div>
              <button
                type="button"
                onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                className="px-3 py-2 bg-elevated border border-border rounded-[10px] text-hint hover:text-text transition-colors"
                title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
              >
                <ArrowUpDown size={16} className={sortOrder === 'asc' ? 'rotate-180' : ''} />
              </button>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <FilterChip active={activeOnly} onClick={() => setActiveOnly(true)}>Active only</FilterChip>
              <FilterChip active={!activeOnly} onClick={() => setActiveOnly(false)}>All chats</FilterChip>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="ml-auto px-2.5 py-1.5 rounded-full text-xs font-medium bg-elevated text-hint border border-[#3f3f46] appearance-none cursor-pointer"
              >
                <option value="created_at">By Date</option>
                <option value="usage_count">By Usage</option>
                <option value="key_phrase">By Key</option>
              </select>
            </div>
          </div>

          {/* Trigger list */}
          <div className="flex-1 overflow-y-auto min-h-0">
            <TriggerCardList
              triggers={triggers}
              selectedId={selectedTrigger?.id ?? null}
              onSelect={handleSelect}
              loading={loading}
              checkedIds={checkedIds}
              onToggleCheck={handleToggleCheck}
              hasMore={hasMore}
              onLoadMore={() => fetchTriggers(false)}
            />
          </div>

          {/* Bulk actions toolbar */}
          {checkedIds.size > 0 && (
            <div className="bg-surface border border-border rounded-[14px] p-3 mt-3 flex items-center gap-2 flex-wrap">
              <button
                onClick={handleSelectAll}
                className="p-1.5 text-hint hover:text-text transition-colors"
                title={checkedIds.size === triggers.length ? 'Deselect all' : 'Select all'}
              >
                <CheckSquare size={16} />
              </button>
              <span className="text-sm font-medium text-text mr-1">{checkedIds.size} selected</span>
              <button onClick={() => setCheckedIds(new Set())} className="p-1 text-hint hover:text-text">
                <X size={14} />
              </button>
              <div className="flex gap-1.5 ml-auto">
                <button
                  onClick={handleBulkApprove}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-green-500/10 text-green-500 hover:bg-green-500/20 transition-colors disabled:opacity-50"
                >
                  <CheckCircle size={14} /> Approve
                </button>
                <button
                  onClick={handleBulkRequeue}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                >
                  <Clock size={14} /> Requeue
                </button>
                <button
                  onClick={handleBulkDelete}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors disabled:opacity-50"
                >
                  <Trash2 size={14} /> Delete
                </button>
                <button
                  onClick={handleBulkBan}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors disabled:opacity-50"
                >
                  <ShieldBan size={14} /> Ban
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right panel — details / editor (desktop only) */}
        <div className="hidden md:block flex-1 bg-surface border border-border rounded-[14px] overflow-hidden overflow-y-auto">
          {(editorMode === 'create' || editorMode === 'edit') ? (
            <div className="p-4">
              <div className="text-hint text-xs uppercase tracking-wide mb-3">
                {editorMode === 'create' ? 'Новый триггер' : `Редактирование #${editingTrigger?.id}`}
              </div>
              <TriggerEditor
                chatId={editorChatId}
                trigger={editorMode === 'edit' ? editingTrigger : null}
                onSaved={handleEditorSaved}
                onCancel={handleEditorCancel}
              />
            </div>
          ) : (
            <TriggerDetailPanel
              trigger={selectedTrigger}
              onApprove={handleApprove}
              onRequeue={handleRequeue}
              onDelete={handleDelete}
              onBanChat={handleBanChat}
              onTriggerUpdate={handleTriggerUpdate}
              onEdit={handleOpenEdit}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default Triggers;
