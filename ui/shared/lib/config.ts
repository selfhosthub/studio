// ui/shared/lib/config.ts

// Runtime config. In Docker, NEXT_PUBLIC_* are baked at build time; the entrypoint
// injects runtime overrides into window.__ENV before hydration.

// Static process.env reads - Next.js / Turbopack only replace literal accesses,
// not dynamic process.env[key].
const STATIC_ENV: Record<string, string | undefined> = {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  NEXT_PUBLIC_API_ENV: process.env.NEXT_PUBLIC_API_ENV,
};

/** window.__ENV (browser, runtime) wins over process.env (server/dev, build-time). */
function getEnv(key: string): string | undefined {
  if (typeof window !== 'undefined' && (window as any).__ENV?.[key]) {
    return (window as any).__ENV[key];
  }
  return STATIC_ENV[key];
}

export function getApiUrl(): string {
  const url = getEnv('NEXT_PUBLIC_API_URL');
  if (!url) {
    throw new Error('NEXT_PUBLIC_API_URL is not set. Configure it in your .env file.');
  }
  return url;
}

export function getWsUrl(): string {
  const url = getEnv('NEXT_PUBLIC_WS_URL');
  if (!url) {
    throw new Error('NEXT_PUBLIC_WS_URL is not set. Configure it in your .env file.');
  }
  return url;
}

export const API_VERSION = '/api/v1';

/**
 * Resolve a server-relative upload path (e.g. "/uploads/orgs/.../avatar.jpg")
 * to an absolute URL on the API origin. Static uploads are served by the API,
 * not the Next.js UI origin, so a bare "/uploads/..." src would 404 against the UI.
 * Pass-through for empty values and already-absolute URLs (http/https/data/blob).
 */
export function resolveUploadUrl(path?: string | null): string | undefined {
  if (!path) {
    return undefined;
  }
  if (/^(https?:|data:|blob:)/.test(path)) {
    return path;
  }
  const base = getApiUrl();
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export function getApiEndpoint(path: string): string {
  const base = getApiUrl();
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${API_VERSION}${cleanPath}`;
}
