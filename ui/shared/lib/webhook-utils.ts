// ui/shared/lib/webhook-utils.ts

import { getApiUrl } from './config';
import type { FormFieldResponse } from '@/shared/api/workflows';

/**
 * Build a sample trigger payload keyed by each field's stable `field_id`
 * (never the internal `{step_id}.{parameter_key}`): the configured default
 * where one exists, otherwise blank (`""`) — no `<required: …>` help text the
 * caller would have to delete from the JSON. Firing the snippet verbatim is
 * safe: the backend treats a blank value as not-supplied, so it falls back to
 * the default or returns a clear "missing required field" error. Returns a
 * JSON string for a curl `-d` body; `"{}"` when there are no form fields.
 */
export function buildTriggerSampleBody(fields: FormFieldResponse[]): string {
  const body: Record<string, unknown> = {};
  for (const field of fields) {
    const def = field.config.default_value;
    body[field.field_id] = def !== undefined && def !== null ? def : '';
  }
  return JSON.stringify(body);
}

/** Webhooks land on the backend API, not the frontend. */
export function getWebhookBaseUrl(): string {
  return getApiUrl();
}

export function buildWebhookUrl(webhookToken: string | null): string {
  if (!webhookToken) return '';
  return `${getWebhookBaseUrl()}/api/v1/webhooks/incoming/${webhookToken}`;
}

export function buildCurlCommand(
  url: string,
  method: 'POST' | 'GET',
  authType: 'none' | 'header' | 'jwt' | 'hmac',
  authHeaderValue: string,
  jwtSecret: string,
  body: string = '{"key": "value"}'
): string {
  let authHeader = '';
  if (authType === 'header' && authHeaderValue) {
    authHeader = ` -H "X-API-Key: ${authHeaderValue}"`;
  } else if (authType === 'jwt' && jwtSecret) {
    authHeader = ` -H "Authorization: Bearer <your-jwt-token>"`;
  }

  return method === 'GET'
    ? `curl${authHeader} "${url}?param=value"`
    : `curl -X POST${authHeader} -H "Content-Type: application/json" -d '${body}' "${url}"`;
}

export function generateSecureToken(length: number = 32): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('').slice(0, length);
}
