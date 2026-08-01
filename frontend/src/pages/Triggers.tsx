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
import { useTelegramBackButton } from '../hooks/useTelegramBackButton';

const STORAGE_KEY = 'triggers_filters';

type ModerationStatus = 'safe' | 'pending' | 'flagged' | 'deleted' | 'banned_chat';
type StatusFilter = 'all' | ModerationStatus;

const statusColors: Record<StatusFilter, string> = {
  all: '',
  safe: 'text-success',
  pending: 'text-warning',
  flagged: 'text-warning',
  deleted: 'text-hint',
  banned_chat: 'text-danger',
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
  // Корневая вкладка -- нативную кнопку "Назад" Telegram прячем
  useTelegramBackButton(false);
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
  const [editorChatTitle, setEditorChatTitle] = useState<string | undefined>(undefined);
  const [editingTrigger, setEditingTrigger] = useState<Trigger | null>(null);

  // Mobile detail view
  const [showMobileDetail, setShowMobileDetail] = useState(false);

  // Bulk remoderation state
  const [bulkProgress, setBulkProgress] = useState<{
    status: string; total: number; processed: number; flagged: number; safe: number;
  } | null>(null);
  const bulkPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Стейт вместо рефа: значение читается в рендере (расчёт ETA), а рефы для этого не годятся
  const [bulkStartTime, setBulkStartTime] = useState<number>(0);
  // Тикающие "текущее время" — чтобы не звать Date.now() прямо в рендере
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (bulkProgress?.status !== 'running') return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [bulkProgress?.status]);

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
  const requestIdRef = useRef(0);

  const fetchTriggers = useCallback(async (reset = false) => {
    if (loading && !reset) return;
    const requestId = ++requestIdRef.current;
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

      // Игнорируем устаревший ответ, если за время запроса ушёл более новый
      if (requestIdRef.current !== requestId) return;

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
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [page, status, search, sortBy, sortOrder, activeOnly, loading]);

  const startBulkRemoderate = async () => {
    const ok = await confirm({
      title: 'Перемодерация',
      message: 'Все триггеры со статусом «Чисто» будут отправлены на повторную проверку AI. Уведомления модераторам отправляться не будут. Продолжить?',
      confirmText: 'Запустить',
      variant: 'warning',
    });
    if (!ok) return;

    try {
      const res = await triggersApi.startBulkRemoderate();
      toast.success(`Перемодерация запущена: ${res.total} триггеров`);
      setBulkStartTime(Date.now());
      setBulkProgress({ status: 'running', total: res.total, processed: 0, flagged: 0, safe: 0 });
      bulkPollRef.current = setInterval(async () => {
        try {
          const p = await triggersApi.getBulkRemodProgress();
          setBulkProgress(p);
          if (p.status === 'completed' || p.processed >= p.total) {
            if (bulkPollRef.current) clearInterval(bulkPollRef.current);
            toast.success(`Перемодерация завершена: чисто ${p.safe}, помечено ${p.flagged}`);
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
          setBulkStartTime(Date.now());
          bulkPollRef.current = setInterval(async () => {
            try {
              const progress = await triggersApi.getBulkRemodProgress();
              setBulkProgress(progress);
              if (progress.status === 'completed' || progress.processed >= progress.total) {
                if (bulkPollRef.current) clearInterval(bulkPollRef.current);
                toast.success(`Перемодерация завершена: чисто ${progress.safe}, помечено ${progress.flagged}`);
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
      toast.success('Триггер одобрен');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  const handleRequeue = async (id: number) => {
    try {
      const updated = await triggersApi.requeue(id);
      updateTriggerInList(id, updated);
      toast.info('Триггер отправлен на перепроверку');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  const handleDelete = async (id: number) => {
    const confirmed = await confirm({
      title: 'Удалить триггер',
      message: 'Удалить этот триггер? Действие нельзя отменить.',
      confirmText: 'Удалить',
      cancelText: 'Отмена',
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
      toast.success('Триггер удалён');
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
      title: 'Забанить чат',
      message: `Забанить чат ${selectedTrigger?.chat_title || `#${chatId}`} и удалить этот триггер? Бот покинет чат.`,
      confirmText: 'Забанить',
      cancelText: 'Отмена',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await chatsApi.ban(chatId, { reason: `Забанен по модерации триггера #${triggerId}` });
      await triggersApi.delete(triggerId);
      setTriggers(prev => prev.filter(t => t.id !== triggerId));
      setTotal(prev => Math.max(0, prev - 1));
      if (selectedTrigger?.id === triggerId) {
        setSelectedTrigger(null);
        setShowMobileDetail(false);
      }
      toast.success('Чат забанен, триггер удалён');
      fetchStats();
    } catch {
      // Error handled by interceptor
    }
  };

  // Bulk selection
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const lastCheckedRef = useRef<number | null>(null);

  // Смена любого фильтра сбрасывает выделение — сброс делаем прямо в обработчиках
  // изменения фильтра, а не отдельным эффектом (setState в эффекте без внешнего источника)
  const handleSearchChange = (value: string) => {
    setSearch(value);
    setCheckedIds(new Set());
  };

  const handleSortOrderToggle = () => {
    setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    setCheckedIds(new Set());
  };

  const handleActiveOnlyChange = (value: boolean) => {
    setActiveOnly(value);
    setCheckedIds(new Set());
  };

  const handleSortByChange = (value: string) => {
    setSortBy(value);
    setCheckedIds(new Set());
  };

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
    toast.success(`Одобрено: ${succeeded}/${items.length}`);
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
    toast.info(`Отправлено на перепроверку: ${succeeded}/${items.length}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleBulkDelete = async () => {
    const items = getCheckedTriggers();
    if (!items.length) return;
    const confirmed = await confirm({
      title: 'Удалить триггеры',
      message: `Удалить триггеров: ${items.length}? Действие нельзя отменить.`,
      confirmText: 'Удалить все',
      cancelText: 'Отмена',
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
    toast.success(`Удалено: ${succeeded}/${items.length}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleBulkBan = async () => {
    const items = getCheckedTriggers();
    const uniqueChats = [...new Set(items.map(t => t.chat_id))];
    if (!uniqueChats.length) return;
    const confirmed = await confirm({
      title: 'Забанить чаты',
      message: `Забанить чатов: ${uniqueChats.length} и удалить триггеров: ${items.length}? Бот покинет эти чаты.`,
      confirmText: 'Забанить все',
      cancelText: 'Отмена',
      variant: 'danger',
    });
    if (!confirmed) return;
    setBulkLoading(true);
    await Promise.allSettled(uniqueChats.map(cid =>
      chatsApi.ban(cid, { reason: 'Забанено массовой модерацией' })
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
    toast.success(`Забанено чатов: ${uniqueChats.length}, удалено триггеров: ${succeeded}`);
    fetchStats();
    setBulkLoading(false);
  };

  const handleSelect = (trigger: Trigger) => {
    setSelectedTrigger(trigger);
    setEditorMode('view');
    setShowMobileDetail(true);
  };

  const handleOpenCreate = () => {
    // chat_id/название берём из выбранного триггера, если есть; иначе пусто -- чат
    // выберет сам пользователь через поиск в TriggerEditor. Это единственный способ
    // завести первый триггер в чате, где ещё нет ни одного (взять chat_id больше неоткуда)
    setEditorChatId(selectedTrigger?.chat_id ?? 0);
    setEditorChatTitle(selectedTrigger?.chat_title ?? undefined);
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
    setCheckedIds(new Set());
  };

  const statEntries: { key: ModerationStatus; label: string }[] = [
    { key: 'safe', label: 'Чисто' },
    { key: 'pending', label: 'В очереди' },
    { key: 'flagged', label: 'Помечен' },
    { key: 'deleted', label: 'Удалён' },
    { key: 'banned_chat', label: 'Забанен' },
  ];

  return (
    <div className="p-4 max-w-7xl mx-auto h-[calc(100vh-2rem)]">
      <Breadcrumbs />

      {/* Header. flex-wrap обязателен: на 360px заголовок, счётчик и обе кнопки в одну
          строку не помещаются -- без переноса "Перемодерация" уезжала за край экрана,
          а счётчик наползал на заголовок и ломался на две строки. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <Zap size={24} className="text-link shrink-0" />
          <h1 className="text-2xl font-bold m-0">Триггеры</h1>
          <span className="text-sm text-hint whitespace-nowrap">{total}</span>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={handleOpenCreate}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-button text-button-text hover:opacity-90 transition-opacity"
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
        const elapsed = bulkStartTime ? (now - bulkStartTime) / 1000 : 0;
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
                className="h-full bg-button rounded-full transition-[width] duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex gap-4 text-xs">
              <span className="text-success">Чисто: {bulkProgress.safe}</span>
              <span className={bulkProgress.flagged > 0 ? 'text-warning' : 'text-hint'}>Помечено: {bulkProgress.flagged}</span>
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
              key={editorMode === 'edit' ? editingTrigger?.id : 'new'}
              chatId={editorChatId}
              chatTitle={editorChatTitle}
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
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-hint" size={16} />
                <input
                  type="text"
                  placeholder="Поиск триггеров…"
                  value={search}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-elevated text-text border border-border rounded-[10px] text-sm outline-none focus:border-button transition-colors placeholder:text-hint"
                />
              </div>
              <button
                type="button"
                onClick={handleSortOrderToggle}
                className="px-3 py-2 bg-elevated border border-border rounded-[10px] text-hint hover:text-text transition-colors"
                title={sortOrder === 'asc' ? 'По возрастанию' : 'По убыванию'}
              >
                <ArrowUpDown size={16} className={sortOrder === 'asc' ? 'rotate-180' : ''} />
              </button>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              <FilterChip active={activeOnly} onClick={() => handleActiveOnlyChange(true)}>Только активные</FilterChip>
              <FilterChip active={!activeOnly} onClick={() => handleActiveOnlyChange(false)}>Все чаты</FilterChip>
              <select
                value={sortBy}
                onChange={(e) => handleSortByChange(e.target.value)}
                className="ml-auto px-2.5 py-1.5 rounded-full text-xs font-medium bg-elevated text-hint border border-border appearance-none cursor-pointer"
              >
                <option value="created_at">По дате</option>
                <option value="usage_count">По использованию</option>
                <option value="key_phrase">По фразе</option>
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
                title={checkedIds.size === triggers.length ? 'Снять выделение' : 'Выбрать все'}
              >
                <CheckSquare size={16} />
              </button>
              <span className="text-sm font-medium text-text mr-1">Выбрано: {checkedIds.size}</span>
              <button onClick={() => setCheckedIds(new Set())} className="p-1 text-hint hover:text-text">
                <X size={14} />
              </button>
              <div className="flex gap-1.5 ml-auto flex-wrap">
                <button
                  onClick={handleBulkApprove}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-success-soft text-success hover:bg-success-soft transition-colors disabled:opacity-50"
                >
                  <CheckCircle size={14} /> Одобрить
                </button>
                <button
                  onClick={handleBulkRequeue}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-elevated text-text hover:bg-border transition-colors disabled:opacity-50"
                >
                  <Clock size={14} /> На перепроверку
                </button>
                <button
                  onClick={handleBulkDelete}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-danger-soft text-danger hover:bg-danger-soft transition-colors disabled:opacity-50"
                >
                  <Trash2 size={14} /> Удалить
                </button>
                <button
                  onClick={handleBulkBan}
                  disabled={bulkLoading}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-danger-soft text-danger hover:bg-danger-soft transition-colors disabled:opacity-50"
                >
                  <ShieldBan size={14} /> Забанить
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
                key={editorMode === 'edit' ? editingTrigger?.id : 'new'}
                chatId={editorChatId}
                chatTitle={editorChatTitle}
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
