// ui/app/secrets/new/page.tsx

'use client';

import { DashboardLayout } from '@/widgets/layout';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createOrganizationSecret } from '@/shared/api';
import { useToast } from '@/features/toast';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function NewSecretPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [secretType, setSecretType] = useState<'bearer' | 'api_key' | 'custom'>('bearer');
  const [secretData, setSecretData] = useState('{}');
  const [expiresAt, setExpiresAt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [useJsonMode, setUseJsonMode] = useState(false);
  const [simpleValue, setSimpleValue] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast({ title: 'Secret name is required', variant: 'destructive' });
      return;
    }

    try {
      setSubmitting(true);

      // Parse secret_data based on mode
      let parsedSecretData = {};
      try {
        if (useJsonMode) {
          // JSON mode: parse the JSON textarea
          parsedSecretData = JSON.parse(secretData);
        } else {
          // Simple mode: wrap based on secret type
          if (secretType === 'api_key') {
            parsedSecretData = { api_key: simpleValue };
          } else if (secretType === 'bearer') {
            parsedSecretData = { token: simpleValue };
          } else {
            // Custom type - fallback to value
            parsedSecretData = { value: simpleValue };
          }
        }
      } catch (err) {
        throw new Error('Invalid JSON in secret data field');
      }

      await createOrganizationSecret({
        name: name.trim(),
        secret_type: secretType,
        secret_data: parsedSecretData,
        expires_at: expiresAt || null,
      });

      toast({ title: 'Secret created successfully', variant: 'success' });
      router.push('/secrets');
    } catch (err: unknown) {
      console.error('Failed to create secret:', err);
      toast({ title: 'Failed to create secret', description: err instanceof Error ? err.message : String(err), variant: 'destructive' });
      setSubmitting(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8 w-full max-w-3xl mx-auto">
        <div className="mb-6">
          <Link
            href="/secrets"
            className="link-subtle inline-flex items-center text-sm"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Secrets
          </Link>
        </div>

        <div className="infra-card">
          <div className="infra-card-header">
            <h1 className="section-title text-2xl">
              Create Organization Secret
            </h1>
            <p className="section-subtitle mt-1">
              Create a reusable secret for webhook authentication, internal APIs, and templates
            </p>
          </div>

          <form onSubmit={handleSubmit} className="infra-card-body">
            <div className="space-y-4">
              <div>
                <label htmlFor="secret-name" className="form-label">
                  Secret Name <span className="text-danger">*</span>
                  <span className="ml-2 text-xs text-muted">(immutable after creation)</span>
                </label>
                <input
                  id="secret-name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="form-input"
                  placeholder="e.g., my_api_token"
                />
                <p className="form-helper">
                  Name cannot be changed after creation. Use in templates as {`{{ secrets.secret_name.field }}`}
                </p>
              </div>

              <div>
                <label htmlFor="secret-type" className="form-label">
                  Secret Type <span className="text-danger">*</span>
                </label>
                <select
                  id="secret-type"
                  value={secretType}
                  onChange={(e) => setSecretType(e.target.value as 'bearer' | 'api_key' | 'custom')}
                  className="form-select w-full"
                >
                  <option value="bearer">Bearer Token</option>
                  <option value="api_key">API Key</option>
                  <option value="custom">Custom</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="secret-value" className="form-label mb-0">
                    Secret Value <span className="text-danger">*</span>
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
                  <>
                    <input
                      id="secret-value"
                      type="text"
                      required
                      value={simpleValue}
                      onChange={(e) => setSimpleValue(e.target.value)}
                      className="form-input-mono"
                      placeholder={
                        secretType === 'api_key' ? 'sk-...' :
                        secretType === 'bearer' ? 'xoxb-...' :
                        'Your secret value'
                      }
                    />
                    <p className="form-helper">
                      {secretType === 'api_key' && `Stored as {"api_key": "..."}`}
                      {secretType === 'bearer' && `Stored as {"token": "..."}`}
                      {secretType === 'custom' && 'Use JSON mode for custom structure'}
                    </p>
                  </>
                ) : (
                  <>
                    <textarea
                      id="secret-value"
                      required
                      rows={8}
                      value={secretData}
                      onChange={(e) => setSecretData(e.target.value)}
                      className="form-textarea font-mono text-xs"
                      placeholder={
                        secretType === 'api_key' ? '{"api_key": "sk-...", "api_secret": "..."}' :
                        secretType === 'bearer' ? '{"token": "xoxb-...", "refresh_token": "..."}' :
                        '{"key": "value"}'
                      }
                    />
                    <p className="form-helper">
                      Advanced: Enter secret as JSON
                    </p>
                  </>
                )}
              </div>

              <div>
                <label htmlFor="secret-expires-at" className="form-label">
                  Expiration Date (optional)
                </label>
                <input
                  id="secret-expires-at"
                  type="datetime-local"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className="form-input"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <Link
                href="/secrets"
                className="btn-secondary"
              >
                Cancel
              </Link>
              <button
                type="submit"
                disabled={submitting}
                className="btn-primary disabled:opacity-50"
              >
                {submitting ? 'Creating...' : 'Create Secret'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
