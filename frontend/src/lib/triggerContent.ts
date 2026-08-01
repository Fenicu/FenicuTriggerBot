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

export const getContentType = (trigger: Trigger): TriggerContentType => {
  const content = trigger.content as Record<string, unknown>;
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
