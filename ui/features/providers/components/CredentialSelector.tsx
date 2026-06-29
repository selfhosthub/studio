// ui/features/providers/components/CredentialSelector.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { getProviderCredentials, getProviders } from '@/shared/api';
import { useUser } from '@/entities/user';
import { Plus } from 'lucide-react';
import { CreateCredentialModal } from './CreateCredentialModal';
import type { Credential } from '../credential-types';

interface CredentialSelectorProps {
  providerId: string;
  selectedCredentialId?: string;
  onSelect: (credentialId: string | null) => void;
  label?: string;
  required?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  /** Allow selecting credentials from any provider (for services like Poll Service that make external API calls) */
  allowCrossProvider?: boolean;
  /** Optional callback when provider changes in cross-provider mode */
  onProviderChange?: (providerId: string) => void;
  /** Selected provider ID in cross-provider mode (controlled externally) */
  selectedProviderId?: string;
}

export default function CredentialSelector({
  providerId,
  selectedCredentialId,
  onSelect,
  label = 'Credential',
  required = false,
  disabled = false,
  disabledReason,
  allowCrossProvider = false,
  onProviderChange,
  selectedProviderId,
}: CredentialSelectorProps) {
  const { user } = useUser();
  const [credentials, setCredentials] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [allProviders, setAllProviders] = useState<any[]>([]);
  // Initialize with selectedProviderId if it differs from base providerId (cross-provider credential exists)
  const [internalSelectedProvider, setInternalSelectedProvider] = useState<string>(selectedProviderId || '');
  // Auto-show all providers when cross-provider is allowed (Core services always need external credentials)
  const [showAllProviders, setShowAllProviders] = useState(allowCrossProvider);

  // Effective provider ID for fetching credentials
  // In cross-provider mode:
  // - If "show all" is enabled, use the selected provider (controlled or internal)
  // - Otherwise use the base providerId
  const effectiveProviderId = allowCrossProvider
    ? (showAllProviders
        ? (selectedProviderId || internalSelectedProvider || providerId)
        : providerId)
    : providerId;
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Check if user can manage credentials
  const canManage = user?.role === 'admin' || user?.role === 'super_admin';

  // Auto-enable "show all providers" when there's a saved cross-provider credential
  // (Pattern C: adjust during render keyed on the composite trigger — fires same times as the old effect)
  const crossProviderKey = `${String(allowCrossProvider)}|${selectedProviderId ?? ''}|${providerId}`;
  const [prevCrossProviderKey, setPrevCrossProviderKey] = useState(crossProviderKey);
  if (crossProviderKey !== prevCrossProviderKey) {
    setPrevCrossProviderKey(crossProviderKey);
    if (allowCrossProvider && selectedProviderId && selectedProviderId !== providerId) {
      setShowAllProviders(true);
      setInternalSelectedProvider(selectedProviderId);
    }
  }

  // Fetch all providers when in cross-provider mode
  useEffect(() => {
    if (!allowCrossProvider) return;

    const fetchProviders = async () => {
      try {
        const providers = await getProviders();
        // Filter to only providers that have credentials
        // credential_schema is stored inside client_metadata
        const providersWithCredentials = providers.filter((p: any) => {
          const credSchema = p.client_metadata?.credential_schema || p.credential_schema;
          // Has a non-empty credential schema
          return credSchema && Object.keys(credSchema).length > 0;
        });
        setAllProviders(providersWithCredentials);
      } catch (err) {
        console.error('Failed to fetch providers:', err);
      }
    };
    fetchProviders();
  }, [allowCrossProvider]);

  // Fetch credentials (Pattern A: async IIFE so deferred setState isn't read as synchronous)
  useEffect(() => {
    void (async () => {
      const providerToFetch = allowCrossProvider ? effectiveProviderId : providerId;
      if (!providerToFetch) {
        setCredentials([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const creds = await getProviderCredentials(providerToFetch);
        setCredentials(creds);
      } catch (err) {
        console.error('Failed to fetch credentials:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [providerId, effectiveProviderId, allowCrossProvider]);

  // Add the newly created credential to the list and select it.
  const handleCredentialCreated = (created: Credential) => {
    setCredentials((prev) => [...prev, created]);
    onSelect(created.id);
  };

  if (loading) {
    return (
      <div className="space-y-2">
        <label className="form-label">
          {label} {required && <span className="text-danger">*</span>}
        </label>
        <div className="text-sm text-muted">Loading credentials...</div>
      </div>
    );
  }

  // Handle provider change in cross-provider mode
  const handleProviderChange = (newProviderId: string) => {
    setInternalSelectedProvider(newProviderId);
    // Clear credential selection when provider changes
    onSelect(null);
    // Notify parent if callback provided
    onProviderChange?.(newProviderId);
  };

  return (
    <>
      <div className="space-y-2">
        <label htmlFor={`credential-select-${providerId}`} className="form-label">
          {label} {required && <span className="text-danger">*</span>}
        </label>

        {/* Cross-provider mode: Show checkbox to enable selecting from other providers */}
        {allowCrossProvider && (
          <div className="space-y-2">
            {/* Provider picker - only shown when "show all" is checked */}
            {showAllProviders && (
              <div>
                <label htmlFor={`credential-provider-${providerId}`} className="block text-xs font-medium text-muted mb-1">
                  Select Provider
                </label>
                <select
                  id={`credential-provider-${providerId}`}
                  value={effectiveProviderId}
                  onChange={(e) => handleProviderChange(e.target.value)}
                  className="form-select w-full"
                >
                  <option value="">Choose a provider...</option>
                  {allProviders.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        <div className="flex space-x-2">
          <select
            id={`credential-select-${providerId}`}
            value={selectedCredentialId || ''}
            onChange={(e) => onSelect(e.target.value || null)}
            className={`form-select flex-1${disabled || (showAllProviders && !effectiveProviderId) ? ' opacity-50 cursor-not-allowed' : ''}`}
            required={required}
            disabled={disabled || (showAllProviders && !effectiveProviderId)}
          >
            <option value="">{showAllProviders && !effectiveProviderId ? 'Select provider first...' : 'Select credential...'}</option>
            {credentials
              .filter((c) => c.is_active && (!c.expires_at || new Date(c.expires_at) > new Date()))
              .map((cred) => (
                <option key={cred.id} value={cred.id}>
                  {cred.name}
                  {cred.expires_at && ` (expires ${new Date(cred.expires_at).toLocaleDateString()})`}
                </option>
              ))}
          </select>
          {canManage && effectiveProviderId && (
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className={`btn-secondary btn-icon${disabled ? ' opacity-50 cursor-not-allowed' : ''}`}
              title="Create new credential"
              disabled={disabled}
            >
              <Plus size={16} />
            </button>
          )}
        </div>

        {/* Cross-provider toggle - shown below the credential selector */}
        {allowCrossProvider && (
          <label className="flex items-center gap-2 text-xs text-muted cursor-pointer mt-1">
            <input
              type="checkbox"
              checked={showAllProviders}
              onChange={(e) => {
                setShowAllProviders(e.target.checked);
                if (!e.target.checked) {
                  // Reset to original provider when unchecking
                  setInternalSelectedProvider('');
                  onSelect(null);
                  // Clear the saved credential provider
                  onProviderChange?.('');
                }
              }}
              className="form-checkbox"
            />
            Show credentials from all providers
          </label>
        )}

        {disabled && disabledReason && (
          <p className="text-sm text-muted">
            {disabledReason}
          </p>
        )}
        {!disabled && credentials.length === 0 && effectiveProviderId && (
          <p className="text-sm text-muted">
            No credentials available. {canManage && 'Click + to create one.'}
          </p>
        )}
      </div>

      {/* Schema-aware create modal (OAuth providers deep-link to their secrets page). */}
      <CreateCredentialModal
        providerId={effectiveProviderId}
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleCredentialCreated}
      />
    </>
  );
}
