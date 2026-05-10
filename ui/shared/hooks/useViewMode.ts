// ui/shared/hooks/useViewMode.ts

'use client';

import { useSyncExternalStore, useCallback } from 'react';
import { STORAGE_KEYS } from '@/shared/lib/constants';
import { INSTANCE_DEFAULTS } from '@/shared/defaults';

const STORAGE_KEY = STORAGE_KEYS.INSTANCE_VIEW_MODE;
const DEFAULT_SIMPLE = INSTANCE_DEFAULTS.simpleMode;

function readStored(): boolean {
  if (typeof window === 'undefined') return DEFAULT_SIMPLE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'simple') return true;
  if (stored === 'technical') return false;
  return DEFAULT_SIMPLE;
}

function subscribe(callback: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener('storage', callback);
  return () => window.removeEventListener('storage', callback);
}

/**
 * Persists the user's instance-view preference (simple vs technical) across
 * sessions via localStorage. Default is simple - technical is opt-in.
 *
 * Uses `useSyncExternalStore` (the React 18 idiom for external stores) so
 * the stored value is read synchronously as the initial state - no
 * setState-in-effect cascade. Cross-tab updates flow through the native
 * `storage` event; same-tab updates dispatch a synthetic `storage` event
 * from the setters so listeners re-render immediately.
 */
export function useViewMode(): { simpleMode: boolean; toggleSimpleMode: () => void; setSimpleMode: (v: boolean) => void } {
  const simpleMode = useSyncExternalStore(
    subscribe,
    readStored,
    () => DEFAULT_SIMPLE, // SSR snapshot - hydrates consistently before the first client render.
  );

  const setSimpleMode = useCallback((v: boolean) => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, v ? 'simple' : 'technical');
    window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY }));
  }, []);

  const toggleSimpleMode = useCallback(() => {
    setSimpleMode(!readStored());
  }, [setSimpleMode]);

  return { simpleMode, toggleSimpleMode, setSimpleMode };
}
