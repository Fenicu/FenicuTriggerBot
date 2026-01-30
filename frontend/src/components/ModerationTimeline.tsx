import React, { useEffect, useState } from 'react';
import {
  Clock,
  FileText,
  Image,
  Brain,
  CheckCircle,
  AlertTriangle,
  UserCheck,
  Trash2,
  Ban,
  RefreshCw,
  Send,
  Loader2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { ModerationHistoryItem } from '../types';
import { triggersApi } from '../api/client';

const STEP_CONFIG: Record<
  string,
  {
    label: string;
    icon: React.ComponentType<{ size: number; className?: string }>;
    colorClass: string;
  }
> = {
  created: { label: 'Триггер создан', icon: FileText, colorClass: 'text-blue-500' },
  queued: { label: 'В очереди модерации', icon: Clock, colorClass: 'text-yellow-500' },
  processing_started: { label: 'Начата обработка', icon: RefreshCw, colorClass: 'text-blue-500' },
  media_processing: { label: 'Обработка медиа', icon: Image, colorClass: 'text-purple-500' },
  media_processed: { label: 'Медиа обработано', icon: Image, colorClass: 'text-green-500' },
  vision_analyzing: { label: 'Vision анализирует', icon: Brain, colorClass: 'text-purple-500' },
  vision_completed: { label: 'Vision завершил', icon: Brain, colorClass: 'text-green-500' },
  text_analyzing: { label: 'Классификация', icon: Brain, colorClass: 'text-purple-500' },
  text_completed: { label: 'Классификация завершена', icon: Brain, colorClass: 'text-green-500' },
  auto_approved: { label: 'Автоматически одобрен', icon: CheckCircle, colorClass: 'text-green-500' },
  auto_flagged: { label: 'Помечен для проверки', icon: AlertTriangle, colorClass: 'text-orange-500' },
  auto_error: { label: 'Ошибка обработки', icon: AlertTriangle, colorClass: 'text-red-500' },
  alert_sent: { label: 'Отправлен модератору', icon: Send, colorClass: 'text-orange-500' },
  manual_approved: { label: 'Одобрен модератором', icon: UserCheck, colorClass: 'text-green-500' },
  manual_deleted: { label: 'Удален модератором', icon: Trash2, colorClass: 'text-red-500' },
  manual_banned: { label: 'Чат забанен', icon: Ban, colorClass: 'text-red-500' },
  requeued: { label: 'На перепроверку', icon: RefreshCw, colorClass: 'text-blue-500' },
};

// Шаги, которые начинают новый "запуск" модерации
const RUN_START_STEPS = ['queued', 'requeued'];

interface ModerationRun {
  items: ModerationHistoryItem[];
  startTime: string;
}

function groupHistoryByRuns(history: ModerationHistoryItem[]): ModerationRun[] {
  const runs: ModerationRun[] = [];
  let currentRun: ModerationHistoryItem[] = [];

  for (const item of history) {
    if (RUN_START_STEPS.includes(item.step) && currentRun.length > 0) {
      // Начинается новый запуск, сохраняем предыдущий
      runs.push({
        items: currentRun,
        startTime: currentRun[0].created_at,
      });
      currentRun = [];
    }
    currentRun.push(item);
  }

  // Добавляем последний запуск
  if (currentRun.length > 0) {
    runs.push({
      items: currentRun,
      startTime: currentRun[0].created_at,
    });
  }

  return runs;
}

interface Props {
  triggerId: number;
  scrollToTimeline?: boolean;
}

const ModerationTimeline: React.FC<Props> = ({ triggerId, scrollToTimeline }) => {
  const [history, setHistory] = useState<ModerationHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRuns, setExpandedRuns] = useState<Set<number>>(new Set());
  const timelineRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        const data = await triggersApi.getModerationHistory(triggerId);
        setHistory(data.items);
        setError(null);
      } catch (e) {
        setError('Не удалось загрузить историю');
        console.error('Failed to load moderation history:', e);
      } finally {
        setLoading(false);
      }
    };

    loadHistory();

    const unsubscribe = triggersApi.streamModerationHistory(triggerId, (newItem) => {
      setHistory((prev) => {
        if (prev.some((item) => item.id === newItem.id)) {
          return prev;
        }
        return [...prev, newItem];
      });
    });

    return () => {
      unsubscribe();
    };
  }, [triggerId]);

  // Прокрутка к таймлайну при scrollToTimeline
  useEffect(() => {
    if (scrollToTimeline && timelineRef.current && !loading) {
      timelineRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [scrollToTimeline, loading]);

  const toggleRun = (runIndex: number) => {
    setExpandedRuns((prev) => {
      const next = new Set(prev);
      if (next.has(runIndex)) {
        next.delete(runIndex);
      } else {
        next.add(runIndex);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-hint">
        <Loader2 size={20} className="animate-spin mr-2" />
        <span>Загрузка истории...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-8 text-red-500">
        <AlertTriangle size={20} className="mr-2" />
        <span>{error}</span>
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-hint">
        <Clock size={20} className="mr-2" />
        <span>История модерации пуста</span>
      </div>
    );
  }

  const runs = groupHistoryByRuns(history);
  const latestRunIndex = runs.length - 1;

  const renderTimelineItem = (item: ModerationHistoryItem, isLast: boolean) => {
    const config = STEP_CONFIG[item.step] || {
      label: item.step,
      icon: Clock,
      colorClass: 'text-hint',
    };
    const Icon = config.icon;
    const time = new Date(item.created_at).toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    // Не показываем reasoning для auto_approved (дублирование)
    const showReasoning = item.step !== 'auto_approved';

    return (
      <div key={item.id} className="relative flex gap-3">
        {/* Иконка с коннектором */}
        <div className="relative flex flex-col items-center shrink-0 pb-3">
          {/* Круг */}
          <div
            className={`
              relative z-10 flex items-center justify-center
              w-6 h-6 rounded-full bg-section-bg border-2
              ${isLast ? 'border-link' : 'border-secondary-bg'}
              ${isLast ? 'animate-pulse' : ''}
            `}
          >
            <Icon size={12} className={config.colorClass} />
          </div>
          {/* Линия-коннектор к следующему элементу */}
          {!isLast && (
            <div className="w-0.5 flex-1 bg-secondary-bg -mb-3" />
          )}
        </div>

        {/* Контент */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-text">{config.label}</span>
            <span className="text-xs text-hint">{time}</span>
          </div>

          {item.details && Object.keys(item.details).length > 0 && (
            <div className="mt-1 text-xs text-hint">
              {showReasoning && 'reasoning' in item.details && item.details.reasoning != null && (
                <p className="truncate">Причина: {String(item.details.reasoning)}</p>
              )}
              {'category' in item.details && item.details.category != null && (
                <p>Категория: {String(item.details.category)}</p>
              )}
              {'confidence' in item.details && item.details.confidence != null && (
                <p>Уверенность: {(Number(item.details.confidence) * 100).toFixed(0)}%</p>
              )}
              {'marked_by' in item.details && item.details.marked_by != null && (
                <p>Модератор: {String(item.details.marked_by)}</p>
              )}
              {'deleted_by' in item.details && item.details.deleted_by != null && (
                <p>Удалил: {String(item.details.deleted_by)}</p>
              )}
              {'banned_by' in item.details && item.details.banned_by != null && (
                <p>Забанил: {String(item.details.banned_by)}</p>
              )}
              {'error' in item.details && item.details.error != null && (
                <p className="text-red-400">Ошибка: {String(item.details.error)}</p>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div ref={timelineRef} className="space-y-1">
      <h4 className="text-sm font-medium text-text mb-3">Прогресс модерации</h4>

      {/* Показываем предыдущие запуски как сворачиваемые секции */}
      {runs.length > 1 &&
        runs.slice(0, -1).map((run, runIndex) => {
          const isExpanded = expandedRuns.has(runIndex);
          const runDate = new Date(run.startTime).toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          });

          return (
            <div key={runIndex} className="mb-3">
              <button
                onClick={() => toggleRun(runIndex)}
                className="flex items-center gap-2 text-xs text-hint hover:text-text transition-colors w-full"
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span>Предыдущий запуск ({runDate})</span>
              </button>

              {isExpanded && (
                <div className="relative mt-2 ml-2 pl-3 border-l-2 border-secondary-bg">
                  {run.items.map((item, idx) =>
                    renderTimelineItem(item, idx === run.items.length - 1)
                  )}
                </div>
              )}
            </div>
          );
        })}

      {/* Последний (текущий) запуск - всегда развернут */}
      <div className="relative">
        {runs[latestRunIndex].items.map((item, idx) =>
          renderTimelineItem(item, idx === runs[latestRunIndex].items.length - 1)
        )}
      </div>
    </div>
  );
};

export default ModerationTimeline;
