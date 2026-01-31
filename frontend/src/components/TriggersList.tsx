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
  text: { label: 'Text', icon: FileText, color: 'text-gray-400' },
  photo: { label: 'Photo', icon: Image, color: 'text-green-500' },
  video: { label: 'Video', icon: Video, color: 'text-blue-500' },
  video_note: { label: 'Video Note', icon: Circle, color: 'text-blue-400' },
  animation: { label: 'GIF', icon: Film, color: 'text-purple-500' },
  sticker: { label: 'Sticker', icon: Sticker, color: 'text-yellow-500' },
  voice: { label: 'Voice', icon: Mic, color: 'text-purple-400' },
  audio: { label: 'Audio', icon: Music, color: 'text-orange-500' },
  document: { label: 'Document', icon: FileIcon, color: 'text-blue-400' },
  dice: { label: 'Dice', icon: Dices, color: 'text-red-500' },
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
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
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
    return <span className="text-hint text-sm italic">No content</span>;
  };

  if (triggers.length === 0) {
    return (
      <div className="text-center p-10 text-hint bg-section-bg rounded-xl border border-black/5">
        No triggers found matching your criteria.
      </div>
    );
  }

  return (
    <>
      {/* Desktop Table View */}
      <div className="hidden md:block overflow-x-auto bg-section-bg rounded-xl border border-black/5">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-secondary-bg text-hint text-sm">
              <th className="p-4 font-medium">Trigger</th>
              <th className="p-4 font-medium">Type</th>
              <th className="p-4 font-medium">Content</th>
              <th className="p-4 font-medium">Chat</th>
              <th className="p-4 font-medium">Created</th>
              <th className="p-4 font-medium">Usage</th>
              <th className="p-4 font-medium">Status</th>
              <th className="p-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {triggers.map((trigger) => (
              <tr key={trigger.id} className="border-b border-secondary-bg last:border-none hover:bg-black/5 transition-colors">
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
                        className="p-2 text-hint hover:text-green-500 hover:bg-green-500/10 rounded-lg transition-colors disabled:opacity-30"
                        title="Approve"
                      >
                        <ShieldCheck size={18} />
                      </button>
                    )}
                    {onRequeue && (
                      <button
                        onClick={() => onRequeue(trigger.id)}
                        className="p-2 text-hint hover:text-blue-500 hover:bg-blue-500/10 rounded-lg transition-colors"
                        title="Requeue"
                      >
                        <RefreshCw size={18} />
                      </button>
                    )}
                    <button
                      onClick={() => onViewDetails(trigger)}
                      className="p-2 text-hint hover:text-link hover:bg-link/10 rounded-lg transition-colors"
                      title="View Details"
                    >
                      <Eye size={18} />
                    </button>
                    <button
                      onClick={() => onDelete(trigger.id)}
                      className="p-2 text-hint hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
                      title="Delete"
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
          <div key={trigger.id} className="bg-section-bg p-4 rounded-xl border border-black/5 shadow-sm">
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
                  <span className="text-xs text-hint uppercase bg-secondary-bg px-1.5 py-0.5 rounded">
                    {trigger.match_type}
                  </span>
                  {(() => {
                    const type = getContentType(trigger);
                    const config = contentTypeConfig[type];
                    const Icon = config.icon;
                    return (
                      <span className={`text-xs flex items-center gap-1 bg-secondary-bg px-1.5 py-0.5 rounded ${config.color}`}>
                        <Icon size={12} />
                        {config.label}
                      </span>
                    );
                  })()}
                </div>
                <div className="text-xs text-hint flex gap-2">
                  <span>
                    Chat: {onChatClick ? (
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

            <div className="bg-bg rounded-lg p-3 mb-3 border border-secondary-bg">
              {renderContentPreview(trigger)}
            </div>

            <div className="flex justify-between items-center text-sm text-hint border-t border-secondary-bg pt-3 mt-2">
              <span>Used: {trigger.usage_count} times</span>
              <div className="flex gap-2">
                {onApprove && trigger.moderation_status !== 'safe' && (
                  <button
                    onClick={() => onApprove(trigger.id)}
                    className="text-green-500 flex items-center gap-1 px-2 py-1 rounded hover:bg-green-500/10 transition-colors"
                  >
                    <ShieldCheck size={14} />
                  </button>
                )}
                {onRequeue && (
                  <button
                    onClick={() => onRequeue(trigger.id)}
                    className="text-blue-500 flex items-center gap-1 px-2 py-1 rounded hover:bg-blue-500/10 transition-colors"
                  >
                    <RefreshCw size={14} />
                  </button>
                )}
                <button
                  onClick={() => onDelete(trigger.id)}
                  className="text-red-500 flex items-center gap-1 px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 size={14} /> Delete
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
