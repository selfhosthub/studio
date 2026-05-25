// ui/app/providers/[providerId]/edit/page.tsx

"use client";

import React, { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/widgets/layout';
import { getProvider, updateProvider, getProviderPackageDefaults } from '@/shared/api';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { ChevronDown, ChevronRight } from 'lucide-react';

// Collapsible Section Component
function CollapsibleSection({
  title,
  description,
  isExpanded,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface hover:bg-card transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-secondary" />
          ) : (
            <ChevronRight className="h-4 w-4 text-secondary" />
          )}
          <span className="text-sm font-medium text-primary">{title}</span>
          {description && (
            <span className="text-muted text-xs">- {description}</span>
          )}
        </div>
      </button>
      {isExpanded && (
        <div className="px-4 py-4 bg-card">
          {children}
        </div>
      )}
    </div>
  );
}

export default function EditProviderPage({
  params
}: {
  params: Promise<{ providerId: string }>
}) {
  const { providerId } = use(params);
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<any>(null);

  // Collapsible section states
  const [configExpanded, setConfigExpanded] = useState(false);
  const [capabilitiesExpanded, setCapabilitiesExpanded] = useState(false);
  const [metadataExpanded, setMetadataExpanded] = useState(false);

  // Reset to defaults state
  const [resetting, setResetting] = useState(false);

  const isSuperAdmin = user?.role === 'super_admin';

  const [formData, setFormData] = useState({
    name: '',
    provider_type: 'api' as string,
    description: '',
    endpoint_url: '',
    config: '{}',
    capabilities: '{}',
    client_metadata: '{}',
    status: 'active' as string,
  });

  useEffect(() => {
    async function fetchProvider() {
      try {
        setLoading(true);
        const providerData = await getProvider(providerId);
        setProvider(providerData);

        // Populate form with existing data
        setFormData({
          name: providerData.name || '',
          provider_type: providerData.provider_type || 'api',
          description: providerData.description || '',
          endpoint_url: providerData.endpoint_url || '',
          config: JSON.stringify(providerData.config || {}, null, 2),
          capabilities: JSON.stringify(providerData.capabilities || {}, null, 2),
          client_metadata: JSON.stringify(providerData.client_metadata || {}, null, 2),
          status: providerData.status || 'active',
        });

        setError(null);
      } catch (err: unknown) {
        console.error('Failed to load provider:', err);
        let errorMessage = 'Failed to load provider';

        if (err instanceof Error) {
          errorMessage = err.message;
        } else if (typeof err === 'string') {
          errorMessage = err;
        } else if (typeof err === 'object' && err !== null && 'detail' in err) {
          errorMessage = String((err as { detail: string }).detail);
        }

        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    }

    fetchProvider();
  }, [providerId]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Confirm system-wide change for super_admin
    if (isSuperAdmin) {
      const confirmed = window.confirm(
        '⚠️ WARNING: System-Wide Change\n\n' +
        'This provider configuration is shared across ALL organizations.\n\n' +
        'Any changes you make will immediately affect all users and workflows using this provider.\n\n' +
        'Are you sure you want to save these changes?'
      );

      if (!confirmed) {
        return;
      }
    }

    setSaving(true);
    setError(null);

    try {
      // Parse JSON fields
      let config = {};
      let capabilities = {};
      let client_metadata = {};

      try {
        if (formData.config.trim()) {
          config = JSON.parse(formData.config);
        }
      } catch (err) {
        throw new Error('Invalid JSON in config field');
      }

      try {
        if (formData.capabilities.trim()) {
          capabilities = JSON.parse(formData.capabilities);
        }
      } catch (err) {
        throw new Error('Invalid JSON in capabilities field');
      }

      try {
        if (formData.client_metadata.trim()) {
          client_metadata = JSON.parse(formData.client_metadata);
        }
      } catch (err) {
        throw new Error('Invalid JSON in client metadata field');
      }

      await updateProvider(providerId, {
        name: formData.name,
        description: formData.description || null,
        endpoint_url: formData.endpoint_url || null,
        config: Object.keys(config).length > 0 ? config : undefined,
        capabilities: Object.keys(capabilities).length > 0 ? capabilities : undefined,
        client_metadata: Object.keys(client_metadata).length > 0 ? client_metadata : undefined,
        status: formData.status,
      });

      toast({ title: 'Provider updated', description: 'Provider updated successfully!', variant: 'success' });
      router.push(`/providers/${providerId}`);
    } catch (err: unknown) {
      console.error('Failed to update provider:', err);
      let errorMessage = 'Failed to update provider';

      if (err instanceof Error) {
        errorMessage = err.message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      } else if (typeof err === 'object' && err !== null && 'detail' in err) {
        errorMessage = String((err as { detail: string }).detail);
      }

      setError(errorMessage);
      setSaving(false);
    }
  };

  // Reset form to package defaults (reads original values from disk)
  const handleResetToDefaults = async () => {
    // Confirm with warning about system-wide impact
    const confirmed = window.confirm(
      '⚠️ Reset to Package Defaults\n\n' +
      'This will reset the form to the original values from the provider package.\n\n' +
      'Note: This only updates the form. You must click "Save Changes" to apply the reset, ' +
      'which will affect ALL organizations using this provider.\n\n' +
      'Continue?'
    );

    if (!confirmed) {
      return;
    }

    setResetting(true);
    setError(null);

    try {
      const defaults = await getProviderPackageDefaults(providerId);

      setFormData({
        name: defaults.name || formData.name,
        provider_type: (defaults.provider_type || formData.provider_type) as 'api' | 'infrastructure' | 'hybrid' | 'internal',
        description: defaults.description || '',
        endpoint_url: defaults.endpoint_url || '',
        config: JSON.stringify(defaults.config || {}, null, 2),
        capabilities: JSON.stringify(defaults.capabilities || {}, null, 2),
        client_metadata: JSON.stringify(defaults.client_metadata || {}, null, 2),
        status: formData.status, // Keep current status
      });

      toast({ title: 'Form reset', description: 'Reset to package defaults. Click "Save Changes" to apply.', variant: 'default' });
    } catch (err: unknown) {
      console.error('Failed to fetch package defaults:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch package defaults. The package files may not be available.');
    } finally {
      setResetting(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="spinner-lg"></div>
              <p className="mt-4 text-muted">Loading provider...</p>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error && !provider) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
          <div className="alert alert-error">
            <h1 className="text-2xl font-bold mb-2">Error</h1>
            <p>{error}</p>
            <button
              onClick={() => router.push('/providers/list')}
              className="link mt-4"
            >
              Back to providers list
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-primary">
            Edit Provider: {provider?.name}
          </h1>
          <p className="text-sm mt-1 text-secondary">
            Update provider configuration and settings
          </p>
        </div>

        {/* System-wide warning banner */}
        {isSuperAdmin && (
          <div className="mb-6 alert alert-warning">
            <div className="flex items-start gap-3">
              <svg className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <h3 className="text-sm font-semibold">
                  System-Wide Configuration
                </h3>
                <p className="text-sm mt-1">
                  This provider is shared across <strong>all organizations</strong>. Changes will immediately affect all users and workflows using this provider.
                </p>
              </div>
            </div>
          </div>
        )}

        {!isSuperAdmin && (
          <div className="mb-6 alert alert-info">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-info" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm">
                  You are viewing provider configuration in read-only mode. Only super administrators can edit provider settings.
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 alert alert-error">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm">{error}</p>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="card">
          <div className="space-y-6">
            {/* ===== BASIC INFO SECTION (Always Visible) ===== */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-primary uppercase tracking-wide">
                Basic Information
              </h3>

              {/* Name */}
              <div>
                <label htmlFor="name" className="form-label">
                  Provider Name *
                </label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  required
                  value={formData.name}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-input disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              {/* Status */}
              <div>
                <label htmlFor="status" className="form-label">
                  Status
                </label>
                <select
                  id="status"
                  name="status"
                  value={formData.status}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-select w-full disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="form-label">
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={2}
                  value={formData.description}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-textarea disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              {/* Endpoint URL */}
              <div>
                <label htmlFor="endpoint_url" className="form-label">
                  Endpoint URL
                </label>
                <input
                  type="url"
                  id="endpoint_url"
                  name="endpoint_url"
                  value={formData.endpoint_url}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-input disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>
            </div>

            {/* ===== COLLAPSIBLE SECTIONS ===== */}
            <div className="space-y-3 pt-4 border-t border-primary">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-primary uppercase tracking-wide">
                  Advanced Configuration
                </h3>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs text-warning">
                    <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span>These settings are managed by the provider package. Edit with caution.</span>
                  </div>
                  {isSuperAdmin && (
                    <button
                      type="button"
                      onClick={handleResetToDefaults}
                      disabled={resetting}
                      className="text-xs text-info hover:text-info dark:hover:text-info hover:underline disabled:opacity-50"
                    >
                      {resetting ? 'Loading defaults...' : 'Reset to Package Defaults'}
                    </button>
                  )}
                </div>
              </div>

              {/* Config (Collapsible) */}
              <CollapsibleSection
                title="Configuration"
                description="Provider-specific settings"
                isExpanded={configExpanded}
                onToggle={() => setConfigExpanded(!configExpanded)}
              >
                <textarea
                  id="config"
                  name="config"
                  rows={10}
                  value={formData.config}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-textarea font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"key": "value"}'
                />
              </CollapsibleSection>

              {/* Capabilities (Collapsible) */}
              <CollapsibleSection
                title="Capabilities"
                description="What the provider supports"
                isExpanded={capabilitiesExpanded}
                onToggle={() => setCapabilitiesExpanded(!capabilitiesExpanded)}
              >
                <textarea
                  id="capabilities"
                  name="capabilities"
                  rows={10}
                  value={formData.capabilities}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-textarea font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"feature": true}'
                />
              </CollapsibleSection>

              {/* Client Metadata (Collapsible) */}
              <CollapsibleSection
                title="Client Metadata"
                description="Credential schema, marketplace info, adapter settings"
                isExpanded={metadataExpanded}
                onToggle={() => setMetadataExpanded(!metadataExpanded)}
              >
                <textarea
                  id="client_metadata"
                  name="client_metadata"
                  rows={12}
                  value={formData.client_metadata}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="form-textarea font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"credential_schema": {...}}'
                />
              </CollapsibleSection>
            </div>
          </div>

          {/* Form Actions */}
          {isSuperAdmin && (
            <div className="mt-8 flex items-center justify-end space-x-4">
              <button
                type="button"
                onClick={() => router.push(`/providers/${providerId}`)}
                disabled={saving}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="btn-primary"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}

          {!isSuperAdmin && (
            <div className="mt-8 flex items-center justify-end">
              <button
                type="button"
                onClick={() => router.push(`/providers/${providerId}`)}
                className="btn-secondary"
              >
                Back to Provider
              </button>
            </div>
          )}
        </form>
      </div>
    </DashboardLayout>
  );
}
