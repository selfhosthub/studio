// ui/app/providers/[providerId]/credentials/page.tsx

"use client";

import { DashboardLayout } from "@/widgets/layout";
import { ActionButton } from "@/shared/ui";
import { Suspense, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { useReturnTo } from "@/shared/hooks/useReturnTo";

import { getApiUrl } from "@/shared/lib/config";
import { getProviderDocSlug } from "@/shared/lib/provider-docs";
import { ProviderDocsSlideOver } from "@/features/provider-docs/ProviderDocsSlideOver";
import { useCredentialData } from "./hooks/useCredentialData";
import { useOAuthFlow } from "./hooks/useOAuthFlow";
import { useSecretReveal } from "./hooks/useSecretReveal";
import { useCredentialForm, CredentialFormModal, OAuthRedirectUri } from "@/features/providers";
import { CredentialListItem } from "./components/CredentialListItem";

export default function ProviderCredentialsPage() {
  return (
    <Suspense>
      <ProviderCredentialsPageContent />
    </Suspense>
  );
}

function ProviderCredentialsPageContent() {
  const params = useParams();
  const providerId = params.providerId as string;
  const { returnTo } = useReturnTo("/providers/list");

  // --- Data fetching, permissions, OAuth callback handling ---
  const data = useCredentialData({ providerId });

  // --- Provider docs slide-over ---
  const [isDocsOpen, setIsDocsOpen] = useState(false);
  const docsSlug = data.provider ? getProviderDocSlug(data.provider) ?? null : null;

  // --- Secret reveal / copy ---
  const secrets = useSecretReveal();

  // --- OAuth flow operations ---
  const oauth = useOAuthFlow({
    providerId,
    oauthProviderKey: data.oauthProviderKey,
    setCredentials: data.setCredentials,
  });

  // --- Form state & CRUD ---
  const form = useCredentialForm({
    providerId,
    credentialSchema: data.credentialSchema,
    hasCredentialSchema: data.hasCredentialSchema,
    setCredentials: data.setCredentials,
    onRevealedSecretInvalidate: secrets.invalidateRevealedSecret,
  });

  // --- Delete handler that also cleans up revealed secrets ---
  const handleDelete = async (credentialId: string, name: string) => {
    const deletedId = await data.handleDeleteCredential(credentialId, name);
    if (deletedId) {
      secrets.invalidateRevealedSecret(deletedId);
    }
  };

  // --- Loading state (show before access check to avoid Access Denied flash) ---
  if (data.loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="spinner-md"></div>
            <p className="mt-2 text-muted">Loading credentials...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // --- Access denied (only after loading completes) ---
  if (!data.canView) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-danger mb-2">Access Denied</h2>
            <p className="text-secondary">
              You do not have permission to view provider credentials.
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        {/* Breadcrumb */}
        <div className="mb-6">
          <div className="flex items-center text-sm text-muted">
            <Link href={returnTo} className="link">Providers</Link>
            <span className="mx-2">/</span>
            <Link href={`/providers/${providerId}`} className="link">
              {data.provider?.name || 'Provider'}
            </Link>
            <span className="mx-2">/</span>
            <span className="text-primary">Credentials</span>
          </div>
        </div>

        {/* Error */}
        {data.error && (
          <div className="alert alert-error">
            <p>{data.error}</p>
          </div>
        )}

        {/* Main content */}
        {!data.error && data.provider && (
          <>
            {/* Header */}
            <div className="sm:flex sm:items-center mb-8">
              <div className="sm:flex-auto">
                <h1 className="text-2xl font-semibold text-primary">
                  {data.provider.name} Credentials
                </h1>
                <p className="mt-2 text-sm text-secondary">
                  Manage API keys, tokens, and other credentials for accessing this provider.
                </p>
              </div>
              <div className="mt-4 sm:mt-0 sm:ml-16 sm:flex-none">
                <ActionButton variant="active" onClick={form.handleOpenAddModal}>
                  Add Credential
                </ActionButton>
              </div>
            </div>

            {/* Provider docs - available for any provider that has docs. */}
            {docsSlug && (
              <div className="mb-4">
                <button
                  type="button"
                  onClick={() => setIsDocsOpen(true)}
                  className="inline-flex items-center gap-1 text-sm text-info hover:underline"
                >
                  <BookOpen className="w-4 h-4" />
                  Setup guide
                </button>
              </div>
            )}

            {/* OAuth redirect URI - always visible for OAuth providers (needed to register the OAuth app). */}
            {data.oauthProviderKey && (
              <div className="mb-6">
                <OAuthRedirectUri redirectUri={`${getApiUrl()}/api/v1/oauth/${data.oauthProviderKey}/callback`} />
              </div>
            )}

            {/* Credentials List */}
            <div>
              {data.credentials.length === 0 ? (
                <div className="bg-card border border-primary rounded-lg text-center py-12">
                  <p className="text-muted mb-4">
                    No credentials configured for this provider.
                  </p>
                  <ActionButton variant="active" onClick={form.handleOpenAddModal}>
                    Add First Credential
                  </ActionButton>
                </div>
              ) : (
                <div className="space-y-4">
                  {data.credentials.map((cred) => (
                    <CredentialListItem
                      key={cred.id}
                      credential={cred}
                      canManage={data.canManage}
                      supportsOAuth={data.supportsOAuth}
                      oauthProviderKey={data.oauthProviderKey}
                      oauthLoading={oauth.oauthLoading}
                      refreshingCredential={oauth.refreshingCredential}
                      credentialNeedsOAuth={oauth.credentialNeedsOAuth}
                      credentialHasOAuth={oauth.credentialHasOAuth}
                      onOAuthAuthorize={oauth.handleOAuthAuthorize}
                      onRefreshOAuthToken={oauth.handleRefreshOAuthToken}
                      onReauthorize={oauth.handleReauthorize}
                      revealedSecrets={secrets.revealedSecrets}
                      revealingCredential={secrets.revealingCredential}
                      copiedCredential={secrets.copiedCredential}
                      onRevealCredential={secrets.handleRevealCredential}
                      onCopySecret={secrets.handleCopySecret}
                      onEdit={form.handleEditClick}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* Add Credential Modal */}
        {form.showAddModal && (
          <CredentialFormModal
            mode="add"
            onSubmit={form.handleCreateCredential}
            onClose={form.handleCloseAddModal}
            providerDocSlug={data.provider ? getProviderDocSlug(data.provider) ?? undefined : undefined}
            oauthRedirectUri={data.supportsOAuth && data.oauthProviderKey
              ? `${getApiUrl()}/api/v1/oauth/${data.oauthProviderKey}/callback`
              : undefined}
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
            credentialSchema={data.credentialSchema}
            hasCredentialSchema={data.hasCredentialSchema}
            webhookCallbackToken={form.webhookCallbackToken}
            setWebhookCallbackToken={form.setWebhookCallbackToken}
          />
        )}

        {/* Edit Credential Modal */}
        {form.showEditModal && (
          <CredentialFormModal
            mode="edit"
            onSubmit={form.handleUpdateCredential}
            onClose={form.handleCloseEditModal}
            providerDocSlug={data.provider ? getProviderDocSlug(data.provider) ?? undefined : undefined}
            oauthRedirectUri={data.supportsOAuth && data.oauthProviderKey
              ? `${getApiUrl()}/api/v1/oauth/${data.oauthProviderKey}/callback`
              : undefined}
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
            credentialSchema={data.credentialSchema}
            hasCredentialSchema={data.hasCredentialSchema}
            webhookCallbackToken={form.webhookCallbackToken}
            setWebhookCallbackToken={form.setWebhookCallbackToken}
          />
        )}

        {docsSlug && (
          <ProviderDocsSlideOver
            slug={docsSlug}
            isOpen={isDocsOpen}
            onClose={() => setIsDocsOpen(false)}
          />
        )}
      </div>
    </DashboardLayout>
  );
}
