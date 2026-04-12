import React, { useRef, useCallback, useEffect } from 'react';
import type { Trigger } from '../types/index';
import StatusBadge from './StatusBadge';

interface TriggerCardListProps {
  triggers: Trigger[];
  selectedId: number | null;
  onSelect: (trigger: Trigger) => void;
  loading?: boolean;
  checkedIds: Set<number>;
  onToggleCheck: (id: number, shiftKey: boolean) => void;
  hasMore?: boolean;
  onLoadMore?: () => void;
}

const matchTypeLabel: Record<string, string> = {
  exact: '=',
  contains: '≈',
  regexp: '.*',
};

const TriggerCardList: React.FC<TriggerCardListProps> = ({
  triggers, selectedId, onSelect, loading,
  checkedIds, onToggleCheck, hasMore, onLoadMore,
}) => {
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!hasMore || !onLoadMore) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          onLoadMore();
        }
      },
      { rootMargin: '200px' }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, onLoadMore]);

  const handleCardClick = useCallback((e: React.MouseEvent, trigger: Trigger) => {
    // If clicking the checkbox area, don't select
    if ((e.target as HTMLElement).closest('[data-checkbox]')) return;
    onSelect(trigger);
  }, [onSelect]);

  if (loading && triggers.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="bg-surface border border-border rounded-xl p-3 animate-pulse">
            <div className="flex justify-between items-center mb-1.5">
              <div className="h-4 w-32 bg-elevated rounded" />
              <div className="h-5 w-12 bg-elevated rounded-full" />
            </div>
            <div className="flex items-center gap-2">
              <div className="h-3 w-24 bg-elevated rounded" />
              <div className="h-3 w-6 bg-elevated rounded" />
              <div className="h-3 w-16 bg-elevated rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (triggers.length === 0) {
    return (
      <div className="text-center p-8 text-hint bg-surface rounded-xl border border-border">
        No triggers found
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {triggers.map((trigger) => {
        const isSelected = trigger.id === selectedId;
        const isChecked = checkedIds.has(trigger.id);
        return (
          <div
            key={trigger.id}
            onClick={(e) => handleCardClick(e, trigger)}
            className={`w-full text-left p-3 rounded-xl border transition-colors cursor-pointer flex gap-2.5 ${
              isChecked
                ? 'border-link bg-link/10'
                : isSelected
                  ? 'border-link bg-link/5'
                  : 'border-border bg-surface hover:bg-elevated/50'
            }`}
          >
            <div
              data-checkbox
              className="pt-0.5 shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                onToggleCheck(trigger.id, e.shiftKey);
              }}
            >
              <div className={`w-4 h-4 rounded border-2 transition-colors flex items-center justify-center ${
                isChecked
                  ? 'bg-link border-link'
                  : 'border-[#52525b] hover:border-hint'
              }`}>
                {isChecked && (
                  <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                    <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-center mb-1">
                <span className="font-medium text-text truncate mr-2">
                  {trigger.key_phrase}
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  {trigger.moderation_reason && trigger.moderation_status === 'flagged' && (
                    <span className="text-[10px] text-[#fbbf24] bg-warning/12 px-1.5 py-0.5 rounded-full truncate max-w-24">
                      {trigger.moderation_reason.split('\n')[0]}
                    </span>
                  )}
                  <StatusBadge status={trigger.moderation_status} />
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-hint">
                <span className="truncate">
                  {trigger.chat_title || `Chat #${trigger.chat_id}`}
                </span>
                <span className="bg-elevated px-1.5 py-0.5 rounded font-mono">
                  {matchTypeLabel[trigger.match_type] || trigger.match_type}
                </span>
                <span className="ml-auto whitespace-nowrap">
                  used: {trigger.usage_count}
                </span>
              </div>
            </div>
          </div>
        );
      })}

      {/* Infinite scroll sentinel */}
      {hasMore && (
        <div ref={sentinelRef} className="py-4 text-center text-sm text-hint">
          {loading ? 'Loading...' : ''}
        </div>
      )}
    </div>
  );
};

export default TriggerCardList;
