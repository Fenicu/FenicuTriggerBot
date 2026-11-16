// Откат оптимистичных правок настроек после неудачного сохранения.

/**
 * Возвращает поля из patch к последнему значению сервера. Остальные локальные правки
 * (например, недописанный текст в другом поле) остаются.
 */
export function revertPatchedFields<T extends object>(current: T | null, server: T | null, patch: Partial<T>): T | null {
  if (!current || !server) return current;

  const reverted = { ...current };
  for (const key of Object.keys(patch) as (keyof T)[]) {
    reverted[key] = server[key];
  }
  return reverted;
}
