// ui/shared/hooks/useApiStatus.ts

'use client';

import { useState, useEffect } from 'react';
import { type ApiStatus, getApiStatus, subscribe, ensureChecked } from '../lib/api-status';

/** Tracks API reachability. First mount triggers the singleton health check. */
export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>(getApiStatus);

  useEffect(() => {
    const unsubscribe = subscribe(setStatus);
    ensureChecked();
    return unsubscribe;
  }, []);

  return status;
}
