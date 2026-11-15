// Определение типа содержимого триггера и текстового превью ответа.
// Общая логика для TriggersList (список/таблица триггеров) и карточки
// пользователя (UserDetails) -- не дублировать.

import type React from 'react';
import type { Trigger } from '../types';
import { FileText, Image, Video, Film, Sticker, Mic, Music, FileIcon, Dices, Circle } from 'lucide-react';

export type TriggerContentType =
  | 'text'
  | 'photo'
  | 'video'
  | 'video_note'
  | 'animation'
  | 'sticker'
  | 'voice'
  | 'audio'
  | 'document'
  | 'dice';

export interface ContentTypeConfigEntry {
  label: string;
  icon: React.ElementType;
  color: string;
}

export const contentTypeConfig: Record<TriggerContentType, ContentTypeConfigEntry> = {
  text: { label: 'Текст', icon: FileText, color: 'text-hint' },
  photo: { label: 'Фото', icon: Image, color: 'text-hint' },
  video: { label: 'Видео', icon: Video, color: 'text-hint' },
  video_note: { label: 'Видеосообщение', icon: Circle, color: 'text-hint' },
  animation: { label: 'GIF', icon: Film, color: 'text-hint' },
  sticker: { label: 'Стикер', icon: Sticker, color: 'text-hint' },
  voice: { label: 'Голосовое', icon: Mic, color: 'text-hint' },
  audio: { label: 'Аудио', icon: Music, color: 'text-hint' },
  document: { label: 'Документ', icon: FileIcon, color: 'text-hint' },
  dice: { label: 'Кубик', icon: Dices, color: 'text-hint' },
};

export const getContentType = (trigger: Trigger): TriggerContentType => contentTypeOf(trigger.content);

const contentTypeOf = (content: Record<string, unknown>): TriggerContentType => {
  if (content.animation) return 'animation';
  if (content.video) return 'video';
  if (content.video_note) return 'video_note';
  if (content.sticker) return 'sticker';
  if (content.photo) return 'photo';
  if (content.voice) return 'voice';
  if (content.audio) return 'audio';
  if (content.document) return 'document';
  if (content.dice) return 'dice';
  if (content.text) return 'text';
  return 'text';
};

/**
 * Текст превью ответа триггера: content.text для текстовых триггеров,
 * content.caption для медиа с подписью (см. app/services/trigger_service.py,
 * там то же самое "text or caption"). Для rich-триггеров content -- HTML,
 * поэтому теги вырезаются -- превью показывает текст, а не разметку.
 */
export const getContentPreviewText = (trigger: Trigger): string | null => {
  const content = trigger.content as Record<string, unknown>;
  const raw =
    (typeof content.text === 'string' && content.text) ||
    (typeof content.caption === 'string' && content.caption) ||
    '';
  if (!raw) return null;
  const plain = trigger.rich ? raw.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim() : raw.trim();
  return plain || null;
};

/** Имя поля, в котором лежит редактируемый текст: text у текстовых, caption у медиа. */
const editableTextField = (content: Record<string, unknown>): 'text' | 'caption' => {
  if (contentTypeOf(content) === 'text') return 'text';
  if (typeof content.text === 'string' && content.text && typeof content.caption !== 'string') return 'text';
  return 'caption';
};

/** Текст триггера для формы редактирования: content.text либо подпись медиа. */
export const getEditableText = (content: Record<string, unknown> | null | undefined): string => {
  if (!content || typeof content !== 'object') return '';
  const value = content[editableTextField(content)];
  return typeof value === 'string' ? value : '';
};

/**
 * Содержимое триггера с новым текстом. Остальные поля (медиа, кнопки и т.п.) сохраняются:
 * у текстового триггера меняется text, у медиа -- подпись. Если текст изменился, вместе
 * с ним уходят его entities.
 */
export const withEditedText = (
  content: Record<string, unknown> | null | undefined,
  text: string,
): Record<string, unknown> => {
  if (!content || typeof content !== 'object') return { text };
  const field = editableTextField(content);
  // Медиа без подписи остаётся без подписи, пока её не ввели
  if (field === 'caption' && !text && !('caption' in content)) return { ...content };
  if (content[field] === text) return { ...content };

  const next: Record<string, unknown> = { ...content, [field]: text };
  // Офсеты entities считались по старому тексту и к новому не подходят
  delete next[field === 'text' ? 'entities' : 'caption_entities'];
  return next;
};
