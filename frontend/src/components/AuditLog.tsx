import React, { useEffect, useState } from 'react';
import { chatsApi } from '../api/client';
import type { AuditLogEntry } from '../types';
import { History } from 'lucide-react';

// Section name translations
const SECTION_NAMES: Record<string, string> = {
  general: 'Общие',
  captcha: 'Капча',
  moderation: 'Модерация',
  triggers: 'Триггеры',
  tags: 'Теги',
  welcome: 'Приветствие',
  other: 'Прочее',
};

// Field name translations
const FIELD_NAMES: Record<string, string> = {
  language_code: 'Язык',
  timezone: 'Часовой пояс',
  captcha_enabled: 'Капча',
  captcha_type: 'Тип капчи',
  captcha_timeout: 'Таймаут капчи',
  captcha_max_attempts: 'Попытки капчи',
  captcha_ban_duration: 'Бан за капчу',
  module_moderation: 'Модерация',
  warn_limit: 'Лимит варнов',
  warn_punishment: 'Наказание',
  warn_duration: 'Длительность наказания',
  module_triggers: 'Триггеры',
  admins_only_add: 'Только админы',
  tags_enabled: 'Теги',
  tags_preset: 'Пресет тегов',
  tags_custom: 'Кастомные теги',
  tags_thresholds: 'Пороги тегов',
  tags_weight_reactions: 'Вес реакций',
  tags_weight_replies: 'Вес ответов',
  tags_weight_messages: 'Вес сообщений',
  tags_daily_message_limit: 'Лимит сообщений/день',
  tags_daily_reaction_limit: 'Лимит реакций/день',
  welcome_enabled: 'Приветствие',
  welcome_message: 'Текст приветствия',
  welcome_delete_timeout: 'Автоудаление',
  gban_enabled: 'Глобальные баны',
  is_trusted: 'Доверенный чат',
  settings_locked_sections: 'Блокировка секций',
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? '✅' : '❌';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

interface AuditLogProps {
  chatId: number;
}

const AuditLog: React.FC<AuditLogProps> = ({ chatId }) => {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    const fetchLog = async () => {
      setLoading(true);
      try {
        const data = await chatsApi.getAuditLog(chatId, { page, limit: 10 });
        setEntries(data.items);
        setTotalPages(data.pagination.total_pages);
      } catch {
        // handled by interceptor
      } finally {
        setLoading(false);
      }
    };
    fetchLog();
  }, [chatId, page]);

  if (loading) return <div className="text-hint text-center p-4">Загрузка...</div>;
  if (entries.length === 0) return <div className="text-hint text-center p-4">История изменений пуста</div>;

  return (
    <div className="bg-section-bg rounded-xl p-4 mb-4">
      <div className="flex items-center mb-3 text-link">
        <History size={20} className="mr-2" />
        <h2 className="text-base font-bold m-0">История изменений</h2>
      </div>
      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="bg-bg rounded-lg p-3">
            <div className="flex justify-between items-start mb-2">
              <span className="text-xs bg-secondary-bg px-2 py-0.5 rounded">
                {SECTION_NAMES[entry.section] || entry.section}
              </span>
              <span className="text-xs text-hint">
                {new Date(entry.created_at).toLocaleString()}
              </span>
            </div>
            <div className="text-xs text-hint mb-1">User ID: {entry.user_id}</div>
            <div className="space-y-1">
              {entry.changes.map((change, i) => (
                <div key={i} className="text-sm flex flex-wrap gap-1 items-center">
                  <span className="font-medium">{FIELD_NAMES[change.field] || change.field}:</span>
                  <span className="text-red-400 line-through">{formatValue(change.old)}</span>
                  <span>→</span>
                  <span className="text-green-400">{formatValue(change.new)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="bg-secondary-bg text-text px-3 py-1 rounded text-sm disabled:opacity-50"
          >←</button>
          <span className="text-sm text-hint py-1">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="bg-secondary-bg text-text px-3 py-1 rounded text-sm disabled:opacity-50"
          >→</button>
        </div>
      )}
    </div>
  );
};

export default AuditLog;
