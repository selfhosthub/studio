// ui/app/secrets/[id]/edit/page.tsx

'use client';

import { DashboardLayout } from '@/widgets/layout';
import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { getOrganizationSecret, updateOrganizationSecret, deleteOrganizationSecret } from '@/shared/api';
import { useToast } from '@/features/toast';
import { ArrowLeft, Trash2, Lock, Eye, EyeOff, Copy, Check } from 'lucide-react';
import Link from 'next/link';
import { LinkedText } from '@/shared/ui';
import { TIMEOUTS } from '@/shared/lib/constants';

interface SecretData {
  id: string;
  name: string;
  secret_type: string;
  description?: string;
  secret_data?: Record<string, unknown>;
  is_active: boolean;
  is_protected?: boolean;
  expires_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export default function EditSecretPage() {
  const router = useRouter();
  const params = useParams();
  const { toast } = useToast();
  const secretId = params.id as string;

  const [loading, setLoading] = useState(true);
  const [secret, setSecret] = useState<SecretData | null>(null);
  const [secretType, setSecretType] = useState<string>('');
  const [isActive, setIsActive] = useState(true);
  const [expiresAt, setExpiresAt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [useJsonMode, setUseJsonMode] = useState(false);
  const [simpleValue, setSimpleValue] = useState('');
  const [secretData, setSecretData] = useState('{}');

  // Track if the secret has a value and if user is editing it
  const [hasExistingValue, setHasExistingValue] = useState(false);
  const [isEditingValue, setIsEditingValue] = useState(false);
  // Track reveal state and actual secret value
  const [showSecretValue, setShowSecretValue] = useState(false);
  const [actualSecretValue, setActualSecretValue] = useState<string | null>(null);
  const [copiedSecret, setCopiedSecret] = useState(false);

  useEffect(() => {
    const fetchSecret = async () => {
      try {
        setLoading(true);
        const data = await getOrganizationSecret(secretId);
        setSecret(data);
        setSecretType(data.secret_type);
        setIsActive(data.is_active);
        setExpiresAt(data.expires_at ? data.expires_at.slice(0, 16) : '');

        // Set secret data based on structure
        const secretDataObj = data.secret_data || {};
        setSecretData(JSON.stringify(secretDataObj, null, 2));

        // Check if there's an existing value (non-empty)
        const existingValue = String(secretDataObj.api_key || secretDataObj.token || secretDataObj.value || '');
        setHasExistingValue(!!existingValue);
        // Store the actual secret value for reveal
        setActualSecretValue(existingValue);

        // Don't populate the value - keep it masked
        // User must explicitly click "Change" to edit
        setSimpleValue('');
        // Default to simple mode (useJsonMode is already false)
      } catch (err: unknown) {
        console.error('Failed to fetch secret:', err);
        toast({ title: 'Failed to load secret', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      } finally {
        setLoading(false);
      }
    };

    if (secretId) {
      fetchSecret();
    }
  }, [secretId, toast]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setSubmitting(true);

      // Build update payload
      // Auto-activate if user is setting/changing the secret value
      const updatePayload: any = {
        is_active: isEditingValue ? true : isActive,
        expires_at: expiresAt || null,
      };

      // Only include secret_data if user is editing the value
      if (isEditingValue) {
        if (!simpleValue && !useJsonMode) {
          throw new Error('Secret value is required');
        }

        let parsedSecretData = {};
        try {
          if (useJsonMode) {
            parsedSecretData = JSON.parse(secretData);
          } else {
            if (secretType === 'api_key') {
              parsedSecretData = { api_key: simpleValue };
            } else if (secretType === 'bearer') {
              parsedSecretData = { token: simpleValue };
            } else {
              parsedSecretData = { value: simpleValue };
            }
          }
        } catch (err) {
          throw new Error('Invalid JSON in secret data field');
        }
        updatePayload.secret_data = parsedSecretData;
      }

      await updateOrganizationSecret(secretId, updatePayload);

      toast({ title: 'Secret updated successfully', variant: 'success' });
      router.push('/secrets');
    } catch (err: unknown) {
      console.error('Failed to update secret:', err);
      toast({ title: 'Failed to update secret', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this secret? This action cannot be undone.')) {
      return;
    }

    try {
      setDeleting(true);
      await deleteOrganizationSecret(secretId);
      router.push('/secrets');
    } catch (err: unknown) {
      console.error('Failed to delete secret:', err);
      toast({ title: 'Failed to delete secret', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-muted">Loading...</div>
        </div>
      </DashboardLayout>
    );
  }

  if (!secret) {
    return (
      <DashboardLayout>
        <div className="px-4 py-6 sm:px-6 lg:px-8">
          <div className="text-center">
            <h2 className="text-lg font-medium text-primary">Secret not found</h2>
            <Link href="/secrets" className="mt-4 text-info hover:text-info">
              Back to Secrets
            </Link>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8 w-full max-w-4xl mx-auto">
        <div className="mb-6">
          <Link
            href="/secrets"
            className="inline-flex items-center text-sm text-secondary hover:text-secondary"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Secrets
          </Link>
        </div>

        <div className="bg-card shadow rounded-lg border border-primary">
          <div className="px-6 py-4 border-b border-primary flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-semibold text-primary">
                  Edit Secret
                </h1>
                {secret.is_protected && (
                  <span title="Protected - cannot be deleted">
                    <Lock className="h-5 w-5 text-warning" />
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-secondary">
                Update the secret value and settings
              </p>
              {secret.description && (
                <p className="mt-2 text-sm text-secondary">
                  <LinkedText text={secret.description} />
                </p>
              )}
            </div>
            {!secret.is_protected && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center px-3 py-1.5 border border-danger rounded-md text-sm font-medium text-danger bg-card hover:bg-danger-subtle"
              >
                <Trash2 className="mr-1.5 h-4 w-4" />
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            )}
          </div>

          <form onSubmit={handleSubmit} className="px-6 py-4">
            <div className="space-y-4">
              <div>
                <label htmlFor="secret-name" className="block text-sm font-medium text-secondary mb-1">
                  Secret Name
                </label>
                <input
                  id="secret-name"
                  type="text"
                  disabled
                  value={secret.name}
                  className="w-full rounded-md border-primary bg-card text-secondary sm:text-sm px-3 py-2 cursor-not-allowed"
                />
                <p className="mt-1 text-xs text-secondary">
                  Secret name cannot be changed after creation
                </p>
              </div>

              <div>
                <label htmlFor="secret-type" className="block text-sm font-medium text-secondary mb-1">
                  Secret Type
                </label>
                <input
                  id="secret-type"
                  type="text"
                  disabled
                  value={secretType}
                  className="w-full rounded-md border-primary bg-card text-secondary sm:text-sm px-3 py-2 cursor-not-allowed"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="secret-value" className="form-label">
                    Secret Value {isEditingValue && <span className="text-danger">*</span>}
                  </label>
                  {isEditingValue && (
                    <button
                      type="button"
                      onClick={() => setUseJsonMode(!useJsonMode)}
                      className="text-xs text-info hover:text-info"
                    >
                      {useJsonMode ? '← Simple Mode' : 'JSON Mode →'}
                    </button>
                  )}
                </div>

                {/* Show masked value if not editing */}
                {!isEditingValue ? (
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0 rounded-md border border-primary bg-surface px-3 py-2 overflow-x-auto">
                      <span className="font-mono text-sm text-secondary break-all">
                        {hasExistingValue
                          ? (showSecretValue && actualSecretValue
                              ? actualSecretValue
                              : '••••••••••••••••')
                          : '(not set)'}
                      </span>
                    </div>
                    {/* Reveal button */}
                    {hasExistingValue && (
                      <button
                        type="button"
                        onClick={() => setShowSecretValue(!showSecretValue)}
                        className="p-2 text-secondary hover:text-secondary border border-primary rounded-md hover:bg-surface"
                        title={showSecretValue ? 'Hide secret' : 'Show secret'}
                      >
                        {showSecretValue ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    )}
                    {/* Copy button */}
                    {hasExistingValue && actualSecretValue && (
                      <button
                        type="button"
                        onClick={() => {
                          if (actualSecretValue) {
                            navigator.clipboard.writeText(actualSecretValue);
                            setCopiedSecret(true);
                            setTimeout(() => setCopiedSecret(false), TIMEOUTS.COPY_FEEDBACK);
                          }
                        }}
                        className="p-2 text-secondary hover:text-secondary border border-primary rounded-md hover:bg-surface"
                        title="Copy to clipboard"
                      >
                        {copiedSecret ? <Check size={18} className="text-success" /> : <Copy size={18} />}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setIsEditingValue(true)}
                      className="px-3 py-2 text-sm font-medium text-info hover:text-info border border-info  rounded-md hover:bg-info-subtle"
                    >
                      {hasExistingValue ? 'Change' : 'Set Value'}
                    </button>
                  </div>
                ) : !useJsonMode ? (
                  <>
                    <div className="flex items-center gap-2">
                      <input
                        id="secret-value"
                        type="text"
                        required
                        value={simpleValue}
                        onChange={(e) => setSimpleValue(e.target.value)}
                        className="flex-1 rounded-md border border-primary shadow-sm focus:border-info focus:ring-blue-500 bg-surface sm:text-sm px-3 py-2 font-mono"
                        placeholder={
                          secretType === 'api_key' ? 'sk-...' :
                          secretType === 'bearer' ? 'ghp_... or token value' :
                          'Your secret value'
                        }
                        autoFocus
                      />
                      {hasExistingValue && (
                        <button
                          type="button"
                          onClick={() => {
                            setIsEditingValue(false);
                            setSimpleValue('');
                          }}
                          className="px-3 py-2 text-sm text-secondary hover:text-secondary"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-secondary">
                      {secretType === 'api_key' && `Stored as {"api_key": "..."}`}
                      {secretType === 'bearer' && `Stored as {"token": "..."}`}
                      {secretType === 'custom' && 'Use JSON mode for custom structure'}
                    </p>
                  </>
                ) : (
                  <>
                    <div className="flex flex-col gap-2">
                      <textarea
                        id="secret-value"
                        required
                        rows={8}
                        value={secretData}
                        onChange={(e) => setSecretData(e.target.value)}
                        className="w-full rounded-md border border-primary shadow-sm focus:border-info focus:ring-blue-500 bg-surface sm:text-sm px-3 py-2 font-mono text-xs"
                        placeholder='{"key": "value"}'
                        autoFocus
                      />
                      {hasExistingValue && (
                        <button
                          type="button"
                          onClick={() => {
                            setIsEditingValue(false);
                            setUseJsonMode(false);
                          }}
                          className="self-end px-3 py-1 text-sm text-secondary hover:text-secondary"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-secondary">
                      Advanced: Edit secret as JSON
                    </p>
                  </>
                )}
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="h-4 w-4 rounded border-primary text-info focus:ring-blue-500"
                />
                <label htmlFor="is_active" className="ml-2 block text-sm text-secondary">
                  Active
                </label>
              </div>

              <div>
                <label htmlFor="secret-expires-at" className="block text-sm font-medium text-secondary mb-1">
                  Expiration Date (optional)
                </label>
                <input
                  id="secret-expires-at"
                  type="datetime-local"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className="w-full rounded-md border border-primary shadow-sm focus:border-info focus:ring-blue-500 bg-surface sm:text-sm px-3 py-2"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <Link
                href="/secrets"
                className="px-4 py-2 border border-primary rounded-md shadow-sm text-sm font-medium text-secondary bg-card hover:bg-surface"
              >
                Cancel
              </Link>
              <button
                type="submit"
                disabled={submitting}
                className="btn-primary"
              >
                {submitting ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
