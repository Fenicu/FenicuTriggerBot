import React, { useEffect, useCallback, useState, useRef } from 'react';
import { X } from 'lucide-react';
import { usePromptModal } from '../store/store';

// Замена window.prompt(): в Telegram WebView нативные диалоги заблокированы и
// window.prompt() всегда молча возвращает null. Паттерн — как у ConfirmModal.
const PromptModal: React.FC = () => {
  const { isOpen, title, message, placeholder, defaultValue, confirmText, cancelText, onConfirm, onCancel } =
    usePromptModal();
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      // Синхронизация со внешним стором при открытии -- сброс поля на значение
      // по умолчанию для нового вызова prompt(), не цикл рендеров
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValue(defaultValue ?? '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    // Автофокус и выделение значения по умолчанию при открытии
    const id = setTimeout(() => inputRef.current?.select(), 0);
    return () => clearTimeout(id);
  }, [isOpen]);

  const handleConfirm = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return; // пусто = не отправлять
    onConfirm(trimmed);
  }, [value, onConfirm]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onCancel();
      } else if (e.key === 'Enter') {
        handleConfirm();
      }
    },
    [isOpen, onCancel, handleConfirm]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const isEmpty = !value.trim();

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-100 p-4 animate-fadeIn"
      onClick={onCancel}
    >
      <div
        className="bg-surface p-6 rounded-2xl max-w-sm w-full shadow-lg border border-border relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-hint hover:text-text transition-colors"
        >
          <X size={20} />
        </button>

        {/* Title */}
        <h2 className="text-lg font-bold mb-2 pr-6">{title}</h2>

        {/* Message */}
        {message && <p className="text-hint mb-4">{message}</p>}

        {/* Input */}
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text mb-6 outline-none focus:border-button transition-colors"
        />

        {/* Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-3 px-4 rounded-xl font-medium bg-elevated hover:bg-elevated transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={handleConfirm}
            disabled={isEmpty}
            className="flex-1 py-3 px-4 rounded-xl font-medium bg-button hover:opacity-90 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PromptModal;
