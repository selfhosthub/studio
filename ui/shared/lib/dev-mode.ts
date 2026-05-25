// ui/shared/lib/dev-mode.ts

/**
 * Probes the API for dev mode by attempting to authenticate with the seeded test admin -
 * those credentials only exist in development/testing environments.
 */

import { getApiUrl, API_VERSION } from './config';

const DEV_TEST_CREDENTIALS = {
  email: 'admin@example.com',
  password: 'Admin123!',
} as const;

export async function isDevMode(): Promise<boolean> {
  const apiUrl = getApiUrl();

  try {
    const response = await fetch(`${apiUrl}${API_VERSION}/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        username: DEV_TEST_CREDENTIALS.email,
        password: DEV_TEST_CREDENTIALS.password,
      }),
    });

    return response.ok;
  } catch (error) {
    console.warn('Dev mode check failed - API not accessible:', error);
    return false;
  }
}

export function getTestCredentials() {
  return DEV_TEST_CREDENTIALS;
}

export async function assertDevMode(): Promise<void> {
  const devMode = await isDevMode();

  if (!devMode) {
    throw new Error(
      'Dev mode required: Test super-admin credentials (superadmin@example.com) ' +
      'are not available. Ensure SHSApi is running in development mode.'
    );
  }
}
