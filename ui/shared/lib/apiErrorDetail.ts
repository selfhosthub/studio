// ui/shared/lib/apiErrorDetail.ts

import type { ValidationError } from '@/shared/types/api';

const REQUEST_LOCATIONS = new Set(['body', 'query', 'path', 'header', 'cookie']);

const EMAIL_ERROR_PREFIX = 'value is not a valid email address';
const VALUE_ERROR_PREFIX = 'Value error, ';

/** Rewrites a known pydantic error as a sentence naming the field, or returns null. */
function plainValidationSentence(e: ValidationError, field: string): string | null {
  if (e.msg?.startsWith(EMAIL_ERROR_PREFIX)) return 'Enter a valid email address.';
  if (!field) return null;
  if (e.type === 'missing') return `${field} is required.`;
  if (e.type === 'string_too_short' && e.ctx?.min_length !== undefined) {
    return `${field} must be at least ${e.ctx.min_length} characters.`;
  }
  if (e.type === 'string_too_long' && e.ctx?.max_length !== undefined) {
    return `${field} must be at most ${e.ctx.max_length} characters.`;
  }
  return null;
}

/** Formats one FastAPI validation error as a plain sentence or "Field name: message", dropping the request location. */
function formatValidationError(e: ValidationError): string {
  const path = (e.loc ?? []).filter((part, i) => !(i === 0 && REQUEST_LOCATIONS.has(String(part))));
  const raw = path.join('.').replace(/_/g, ' ');
  const field = raw ? `${raw.charAt(0).toUpperCase()}${raw.slice(1)}` : '';
  const sentence = plainValidationSentence(e, field);
  if (sentence) return sentence;
  const msg = e.msg?.startsWith(VALUE_ERROR_PREFIX) ? e.msg.slice(VALUE_ERROR_PREFIX.length) : e.msg;
  return field ? `${field}: ${msg}` : msg;
}

/** Joins validation messages, using a space after a full sentence and a comma otherwise. */
function joinValidationMessages(messages: string[]): string {
  return messages.reduce((out, m, i) => (i === 0 ? m : `${out}${out.endsWith('.') ? ' ' : ', '}${m}`), '');
}

/** Turns an API error `detail` (string, FastAPI validation array or object) into display text, or null when empty. */
export function formatErrorDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return joinValidationMessages((detail as ValidationError[]).map(formatValidationError));
  if (typeof detail === 'object') return JSON.stringify(detail);
  return null;
}
