// ui/features/providers/components/CredentialSelector.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { getProviderCredentials, createProviderCredential, getProviders } from '@/shared/api';
import { useUser } from '@/entities/user';
import { Modal } from '@/shared/ui';
import { Plus } from 'lucide-react';

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
  const [newCredential, setNewCredential] = useState({
    name: '',
    credential_type: 'api_key' as 'api_key' | 'oauth' | 'bearer' | 'basic_auth' | 'custom',
    secret_data: '{}',
    expires_at: '',
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [useJsonMode, setUseJsonMode] = useState(false);
  const [simpleValue, setSimpleValue] = useState('');
  const [basicAuthUsername, setBasicAuthUsername] = useState('');
  const [basicAuthPassword, setBasicAuthPassword] = useState('');

  // Check if user can manage credentials
  const canManage = user?.role === 'admin' || user?.role === 'super_admin';

  // Auto-enable "show all providers" when there's a saved cross-provider credential
  // This happens when selectedProviderId is set and differs from the base providerId
  useEffect(() => {
    if (allowCrossProvider && selectedProviderId && selectedProviderId !== providerId) {
      setShowAllProviders(true);
      setInternalSelectedProvider(selectedProviderId);
    }
  }, [allowCrossProvider, selectedProviderId, providerId]);

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

  // Fetch credentials
  useEffect(() => {
    const providerToFetch = allowCrossProvider ? effectiveProviderId : providerId;
    if (!providerToFetch) {
      setCredentials([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    getProviderCredentials(providerToFetch)
      .then((creds) => {
        setCredentials(creds);
      })
      .catch((err) => {
        console.error('Failed to fetch credentials:', err);
      })
      .finally(() => setLoading(false));
  }, [providerId, effectiveProviderId, allowCrossProvider]);

  // Handle create credential
  const handleCreateCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation(); // Prevent bubbling to parent forms
    setCreateError(null);

    if (!newCredential.name.trim()) {
      setCreateError('Credential name is required');
      return;
    }

    try {
      // Parse secret_data based on mode
      let secretData = {};
      try {
        if (useJsonMode) {
          // JSON mode: parse the JSON textarea
          secretData = JSON.parse(newCredential.secret_data);
        } else {
          // Simple mode: wrap based on credential type
          const type = newCredential.credential_type;
          if (type === 'api_key') {
            secretData = { api_key: simpleValue };
          } else if (type === 'bearer' || type === 'oauth') {
            secretData = { access_token: simpleValue };
          } else if (type === 'basic_auth') {
            // Basic auth uses username/password fields
            secretData = { username: basicAuthUsername, password: basicAuthPassword };
          } else {
            // Fallback for unknown types
            secretData = { value: simpleValue };
          }
        }
      } catch (err) {
        throw new Error('Invalid JSON in secret data field');
      }

      const providerForCreate = allowCrossProvider ? effectiveProviderId : providerId;
      const created = await createProviderCredential(providerForCreate, {
        name: newCredential.name,
        credential_type: newCredential.credential_type,
        secret_data: secretData,
        expires_at: newCredential.expires_at || null,
      });

      // Add to list and select it
      setCredentials([...credentials, created]);
      onSelect(created.id);

      // Reset and close
      setNewCredential({
        name: '',
        credential_type: 'api_key',
        secret_data: '{}',
        expires_at: '',
      });
      setUseJsonMode(false);
      setSimpleValue('');
      setBasicAuthUsername('');
      setBasicAuthPassword('');
      setShowCreateModal(false);
    } catch (err: unknown) {
      console.error('Failed to create credential:', err);
      setCreateError(err instanceof Error ? err.message : 'Failed to create credential');
    }
  };

  const handleCloseCreateModal = () => {
    setShowCreateModal(false);
    setCreateError(null);
    setNewCredential({
      name: '',
      credential_type: 'api_key',
      secret_data: '{}',
      expires_at: '',
    });
    setUseJsonMode(false);
    setSimpleValue('');
    setBasicAuthUsername('');
    setBasicAuthPassword('');
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

      {/* Create Credential Modal */}
      <Modal isOpen={showCreateModal} onClose={handleCloseCreateModal} title="Create Credential" size="md">
              <form onSubmit={handleCreateCredential} autoComplete="off" data-1p-ignore="true" data-lpignore="true">
                <div className="px-4 pt-5 pb-4 sm:p-6 sm:pb-4">

                  {createError && (
                    <div className="mb-4 alert alert-error">
                      <p className="text-sm alert-error-text">{createError}</p>
                    </div>
                  )}

                  <div className="space-y-4">
                    <div>
                      <label htmlFor={`credential-name-${providerId}`} className="form-label">
                        Credential Name *
                      </label>
                      <input
                        id={`credential-name-${providerId}`}
                        type="text"
                        required
                        value={newCredential.name}
                        onChange={(e) => setNewCredential({ ...newCredential, name: e.target.value })}
                        className="form-input"
                        placeholder="e.g., Production API Key"
                        autoComplete="off"
                        data-1p-ignore="true"
                      />
                    </div>

                    <div>
                      <label htmlFor={`credential-type-${providerId}`} className="form-label">
                        Credential Type *
                      </label>
                      <select
                        id={`credential-type-${providerId}`}
                        value={newCredential.credential_type}
                        onChange={(e) => setNewCredential({ ...newCredential, credential_type: e.target.value as any })}
                        className="form-select w-full"
                      >
                        <option value="api_key">API Key</option>
                        <option value="oauth">OAuth Token</option>
                        <option value="bearer">Bearer Token</option>
                        <option value="basic_auth">Basic Auth</option>
                        <option value="custom">Custom</option>
                      </select>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label htmlFor={`credential-secret-${providerId}`} className="form-label !mb-0">
                          Secret Value *
                        </label>
                        <button
                          type="button"
                          onClick={() => setUseJsonMode(!useJsonMode)}
                          className="text-xs link"
                        >
                          {useJsonMode ? '← Simple Mode' : 'JSON Mode →'}
                        </button>
                      </div>

                      {!useJsonMode ? (
                        newCredential.credential_type === 'basic_auth' ? (
                          // Basic auth: show username and password fields
                          <div className="space-y-3">
                            <div>
                              <label htmlFor={`credential-username-${providerId}`} className="block text-xs font-medium text-muted mb-1">
                                Username
                              </label>
                              <input
                                id={`credential-username-${providerId}`}
                                type="text"
                                required
                                value={basicAuthUsername}
                                onChange={(e) => setBasicAuthUsername(e.target.value)}
                                className="form-input"
                                placeholder="Username"
                                autoComplete="off"
                              />
                            </div>
                            <div>
                              <label htmlFor={`credential-password-${providerId}`} className="block text-xs font-medium text-muted mb-1">
                                Password
                              </label>
                              <input
                                id={`credential-password-${providerId}`}
                                type="password"
                                required
                                value={basicAuthPassword}
                                onChange={(e) => setBasicAuthPassword(e.target.value)}
                                className="form-input"
                                placeholder="Password"
                                autoComplete="off"
                              />
                            </div>
                            <p className="form-helper">
                              Stored as {"{"}&#34;username&#34;: &#34;...&#34;, &#34;password&#34;: &#34;...&#34;{"}"}
                            </p>
                          </div>
                        ) : (
                          // Other types: simple value input
                          <>
                            <input
                              id={`credential-secret-${providerId}`}
                              type="text"
                              required
                              value={simpleValue}
                              onChange={(e) => setSimpleValue(e.target.value)}
                              className="form-input-mono"
                              placeholder={
                                newCredential.credential_type === 'api_key' ? 'sk-...' :
                                newCredential.credential_type === 'bearer' ? 'Bearer token' :
                                newCredential.credential_type === 'oauth' ? 'OAuth access token' :
                                'Your secret value'
                              }
                              autoComplete="off"
                            />
                            <p className="form-helper">
                              {newCredential.credential_type === 'api_key' && `Stored as {"api_key": "..."}`}
                              {newCredential.credential_type === 'bearer' && `Stored as {"access_token": "..."}`}
                              {newCredential.credential_type === 'oauth' && `Stored as {"access_token": "..."}`}
                              {newCredential.credential_type === 'custom' && 'Use JSON mode for custom structure'}
                            </p>
                          </>
                        )
                      ) : (
                        <>
                          <textarea
                            id={`credential-secret-${providerId}`}
                            required
                            rows={6}
                            value={newCredential.secret_data}
                            onChange={(e) => setNewCredential({ ...newCredential, secret_data: e.target.value })}
                            className="form-textarea font-mono text-xs"
                            placeholder={
                              newCredential.credential_type === 'api_key' ? '{"api_key": "sk-...", "api_secret": "..."}' :
                              newCredential.credential_type === 'oauth' ? '{"access_token": "...", "refresh_token": "..."}' :
                              newCredential.credential_type === 'basic_auth' ? '{"username": "...", "password": "..."}' :
                              '{"key": "value"}'
                            }
                          />
                          <p className="form-helper">
                            Advanced: Enter credential data as JSON
                          </p>
                        </>
                      )}
                    </div>

                    <div>
                      <label htmlFor={`credential-expires-${providerId}`} className="form-label">
                        Expiration Date (optional)
                      </label>
                      <input
                        id={`credential-expires-${providerId}`}
                        type="datetime-local"
                        value={newCredential.expires_at}
                        onChange={(e) => setNewCredential({ ...newCredential, expires_at: e.target.value })}
                        className="form-input"
                      />
                    </div>
                  </div>
                </div>

                <div className="card-footer sm:flex sm:flex-row-reverse">
                  <button
                    type="submit"
                    className="btn-primary w-full sm:ml-3 sm:w-auto"
                  >
                    Create Credential
                  </button>
                  <button
                    type="button"
                    onClick={handleCloseCreateModal}
                    className="btn-secondary w-full mt-3 sm:mt-0 sm:ml-3 sm:w-auto"
                  >
                    Cancel
                  </button>
                </div>
              </form>
      </Modal>
    </>
  );
}
