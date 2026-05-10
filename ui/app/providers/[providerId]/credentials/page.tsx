// ui/app/providers/[providerId]/credentials/page.tsx

"use client";

import { DashboardLayout } from "@/widgets/layout";
import { ActionButton } from "@/shared/ui";
import { Suspense } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { getApiUrl } from "@/shared/lib/config";
import { getProviderDocSlug } from "@/shared/lib/provider-docs";
import { useCredentialData } from "./hooks/useCredentialData";
import { useCredentialForm } from "./hooks/useCredentialForm";
import { useOAuthFlow } from "./hooks/useOAuthFlow";
import { useSecretReveal } from "./hooks/useSecretReveal";
import { CredentialFormModal } from "./components/CredentialFormModal";
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

  // --- Data fetching, permissions, OAuth callback handling ---
  const data = useCredentialData({ providerId });

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
            <Link href="/providers/list" className="link">Providers</Link>
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

            {/* Platform OAuth: one-click connect - hide once a connected credential exists */}
            {data.platformOAuthAvailable && data.oauthProviderKey && data.credentials.length === 0 && (
              <div className="mb-6 alert alert-info">
                <div className="flex items-start justify-between">
                  <div className="flex items-start">
                    <ExternalLink className="h-5 w-5 text-info mt-0.5 mr-3 flex-shrink-0" />
                    <div>
                      <h3 className="text-sm font-medium text-info">
                        Connect {data.provider.name}
                      </h3>
                      <p className="mt-1 text-sm text-info">
                        Click the button to authorize your {data.provider.name} account. No setup required.
                      </p>
                    </div>
                  </div>
                  <ActionButton
                    variant="active"
                    onClick={oauth.handlePlatformConnect}
                    disabled={oauth.oauthLoading}
                  >
                    {oauth.oauthLoading ? 'Connecting...' : `Connect with ${data.provider.name}`}
                  </ActionButton>
                </div>
              </div>
            )}

            {/* Org-managed OAuth: setup instructions */}
            {!data.platformOAuthAvailable && data.supportsOAuth && (
              <div className="mb-6 alert alert-info">
                <div className="flex items-start">
                  <ExternalLink className="h-5 w-5 text-info mt-0.5 mr-3 flex-shrink-0" />
                  <div>
                    <h3 className="text-sm font-medium text-info">
                      OAuth Setup
                    </h3>
                    <p className="mt-1 text-sm text-info">
                      To connect {data.provider.name}, create your own OAuth app and add the credentials here.
                    </p>
                    <details className="mt-2">
                      <summary className="text-sm text-info cursor-pointer hover:underline">
                        Setup instructions
                      </summary>
                      <ol className="mt-2 ml-4 text-sm text-info list-decimal space-y-1">
                        <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" className="underline">Google Cloud Console</a></li>
                        <li>Create a project and enable the APIs you need (Sheets, Drive, Gmail)</li>
                        <li>Create OAuth 2.0 Client ID (Web application type)</li>
                        <li>Add authorized redirect URI: <code className="bg-info-subtle px-1 rounded text-xs">{getApiUrl()}/api/v1/oauth/{data.oauthProviderKey}/callback</code></li>
                        <li>Click &quot;Add Credential&quot; above, enter your Client ID and Client Secret</li>
                        <li>Click &quot;Authorize&quot; on the credential to complete the connection</li>
                      </ol>
                    </details>
                  </div>
                </div>
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
                      platformOAuthAvailable={data.platformOAuthAvailable}
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
            schemaValues={form.schemaValues}
            setSchemaValues={form.setSchemaValues}
            handleCredentialTypeChange={form.handleCredentialTypeChange}
            credentialSchema={data.credentialSchema}
            hasCredentialSchema={data.hasCredentialSchema}
          />
        )}

        {/* Edit Credential Modal */}
        {form.showEditModal && (
          <CredentialFormModal
            mode="edit"
            onSubmit={form.handleUpdateCredential}
            onClose={form.handleCloseEditModal}
            providerDocSlug={data.provider ? getProviderDocSlug(data.provider) ?? undefined : undefined}
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
            schemaValues={form.schemaValues}
            setSchemaValues={form.setSchemaValues}
            handleCredentialTypeChange={form.handleCredentialTypeChange}
            credentialSchema={data.credentialSchema}
            hasCredentialSchema={data.hasCredentialSchema}
          />
        )}
      </div>
    </DashboardLayout>
  );
}
