import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, Clock, Trash2, ChevronDown, ChevronRight, Zap } from 'lucide-react';
import type { Trigger } from '../types/index';
import StatusBadge from './StatusBadge';
import TriggerImage from './TriggerImage';
import ModerationTimeline from './ModerationTimeline';

interface TriggerDetailPanelProps {
  trigger: Trigger | null;
  onApprove: (id: number) => void;
  onRequeue: (id: number) => void;
  onDelete: (id: number) => void;
  onTriggerUpdate: (id: number) => void;
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
  all: 'All',
  admins: 'Admins',
  owner: 'Owner',
};

const TriggerDetailPanel: React.FC<TriggerDetailPanelProps> = ({
  trigger,
  onApprove,
  onRequeue,
  onDelete,
  onTriggerUpdate,
}) => {
  const [jsonExpanded, setJsonExpanded] = useState(false);

  if (!trigger) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-hint p-8">
        <Zap size={48} className="mb-4 opacity-30" />
        <p className="text-lg">Select a trigger to view details</p>
      </div>
    );
  }

  const content = trigger.content as TriggerContent;

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    return date.toLocaleString(navigator.language);
  };

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
    );
  };

  return (
    <div className="h-full overflow-y-auto">
      {/* Action bar */}
      <div className="sticky top-0 bg-surface z-10 p-4 border-b border-border flex gap-2">
        {trigger.moderation_status !== 'safe' && (
          <button
            onClick={() => onApprove(trigger.id)}
            className="flex-1 bg-green-500/10 text-green-500 py-2 rounded-lg font-medium hover:bg-green-500/20 transition-colors flex items-center justify-center gap-2"
          >
            <CheckCircle size={18} /> Approve
          </button>
        )}
        <button
          onClick={() => onRequeue(trigger.id)}
          className="flex-1 bg-blue-500/10 text-blue-500 py-2 rounded-lg font-medium hover:bg-blue-500/20 transition-colors flex items-center justify-center gap-2"
        >
          <Clock size={18} /> Requeue
        </button>
        <button
          onClick={() => onDelete(trigger.id)}
          className="flex-1 bg-red-500/10 text-red-500 py-2 rounded-lg font-medium hover:bg-red-500/20 transition-colors flex items-center justify-center gap-2"
        >
          <Trash2 size={18} /> Delete
        </button>
      </div>

      <div className="p-4 space-y-6">
        {/* Info */}
        <div>
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Info</h3>
          <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-sm">
            <span className="text-hint">Chat</span>
            <Link to={`/chats/${trigger.chat_id}`} className="text-link hover:underline truncate">
              {trigger.chat_title || `Chat #${trigger.chat_id}`}
            </Link>

            <span className="text-hint">Match type</span>
            <span className="text-text">{trigger.match_type}</span>

            <span className="text-hint">Case sensitive</span>
            <span className="text-text">{trigger.is_case_sensitive ? 'Yes' : 'No'}</span>

            <span className="text-hint">Access</span>
            <span className="text-text">{accessLabels[trigger.access_level] || trigger.access_level}</span>

            <span className="text-hint">Template</span>
            <span className="text-text">{trigger.is_template ? 'Yes' : 'No'}</span>

            <span className="text-hint">Created by</span>
            {trigger.created_by ? (
              <Link to={`/users/${trigger.created_by}`} className="text-link hover:underline">
                User #{trigger.created_by}
              </Link>
            ) : (
              <span className="text-hint">System</span>
            )}

            <span className="text-hint">Created</span>
            <span className="text-text">{formatDate(trigger.created_at)}</span>

            <span className="text-hint">Usage</span>
            <span className="text-text">{trigger.usage_count}</span>
          </div>
        </div>

        {/* Content */}
        <div>
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Content</h3>
          {renderContentPreview()}
          {renderButtons()}

          {/* Collapsible Raw JSON */}
          <button
            onClick={() => setJsonExpanded(!jsonExpanded)}
            className="flex items-center gap-1 text-xs text-hint hover:text-text mt-3 transition-colors"
          >
            {jsonExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Raw JSON
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
          <h3 className="text-sm font-semibold text-hint uppercase mb-3">Moderation</h3>
          <div className="flex items-center gap-3 mb-3">
            <StatusBadge status={trigger.moderation_status} size="md" />
          </div>
          {trigger.moderation_reason && (
            <div className="bg-elevated p-3 rounded-lg text-sm border border-border mb-3">
              <span className="font-semibold block mb-1 text-hint">Reasoning:</span>
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
