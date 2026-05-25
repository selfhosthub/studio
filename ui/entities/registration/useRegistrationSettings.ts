// ui/entities/registration/useRegistrationSettings.ts

'use client';

import { useState, useEffect } from 'react';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { getPublicRegistrationSettings } from '@/shared/api';

interface RegistrationSettings {
  allowRegistration: boolean;
}

export function useRegistrationSettings() {
  const apiStatus = useApiStatus();
  const [settings, setSettings] = useState<RegistrationSettings>({ allowRegistration: false });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (apiStatus !== 'up') return;

    const fetchSettings = async () => {
      try {
        const data = await getPublicRegistrationSettings();
        setSettings({ allowRegistration: data.allow_registration ?? true });
      } catch {
        // Silently fail - API may be unreachable
      } finally {
        setIsLoading(false);
      }
    };
    fetchSettings();
  }, [apiStatus]);

  return { ...settings, isLoading };
}
