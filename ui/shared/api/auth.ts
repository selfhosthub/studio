// ui/shared/api/auth.ts

import type { User } from '@/shared/types/user';
import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import { STORAGE_KEYS } from '@/shared/lib/constants';

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ApiError {
  detail: string;
}

export interface OAuthProviderInfo {
  name: string;
  slug: string;
  icon_url?: string;
  description?: string;
}

export interface OAuthProvidersResponse {
  providers: OAuthProviderInfo[];
}

export interface OAuthAuthorizeResponse {
  authorization_url: string;
  state: string;
}

export interface OAuthTokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
}

export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
}

export function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.CURRENT_USER);
}

export function storeAuth(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, accessToken);
  if (refreshToken) {
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  }
  // The token is a pure session pointer - it carries no identity/role claims.
  // The user profile is cached separately via cacheUser() after /users/me.
}

/**
 * Cache the DB-sourced user profile (from /users/me) for synchronous reads by
 * non-context API helpers. This is NOT the source of truth for UI role gating -
 * that comes from the React context, hydrated fresh from /users/me each session.
 */
export function cacheUser(user: User): void {
  localStorage.setItem(STORAGE_KEYS.CURRENT_USER, JSON.stringify(user));
}

/**
 * Extract the user id (the `sub` claim) from the token. The token no longer
 * carries display/role claims, so id is all that can be read from it.
 */
export function decodeToken(token: string): { id: string } {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid token format');
    }

    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(decoded);

    if (!claims.sub) {
      throw new Error('Invalid token');
    }

    return { id: claims.sub };
  } catch {
    throw new Error('Invalid token');
  }
}

/**
 * Returns the cached DB-sourced user profile, or null if not authenticated /
 * not yet hydrated. The token must be present (session pointer) AND a cached
 * profile must exist. Role/identity come from /users/me, never the token.
 */
export function getCurrentUser(): User | null {
  if (!localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)) {
    return null;
  }

  const cached = localStorage.getItem(STORAGE_KEYS.CURRENT_USER);
  if (!cached) {
    return null;
  }

  try {
    return JSON.parse(cached) as User;
  } catch {
    localStorage.removeItem(STORAGE_KEYS.CURRENT_USER);
    return null;
  }
}

export function isAuthenticated(): boolean {
  return localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN) !== null;
}

export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  const apiUrl = getApiUrl();
  const loginUrl = `${apiUrl}${API_VERSION}/auth/token`;

  try {
    const response = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        username,
        password,
      }),
    });

    if (!response.ok) {
      const contentType = response.headers.get('content-type') ?? '';
      if (contentType.includes('application/json')) {
        const error: ApiError = await response.json();
        throw new Error(error.detail || 'Login failed');
      }
      throw new Error(`Login failed (HTTP ${response.status})`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error(`Cannot connect to server at ${apiUrl}. Check your network connection.`);
    }
    throw error;
  }
}

export async function register(
  firstName: string,
  lastName: string,
  email: string,
  password: string,
  planSlug?: string
): Promise<RegisterResponse> {
  const response = await fetch(`${getApiUrl()}${API_VERSION}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      first_name: firstName,
      last_name: lastName,
      email,
      password,
      plan_slug: planSlug || undefined,
    }),
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }
    throw new Error(`Registration failed (HTTP ${response.status})`);
  }

  return response.json();
}

/**
 * Calls the backend logout endpoint for audit logging, then clears local auth
 * unconditionally - local clear runs even if the network call fails.
 */
export async function logout(): Promise<void> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);

  if (token) {
    try {
      await fetch(`${getApiUrl()}${API_VERSION}/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
    } catch {
      // Network failures must not block local logout.
    }
  }

  clearAuth();
}

export async function refreshAccessToken(): Promise<RefreshResponse | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(`${getApiUrl()}${API_VERSION}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearAuth();
      return null;
    }

    const tokens: RefreshResponse = await response.json();

    storeAuth(tokens.access_token, tokens.refresh_token);

    return tokens;
  } catch {
    clearAuth();
    return null;
  }
}

export async function getOAuthProviders(): Promise<OAuthProvidersResponse> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
  const response = await fetch(`${getApiUrl()}${API_VERSION}/oauth/providers`, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error('Failed to fetch OAuth providers');
  }
  return response.json();
}

export async function getOAuthAuthorizeUrl(
  providerSlug: string,
  credentialId?: string,
  redirectUri?: string
): Promise<OAuthAuthorizeResponse> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);

  const params = new URLSearchParams();
  if (credentialId) {
    params.append('credential_id', credentialId);
  }
  if (redirectUri) {
    params.append('redirect_uri', redirectUri);
  }

  const queryString = params.toString();
  const url = `${getApiUrl()}${API_VERSION}/oauth/${providerSlug}/authorize${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get authorization URL');
  }

  return response.json();
}

export async function isOAuthSupported(providerSlug: string): Promise<boolean> {
  try {
    const { providers } = await getOAuthProviders();
    return providers.some(p => p.slug === providerSlug);
  } catch {
    return false;
  }
}

export interface OAuthTokenResponse {
  credential_id: string;
  provider: string;
  expires_at: string | null;
  message: string;
}

/**
 * Start OAuth flow against a tenant-owned credential. The credential must already
 * have client_id and client_secret populated; the API updates it with access_token
 * and refresh_token after authorization.
 */
export async function startOAuthFlow(
  provider: string,
  credentialId: string
): Promise<OAuthAuthorizeResponse> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
  const params = new URLSearchParams({
    credential_id: credentialId,
  });
  const url = `${getApiUrl()}${API_VERSION}/oauth/${provider}/authorize?${params.toString()}`;

  const response = await fetch(url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start OAuth flow');
  }

  return response.json();
}

export async function refreshOAuthTokens(
  provider: string,
  credentialId: string
): Promise<OAuthTokenResponse> {
  const token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
  const url = `${getApiUrl()}${API_VERSION}/oauth/${provider}/refresh/${credentialId}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to refresh OAuth tokens');
  }

  return response.json();
}
