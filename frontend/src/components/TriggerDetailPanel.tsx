import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, Clock, Trash2, ChevronDown, ChevronRight, Zap, ShieldBan, AlertTriangle, Loader2, ExternalLink, Pencil } from 'lucide-react';
import type { Trigger } from '../types/index';
import { triggersApi } from '../api/client';
import StatusBadge from './StatusBadge';
import TriggerImage from './TriggerImage';
import ModerationTimeline from './ModerationTimeline';
import { formatDateTime } from '../lib/dateFormat';

interface TriggerDetailPanelProps {
  trigger: Trigger | null;
  onApprove: (id: number) => void;
  onRequeue: (id: number) => void;
  onDelete: (id: number) => void;
  onBanChat: (chatId: number, triggerId: number) => void;
  onTriggerUpdate: (id: number) => void;
  onEdit?: (trigger: Trigger) => void;
}

interface TriggerContent {
  text?: string;
  buttons?: Array<Array<{ text?: string; url?: string }> | { text?: string; url?: string }>;
  reply_markup?: {
    inline_keyboard?: Array<Array<{ text?: string; url?: string }>>;
    keyboard?: Array<Array<{ text?: string }>>;
  };
  [key: string]: unknown;
}

const accessLabels: Record<string, string> = {
  all: 'Все',
  admins: 'Админы',
  owner: 'Владелец',
};

const TriggerDetailPanel: React.FC<TriggerDetailPanelProps> = ({
  trigger,
  onApprove,
  onRequeue,
  onDelete,
  onBanChat,
  onTriggerUpdate,
  onEdit,
}) => {
  const [jsonExpanded, setJsonExpanded] = useState(false);
  const [queueStatus, setQueueStatus] = useState<boolean | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);

  useEffect(() => {
    if (trigger?.moderation_status === 'pending') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQueueLoading(true);
      triggersApi.getQueueStatus(trigger.id)
        .then(res => setQueueStatus(res.is_processing))
        .catch(() => setQueueStatus(null))
        .finally(() => setQueueLoading(false));
    } else {
      setQueueStatus(null);
    }
  }, [trigger?.id, trigger?.moderation_status]);

  if (!trigger) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-hint p-8">
        <Zap size={48} className="mb-4 opacity-30" />
        <p className="text-lg">Выберите триггер для просмотра деталей</p>
      </div>
    );
  }

  const content = trigger.content as TriggerContent;

  const renderContentPreview = () => {
    if (content.text && typeof content.text === 'string') {
      return (
        <div className="bg-elevated p-3 rounded-lg text-sm whitespace-pre-wrap border border-border">
          {content.text}
        </div>
      );
    }
    return <TriggerImage trigger={trigger} />;
  };

  const renderButtons = () => {
    const buttons = content.buttons ||
      content.reply_markup?.inline_keyboard ||
      content.reply_markup?.keyboard;

    if (!Array.isArray(buttons)) return null;

    return (
      <div className="flex flex-col gap-2 mt-3">
        {buttons.map((row, i: number) => (
          <div key={i} className="flex gap-2 justify-center">
            {Array.isArray(row) ? row.map((btn, j: number) => (
              <div key={j} className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                {btn.text || 'Кнопка'}
              </div>
            )) : (
              <div className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                {(row as { text?: string }).text || 'Кнопка'}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const isStuck = trigger.moderation_status === 'pending' && queueStatus === false;

  return (
    <div className="h-full overflow-y-auto">
      {/* Action bar */}
      <div className="sticky top-0 bg-surface z-10 p-4 border-b border-border">
        <div className="flex gap-2 flex-wrap">
          {onEdit && (
            <button
              onClick={() => onEdit(trigger)}
              className="flex-1 bg-elevated text-text py-2 rounded-lg font-medium hover:bg-button hover:text-button-text transition-colors flex items-center justify-center gap-2"
            >
              <Pencil size={18} /> Редактировать
            </button>
          )}
          {trigger.moderation_status !== 'safe' && (
            <button
              onClick={() => onApprove(trigger.id)}
              className="flex-1 bg-success-soft text-success py-2 rounded-lg font-medium hover:bg-success-soft transition-colors flex items-center justify-center gap-2"
            >
              <CheckCircle size={18} /> Одобрить
            </button>
          )}
          {isStuck ? (
            <button
              onClick={() => onRequeue(trigger.id)}
              className="flex-1 bg-warning-soft text-warning py-2 rounded-lg font-medium hover:bg-warning-soft transition-colors flex items-center justify-center gap-2 ring-1 ring-warning/30"
            >
              <AlertTriangle size={18} /> На перепроверку
            </button>
          ) : (
            <button
              onClick={() => onRequeue(trigger.id)}
              className="flex-1 bg-elevated text-text py-2 rounded-lg font-medium hover:bg-border transition-colors flex items-center justify-center gap-2"
            >
              <Clock size={18} /> На перепроверку
            </button>
          )}
          <button
            onClick={() => onDelete(trigger.id)}
            className="flex-1 bg-danger-soft text-danger py-2 rounded-lg font-medium hover:bg-danger-soft transition-colors flex items-center justify-center gap-2"
          >
            <Trash2 size={18} /> Удалить
          </button>
          <button
            onClick={() => onBanChat(trigger.chat_id, trigger.id)}
            className="flex-1 bg-danger-soft text-danger py-2 rounded-lg font-medium hover:bg-danger-soft transition-colors flex items-center justify-center gap-2"
          >
            <ShieldBan size={18} /> Забанить чат
          </button>
        </div>

        {/* Queue status for pending triggers */}
        {trigger.moderation_status === 'pending' && (
          <div className="mt-2 text-xs flex items-center gap-1.5">
            {queueLoading ? (
              <><Loader2 size={12} className="animate-spin text-hint" /> Проверка очереди…</>
            ) : queueStatus === true ? (
              <><div className="w-2 h-2 rounded-full bg-warning" /> В очереди - обрабатывается</>
            ) : queueStatus === false ? (
              <><AlertTriangle size={12} className="text-warning" /> <span className="text-warning">Завис - не в очереди</span></>
            ) : null}
          </div>
        )}
      </div>

      <div className="p-4 space-y-6">
        {/* Info */}
        <div>
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Информация</h3>
          <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-sm">
            <span className="text-hint">Чат</span>
            <Link to={`/chats/${trigger.chat_id}`} className="text-link hover:underline truncate">
              {trigger.chat_title || `Чат #${trigger.chat_id}`}
            </Link>

            <span className="text-hint">Тип совпадения</span>
            <span className="text-text">{trigger.match_type}</span>

            <span className="text-hint">Учёт регистра</span>
            <span className="text-text">{trigger.is_case_sensitive ? 'Да' : 'Нет'}</span>

            <span className="text-hint">Доступ</span>
            <span className="text-text">{accessLabels[trigger.access_level] || trigger.access_level}</span>

            <span className="text-hint">Шаблон</span>
            <span className="text-text">{trigger.is_template ? 'Да' : 'Нет'}</span>

            <span className="text-hint">Автор</span>
            {trigger.created_by ? (
              <Link to={`/users/${trigger.created_by}`} className="text-link hover:underline">
                Пользователь #{trigger.created_by}
              </Link>
            ) : (
              <span className="text-hint">Система</span>
            )}

            <span className="text-hint">Создан</span>
            <span className="text-text">{formatDateTime(trigger.created_at)}</span>

            <span className="text-hint">Использований</span>
            <span className="text-text">{trigger.usage_count}</span>
          </div>

          {trigger.preview_url && (
            <a
              href={trigger.preview_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 flex items-center gap-1.5 text-sm text-link hover:underline"
            >
              <ExternalLink size={14} />
              Предпросмотр
            </a>
          )}
        </div>

        {/* Content */}
        <div>
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Содержимое</h3>
          {renderContentPreview()}
          {renderButtons()}

          {/* Collapsible Raw JSON */}
          <button
            onClick={() => setJsonExpanded(!jsonExpanded)}
            className="flex items-center gap-1 text-xs text-hint hover:text-text mt-3 transition-colors"
          >
            {jsonExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Исходный JSON
          </button>
          {jsonExpanded && (
            <div className="bg-elevated p-3 rounded-lg overflow-x-auto border border-border mt-1">
              <pre className="text-xs font-mono whitespace-pre-wrap">
                {JSON.stringify(trigger.content, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Moderation */}
        <div>
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Модерация</h3>
          <div className="flex items-center gap-3 mb-3">
            <StatusBadge status={trigger.moderation_status} size="md" />
            {trigger.moderation_category && (
              <span className="text-sm text-hint">{trigger.moderation_category}</span>
            )}
            {trigger.moderation_confidence != null && (
              <span className="text-sm text-hint">увер.: {Math.round(trigger.moderation_confidence * 100)}%</span>
            )}
          </div>
          {trigger.moderation_reason && (
            <div className="bg-elevated p-3 rounded-lg text-sm border border-border mb-3">
              <span className="font-semibold block mb-1 text-hint">Обоснование:</span>
              <div className="whitespace-pre-wrap">{trigger.moderation_reason}</div>
            </div>
          )}
          <ModerationTimeline
            triggerId={trigger.id}
            scrollToTimeline={false}
            onModerationComplete={() => onTriggerUpdate(trigger.id)}
          />
        </div>
      </div>
    </div>
  );
};

export default TriggerDetailPanel;
