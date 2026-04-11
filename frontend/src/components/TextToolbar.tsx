import React, { useState, useRef, useEffect } from 'react';

interface TextToolbarProps {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onTextChange: (text: string) => void;
}

interface Variable {
  key: string;
  label: string;
}

const variables: Variable[] = [
  { key: 'user.mention', label: 'Упоминание пользователя' },
  { key: 'user.full_name', label: 'Полное имя' },
  { key: 'chat.title', label: 'Название чата' },
  { key: 'date', label: 'Дата' },
  { key: 'time', label: 'Время' },
];

const TextToolbar: React.FC<TextToolbarProps> = ({ textareaRef, onTextChange }) => {
  const [showVars, setShowVars] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowVars(false);
      }
    };
    if (showVars) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showVars]);

  const wrapSelection = (openTag: string, closeTag: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;

    let newValue: string;
    let newCursorPos: number;

    if (start !== end) {
      const selected = value.slice(start, end);
      newValue = value.slice(0, start) + openTag + selected + closeTag + value.slice(end);
      newCursorPos = start + openTag.length + selected.length + closeTag.length;
    } else {
      newValue = value.slice(0, start) + openTag + closeTag + value.slice(start);
      newCursorPos = start + openTag.length;
    }

    textarea.value = newValue;
    onTextChange(newValue);
    textarea.focus();
    textarea.setSelectionRange(newCursorPos, newCursorPos);
  };

  const handleLink = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.slice(start, end);

    const url = window.prompt('Введите URL:');
    if (url === null) return;

    const openTag = `<a href="${url}">`;
    const closeTag = '</a>';
    const linkText = selectedText || url;

    const value = textarea.value;
    const newValue = value.slice(0, start) + openTag + linkText + closeTag + value.slice(end);
    const newCursorPos = start + openTag.length + linkText.length + closeTag.length;

    textarea.value = newValue;
    onTextChange(newValue);
    textarea.focus();
    textarea.setSelectionRange(newCursorPos, newCursorPos);
  };

  const insertVariable = (key: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const value = textarea.value;
    const insertion = `{{ ${key} }}`;
    const newValue = value.slice(0, start) + insertion + value.slice(start);
    const newCursorPos = start + insertion.length;

    textarea.value = newValue;
    onTextChange(newValue);
    setShowVars(false);
    textarea.focus();
    textarea.setSelectionRange(newCursorPos, newCursorPos);
  };

  const buttons = [
    { label: 'B', title: 'Жирный', onClick: () => wrapSelection('<b>', '</b>') },
    { label: 'I', title: 'Курсив', onClick: () => wrapSelection('<i>', '</i>') },
    { label: 'U', title: 'Подчёркнутый', onClick: () => wrapSelection('<u>', '</u>') },
    { label: 'S', title: 'Зачёркнутый', onClick: () => wrapSelection('<s>', '</s>') },
    { label: '</>', title: 'Код', onClick: () => wrapSelection('<code>', '</code>') },
    { label: 'pre', title: 'Предформатированный', onClick: () => wrapSelection('<pre>', '</pre>') },
    { label: '◐', title: 'Спойлер', onClick: () => wrapSelection('<tg-spoiler>', '</tg-spoiler>') },
    { label: '🔗', title: 'Ссылка', onClick: handleLink },
  ];

  return (
    <div className="flex flex-wrap gap-1 mb-2 items-start">
      {buttons.map((btn) => (
        <button
          key={btn.label}
          onClick={btn.onClick}
          className="bg-elevated text-text px-2.5 py-1 rounded text-sm hover:bg-button hover:text-button-text transition-colors"
          title={btn.title}
          type="button"
        >
          {btn.label}
        </button>
      ))}

      <div className="relative inline-block" ref={dropdownRef}>
        <button
          onClick={() => setShowVars((v) => !v)}
          className="bg-elevated text-text px-2.5 py-1 rounded text-sm hover:bg-button hover:text-button-text transition-colors"
          title="Переменные"
          type="button"
        >
          {'{{ }}'}
        </button>
        {showVars && (
          <div className="absolute top-full left-0 mt-1 bg-surface border border-border rounded-lg shadow-lg z-10 min-w-48">
            {variables.map((v) => (
              <button
                key={v.key}
                onClick={() => insertVariable(v.key)}
                className="block w-full text-left px-3 py-2 text-sm hover:bg-elevated"
                type="button"
              >
                <span className="font-mono text-link">{`{{ ${v.key} }}`}</span>
                <span className="text-hint ml-2">{v.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TextToolbar;
