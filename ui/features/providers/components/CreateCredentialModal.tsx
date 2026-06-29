// ui/features/providers/components/CreateCredentialModal.tsx

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Modal } from '@/shared/ui';
import { getProvider } from '@/shared/api';
import { getApiUrl } from '@/shared/lib/config';
import { ExternalLink } from 'lucide-react';
import { useCredentialForm } from '../hooks/useCredentialForm';
import { CredentialFormModal } from './CredentialFormModal';
import { OAuthRedirectUri } from './OAuthRedirectUri';
import type { Credential, CredentialSchema } from '../credential-types';

interface CreateCredentialModalProps {
  providerId: string;
  isOpen: boolean;
  onClose: () => void;
  onCreated: (credential: Credential) => void;
}

/**
 * Self-contained "add credential" modal: fetches the provider's credential
 * schema, renders the schema-driven or legacy form, and deep-links OAuth
 * providers to their secrets page (where the redirect-based connect flow lives).
 */
export function CreateCredentialModal({
  providerId,
  isOpen,
  onClose,
  onCreated,
}: CreateCredentialModalProps) {
  const [credentialSchema, setCredentialSchema] = useState<CredentialSchema | undefined>(undefined);
  const [providerName, setProviderName] = useState('');
  const [oauthProviderKey, setOauthProviderKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch provider metadata (schema + OAuth key) when opened for a provider.
  useEffect(() => {
    if (!isOpen || !providerId) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const provider = await getProvider(providerId);
        if (cancelled) return;
        const schema = (provider.client_metadata as Record<string, unknown>)
          ?.credential_schema as CredentialSchema | undefined;
        setCredentialSchema(schema);
        setProviderName(provider.name || '');
        setOauthProviderKey((provider.config?.oauth_provider as string) || null);
      } catch {
        if (!cancelled) {
          setCredentialSchema(undefined);
          setOauthProviderKey(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, providerId]);

  const hasCredentialSchema = !!(
    credentialSchema?.properties && Object.keys(credentialSchema.properties).length > 0
  );

  const form = useCredentialForm({
    providerId,
    credentialSchema,
    hasCredentialSchema,
    // handleCreateCredential calls this with the appended list; surface the new credential.
    setCredentials: ((updater) => {
      const next =
        typeof updater === 'function'
          ? (updater as (prev: Credential[]) => Credential[])([])
          : (updater as Credential[]);
      const created = next[next.length - 1];
      if (created) {
        onCreated(created);
        onClose();
      }
    }) as React.Dispatch<React.SetStateAction<Credential[]>>,
    onRevealedSecretInvalidate: () => {},
  });

  // Reset form fields each time the modal opens.
  const handleOpenAddModal = form.handleOpenAddModal;
  useEffect(() => {
    if (isOpen) handleOpenAddModal();
  }, [isOpen, handleOpenAddModal]);

  if (!isOpen) return null;

  if (loading) {
    return (
      <Modal isOpen onClose={onClose} title="Add Provider Credential" size="md">
        <div className="p-6 text-sm text-muted">Loading provider…</div>
      </Modal>
    );
  }

  // OAuth providers: the real connect flow needs a redirect, which would lose
  // editor state. Deep-link to the provider secrets page instead.
  if (oauthProviderKey) {
    const connectTitle = `Connect ${providerName || 'Provider'}`; // defaults-ok
    return (
      <Modal isOpen onClose={onClose} title={connectTitle} size="md">
        <div className="px-4 pt-5 pb-4 sm:p-6 space-y-4">
          <p className="text-sm text-secondary">
            This provider uses OAuth. Connect your account or manage credentials on the provider&apos;s
            secrets page, then return to select the credential here.
          </p>
          <OAuthRedirectUri redirectUri={`${getApiUrl()}/api/v1/oauth/${oauthProviderKey}/callback`} />
          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose} className="btn-orange text-sm inline-flex items-center">
              Cancel
            </button>
            <Link
              href={`/providers/${encodeURIComponent(providerId)}/credentials`}
              className="btn-primary inline-flex items-center gap-1"
            >
              <ExternalLink className="w-4 h-4" />
              Connect on provider page
            </Link>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <CredentialFormModal
      mode="add"
      onSubmit={form.handleCreateCredential}
      onClose={() => {
        form.handleCloseAddModal();
        onClose();
      }}
      credentialForm={form.credentialForm}
      setCredentialForm={form.setCredentialForm}
      formError={form.formError}
      useJsonMode={form.useJsonMode}
      setUseJsonMode={form.setUseJsonMode}
      simpleValue={form.simpleValue}
      setSimpleValue={form.setSimpleValue}
      basicAuthUsername={form.basicAuthUsername}
      setBasicAuthUsername={form.setBasicAuthUsername}
      basicAuthPassword={form.basicAuthPassword}
      setBasicAuthPassword={form.setBasicAuthPassword}
      basicAuthPasswordConfirm={form.basicAuthPasswordConfirm}
      setBasicAuthPasswordConfirm={form.setBasicAuthPasswordConfirm}
      oauthFields={form.oauthFields}
      setOauthFields={form.setOauthFields}
      schemaValues={form.schemaValues}
      setSchemaValues={form.setSchemaValues}
      handleCredentialTypeChange={form.handleCredentialTypeChange}
      credentialSchema={credentialSchema}
      hasCredentialSchema={hasCredentialSchema}
      webhookCallbackToken={form.webhookCallbackToken}
      setWebhookCallbackToken={form.setWebhookCallbackToken}
    />
  );
}
