import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import type { Trigger, PaginatedResponse } from '../types';
import { ArrowLeft, Zap, Trash2, Eye, X, CheckCircle, Ban, Clock, AlertTriangle } from 'lucide-react';
import TriggerImage from '../components/TriggerImage';

const ChatTriggers: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [selectedTrigger, setSelectedTrigger] = useState<Trigger | null>(null);

  const fetchTriggers = async (reset = false) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const currentPage = reset ? 1 : page;
      const res = await apiClient.get<PaginatedResponse<Trigger>>(`/chats/${id}/triggers`, {
        params: { page: currentPage, limit: 20 },
      });

      if (reset) {
        setTriggers(res.data.items);
      } else {
        setTriggers((prev) => [...prev, ...res.data.items]);
      }

      setHasMore(currentPage < res.data.pagination.total_pages);
      setPage(currentPage + 1);
    } catch (error: any) {
      console.error(error);
      setError(error.response?.data?.detail || error.message || 'Failed to load triggers');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTriggers(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleDelete = async (triggerId: number) => {
    if (!window.confirm('Are you sure you want to delete this trigger?')) return;
    try {
      await apiClient.delete(`/triggers/${triggerId}`);
      setTriggers((prev) => prev.filter((t) => t.id !== triggerId));
    } catch (error: any) {
      console.error(error);
      alert(error.response?.data?.detail || 'Failed to delete trigger');
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'safe':
        return (
          <span className="flex items-center text-green-500 bg-green-500/10 px-2 py-1 rounded text-xs font-medium">
            <CheckCircle size={12} className="mr-1" /> Safe
          </span>
        );
      case 'banned':
        return (
          <span className="flex items-center text-red-500 bg-red-500/10 px-2 py-1 rounded text-xs font-medium">
            <Ban size={12} className="mr-1" /> Banned
          </span>
        );
      case 'pending':
        return (
          <span className="flex items-center text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded text-xs font-medium">
            <Clock size={12} className="mr-1" /> Pending
          </span>
        );
      case 'flagged':
        return (
          <span className="flex items-center text-orange-500 bg-orange-500/10 px-2 py-1 rounded text-xs font-medium">
            <AlertTriangle size={12} className="mr-1" /> Flagged
          </span>
        );
      default:
        return (
          <span className="flex items-center text-gray-500 bg-gray-500/10 px-2 py-1 rounded text-xs font-medium">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="p-4 max-w-200 mx-auto">
      <button onClick={() => navigate(-1)} className="mb-4 flex items-center text-link bg-transparent border-none cursor-pointer text-base">
        <ArrowLeft size={20} className="mr-1" /> Back
      </button>

      <div className="flex items-center mb-5">
        <Zap size={24} className="mr-2.5 text-link" />
        <h1 className="text-2xl font-bold m-0">Chat Triggers</h1>
      </div>

      {error && (
        <div className="bg-red-500/10 text-red-500 p-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {triggers.map((trigger) => (
          <div
            key={trigger.id}
            className="bg-section-bg p-4 rounded-xl"
          >
            <div className="flex justify-between items-start mb-2">
              <div className="font-bold text-base">
                {trigger.key_phrase}
              </div>
              <div className="flex items-center gap-2">
                {getStatusBadge(trigger.moderation_status)}
                <span className="text-xs bg-secondary-bg px-2 py-1 rounded-md uppercase">
                  {trigger.match_type}
                </span>
              </div>
            </div>

            <div className="text-hint text-sm mb-2">
              Uses: {trigger.usage_count} • Access: {trigger.access_level}
            </div>

            <div className="text-sm break-all mb-3">
               {/* Display content summary */}
               {trigger.content.text && <div className="mb-2 line-clamp-2">{trigger.content.text}</div>}

               {trigger.content.photo && (
                 <TriggerImage chatId={trigger.chat_id} triggerId={trigger.id} alt="Trigger photo" />
               )}

               {trigger.content.sticker && (
                 <TriggerImage chatId={trigger.chat_id} triggerId={trigger.id} alt="Trigger sticker" />
               )}

               {trigger.content.video && <div>[Video]</div>}
               {trigger.content.animation && <div>[Animation]</div>}
               {trigger.content.document && <div>[Document]</div>}
               {trigger.content.voice && <div>[Voice]</div>}
               {trigger.content.audio && <div>[Audio]</div>}
            </div>

            <div className="flex justify-end gap-2 mt-2 border-t border-secondary-bg pt-3">
                <button
                    onClick={() => setSelectedTrigger(trigger)}
                    className="flex items-center px-3 py-1.5 bg-secondary-bg hover:bg-secondary-bg/80 rounded text-sm transition-colors"
                >
                    <Eye size={16} className="mr-1.5" /> Details
                </button>
                <button
                    onClick={() => handleDelete(trigger.id)}
                    className="flex items-center px-3 py-1.5 bg-red-500/10 text-red-500 hover:bg-red-500/20 rounded text-sm transition-colors"
                >
                    <Trash2 size={16} className="mr-1.5" /> Delete
                </button>
            </div>
          </div>
        ))}

        {triggers.length === 0 && !loading && !error && (
            <div className="text-center p-5 text-hint">
                No triggers found for this chat.
            </div>
        )}
      </div>

      {hasMore && (
        <button
            onClick={() => fetchTriggers(false)}
            disabled={loading}
            className="w-full p-3 mt-4 text-link bg-transparent border-none cursor-pointer"
        >
            {loading ? 'Loading...' : 'Load More'}
        </button>
      )}

      {/* Details Modal */}
      {selectedTrigger && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setSelectedTrigger(null)}>
            <div className="bg-section-bg p-6 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto relative shadow-2xl border border-secondary-bg" onClick={e => e.stopPropagation()}>
                <button onClick={() => setSelectedTrigger(null)} className="absolute top-4 right-4 text-hint hover:text-text transition-colors">
                    <X size={24} />
                </button>

                <h2 className="text-xl font-bold mb-6 pr-8">Trigger Details</h2>

                <div className="space-y-6">
                    <div>
                        <h3 className="text-sm font-semibold text-hint uppercase mb-2">Moderation</h3>
                        <div className="flex items-center gap-3 mb-2">
                            {getStatusBadge(selectedTrigger.moderation_status)}
                        </div>
                        {selectedTrigger.moderation_reason && (
                            <div className="bg-red-500/10 text-red-500 p-3 rounded-lg text-sm">
                                <span className="font-semibold">Reason:</span> {selectedTrigger.moderation_reason}
                            </div>
                        )}
                    </div>

                    <div>
                        <h3 className="text-sm font-semibold text-hint uppercase mb-2">Content</h3>
                        <div className="bg-secondary-bg p-4 rounded-lg overflow-x-auto">
                            <pre className="text-xs font-mono whitespace-pre-wrap">
                                {JSON.stringify(selectedTrigger.content, null, 2)}
                            </pre>
                        </div>
                    </div>

                    {/* Buttons Visualization */}
                    {(selectedTrigger.content.buttons || selectedTrigger.content.reply_markup) && (
                        <div>
                            <h3 className="text-sm font-semibold text-hint uppercase mb-2">Buttons</h3>
                            <div className="flex flex-col gap-2">
                                {/* Try to parse buttons from common structures */}
                                {(() => {
                                    const buttons = selectedTrigger.content.buttons ||
                                                   selectedTrigger.content.reply_markup?.inline_keyboard ||
                                                   selectedTrigger.content.reply_markup?.keyboard;

                                    if (Array.isArray(buttons)) {
                                        return buttons.map((row: any, i: number) => (
                                            <div key={i} className="flex gap-2 justify-center">
                                                {Array.isArray(row) ? row.map((btn: any, j: number) => (
                                                    <div key={j} className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                                                                {btn.text || 'Button'}
                                                            </div>
                                                        )) : (
                                                            // Single button row or flat list
                                                            <div className="bg-link/20 text-link px-3 py-2 rounded text-sm font-medium min-w-20 text-center">
                                                                {row.text || 'Button'}
                                                            </div>
                                                        )}
                                            </div>
                                        ));
                                    }
                                    return <div className="text-sm text-hint italic">Complex button structure</div>;
                                })()}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
      )}
    </div>
  );
};

export default ChatTriggers;
