import { describe, expect, it } from 'vitest';

import { revertPatchedFields } from './settingsRevert';

interface Settings {
  captcha_enabled: boolean;
  timezone: string;
  tags_preset: string;
  tags_custom: Record<string, string> | null;
}

const server: Settings = {
  captcha_enabled: false,
  timezone: 'UTC',
  tags_preset: 'custom',
  tags_custom: { '1': 'Новичок' },
};

describe('revertPatchedFields', () => {
  it('возвращает несохранённое поле к значению сервера', () => {
    const local = { ...server, captcha_enabled: true };

    expect(revertPatchedFields(local, server, { captcha_enabled: true })).toEqual(server);
  });

  it('откатывает все поля патча', () => {
    const local = { ...server, tags_preset: 'gaming', tags_custom: null };

    expect(revertPatchedFields(local, server, { tags_preset: 'gaming', tags_custom: null })).toEqual(server);
  });

  it('не трогает локальные правки вне патча', () => {
    const local = { ...server, captcha_enabled: true, timezone: 'Europe/Moscow' };

    expect(revertPatchedFields(local, server, { captcha_enabled: true })).toEqual({
      ...server,
      timezone: 'Europe/Moscow',
    });
  });

  it('не изменяет исходные объекты', () => {
    const local = { ...server, captcha_enabled: true };
    revertPatchedFields(local, server, { captcha_enabled: true });

    expect(local.captcha_enabled).toBe(true);
    expect(server.captcha_enabled).toBe(false);
  });

  it('оставляет состояние как есть, пока нет значения сервера', () => {
    const local = { ...server, captcha_enabled: true };

    expect(revertPatchedFields(local, null, { captcha_enabled: true })).toBe(local);
    expect(revertPatchedFields(null, server, { captcha_enabled: true })).toBeNull();
  });
});
