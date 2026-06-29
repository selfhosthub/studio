// ui/shared/api/server.ts

// Server-side API base URL resolver for SSR and route handlers. Reads
// SHS_API_BASE_URL per call (request time) so the ui process's runtime env wins;
// never captured into a module-level constant.

import { API_VERSION } from '@/shared/lib/config';

/** Server-side API base URL, read at request time. Throws if unset - no public fallback (that would hairpin out of Docker). */
export function getServerApiUrl(): string {
  const url = process.env.SHS_API_BASE_URL;
  if (!url) {
    throw new Error('SHS_API_BASE_URL is not set. Configure it in your .env file.');
  }
  return url;
}

/** Server-side fetch against the API. Reads the base URL at request time. */
export async function serverApiFetch(endpoint: string, init?: RequestInit): Promise<Response> {
  const url = `${getServerApiUrl()}${API_VERSION}${endpoint}`;
  return fetch(url, { cache: 'no-store', ...init });
}
