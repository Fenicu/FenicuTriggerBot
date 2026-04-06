import React, { useState, useRef, useEffect } from 'react';
import { chatsApi } from '../api/client';
import { toast } from '../store/store';
import type { WelcomeMessage, WelcomeButton } from '../types';
import { MessageSquare } from 'lucide-react';
import TextToolbar from './TextToolbar';
import MediaUpload from './MediaUpload';
import ButtonConstructor from './ButtonConstructor';
import WelcomePreview from './WelcomePreview';

interface WelcomeEditorProps {
  chatId: number;
  initialMessage: WelcomeMessage | null;
  initialEnabled: boolean;
  onSave: (data: {
    welcome_message: WelcomeMessage | null;
    welcome_enabled: boolean;
  }) => Promise<void>;
}

const Section = ({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) => (
  <div className="bg-section-bg rounded-xl p-4 mb-4">
    <div className="flex items-center mb-3 text-link">
      <Icon size={20} className="mr-2" />
      <h2 className="text-base font-bold m-0">{title}</h2>
    </div>
    {children}
  </div>
);

const WelcomeEditor: React.FC<WelcomeEditorProps> = ({ chatId, initialMessage, initialEnabled, onSave }) => {
  const [enabled, setEnabled] = useState(initialEnabled);
  const [text, setText] = useState('');
  const [media, setMedia] = useState<{ file_id: string; file_type: 'photo' | 'video' | 'animation' } | null>(null);
  const [buttonRows, setButtonRows] = useState<WelcomeButton[][]>([]);
  const [isTemplate, setIsTemplate] = useState(false);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Reset all state
    setText('');
    setMedia(null);
    setButtonRows([]);
    setIsTemplate(false);
    setEnabled(initialEnabled);

    if (!initialMessage) return;

    setText(initialMessage.text || initialMessage.caption || '');
    if (initialMessage.photo?.length) {
      setMedia({ file_id: initialMessage.photo[initialMessage.photo.length - 1].file_id, file_type: 'photo' });
    } else if (initialMessage.video) {
      setMedia({ file_id: initialMessage.video.file_id, file_type: 'video' });
    } else if (initialMessage.animation) {
      setMedia({ file_id: initialMessage.animation.file_id, file_type: 'animation' });
    }
    if (initialMessage.reply_markup?.inline_keyboard) {
      setButtonRows(initialMessage.reply_markup.inline_keyboard);
    }
    setIsTemplate(initialMessage.is_template || false);
  }, [chatId]);

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
    return msg;
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
    <Section title="Приветствие" icon={MessageSquare}>
      {/* Enable toggle */}
      <label className="flex items-center justify-between py-2 cursor-pointer">
        <span>Включено</span>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="w-5 h-5" />
      </label>

      {enabled && (
        <div className="flex flex-col lg:flex-row gap-4 mt-3">
          {/* Editor side */}
          <div className="flex-1 space-y-4">
            {/* Media */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">Медиа</span>
              <MediaUpload chatId={chatId} media={media} onMediaChange={setMedia} />
            </div>

            {/* Text */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">
                {media ? 'Подпись' : 'Текст'}
                <span className="ml-2 normal-case">({text.length}/{media ? 1024 : 4096})</span>
              </span>
              <TextToolbar textareaRef={textareaRef} onTextChange={setText} />
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={media ? 1024 : 4096}
                className="w-full bg-bg border border-secondary-bg rounded-lg px-3 py-2 text-sm text-text resize-y min-h-24 font-mono"
                placeholder="Введите текст приветствия..."
              />
            </div>

            {/* Buttons */}
            <div>
              <span className="block text-hint text-xs uppercase tracking-wide mb-2">URL-кнопки</span>
              <ButtonConstructor rows={buttonRows} onChange={setButtonRows} />
            </div>

            {/* Settings */}
            <div className="space-y-2 border-t border-secondary-bg pt-3">
              <label className="flex items-center justify-between py-1 cursor-pointer">
                <span className="text-sm">Шаблонные переменные</span>
                <input type="checkbox" checked={isTemplate} onChange={(e) => setIsTemplate(e.target.checked)} className="w-5 h-5" />
              </label>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 bg-button text-button-text py-2.5 rounded-lg font-bold border-none cursor-pointer disabled:opacity-50"
              >
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
              <button
                onClick={handleTest}
                className="bg-secondary-bg text-text py-2.5 px-4 rounded-lg font-bold border-none cursor-pointer"
              >
                Тест
              </button>
              <button
                onClick={handleDelete}
                className="bg-secondary-bg text-red-500 py-2.5 px-4 rounded-lg font-bold border-none cursor-pointer"
              >
                Удалить
              </button>
            </div>
          </div>

          {/* Preview side */}
          <div className="lg:w-80 lg:sticky lg:top-4 lg:self-start">
            <WelcomePreview text={text} media={media} buttons={buttonRows} isTemplate={isTemplate} />
          </div>
        </div>
      )}
    </Section>
  );
};

export default WelcomeEditor;
