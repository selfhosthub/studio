// ui/app/organization/manage/settings/page.tsx

'use client';

import { useState, useEffect } from 'react';
import { Settings, Image, LayoutGrid } from 'lucide-react';
import { getOrganization, updateOrganization } from '@/shared/api';
import { useUser } from '@/entities/user';
import { useOrgSettings, CardSize } from '@/entities/organization';
import { useToast } from '@/features/toast';

export default function OrganizationSettingsPage() {
  const { user } = useUser();
  const { refreshSettings } = useOrgSettings();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [organization, setOrganization] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Settings form state
  const [showThumbnails, setShowThumbnails] = useState(true);
  const [resourceCardSize, setResourceCardSize] = useState<CardSize>('medium');

  useEffect(() => {
    async function fetchOrganization() {
      if (!user?.org_id) return;

      try {
        setLoading(true);
        const org = await getOrganization(user.org_id);
        setOrganization(org);

        // Load settings from organization
        const generalSettings = org.settings?.general || {};
        setShowThumbnails(generalSettings.show_thumbnails !== false); // Default true
        setResourceCardSize(generalSettings.resource_card_size || 'medium');

        setError(null);
      } catch (err) {
        console.error('Failed to fetch organization:', err);
        setError(err instanceof Error ? err.message : 'Failed to load organization');
      } finally {
        setLoading(false);
      }
    }

    fetchOrganization();
  }, [user?.org_id]);

  const handleSave = async () => {
    if (!user?.org_id || !organization) return;

    try {
      setSaving(true);
      setError(null);

      // Merge into existing settings, preserving branding and other settings
      const updatedSettings = {
        ...organization.settings,
        general: {
          ...organization.settings?.general,
          show_thumbnails: showThumbnails,
          resource_card_size: resourceCardSize,
        }
      };

      const updated = await updateOrganization(user.org_id, {
        settings: updatedSettings,
      });

      setOrganization(updated);
      toast({ title: 'Settings saved successfully', variant: 'success' });

      // Refresh the global org settings context
      await refreshSettings();
    } catch (err) {
      console.error('Failed to save settings:', err);
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="spinner-lg"></div>
      </div>
    );
  }

  if (error && !organization) {
    return (
      <div className="alert alert-error">
        <p className="text-danger">{error || 'Failed to load settings'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Error Message */}
      {error && (
        <div className="p-3 bg-danger-subtle border border-danger rounded-md">
          <p className="text-sm text-danger">{error}</p>
        </div>
      )}

      {/* Storage Settings Card */}
      <div className="bg-card rounded-lg shadow-md p-6 border border-primary">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center mr-3">
            {/* eslint-disable-next-line jsx-a11y/alt-text -- lucide-react icon, not img */}
            <Image className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-primary">
              Images & Thumbnails
            </h2>
            <p className="text-muted">
              Configure image preview and thumbnail settings
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Show Thumbnails Toggle */}
          <div className="flex items-start">
            <div className="flex items-center h-5">
              <input
                id="show_thumbnails"
                name="show_thumbnails"
                type="checkbox"
                checked={showThumbnails}
                onChange={(e) => setShowThumbnails(e.target.checked)}
                className="focus:ring-blue-500 h-4 w-4 text-info border-primary rounded"
              />
            </div>
            <div className="ml-3 text-sm">
              <label htmlFor="show_thumbnails" className="font-medium text-secondary">
                Show image thumbnails
              </label>
              <p className="text-muted">
                Display thumbnail previews for image files in resource cards.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Display Settings Card */}
      <div className="bg-card rounded-lg shadow-md p-6 border border-primary">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-info-subtle rounded-lg flex items-center justify-center mr-3">
            <LayoutGrid className="w-5 h-5 text-info" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-primary">
              Display Settings
            </h2>
            <p className="text-muted">
              Customize how content is displayed
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Resource Card Size */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Resource Card Size
            </label>
            <p className="text-sm text-secondary mb-3">
              Choose the size of resource cards in the Files page and instance views.
            </p>
            <div className="flex gap-3">
              {(['small', 'medium', 'large'] as const).map((size) => (
                <button
                  key={size}
                  type="button"
                  onClick={() => setResourceCardSize(size)}
                  className={`flex-1 py-3 px-4 rounded-lg border-2 transition-all ${
                    resourceCardSize === size
                      ? 'border-info bg-info-subtle text-info'
                      : 'border-primary hover:border-primary text-secondary'
                  }`}
                >
                  <div className="text-center">
                    <div className={`mx-auto mb-2 bg-surface border border-secondary rounded ${
                      size === 'small' ? 'w-8 h-6' : size === 'medium' ? 'w-12 h-9' : 'w-16 h-12'
                    }`} />
                    <span className="text-sm font-medium capitalize">{size}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
