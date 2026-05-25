// ui/shared/lib/page-visibility.ts

/** Server-side page visibility check for use in Server Components. */

import { API_VERSION } from './config';

export interface PageVisibility {
  about: boolean;
  blueprints: boolean;
  compliance: boolean;
  contact: boolean;
  docs: boolean;
  privacy: boolean;
  support: boolean;
  terms: boolean;
}

// Defaults to true so pages render when the API is unreachable during SSR.
// The API returns the admin-configured values; these only apply on fetch failure.
const defaultVisibility: PageVisibility = {
  about: true,
  blueprints: false,
  compliance: true,
  contact: true,
  docs: true,
  privacy: true,
  support: true,
  terms: true,
};

/** Server-side API base URL - separate from the browser env var because Docker hostnames differ from public URLs. Throws if unset. */
export function getServerApiUrl(): string {
  const url = process.env.SHS_API_BASE_URL;
  if (!url) {
    throw new Error('SHS_API_BASE_URL is not set. Configure it in your .env file.');
  }
  return url;
}

/** Returns null on network failure; config errors (missing env var) propagate uncaught to the nearest error boundary. */
export async function serverFetch(path: string, init?: RequestInit): Promise<Response | null> {
  const baseUrl = getServerApiUrl();
  try {
    const response = await fetch(`${baseUrl}${path}`, init);
    if (response.ok) return response;
  } catch (error: unknown) {
    console.error(`SSR fetch failed for ${path}:`, error); // nosemgrep: unsafe-formatstring
  }
  return null;
}

export async function getPageVisibility(): Promise<PageVisibility> {
  const response = await serverFetch(`${API_VERSION}/public/page-visibility`, {
    next: { revalidate: 60 },
  } as RequestInit);

  if (response) {
    const data = await response.json();
    return {
      about: data.about ?? false,
      blueprints: data.blueprints ?? false,
      compliance: data.compliance ?? false,
      contact: data.contact ?? false,
      docs: data.docs ?? false,
      privacy: data.privacy ?? false,
      support: data.support ?? false,
      terms: data.terms ?? false,
    };
  }
  return defaultVisibility;
}

export async function isPageVisible(page: keyof PageVisibility): Promise<boolean> {
  const visibility = await getPageVisibility();
  return visibility[page];
}
