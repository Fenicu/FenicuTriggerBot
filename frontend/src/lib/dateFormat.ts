// Единый формат дат для UI: дд.мм.гггг и дд.мм.гггг чч:мм, локаль ru-RU.
//
// Голый toLocaleDateString()/toLocaleString() без явной локали в Telegram WebView
// подхватывает локаль системы/клиента (часто американскую) и печатает "6/27/2026,
// 1:26:46 PM" -- фиксируем формат явно вместо navigator.language.

export type DateInput = string | number | Date;

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value);
}

/** дд.мм.гггг */
export function formatDate(value: DateInput): string {
  const date = toDate(value);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/** чч:мм (без секунд) */
export function formatTime(value: DateInput): string {
  const date = toDate(value);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

/** дд.мм.гггг чч:мм (без секунд) */
export function formatDateTime(value: DateInput): string {
  const date = toDate(value);
  if (isNaN(date.getTime())) return '—';
  return `${formatDate(date)} ${formatTime(date)}`;
}
