// ui/shared/lib/webhook-utils.ts

import { getApiUrl } from './config';

/** Webhooks land on the backend API, not the frontend. */
export function getWebhookBaseUrl(): string {
  return getApiUrl();
}

export function buildWebhookUrl(webhookToken: string | null): string {
  if (!webhookToken) return '';
  return `${getWebhookBaseUrl()}/webhooks/incoming/${webhookToken}`;
}

export function buildCurlCommand(
  url: string,
  method: 'POST' | 'GET',
  authType: 'none' | 'header' | 'jwt' | 'hmac',
  authHeaderValue: string,
  jwtSecret: string
): string {
  let authHeader = '';
  if (authType === 'header' && authHeaderValue) {
    authHeader = ` -H "X-API-Key: ${authHeaderValue}"`;
  } else if (authType === 'jwt' && jwtSecret) {
    authHeader = ` -H "Authorization: Bearer <your-jwt-token>"`;
  }

  return method === 'GET'
    ? `curl${authHeader} "${url}?param=value"`
    : `curl -X POST${authHeader} -H "Content-Type: application/json" -d '{"key": "value"}' "${url}"`;
}

export function generateSecureToken(length: number = 32): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('').slice(0, length);
}
