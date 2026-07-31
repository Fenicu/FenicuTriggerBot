import React from 'react';
import { Trash2 } from 'lucide-react';
import type { WelcomeButton } from '../types';

interface ButtonConstructorProps {
  rows: WelcomeButton[][];
  onChange: (rows: WelcomeButton[][]) => void;
}

const ButtonConstructor: React.FC<ButtonConstructorProps> = ({ rows, onChange }) => {
  const addRow = () => {
    onChange([...rows, [{ text: '', url: '' }]]);
  };

  const deleteRow = (rowIndex: number) => {
    const next = rows.filter((_, i) => i !== rowIndex);
    onChange(next);
  };

  const moveRow = (rowIndex: number, direction: 'up' | 'down') => {
    const next = [...rows];
    const swapWith = direction === 'up' ? rowIndex - 1 : rowIndex + 1;
    [next[rowIndex], next[swapWith]] = [next[swapWith], next[rowIndex]];
    onChange(next);
  };

  const addButton = (rowIndex: number) => {
    if (rows[rowIndex].length >= 3) return;
    const next = rows.map((row, i) =>
      i === rowIndex ? [...row, { text: '', url: '' }] : row
    );
    onChange(next);
  };

  const deleteButton = (rowIndex: number, btnIndex: number) => {
    const newRow = rows[rowIndex].filter((_, i) => i !== btnIndex);
    if (newRow.length === 0) {
      onChange(rows.filter((_, i) => i !== rowIndex));
    } else {
      onChange(rows.map((row, i) => (i === rowIndex ? newRow : row)));
    }
  };

  const updateButton = (
    rowIndex: number,
    btnIndex: number,
    field: 'text' | 'url',
    value: string
  ) => {
    const next = rows.map((row, ri) =>
      ri === rowIndex
        ? row.map((btn, bi) =>
            bi === btnIndex ? { ...btn, [field]: value } : btn
          )
        : row
    );
    onChange(next);
  };

  return (
    <div>
      {rows.map((row, rowIndex) => (
        <div
          key={rowIndex}
          className="bg-bg rounded-xl p-3 mb-3 border border-border"
        >
          <div className="flex justify-between items-center mb-2">
            <span className="text-hint text-xs uppercase tracking-wide">
              Ряд {rowIndex + 1}
            </span>
            <div className="flex gap-1">
              {rowIndex > 0 && (
                <button
                  onClick={() => moveRow(rowIndex, 'up')}
                  className="text-hint text-sm bg-transparent border-none cursor-pointer px-1"
                >
                  ▲
                </button>
              )}
              {rowIndex < rows.length - 1 && (
                <button
                  onClick={() => moveRow(rowIndex, 'down')}
                  className="text-hint text-sm bg-transparent border-none cursor-pointer px-1"
                >
                  ▼
                </button>
              )}
              <button
                onClick={() => deleteRow(rowIndex)}
                className="text-danger text-sm bg-transparent border-none cursor-pointer px-1"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>

          {row.map((btn, btnIndex) => (
            <div key={btnIndex} className="flex gap-2 mb-2">
              <input
                placeholder="Текст"
                value={btn.text}
                onChange={(e) =>
                  updateButton(rowIndex, btnIndex, 'text', e.target.value)
                }
                className="flex-1 bg-elevated border-none rounded-lg px-3 py-1.5 text-sm text-text"
              />
              <input
                placeholder="https://..."
                value={btn.url}
                onChange={(e) =>
                  updateButton(rowIndex, btnIndex, 'url', e.target.value)
                }
                className="flex-1 bg-elevated border-none rounded-lg px-3 py-1.5 text-sm text-text"
              />
              <button
                onClick={() => deleteButton(rowIndex, btnIndex)}
                className="text-danger px-2 bg-transparent border-none cursor-pointer"
              >
                ×
              </button>
            </div>
          ))}

          {row.length < 3 && (
            <button
              onClick={() => addButton(rowIndex)}
              className="text-link text-sm bg-transparent border-none cursor-pointer"
            >
              + Кнопка в этот ряд
            </button>
          )}
        </div>
      ))}

      <button
        onClick={addRow}
        className="text-link text-sm bg-transparent border-none cursor-pointer"
      >
        + Новый ряд
      </button>
    </div>
  );
};

export default ButtonConstructor;
