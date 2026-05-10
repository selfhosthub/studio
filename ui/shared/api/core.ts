// ui/shared/api/core.ts

import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import type { APIError, ValidationError } from '@/shared/types/api';
import {
  getAuthHeaders,
  getRefreshToken,
  clearAuth,
  refreshAccessToken,
  RefreshResponse,
} from './auth';

let isRefreshing = false;
let refreshPromise: Promise<RefreshResponse | null> | null = null;

/**
 * Coalesce concurrent 401s onto a single in-flight refresh attempt.
 */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  if (!isRefreshing) {
    isRefreshing = true;
    refreshPromise = refreshAccessToken();
  }

  const tokens = await refreshPromise;
  isRefreshing = false;
  refreshPromise = null;

  return tokens !== null;
}

function failUnauthorized(): never {
  clearAuth();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('session-expired'));
  }
  throw new Error('Unauthorized');
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  _isRetry: boolean = false
): Promise<T> {
  const url = `${getApiUrl()}${API_VERSION}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
    cache: 'no-store',
  });

  if (!response.ok) {
    if (response.status === 401 && !_isRetry) {
      if (await tryRefreshToken()) {
        return apiRequest<T>(endpoint, options, true);
      }
      failUnauthorized();
    }

    if (response.status === 401) {
      failUnauthorized();
    }

    let errorMessage = `API error: ${response.status}`;

    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
      const error = await response.json() as APIError;
      if (error.detail) {
        if (typeof error.detail === 'string') {
          errorMessage = error.detail;
        } else if (Array.isArray(error.detail)) {
          // FastAPI validation errors arrive as arrays.
          errorMessage = (error.detail as ValidationError[]).map((e) => {
            const field = e.loc ? e.loc.join('.') : 'unknown';
            return `${field}: ${e.msg}`;
          }).join(', ');
        } else if (typeof error.detail === 'object') {
          errorMessage = JSON.stringify(error.detail);
        }
      }
    }

    const apiError = new Error(errorMessage) as Error & { status: number };
    apiError.status = response.status;
    throw apiError;
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return response.json();
}

export async function apiFetchBlob(
  url: string,
  options: RequestInit = {},
  _isRetry: boolean = false
): Promise<Blob> {
  const fullUrl = url.startsWith('http') ? url : `${getApiUrl()}${url}`;
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  };

  const response = await fetch(fullUrl, {
    ...options,
    headers,
    cache: 'no-store',
  });

  if (response.status === 401 && !_isRetry) {
    if (await tryRefreshToken()) {
      return apiFetchBlob(url, options, true);
    }
    failUnauthorized();
  }

  if (response.status === 401) {
    failUnauthorized();
  }

  if (!response.ok) {
    throw new Error(`Failed to fetch: ${response.status} ${response.statusText}`);
  }

  return response.blob();
}

export async function publicApiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getApiUrl()}${API_VERSION}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return response.json();
}

export function getToken(): string | null {
  return localStorage.getItem('token');
}
