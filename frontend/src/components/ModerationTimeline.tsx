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
} from 'lucide-react';
import type { ModerationHistoryItem } from '../types';
import { triggersApi } from '../api/client';

const STEP_CONFIG: Record<string, {
  label: string;
  icon: React.ComponentType<{ size: number; className?: string }>;
  colorClass: string;
}> = {
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

interface Props {
  triggerId: number;
}

const ModerationTimeline: React.FC<Props> = ({ triggerId }) => {
  const [history, setHistory] = useState<ModerationHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="space-y-1">
      <h4 className="text-sm font-medium text-text mb-3">Прогресс модерации</h4>

      <div className="relative">
        {/* Вертикальная линия */}
        <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-secondary-bg" />

        {history.map((item, index) => {
          const config = STEP_CONFIG[item.step] || {
            label: item.step,
            icon: Clock,
            colorClass: 'text-hint',
          };
          const Icon = config.icon;
          const isLast = index === history.length - 1;
          const time = new Date(item.created_at).toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          });

          return (
            <div key={item.id} className="relative flex items-start gap-3 pb-3">
              {/* Иконка */}
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

              {/* Контент */}
              <div className="flex-1 min-w-0 pt-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-text">{config.label}</span>
                  <span className="text-xs text-hint">{time}</span>
                </div>

                {item.details && Object.keys(item.details).length > 0 && (
                  <div className="mt-1 text-xs text-hint">
                    {'reasoning' in item.details && item.details.reasoning != null && (
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
        })}
      </div>
    </div>
  );
};

export default ModerationTimeline;
