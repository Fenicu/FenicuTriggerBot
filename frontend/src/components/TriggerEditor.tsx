import React, { useState, useRef } from 'react';
import { triggersApi } from '../api/client';
import { toast } from '../store/store';
import type { Chat, Trigger, TriggerCreatePayload, TriggerUpdatePayload } from '../types';
import TextToolbar from './TextToolbar';
import WelcomePreview from './WelcomePreview';
import ChatPicker from './ChatPicker';
import Toggle from './ui/Toggle';
import Select from './ui/Select';
import Button from './ui/Button';
import { findUnknownTags } from '../lib/richHtml';

interface TriggerEditorProps {
  // 0 = чат ещё не выбран (в режиме создания без предвыбранного триггера пользователь
  // выбирает его сам через ChatPicker ниже)
  chatId: number;
  // Отображаемое название чата, если уже известно (из выбранного в списке триггера)
  chatTitle?: string | null;
  trigger?: Trigger | null;
  onSaved: (trigger: Trigger) => void;
  onCancel: () => void;
}

const MATCH_TYPE_OPTIONS = [
  { value: 'exact', label: 'Точное совпадение' },
  { value: 'contains', label: 'Содержит' },
  { value: 'regexp', label: 'Регулярное выражение' },
];

const ACCESS_LEVEL_OPTIONS = [
  { value: 'all', label: 'Все' },
  { value: 'admins', label: 'Только админы' },
  { value: 'owner', label: 'Только владелец' },
];

// Начальные значения формы из редактируемого триггера (или пустые для создания).
// Вызывающая сторона обязана передавать key={trigger?.id ?? 'new'}, чтобы при смене
// триггера компонент пересоздавался, а не переиспользовал стейт через эффект.
const getInitialState = (trigger?: Trigger | null) => {
  if (!trigger) {
    return {
      keyPhrase: '',
      matchType: 'exact',
      accessLevel: 'all',
      isCaseSensitive: false,
      isTemplate: false,
      rich: false,
      text: '',
    };
  }
  const content = trigger.content;
  let text = '';
  if (typeof content === 'string') {
    text = content;
  } else if (content && typeof content === 'object' && 'text' in content) {
    text = String(content.text || '');
  }
  return {
    keyPhrase: trigger.key_phrase,
    matchType: trigger.match_type,
    accessLevel: trigger.access_level,
    isCaseSensitive: trigger.is_case_sensitive,
    isTemplate: trigger.is_template,
    rich: trigger.rich,
    text,
  };
};

const TriggerEditor: React.FC<TriggerEditorProps> = ({ chatId, chatTitle, trigger, onSaved, onCancel }) => {
  const initial = getInitialState(trigger);
  const [keyPhrase, setKeyPhrase] = useState(initial.keyPhrase);
  const [matchType, setMatchType] = useState<string>(initial.matchType);
  const [accessLevel, setAccessLevel] = useState<string>(initial.accessLevel);
  const [isCaseSensitive, setIsCaseSensitive] = useState(initial.isCaseSensitive);
  const [isTemplate, setIsTemplate] = useState(initial.isTemplate);
  const [rich, setRich] = useState(initial.rich);
  const [text, setText] = useState(initial.text);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Чат выбирается только в режиме создания -- в режиме редактирования он фиксирован
  // (chatId триггера, который редактируем)
  const [createChatId, setCreateChatId] = useState<number>(chatId);
  const [createChatLabel, setCreateChatLabel] = useState<string>(
    chatTitle || (chatId ? `Чат #${chatId}` : '')
  );
  const effectiveChatId = trigger ? trigger.chat_id : createChatId;

  // rich влечёт is_template (только для триггеров)
  const effectiveIsTemplate = isTemplate || rich;

  const handleSave = async () => {
    if (!keyPhrase.trim()) {
      toast.error('Ключевая фраза не может быть пустой');
      return;
    }

    if (!trigger && !effectiveChatId) {
      toast.error('Сначала выберите чат для триггера');
      return;
    }

    if (rich && text.trim()) {
      const unknown = findUnknownTags(text);
      if (unknown.length > 0) {
        toast.error(`Rich-HTML содержит неизвестные теги: ${unknown.join(', ')}`);
        return;
      }
    }

    setSaving(true);
    try {
      let saved: Trigger;
      if (trigger) {
        const payload: TriggerUpdatePayload = {
          key_phrase: keyPhrase.trim(),
          content: { text },
          match_type: matchType,
          is_case_sensitive: isCaseSensitive,
          access_level: accessLevel,
          is_template: effectiveIsTemplate,
          rich,
        };
        saved = await triggersApi.update(trigger.id, payload);
      } else {
        const payload: TriggerCreatePayload = {
          chat_id: effectiveChatId,
          key_phrase: keyPhrase.trim(),
          content: { text },
          match_type: matchType,
          is_case_sensitive: isCaseSensitive,
          access_level: accessLevel,
          is_template: effectiveIsTemplate,
          rich,
        };
        saved = await triggersApi.create(payload);
      }
      toast.success(trigger ? 'Триггер обновлён' : 'Триггер создан');
      onSaved(saved);
    } catch {
      // 422 и другие ошибки обрабатывает интерцептор axios (toast.error)
    } finally {
      setSaving(false);
    }
  };

  const handleChatSelect = (chat: Chat) => {
    setCreateChatId(chat.id);
    setCreateChatLabel(chat.title || chat.username || `Чат #${chat.id}`);
  };

  const handleChatClear = () => {
    setCreateChatId(0);
    setCreateChatLabel('');
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      {/* Форма */}
      <div className="flex-1 space-y-4">
        {/* Чат -- только при создании нового триггера */}
        {!trigger && (
          <div>
            <span className="block text-hint text-xs uppercase tracking-wide mb-2">Чат</span>
            <ChatPicker
              selectedChatId={createChatId}
              selectedChatLabel={createChatLabel}
              onSelect={handleChatSelect}
              onClear={handleChatClear}
            />
          </div>
        )}

        {/* Ключевая фраза */}
        <div>
          <span className="block text-hint text-xs uppercase tracking-wide mb-2">Ключевая фраза</span>
          <input
            value={keyPhrase}
            onChange={(e) => setKeyPhrase(e.target.value)}
            placeholder="Введите ключевую фразу…"
            className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text"
          />
        </div>

        {/* Тип совпадения */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Тип совпадения</span>
          <Select
            value={matchType}
            options={MATCH_TYPE_OPTIONS}
            onChange={setMatchType}
          />
        </div>

        {/* Уровень доступа */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Доступ</span>
          <Select
            value={accessLevel}
            options={ACCESS_LEVEL_OPTIONS}
            onChange={setAccessLevel}
          />
        </div>

        {/* Текст ответа */}
        <div>
          <span className="block text-hint text-xs uppercase tracking-wide mb-2">
            Текст ответа
            <span className="ml-2 normal-case">({text.length}/4096)</span>
          </span>
          <TextToolbar textareaRef={textareaRef} onTextChange={setText} richMode={rich} />
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={4096}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text resize-y min-h-24 font-mono"
            placeholder="Введите текст ответа…"
          />
        </div>

        {/* Настройки */}
        <div className="space-y-1 border-t border-border pt-3">
          <Toggle label="Учитывать регистр" value={isCaseSensitive} onChange={setIsCaseSensitive} />
          <Toggle label="Шаблонные переменные" value={isTemplate} onChange={setIsTemplate} />
          <Toggle
            label="Rich-форматирование"
            hint="Включает шаблонные переменные"
            value={rich}
            onChange={setRich}
          />
        </div>

        {/* Кнопки */}
        <div className="flex gap-2 pt-2">
          <Button variant="primary" onClick={handleSave} disabled={saving} className="flex-1">
            {saving ? 'Сохранение…' : trigger ? 'Обновить' : 'Создать'}
          </Button>
          <Button variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
        </div>
      </div>

      {/* Предпросмотр */}
      <div className="lg:w-80 lg:sticky lg:top-4 lg:self-start">
        <WelcomePreview
          text={text}
          media={null}
          buttons={[]}
          isTemplate={effectiveIsTemplate}
          richMode={rich}
        />
      </div>
    </div>
  );
};

export default TriggerEditor;
