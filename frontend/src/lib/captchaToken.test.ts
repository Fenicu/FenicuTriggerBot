import { describe, expect, it } from 'vitest';
import { parseCaptchaToken } from './captchaToken';

describe('parseCaptchaToken', () => {
  it('returns null for an empty hash', () => {
    expect(parseCaptchaToken('')).toBeNull();
  });

  it('returns null when there is no token param', () => {
    expect(parseCaptchaToken('#/captcha')).toBeNull();
    expect(parseCaptchaToken('#/captcha?foo=bar')).toBeNull();
  });

  it('extracts the token when present', () => {
    expect(parseCaptchaToken('#/captcha?token=abc123')).toBe('abc123');
  });

  it('extracts the token among extra/garbage params in any order', () => {
    expect(parseCaptchaToken('#/captcha?foo=bar&token=abc123&baz=qux')).toBe('abc123');
    expect(parseCaptchaToken('#/captcha?token=abc123&token=xyz789')).toBe('abc123');
  });
});
