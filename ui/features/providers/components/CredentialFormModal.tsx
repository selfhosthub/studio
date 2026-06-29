// ui/features/providers/components/CredentialFormModal.tsx

import { useState } from 'react';
import { Modal } from '@/shared/ui';
import { BookOpen } from 'lucide-react';
import { OAuthRedirectUri } from './OAuthRedirectUri';
import type { CredentialFormValues, CredentialSchema } from '../credential-types';
import { SchemaFields } from './SchemaFields';
import { WebhookCallbackFields } from './WebhookCallbackFields';
import { LegacyCredentialFields } from './LegacyCredentialFields';
import type { OAuthFieldValues } from './OAuthCredentialFields';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';

/** Schema field key for the per-credential webhook callback secret. */
const WEBHOOK_CALLBACK_KEY_FIELD = 'webhook_callback_api_key';

interface CredentialFormModalProps {
  /** 'add' or 'edit' determines title, button text, and field behavior */
  mode: 'add' | 'edit';
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;

  // Form state (passed through from useCredentialForm)
  credentialForm: CredentialFormValues;
  setCredentialForm: React.Dispatch<React.SetStateAction<CredentialFormValues>>;
  formError: string | null;
  useJsonMode: boolean;
  setUseJsonMode: React.Dispatch<React.SetStateAction<boolean>>;
  simpleValue: string;
  setSimpleValue: React.Dispatch<React.SetStateAction<string>>;
  basicAuthUsername: string;
  setBasicAuthUsername: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPassword: string;
  setBasicAuthPassword: React.Dispatch<React.SetStateAction<string>>;
  basicAuthPasswordConfirm: string;
  setBasicAuthPasswordConfirm: React.Dispatch<React.SetStateAction<string>>;
  oauthFields: OAuthFieldValues;
  setOauthFields: React.Dispatch<React.SetStateAction<OAuthFieldValues>>;
  schemaValues: Record<string, string>;
  setSchemaValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  handleCredentialTypeChange: (newType: string) => void;

  // Schema
  credentialSchema: CredentialSchema | undefined;
  hasCredentialSchema: boolean;

  // Optional provider doc slug for setup guide slide-over
  providerDocSlug?: string;

  // OAuth callback URL to register in the provider's OAuth app (shown for OAuth providers).
  oauthRedirectUri?: string;

  // Callback routing token (the random string in the callback URL). Held in form
  // state, generate-only, persisted on save. Null until generated.
  webhookCallbackToken: string | null;
  setWebhookCallbackToken: (value: string) => void;
}

/**
 * Shared modal for adding and editing provider credentials.
 * The form body is identical between modes; only the title, submit text,
 * and the presence of the security notice differ.
 */
export function CredentialFormModal({
  mode,
  onSubmit,
  onClose,
  credentialForm,
  setCredentialForm,
  formError,
  useJsonMode,
  setUseJsonMode,
  simpleValue,
  setSimpleValue,
  basicAuthUsername,
  setBasicAuthUsername,
  basicAuthPassword,
  setBasicAuthPassword,
  basicAuthPasswordConfirm,
  setBasicAuthPasswordConfirm,
  oauthFields,
  setOauthFields,
  schemaValues,
  setSchemaValues,
  handleCredentialTypeChange,
  credentialSchema,
  hasCredentialSchema,
  providerDocSlug,
  oauthRedirectUri,
  webhookCallbackToken,
  setWebhookCallbackToken,
}: CredentialFormModalProps) {
  const hasWebhookCallbackField = Boolean(
    credentialSchema?.properties?.[WEBHOOK_CALLBACK_KEY_FIELD]
  );
  const isEdit = mode === 'edit';
  const title = isEdit ? 'Edit Provider Credential' : 'Add Provider Credential';
  const submitText = isEdit ? 'Update Credential' : 'Add Credential';
  const idPrefix = isEdit ? 'edit-' : '';
  const schemaIdPrefix = isEdit ? 'edit_schema' : 'schema';

  const [isDocsOpen, setIsDocsOpen] = useState(false);

  return (
    <>
      <Modal isOpen={true} onClose={onClose} title={title} size="md" dismissOnOutsideClick={false}>
        <form onSubmit={onSubmit}>
          <div className="px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
            <div className="space-y-4">
              {providerDocSlug && (
                <button
                  type="button"
                  onClick={() => setIsDocsOpen(true)}
                  className="inline-flex items-center gap-1 text-xs text-info hover:underline"
                >
                  <BookOpen className="w-3 h-3" />
                  Setup guide
                </button>
              )}
              {oauthRedirectUri && <OAuthRedirectUri redirectUri={oauthRedirectUri} />}
              {formError && (
                <div className="alert alert-error">
                  <p className="text-sm">{formError}</p>
                </div>
              )}

              {/* Name field */}
              <div>
                <label htmlFor={`${idPrefix}name`} className="form-label">
                  Credential Name *
                </label>
                <input
                  type="text"
                  id={`${idPrefix}name`}
                  required
                  value={credentialForm.name}
                  onChange={(e) => setCredentialForm({ ...credentialForm, name: e.target.value })}
                  className="form-input"
                  placeholder="e.g., Production OpenAI Key"
                />
              </div>

              {/* Schema-driven or legacy fields */}
              {hasCredentialSchema && credentialSchema ? (
                <>
                  {/* api_key etc. (webhook_callback_api_key is filtered out here) */}
                  <SchemaFields
                    credentialSchema={credentialSchema}
                    schemaValues={schemaValues}
                    setSchemaValues={setSchemaValues}
                    idPrefix={schemaIdPrefix}
                  />
                  {/* Callback key + URL, below the API key, generate-only */}
                  {hasWebhookCallbackField && (
                    <WebhookCallbackFields
                      callbackKey={schemaValues[WEBHOOK_CALLBACK_KEY_FIELD] || ''}
                      setCallbackKey={(value) =>
                        setSchemaValues((v) => ({ ...v, [WEBHOOK_CALLBACK_KEY_FIELD]: value }))
                      }
                      callbackToken={webhookCallbackToken}
                      setCallbackToken={setWebhookCallbackToken}
                    />
                  )}
                </>
              ) : (
                <LegacyCredentialFields
                  credentialForm={credentialForm}
                  setCredentialForm={setCredentialForm}
                  useJsonMode={useJsonMode}
                  setUseJsonMode={setUseJsonMode}
                  simpleValue={simpleValue}
                  setSimpleValue={setSimpleValue}
                  basicAuthUsername={basicAuthUsername}
                  setBasicAuthUsername={setBasicAuthUsername}
                  basicAuthPassword={basicAuthPassword}
                  setBasicAuthPassword={setBasicAuthPassword}
                  basicAuthPasswordConfirm={basicAuthPasswordConfirm}
                  setBasicAuthPasswordConfirm={setBasicAuthPasswordConfirm}
                  oauthFields={oauthFields}
                  setOauthFields={setOauthFields}
                  handleCredentialTypeChange={handleCredentialTypeChange}
                  isEdit={isEdit}
                  idPrefix={idPrefix}
                />
              )}

              {/* Expiration date */}
              <div>
                <label htmlFor={`${idPrefix}expires_at`} className="form-label">
                  Expiration Date (optional)
                </label>
                <input
                  type="datetime-local"
                  id={`${idPrefix}expires_at`}
                  value={credentialForm.expires_at}
                  onChange={(e) => setCredentialForm({ ...credentialForm, expires_at: e.target.value })}
                  className="form-input"
                />
              </div>
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3 px-4 pb-4 sm:px-6">
            <button type="submit" className="btn-primary sm:ml-3">
              {submitText}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn-orange text-sm inline-flex items-center mt-3 sm:mt-0 sm:ml-3"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      {providerDocSlug && (
        <ProviderDocsSlideOver
          slug={providerDocSlug}
          isOpen={isDocsOpen}
          onClose={() => setIsDocsOpen(false)}
        />
      )}
    </>
  );
}
