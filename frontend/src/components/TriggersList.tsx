import React from 'react';
import type { Trigger } from '../types/index';
import { Eye, Trash2, FileText, MoreVertical, ShieldCheck, RefreshCw, Image, Video, Film, Sticker, Mic, Music, FileIcon, Dices, Circle } from 'lucide-react';
import TriggerImage from './TriggerImage';
import StatusBadge from './StatusBadge';

interface TriggersListProps {
  triggers: Trigger[];
  onDelete: (id: number) => void;
  onViewDetails: (trigger: Trigger) => void;
  onApprove?: (id: number) => void;
  onRequeue?: (id: number) => void;
  onChatClick?: (chatId: number) => void;
  onStatusClick?: (trigger: Trigger) => void;
}

const contentTypeConfig: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  text: { label: 'Текст', icon: FileText, color: 'text-hint' },
  photo: { label: 'Фото', icon: Image, color: 'text-hint' },
  video: { label: 'Видео', icon: Video, color: 'text-hint' },
  video_note: { label: 'Видеосообщение', icon: Circle, color: 'text-hint' },
  animation: { label: 'GIF', icon: Film, color: 'text-hint' },
  sticker: { label: 'Стикер', icon: Sticker, color: 'text-hint' },
  voice: { label: 'Голосовое', icon: Mic, color: 'text-hint' },
  audio: { label: 'Аудио', icon: Music, color: 'text-hint' },
  document: { label: 'Документ', icon: FileIcon, color: 'text-hint' },
  dice: { label: 'Кубик', icon: Dices, color: 'text-hint' },
};

const getContentType = (trigger: Trigger): string => {
  const content = trigger.content as Record<string, unknown>;
  if (content.animation) return 'animation';
  if (content.video) return 'video';
  if (content.video_note) return 'video_note';
  if (content.sticker) return 'sticker';
  if (content.photo) return 'photo';
  if (content.voice) return 'voice';
  if (content.audio) return 'audio';
  if (content.document) return 'document';
  if (content.dice) return 'dice';
  if (content.text) return 'text';
  return 'text';
};

const TriggersList: React.FC<TriggersListProps> = ({ triggers, onDelete, onViewDetails, onApprove, onRequeue, onChatClick, onStatusClick }) => {
  const formatDate = (dateString: string) => {
    if (!dateString) return '—';
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';

    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day}.${month}.${year} ${hours}:${minutes}`;
  };

  const renderContentPreview = (trigger: Trigger) => {
    const content = trigger.content as Record<string, unknown>;
    if (content.text && typeof content.text === 'string') {
      return (
        <div className="flex items-center text-sm text-text truncate max-w-50">
          <FileText size={14} className="mr-1.5 text-hint shrink-0" />
          <span className="truncate">{content.text}</span>
        </div>
      );
    }
    if (content.photo || content.sticker || content.video || content.video_note || content.animation || content.voice || content.audio || content.document || content.dice) {
      return (
        <div className="flex items-center">
          <TriggerImage trigger={trigger} compact={true} />
        </div>
      );
    }
    return <span className="text-hint text-sm italic">Нет содержимого</span>;
  };

  if (triggers.length === 0) {
    return (
      <div className="text-center p-10 text-hint bg-surface rounded-xl border border-border">
        Ничего не найдено
      </div>
    );
  }

  return (
    <>
      {/* Desktop Table View */}
      <div className="hidden md:block overflow-x-auto bg-surface rounded-xl border border-border">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-hint text-sm">
              <th className="p-4 font-medium">Триггер</th>
              <th className="p-4 font-medium">Тип</th>
              <th className="p-4 font-medium">Содержимое</th>
              <th className="p-4 font-medium">Чат</th>
              <th className="p-4 font-medium">Создан</th>
              <th className="p-4 font-medium">Использований</th>
              <th className="p-4 font-medium">Статус</th>
              <th className="p-4 font-medium text-right">Действия</th>
            </tr>
          </thead>
          <tbody>
            {triggers.map((trigger) => (
              <tr key={trigger.id} className="border-b border-border last:border-none hover:bg-elevated/50 transition-colors">
                <td className="p-4">
                  <div className="font-medium text-text">{trigger.key_phrase}</div>
                  <div className="text-xs text-hint mt-0.5 uppercase">{trigger.match_type}</div>
                </td>
                <td className="p-4">
                  {(() => {
                    const type = getContentType(trigger);
                    const config = contentTypeConfig[type];
                    const Icon = config.icon;
                    return (
                      <div className="flex items-center gap-1.5">
                        <Icon size={14} className={config.color} />
                        <span className="text-sm text-text">{config.label}</span>
                      </div>
                    );
                  })()}
                </td>
                <td className="p-4">
                  {renderContentPreview(trigger)}
                </td>
                <td className="p-4 text-sm text-text">
                  {onChatClick ? (
                    <button
                      onClick={() => onChatClick(trigger.chat_id)}
                      className="text-link hover:underline"
                    >
                      {trigger.chat_id}
                    </button>
                  ) : (
                    trigger.chat_id
                  )}
                </td>
                <td className="p-4 text-sm text-hint whitespace-nowrap">
                  {formatDate(trigger.created_at)}
                </td>
                <td className="p-4 text-sm text-text">
                  {trigger.usage_count}
                </td>
                <td className="p-4">
                  {onStatusClick ? (
                    <button onClick={() => onStatusClick(trigger)} className="hover:opacity-80 transition-opacity">
                      <StatusBadge status={trigger.moderation_status} />
                    </button>
                  ) : (
                    <StatusBadge status={trigger.moderation_status} />
                  )}
                </td>
                <td className="p-4">
                  <div className="flex justify-end gap-2">
                    {onApprove && (
                      <button
                        onClick={() => onApprove(trigger.id)}
                        disabled={trigger.moderation_status === 'safe'}
                        className="p-2 text-hint hover:text-success hover:bg-success-soft rounded-lg transition-colors disabled:opacity-30"
                        title="Одобрить"
                      >
                        <ShieldCheck size={18} />
                      </button>
                    )}
                    {onRequeue && (
                      <button
                        onClick={() => onRequeue(trigger.id)}
                        className="p-2 text-hint hover:text-text hover:bg-border rounded-lg transition-colors"
                        title="На перепроверку"
                      >
                        <RefreshCw size={18} />
                      </button>
                    )}
                    <button
                      onClick={() => onViewDetails(trigger)}
                      className="p-2 text-hint hover:text-link hover:bg-link/10 rounded-lg transition-colors"
                      title="Подробнее"
                    >
                      <Eye size={18} />
                    </button>
                    <button
                      onClick={() => onDelete(trigger.id)}
                      className="p-2 text-hint hover:text-danger hover:bg-danger-soft rounded-lg transition-colors"
                      title="Удалить"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile List View */}
      <div className="md:hidden flex flex-col gap-3">
        {triggers.map((trigger) => (
          <div key={trigger.id} className="bg-surface p-4 rounded-xl border border-border shadow-sm">
            <div className="flex justify-between items-start mb-3">
              <div>
                <div className="font-bold text-base mb-1">{trigger.key_phrase}</div>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  {onStatusClick ? (
                    <button onClick={() => onStatusClick(trigger)} className="hover:opacity-80 transition-opacity">
                      <StatusBadge status={trigger.moderation_status} />
                    </button>
                  ) : (
                    <StatusBadge status={trigger.moderation_status} />
                  )}
                  <span className="text-xs text-hint uppercase bg-elevated px-1.5 py-0.5 rounded">
                    {trigger.match_type}
                  </span>
                  {(() => {
                    const type = getContentType(trigger);
                    const config = contentTypeConfig[type];
                    const Icon = config.icon;
                    return (
                      <span className={`text-xs flex items-center gap-1 bg-elevated px-1.5 py-0.5 rounded ${config.color}`}>
                        <Icon size={12} />
                        {config.label}
                      </span>
                    );
                  })()}
                </div>
                <div className="text-xs text-hint flex gap-2">
                  <span>
                    Чат: {onChatClick ? (
                      <button
                        onClick={() => onChatClick(trigger.chat_id)}
                        className="text-link hover:underline"
                      >
                        {trigger.chat_id}
                      </button>
                    ) : trigger.chat_id}
                  </span>
                  <span>|</span>
                  <span>{formatDate(trigger.created_at)}</span>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => onViewDetails(trigger)}
                  className="p-2 text-hint hover:text-text"
                >
                  <MoreVertical size={20} />
                </button>
              </div>
            </div>

            <div className="bg-bg rounded-lg p-3 mb-3 border border-border">
              {renderContentPreview(trigger)}
            </div>

            <div className="flex justify-between items-center text-sm text-hint border-t border-border pt-3 mt-2">
              <span>Использовано: {trigger.usage_count} раз</span>
              <div className="flex gap-2">
                {onApprove && trigger.moderation_status !== 'safe' && (
                  <button
                    onClick={() => onApprove(trigger.id)}
                    className="text-success flex items-center gap-1 px-2 py-1 rounded hover:bg-success-soft transition-colors"
                  >
                    <ShieldCheck size={14} />
                  </button>
                )}
                {onRequeue && (
                  <button
                    onClick={() => onRequeue(trigger.id)}
                    className="text-text flex items-center gap-1 px-2 py-1 rounded hover:bg-border transition-colors"
                  >
                    <RefreshCw size={14} />
                  </button>
                )}
                <button
                  onClick={() => onDelete(trigger.id)}
                  className="text-danger flex items-center gap-1 px-2 py-1 rounded hover:bg-danger-soft transition-colors"
                >
                  <Trash2 size={14} /> Удалить
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
};

export default TriggersList;
