import { describe, expect, it } from 'vitest';
import {
  getContentType,
  getContentPreviewText,
  contentTypeConfig,
  getEditableText,
  withEditedText,
} from './triggerContent';
import type { Trigger } from '../types';

const baseTrigger: Trigger = {
  id: 1,
  chat_id: 1,
  key_phrase: 'привет',
  content: {},
  match_type: 'exact',
  is_case_sensitive: false,
  access_level: 'all',
  usage_count: 0,
  created_by: 1,
  moderation_status: 'safe',
  moderation_reason: null,
  moderation_category: null,
  moderation_confidence: null,
  is_template: false,
  rich: false,
  is_deleted: false,
  deleted_at: null,
  chat_title: null,
  preview_url: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

describe('getContentType', () => {
  it('returns text when content has only a text field', () => {
    expect(getContentType({ ...baseTrigger, content: { text: 'привет' } })).toBe('text');
  });

  it('returns text for empty content (fallback)', () => {
    expect(getContentType({ ...baseTrigger, content: {} })).toBe('text');
  });

  it.each([
    ['animation', { animation: {} }],
    ['video', { video: {} }],
    ['video_note', { video_note: {} }],
    ['sticker', { sticker: {} }],
    ['photo', { photo: {} }],
    ['voice', { voice: {} }],
    ['audio', { audio: {} }],
    ['document', { document: {} }],
    ['dice', { dice: {} }],
  ])('detects %s content', (expected, content) => {
    expect(getContentType({ ...baseTrigger, content })).toBe(expected);
  });

  it('prioritizes media over a caption/text field when both are present', () => {
    expect(getContentType({ ...baseTrigger, content: { photo: {}, caption: 'подпись' } })).toBe('photo');
  });

  it('has a label and icon configured for every possible content type', () => {
    for (const type of Object.keys(contentTypeConfig) as Array<keyof typeof contentTypeConfig>) {
      expect(contentTypeConfig[type].label).toBeTruthy();
      expect(contentTypeConfig[type].icon).toBeTruthy();
    }
  });
});

describe('getContentPreviewText', () => {
  it('returns the text field for plain text triggers', () => {
    expect(getContentPreviewText({ ...baseTrigger, content: { text: 'Привет, мир!' } })).toBe('Привет, мир!');
  });

  it('falls back to caption when there is no text field', () => {
    expect(getContentPreviewText({ ...baseTrigger, content: { photo: {}, caption: 'Подпись к фото' } })).toBe('Подпись к фото');
  });

  it('prefers text over caption when both are somehow present', () => {
    expect(getContentPreviewText({ ...baseTrigger, content: { text: 'основной текст', caption: 'подпись' } })).toBe('основной текст');
  });

  it('returns null when there is no text and no caption', () => {
    expect(getContentPreviewText({ ...baseTrigger, content: { sticker: {} } })).toBeNull();
  });

  it('returns null for an empty text field', () => {
    expect(getContentPreviewText({ ...baseTrigger, content: { text: '' } })).toBeNull();
  });

  it('strips HTML tags from rich content and collapses whitespace', () => {
    const trigger = { ...baseTrigger, rich: true, content: { text: '<b>Жирный</b>  <i>текст</i>\n\nс переносом' } };
    expect(getContentPreviewText(trigger)).toBe('Жирный текст с переносом');
  });

  it('keeps literal angle brackets as-is for non-rich content', () => {
    const trigger = { ...baseTrigger, rich: false, content: { text: 'меньше < больше' } };
    expect(getContentPreviewText(trigger)).toBe('меньше < больше');
  });
});

describe('getEditableText', () => {
  it('берёт text у текстового триггера', () => {
    expect(getEditableText({ text: 'привет' })).toBe('привет');
  });

  it('берёт подпись у медиа-триггера', () => {
    expect(getEditableText({ photo: [{ file_id: 'abc' }], caption: 'подпись' })).toBe('подпись');
  });

  it('возвращает пустую строку для медиа без подписи и пустого содержимого', () => {
    expect(getEditableText({ sticker: { file_id: 'abc' } })).toBe('');
    expect(getEditableText({})).toBe('');
    expect(getEditableText(null)).toBe('');
  });
});

describe('withEditedText', () => {
  it('меняет text и сохраняет остальные поля текстового триггера', () => {
    const content = { text: 'старый', reply_markup: { inline_keyboard: [] } };

    expect(withEditedText(content, 'новый')).toEqual({ ...content, text: 'новый' });
  });

  it('сохраняет entities, пока текст не менялся', () => {
    const content = { text: 'жирный', entities: [{ type: 'bold', offset: 0, length: 6 }] };

    expect(withEditedText(content, 'жирный')).toEqual(content);
  });

  it('убирает entities изменённого текста, а чужие не трогает', () => {
    const entity = { type: 'bold', offset: 0, length: 3 };

    expect(withEditedText({ text: 'старый', entities: [entity] }, 'новый')).toEqual({ text: 'новый' });
    expect(
      withEditedText({ photo: [{ file_id: 'abc' }], caption: 'старая', caption_entities: [entity] }, 'новая'),
    ).toEqual({ photo: [{ file_id: 'abc' }], caption: 'новая' });
  });

  it('не теряет медиа и меняет подпись', () => {
    const content = { photo: [{ file_id: 'abc' }], caption: 'старая' };

    expect(withEditedText(content, 'новая')).toEqual({ photo: [{ file_id: 'abc' }], caption: 'новая' });
  });

  it('добавляет подпись медиа, у которого её не было', () => {
    const content = { video: { file_id: 'abc' } };

    expect(withEditedText(content, 'подпись')).toEqual({ video: { file_id: 'abc' }, caption: 'подпись' });
  });

  it('оставляет медиа без подписи как есть, если текст пуст', () => {
    const content = { sticker: { file_id: 'abc' } };

    expect(withEditedText(content, '')).toEqual(content);
  });

  it('очищает существующую подпись', () => {
    expect(withEditedText({ animation: { file_id: 'abc' }, caption: 'была' }, '')).toEqual({
      animation: { file_id: 'abc' },
      caption: '',
    });
  });

  it('не изменяет исходный объект', () => {
    const content = { photo: [{ file_id: 'abc' }], caption: 'старая' };
    withEditedText(content, 'новая');

    expect(content.caption).toBe('старая');
  });

  it('создаёт текстовое содержимое, когда исходного нет', () => {
    expect(withEditedText(null, 'текст')).toEqual({ text: 'текст' });
    expect(withEditedText({}, 'текст')).toEqual({ text: 'текст' });
  });
});
