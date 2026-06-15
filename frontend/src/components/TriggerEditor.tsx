import React, { useState, useRef, useEffect } from 'react';
import { triggersApi } from '../api/client';
import { toast } from '../store/store';
import type { Trigger, TriggerCreatePayload, TriggerUpdatePayload } from '../types';
import TextToolbar from './TextToolbar';
import WelcomePreview from './WelcomePreview';
import Toggle from './ui/Toggle';
import Select from './ui/Select';
import Button from './ui/Button';
import { findUnknownTags } from '../lib/richHtml';

interface TriggerEditorProps {
  chatId: number;
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

const TriggerEditor: React.FC<TriggerEditorProps> = ({ chatId, trigger, onSaved, onCancel }) => {
  const [keyPhrase, setKeyPhrase] = useState('');
  const [matchType, setMatchType] = useState<string>('exact');
  const [accessLevel, setAccessLevel] = useState<string>('all');
  const [isCaseSensitive, setIsCaseSensitive] = useState(false);
  const [isTemplate, setIsTemplate] = useState(false);
  const [rich, setRich] = useState(false);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // rich влечёт is_template (только для триггеров)
  const effectiveIsTemplate = isTemplate || rich;

  useEffect(() => {
    if (trigger) {
      setKeyPhrase(trigger.key_phrase);
      setMatchType(trigger.match_type);
      setAccessLevel(trigger.access_level);
      setIsCaseSensitive(trigger.is_case_sensitive);
      setIsTemplate(trigger.is_template);
      setRich(trigger.rich);
      const content = trigger.content;
      if (typeof content === 'string') {
        setText(content);
      } else if (content && typeof content === 'object' && 'text' in content) {
        setText(String(content.text || ''));
      } else {
        setText('');
      }
    } else {
      setKeyPhrase('');
      setMatchType('exact');
      setAccessLevel('all');
      setIsCaseSensitive(false);
      setIsTemplate(false);
      setRich(false);
      setText('');
    }
  }, [trigger]);

  const handleSave = async () => {
    if (!keyPhrase.trim()) {
      toast.error('Ключевая фраза не может быть пустой');
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
          chat_id: chatId,
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

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      {/* Форма */}
      <div className="flex-1 space-y-4">
        {/* Ключевая фраза */}
        <div>
          <span className="block text-hint text-xs uppercase tracking-wide mb-2">Ключевая фраза</span>
          <input
            value={keyPhrase}
            onChange={(e) => setKeyPhrase(e.target.value)}
            placeholder="Введите ключевую фразу..."
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
            placeholder="Введите текст ответа..."
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
            {saving ? 'Сохранение...' : trigger ? 'Обновить' : 'Создать'}
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
