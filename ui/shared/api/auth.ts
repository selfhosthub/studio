// ui/shared/api/auth.ts

import type { User } from '@/shared/types/user';
import { getApiUrl, API_VERSION } from '@/shared/lib/config';

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
  const token = localStorage.getItem('token');
  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

export function getRefreshToken(): string | null {
  return localStorage.getItem('refreshToken');
}

export function clearAuth(): void {
  localStorage.removeItem('token');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('workflowUser');
}

export function storeAuth(accessToken: string, refreshToken?: string): void {
  localStorage.setItem('token', accessToken);
  if (refreshToken) {
    localStorage.setItem('refreshToken', refreshToken);
  }

  try {
    const user = decodeToken(accessToken);
    localStorage.setItem('workflowUser', JSON.stringify(user));
  } catch {
    // Token couldn't be decoded; skip caching the user.
  }
}

export function decodeToken(token: string): User {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid token format');
    }

    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const claims = JSON.parse(decoded);

    return {
      id: claims.sub,
      username: claims.username,
      email: claims.email,
      role: claims.role,
      org_id: claims.org_id,
      org_slug: claims.org_slug,
      first_name: claims.first_name,
      last_name: claims.last_name,
    };
  } catch {
    throw new Error('Invalid token');
  }
}

export function getCurrentUser(): User | null {
  const token = localStorage.getItem('token');
  if (!token) {
    return null;
  }

  try {
    return decodeToken(token);
  } catch (error) {
    localStorage.removeItem('token');
    localStorage.removeItem('workflowUser');
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getCurrentUser() !== null;
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
  const token = localStorage.getItem('token');

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
  const token = localStorage.getItem('token');
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
  const token = localStorage.getItem('token');

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
  const token = localStorage.getItem('token');
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

/**
 * Platform-level OAuth flow using operator-configured app credentials (no per-tenant credential).
 */
export async function startPlatformOAuthFlow(
  oauthProvider: string,
  providerId: string,
): Promise<OAuthAuthorizeResponse> {
  const token = localStorage.getItem('token');
  const params = new URLSearchParams({ provider_id: providerId });
  const url = `${getApiUrl()}${API_VERSION}/oauth/${oauthProvider}/authorize?${params.toString()}`;

  const response = await fetch(url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start platform OAuth flow');
  }

  return response.json();
}

/**
 * Re-authorize an existing platform OAuth credential - used after provider scopes change.
 */
export async function reauthorizePlatformOAuth(
  oauthProvider: string,
  providerId: string,
  credentialId: string,
): Promise<OAuthAuthorizeResponse> {
  const token = localStorage.getItem('token');
  const params = new URLSearchParams({
    provider_id: providerId,
    reauth_credential_id: credentialId,
  });
  const url = `${getApiUrl()}${API_VERSION}/oauth/${oauthProvider}/authorize?${params.toString()}`;

  const response = await fetch(url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start re-authorization');
  }

  return response.json();
}

export async function refreshOAuthTokens(
  provider: string,
  credentialId: string
): Promise<OAuthTokenResponse> {
  const token = localStorage.getItem('token');
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
