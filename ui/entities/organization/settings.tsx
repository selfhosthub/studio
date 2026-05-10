// ui/entities/organization/settings.tsx

'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { getOrganization, updateOrganization } from '@/shared/api';
import { useUser } from '@/entities/user';

export type CardSize = 'small' | 'medium' | 'large';

interface OrgSettings {
  showThumbnails: boolean;
  resourceCardSize: CardSize;
}

interface OrgSettingsContextValue {
  settings: OrgSettings;
  loading: boolean;
  refreshSettings: () => Promise<void>;
  updateSettings: (updates: Partial<OrgSettings>) => Promise<void>;
}

const defaultSettings: OrgSettings = {
  showThumbnails: true,
  resourceCardSize: 'medium',
};

const OrgSettingsContext = createContext<OrgSettingsContextValue>({
  settings: defaultSettings,
  loading: true,
  refreshSettings: async () => {},
  updateSettings: async () => {},
});

export function OrgSettingsProvider({ children }: { children: ReactNode }) {
  const { user } = useUser();
  const [settings, setSettings] = useState<OrgSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);

  const fetchSettings = useCallback(async () => {
    if (!user?.org_id) {
      setLoading(false);
      return;
    }

    try {
      const org = await getOrganization(user.org_id);
      const generalSettings = org.settings?.general || {};

      setSettings({
        showThumbnails: generalSettings.show_thumbnails !== false,
        resourceCardSize: generalSettings.resource_card_size || 'medium',
      });
    } catch (err) {
      console.error('Failed to fetch org settings:', err);
      // Keep default settings on error
    } finally {
      setLoading(false);
    }
  }, [user?.org_id]);

  // Update settings locally and persist to API
  const handleUpdateSettings = async (updates: Partial<OrgSettings>) => {
    // Update local state immediately for responsive UI
    const newSettings = { ...settings, ...updates };
    setSettings(newSettings);

    // Persist to API if user has org_id
    if (user?.org_id) {
      try {
        await updateOrganization(user.org_id, {
          settings: {
            general: {
              show_thumbnails: newSettings.showThumbnails,
              resource_card_size: newSettings.resourceCardSize,
            },
          },
        });
      } catch (err) {
        console.error('Failed to save org settings:', err);
        // Revert on error
        setSettings(settings);
      }
    }
  };

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  return (
    <OrgSettingsContext.Provider value={{ settings, loading, refreshSettings: fetchSettings, updateSettings: handleUpdateSettings }}>
      {children}
    </OrgSettingsContext.Provider>
  );
}

export function useOrgSettings() {
  return useContext(OrgSettingsContext);
}
