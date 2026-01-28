import React from 'react';
import type { Trigger } from '../types/index';
import { Eye, Trash2, CheckCircle, Ban, Clock, AlertTriangle, FileText, MoreVertical, ShieldCheck, RefreshCw } from 'lucide-react';
import TriggerImage from './TriggerImage';

interface TriggersListProps {
  triggers: Trigger[];
  onDelete: (id: number) => void;
  onViewDetails: (trigger: Trigger) => void;
  onApprove?: (id: number) => void;
  onRequeue?: (id: number) => void;
}

const TriggersList: React.FC<TriggersListProps> = ({ triggers, onDelete, onViewDetails, onApprove, onRequeue }) => {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'safe':
        return (
          <span className="flex items-center text-green-500 bg-green-500/10 px-2 py-1 rounded text-xs font-medium w-fit">
            <CheckCircle size={12} className="mr-1" /> Safe
          </span>
        );
      case 'banned':
        return (
          <span className="flex items-center text-red-500 bg-red-500/10 px-2 py-1 rounded text-xs font-medium w-fit">
            <Ban size={12} className="mr-1" /> Banned
          </span>
        );
      case 'pending':
        return (
          <span className="flex items-center text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded text-xs font-medium w-fit">
            <Clock size={12} className="mr-1" /> Pending
          </span>
        );
      case 'flagged':
        return (
          <span className="flex items-center text-orange-500 bg-orange-500/10 px-2 py-1 rounded text-xs font-medium w-fit">
            <AlertTriangle size={12} className="mr-1" /> Flagged
          </span>
        );
      default:
        return (
          <span className="flex items-center text-gray-500 bg-gray-500/10 px-2 py-1 rounded text-xs font-medium w-fit">
            {status}
          </span>
        );
    }
  };

  const renderContentPreview = (trigger: Trigger) => {
    if (trigger.content.text) {
      return (
        <div className="flex items-center text-sm text-text truncate max-w-50">
          <FileText size={14} className="mr-1.5 text-hint shrink-0" />
          <span className="truncate">{trigger.content.text}</span>
        </div>
      );
    }
    if (trigger.content.photo || trigger.content.sticker || trigger.content.video || trigger.content.animation || trigger.content.voice || trigger.content.audio || trigger.content.document) {
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
              <th className="p-4 font-medium">Content</th>
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
                  {renderContentPreview(trigger)}
                </td>
                <td className="p-4 text-sm text-text">
                  {trigger.usage_count}
                </td>
                <td className="p-4">
                  {getStatusBadge(trigger.moderation_status)}
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
                <div className="flex items-center gap-2">
                  {getStatusBadge(trigger.moderation_status)}
                  <span className="text-xs text-hint uppercase bg-secondary-bg px-1.5 py-0.5 rounded">
                    {trigger.match_type}
                  </span>
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
