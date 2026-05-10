// ui/app/providers/[providerId]/credentials/components/CredentialListItem.tsx

import { ActionButton } from '@/shared/ui';
import { isCredentialTypeRevealable } from '@/shared/api';
import { RefreshCw, ExternalLink, Eye, EyeOff, Copy, Check } from 'lucide-react';
import type { Credential } from '../types';

interface CredentialListItemProps {
  credential: Credential;
  canManage: boolean;

  // OAuth state
  supportsOAuth: boolean;
  oauthProviderKey: string | null;
  platformOAuthAvailable: boolean;
  oauthLoading: boolean;
  refreshingCredential: string | null;
  credentialNeedsOAuth: (cred: Credential) => boolean;
  credentialHasOAuth: (cred: Credential) => boolean;

  // OAuth actions
  onOAuthAuthorize: (credentialId: string) => void;
  onRefreshOAuthToken: (credentialId: string) => void;
  onReauthorize: (credentialId: string) => void;

  // Secret reveal state
  revealedSecrets: Record<string, Record<string, unknown>>;
  revealingCredential: string | null;
  copiedCredential: string | null;

  // Secret reveal actions
  onRevealCredential: (credentialId: string, credentialType: string, isTokenType?: boolean) => void;
  onCopySecret: (credentialId: string, secretData: Record<string, unknown>) => void;

  // CRUD actions
  onEdit: (credential: Credential) => void;
  onDelete: (credentialId: string, name: string) => void;
}

/**
 * A single credential row in the credentials list.
 */
export function CredentialListItem({
  credential: cred,
  canManage,
  supportsOAuth,
  oauthProviderKey,
  platformOAuthAvailable,
  oauthLoading,
  refreshingCredential,
  credentialNeedsOAuth,
  credentialHasOAuth,
  onOAuthAuthorize,
  onRefreshOAuthToken,
  onReauthorize,
  revealedSecrets,
  revealingCredential,
  copiedCredential,
  onRevealCredential,
  onCopySecret,
  onEdit,
  onDelete,
}: CredentialListItemProps) {
  return (
    <div className="bg-card border border-primary rounded-lg overflow-hidden">
      {/* Header bar */}
      <div className="flex justify-between items-center px-6 py-3 bg-input border-b border-primary">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="text-base font-semibold text-primary">
            {cred.name}
          </h3>
          <span className="badge badge-default">{cred.credential_type}</span>
          {!cred.is_active && (
            <span className="badge">Inactive</span>
          )}
          {cred.expires_at && new Date(cred.expires_at) < new Date() && (
            <span className="badge-error">Expired</span>
          )}
          {supportsOAuth && credentialNeedsOAuth(cred) && (
            <span className="badge-warning">Needs Authorization</span>
          )}
          {supportsOAuth && credentialHasOAuth(cred) && (
            <span className="badge-success">Connected</span>
          )}
        </div>

        {/* Action buttons */}
        {canManage && (
          <div className="flex items-center gap-2">
            {/* Authorize button for credentials needing OAuth */}
            {supportsOAuth && credentialNeedsOAuth(cred) && (
              <ActionButton
                variant="active"
                onClick={() => onOAuthAuthorize(cred.id)}
                disabled={oauthLoading}
              >
                {oauthLoading ? (
                  <>
                    <RefreshCw className="animate-spin h-4 w-4 mr-2" />
                    Authorizing...
                  </>
                ) : (
                  <>
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Authorize
                  </>
                )}
              </ActionButton>
            )}
            {/* Re-authorize button for completed OAuth credentials */}
            {credentialHasOAuth(cred) && oauthProviderKey && platformOAuthAvailable && (
              <ActionButton
                variant="navigate"
                onClick={() => onReauthorize(cred.id)}
                disabled={oauthLoading}
                title="Re-authorize with current scopes"
                className="inline-flex items-center"
              >
                <ExternalLink className="h-4 w-4 mr-1 shrink-0" />
                Re-authorize
              </ActionButton>
            )}
            {/* Refresh button for completed OAuth credentials */}
            {credentialHasOAuth(cred) && oauthProviderKey && (
              <ActionButton
                variant="active"
                onClick={() => onRefreshOAuthToken(cred.id)}
                disabled={refreshingCredential === cred.id}
                className="inline-flex items-center"
              >
                <RefreshCw className={`h-4 w-4 mr-1 shrink-0 ${refreshingCredential === cred.id ? 'animate-spin' : ''}`} />
                Refresh
              </ActionButton>
            )}
            <ActionButton variant="change" onClick={() => onEdit(cred)}>
              Edit
            </ActionButton>
            <ActionButton
              variant="destructive"
              onClick={() => onDelete(cred.id, cred.name)}
            >
              Delete
            </ActionButton>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="px-6 py-4">
        {/* Metadata fields */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-4">
          {cred.expires_at && (
            <div>
              <p className="text-xs font-medium text-muted uppercase tracking-wide">Expires</p>
              <p className="mt-0.5 text-sm text-primary">{new Date(cred.expires_at).toLocaleDateString()}</p>
            </div>
          )}
          <div>
            <p className="text-xs font-medium text-muted uppercase tracking-wide">Created</p>
            <p className="mt-0.5 text-sm text-primary">{cred.created_at ? new Date(cred.created_at).toLocaleString() : 'N/A'}</p>
          </div>
        </div>

        {/* Secret Data Display */}
        <SecretDataDisplay
          credential={cred}
          canManage={canManage}
          revealedSecrets={revealedSecrets}
          revealingCredential={revealingCredential}
          copiedCredential={copiedCredential}
          onRevealCredential={onRevealCredential}
          onCopySecret={onCopySecret}
        />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Internal sub-component: Secret data display                                */
/* -------------------------------------------------------------------------- */

function SecretDataDisplay({
  credential: cred,
  canManage,
  revealedSecrets,
  revealingCredential,
  copiedCredential,
  onRevealCredential,
  onCopySecret,
}: {
  credential: Credential;
  canManage: boolean;
  revealedSecrets: Record<string, Record<string, unknown>>;
  revealingCredential: string | null;
  copiedCredential: string | null;
  onRevealCredential: (credentialId: string, credentialType: string, isTokenType?: boolean) => void;
  onCopySecret: (credentialId: string, secretData: Record<string, unknown>) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-muted uppercase tracking-wide">Secret Data</p>
        {canManage && isCredentialTypeRevealable(cred.credential_type, cred.is_token_type) && (
          <div className="flex items-center gap-1">
            {revealedSecrets[cred.id] && (
              <button
                onClick={() => onCopySecret(cred.id, revealedSecrets[cred.id])}
                className="p-1 text-muted hover:text-secondary"
                title="Copy to clipboard"
              >
                {copiedCredential === cred.id ? (
                  <Check className="w-4 h-4 text-success" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            )}
            <button
              onClick={() => onRevealCredential(cred.id, cred.credential_type, cred.is_token_type)}
              disabled={revealingCredential === cred.id}
              className="p-1 text-muted hover:text-secondary disabled:opacity-50"
              title={revealedSecrets[cred.id] ? 'Hide secret' : 'Reveal secret'}
            >
              {revealingCredential === cred.id ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : revealedSecrets[cred.id] ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
        )}
      </div>
      <div className="bg-input border border-primary rounded-lg p-3 font-mono text-xs">
        {revealedSecrets[cred.id] ? (
          <div className="space-y-1">
            {Object.entries(revealedSecrets[cred.id]).map(([key, value]) => {
              const isPasswordField = key.toLowerCase() === 'password';
              const displayValue = isPasswordField
                ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'
                : (typeof value === 'string' ? value : JSON.stringify(value));
              return (
                <div key={key} className="flex items-start justify-between gap-2">
                  <span className="text-secondary flex-shrink-0">{key}:</span>
                  <span className="text-primary break-all text-right">
                    {displayValue}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-secondary">
                {cred.credential_type === 'api_key' ? 'api_key' :
                 cred.credential_type === 'bearer' || cred.credential_type === 'oauth' ? 'access_token' :
                 'value'}:
              </span>
              <span className="text-primary">
                {'\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
              </span>
            </div>
            <p className="text-xs text-muted mt-2 italic">
              {isCredentialTypeRevealable(cred.credential_type, cred.is_token_type)
                ? 'Click the eye icon to reveal the secret value.'
                : 'This credential type can only be viewed at creation time.'}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
