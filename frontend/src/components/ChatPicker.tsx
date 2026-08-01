import React, { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { chatsApi } from '../api/client';
import type { Chat } from '../types';

interface ChatPickerProps {
  selectedChatId: number;
  selectedChatLabel: string;
  onSelect: (chat: Chat) => void;
  onClear: () => void;
}

const chatLabel = (chat: Chat) => chat.title || chat.username || `Чат #${chat.id}`;

// Поиск чата по названию/@username/id с debounce. Нужен при создании первого
// триггера в чате: раньше chat_id брался только из уже выбранного триггера в
// списке, а если в чате ещё нет ни одного триггера -- выбрать чат было неоткуда.
const ChatPicker: React.FC<ChatPickerProps> = ({ selectedChatId, selectedChatLabel, onSelect, onClear }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      // Синхронизация со строкой поиска -- очищаем результаты предыдущего запроса,
      // не цикл рендеров
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      chatsApi
        .getAll({ query: trimmed, limit: 10 })
        .then((res) => {
          if (!cancelled) setResults(res.items);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  if (selectedChatId) {
    return (
      <div className="flex items-center justify-between gap-2 bg-bg border border-border rounded-lg px-3 py-2 text-sm">
        <span className="truncate">
          {selectedChatLabel || `Чат #${selectedChatId}`}
          <span className="text-hint ml-1.5">#{selectedChatId}</span>
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-hint hover:text-text shrink-0"
          title="Выбрать другой чат"
        >
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="relative" ref={containerRef}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-hint" size={16} />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Поиск чата по названию, @username или id…"
          className="w-full pl-9 pr-3 py-2 bg-bg border border-border rounded-lg text-sm text-text outline-none focus:border-button transition-colors"
        />
      </div>
      {open && query.trim() && (
        <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-surface border border-border rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {loading ? (
            <div className="px-3 py-2 text-sm text-hint">Поиск…</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-2 text-sm text-hint">Ничего не найдено</div>
          ) : (
            results.map((chat) => (
              <button
                key={chat.id}
                type="button"
                onClick={() => {
                  onSelect(chat);
                  setOpen(false);
                  setQuery('');
                }}
                className="block w-full text-left px-3 py-2 text-sm hover:bg-elevated"
              >
                <div className="font-medium truncate">{chatLabel(chat)}</div>
                <div className="text-xs text-hint">
                  {chat.username && <span>@{chat.username} · </span>}
                  ID: {chat.id}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default ChatPicker;
