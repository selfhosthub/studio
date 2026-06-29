// ui/shared/lib/api-status.ts

// Module-level singleton tracking backend reachability. States: unknown → checking → up | down.
// 'up' may still be in maintenance mode. A single recovery poller refetches when the API returns.

import { getApiUrl, API_VERSION } from './config';
import { API_STATUS } from './constants';

export type ApiStatus = 'unknown' | 'checking' | 'up' | 'down';

let currentStatus: ApiStatus = 'unknown';
let recoveryTimer: ReturnType<typeof setInterval> | null = null;
let checkStarted = false;

const listeners = new Set<(status: ApiStatus) => void>();

const RECOVERY_POLL_MS = API_STATUS.RECOVERY_POLL_MS;
const CHECK_TIMEOUT_MS = API_STATUS.CHECK_TIMEOUT_MS;
const HEALTH_PATH = `${API_VERSION}/public/maintenance`;

export function getApiStatus(): ApiStatus {
  return currentStatus;
}

export function subscribe(fn: (status: ApiStatus) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function markApiUp() {
  stopRecoveryPoller();
  setStatus('up');
}

export function markApiDown() {
  setStatus('down');
  startRecoveryPoller();
}

/** Idempotent. Skips if a hook has already pushed status via markApiUp/Down. */
export async function ensureChecked(): Promise<void> {
  if (checkStarted || currentStatus !== 'unknown') return;
  if (typeof window === 'undefined') return;

  checkStarted = true;
  setStatus('checking');

  try {
    const response = await fetch(`${getApiUrl()}${HEALTH_PATH}`, {
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
    // Any HTTP response - including 4xx/5xx - means the process is alive.
    if (response) markApiUp();
  } catch {
    markApiDown();
  }
}

function setStatus(next: ApiStatus) {
  if (currentStatus === next) return;
  currentStatus = next;
  listeners.forEach(fn => fn(next));
}

function startRecoveryPoller() {
  if (recoveryTimer || typeof window === 'undefined') return;

  recoveryTimer = setInterval(async () => {
    try {
      const response = await fetch(`${getApiUrl()}${HEALTH_PATH}`, {
        signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
      });
      if (response) markApiUp();
    } catch {
      // still unreachable
    }
  }, RECOVERY_POLL_MS);
}

function stopRecoveryPoller() {
  if (recoveryTimer) {
    clearInterval(recoveryTimer);
    recoveryTimer = null;
  }
}
