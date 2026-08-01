import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, formatTime } from './dateFormat';

describe('formatDate', () => {
  it('formats a date as dd.mm.yyyy regardless of locale/env', () => {
    expect(formatDate(new Date(2026, 5, 27))).toBe('27.06.2026');
  });

  it('accepts an ISO string', () => {
    expect(formatDate('2026-01-05T09:06:07Z')).toMatch(/^\d{2}\.\d{2}\.2026$/);
  });

  it('returns an em dash for an invalid date', () => {
    expect(formatDate('not-a-date')).toBe('—');
  });
});

describe('formatTime', () => {
  it('formats time as hh:mm without seconds', () => {
    expect(formatTime(new Date(2026, 5, 27, 9, 6, 42))).toBe('09:06');
  });

  it('returns an em dash for an invalid date', () => {
    expect(formatTime('not-a-date')).toBe('—');
  });
});

describe('formatDateTime', () => {
  it('formats as dd.mm.yyyy hh:mm with a single space, no comma', () => {
    expect(formatDateTime(new Date(2026, 5, 27, 13, 26, 46))).toBe('27.06.2026 13:26');
  });

  it('returns an em dash for an invalid date', () => {
    expect(formatDateTime('not-a-date')).toBe('—');
  });
});
