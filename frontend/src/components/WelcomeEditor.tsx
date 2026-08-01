import React, { useState, useRef } from 'react';
import { chatsApi } from '../api/client';
import { toast } from '../store/store';
import type { WelcomeMessage, WelcomeButton } from '../types';
import { MessageSquare } from 'lucide-react';
import TextToolbar from './TextToolbar';
import MediaUpload from './MediaUpload';
import ButtonConstructor from './ButtonConstructor';
import WelcomePreview from './WelcomePreview';
import Card from './ui/Card';
import Toggle from './ui/Toggle';
import Button from './ui/Button';
import { buildMediaUrl } from '../lib/richHtml';

interface WelcomeEditorProps {
  chatId: number;
  initialMessage: WelcomeMessage | null;
  initialEnabled: boolean;
  onSave: (data: {
    welcome_message: WelcomeMessage | null;
    welcome_enabled: boolean;
  }) => Promise<void>;
}

type WelcomeMedia = { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null;

// Начальные значения формы из initialMessage/initialEnabled. Вызывающая сторона обязана
// передавать key={chatId}, чтобы при смене чата компонент пересоздавался, а не переиспользовал
// стейт через эффект.
const getInitialWelcomeState = (initialMessage: WelcomeMessage | null, initialEnabled: boolean) => {
  let media: WelcomeMedia = null;
  if (initialMessage?.photo?.length) {
    media = { file_id: initialMessage.photo[initialMessage.photo.length - 1].file_id, file_type: 'photo' };
  } else if (initialMessage?.video) {
    media = { file_id: initialMessage.video.file_id, file_type: 'video' };
  } else if (initialMessage?.animation) {
    media = { file_id: initialMessage.animation.file_id, file_type: 'animation' };
  }
  return {
    text: initialMessage ? (initialMessage.text || initialMessage.caption || '') : '',
    media,
    buttonRows: (initialMessage?.reply_markup?.inline_keyboard || []) as WelcomeButton[][],
    isTemplate: initialMessage?.is_template || false,
    rich: initialMessage?.rich || false,
    enabled: initialEnabled,
  };
};

const WelcomeEditor: React.FC<WelcomeEditorProps> = ({ chatId, initialMessage, initialEnabled, onSave }) => {
  const initial = getInitialWelcomeState(initialMessage, initialEnabled);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [text, setText] = useState(initial.text);
  const [media, setMedia] = useState<WelcomeMedia>(initial.media);
  const [buttonRows, setButtonRows] = useState<WelcomeButton[][]>(initial.buttonRows);
  const [isTemplate, setIsTemplate] = useState(initial.isTemplate);
  const [rich, setRich] = useState(initial.rich);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const buildMessage = (): WelcomeMessage | null => {
    const hasText = text.trim().length > 0;
    const hasMedia = media !== null;
    const hasButtons = buttonRows.some(row => row.some(btn => btn.text.trim() && btn.url.trim()));

    if (!hasText && !hasMedia) return null;

    const msg: WelcomeMessage = {};

    if (hasMedia) {
      if (media!.file_type === 'photo') msg.photo = [{ file_id: media!.file_id }];
      else if (media!.file_type === 'video') msg.video = { file_id: media!.file_id };
      else if (media!.file_type === 'animation') msg.animation = { file_id: media!.file_id };
      if (hasText) msg.caption = text;
    } else {
      if (hasText) msg.text = text;
    }

    if (hasButtons) {
      const filtered = buttonRows
        .map(row => row.filter(btn => btn.text.trim() && btn.url.trim()))
        .filter(row => row.length > 0);
      if (filtered.length > 0) {
        msg.reply_markup = { inline_keyboard: filtered };
      }
    }

    if (isTemplate) msg.is_template = true;
    if (rich) msg.rich = true;
    return msg;
  };

  // В rich-режиме медиа вставляется как <img> в текст, а не как structured media
  const handleRichMediaChange = (m: { file_id: string; file_type: 'photo' | 'video' | 'animation' } | null) => {
    if (!rich || m === null) {
      setMedia(m);
      return;
    }
    // Вставляем тег в textarea
    const url = buildMediaUrl(m.file_id);
    const tag = `<img src="${url}">`;
    const textarea = textareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart;
      const value = textarea.value;
      const prefix = start > 0 && value[start - 1] !== '\n' ? '\n' : '';
      const insertion = prefix + tag + '\n';
      const newValue = value.slice(0, start) + insertion + value.slice(start);
      textarea.value = newValue;
      setText(newValue);
      textarea.focus();
      textarea.setSelectionRange(start + insertion.length, start + insertion.length);
    }
    // structured media не ставим
    setMedia(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const msg = buildMessage();
      await onSave({
        welcome_message: msg,
        welcome_enabled: enabled,
      });
      toast.success('Приветствие сохранено');
    } catch {
      // Error handled by interceptor
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    try {
      await chatsApi.testWelcome(chatId);
      toast.success('Тестовое сообщение отправлено');
    } catch {
      // Error handled by interceptor
    }
  };

  const handleDelete = async () => {
    setSaving(true);
    try {
      await onSave({ welcome_message: null, welcome_enabled: false });
      setText('');
      setMedia(null);
      setButtonRows([]);
      setIsTemplate(false);
      setEnabled(false);
      toast.success('Приветствие удалено');
    } catch {
      // Error handled by interceptor
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card icon={MessageSquare} title="Приветствие">
      {/* Enable toggle */}
      <Toggle label="Включено" value={enabled} onChange={setEnabled} />

      {enabled && (
        <div className="flex flex-col lg:flex-row gap-4 mt-3">
          {/* Editor side */}
          <div className="flex-1 space-y-4">
            {/* Media */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">Медиа</span>
              <MediaUpload chatId={chatId} media={media} onMediaChange={handleRichMediaChange} />
            </div>

            {/* Text */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">
                {media ? 'Подпись' : 'Текст'}
                <span className="ml-2 normal-case">({text.length}/{media ? 1024 : 4096})</span>
              </span>
              <TextToolbar textareaRef={textareaRef} onTextChange={setText} richMode={rich} />
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={media ? 1024 : 4096}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text resize-y min-h-24 font-mono"
                placeholder="Введите текст приветствия…"
              />
            </div>

            {/* Buttons */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">URL-кнопки</span>
              <ButtonConstructor rows={buttonRows} onChange={setButtonRows} />
            </div>

            {/* Settings */}
            <div className="space-y-2 border-t border-border pt-3">
              <Toggle label="Шаблонные переменные" value={isTemplate} onChange={setIsTemplate} />
              <Toggle label="Rich-форматирование" value={rich} onChange={setRich} />
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 pt-2">
              <Button
                variant="primary"
                onClick={handleSave}
                disabled={saving}
                className="flex-1"
              >
                {saving ? 'Сохранение…' : 'Сохранить'}
              </Button>
              <Button variant="secondary" onClick={handleTest}>
                Тест
              </Button>
              <Button variant="danger" onClick={handleDelete}>
                Удалить
              </Button>
            </div>
          </div>

          {/* Preview side */}
          <div className="lg:w-80 lg:sticky lg:top-4 lg:self-start">
            <WelcomePreview text={text} media={media} buttons={buttonRows} isTemplate={isTemplate} richMode={rich} />
          </div>
        </div>
      )}
    </Card>
  );
};

export default WelcomeEditor;
