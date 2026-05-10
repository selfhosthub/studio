// ui/app/providers/[providerId]/credentials/hooks/useCredentialData.ts

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  getProvider,
  getProviderCredentials,
  getOAuthProviders,
  deleteProviderCredential,
} from '@/shared/api';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import type {
  Credential,
  ProviderInfo,
  OAuthProviders,
} from '../types';

interface UseCredentialDataOptions {
  providerId: string;
}

export function useCredentialData({ providerId }: UseCredentialDataOptions) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();

  const [provider, setProvider] = useState<ProviderInfo | null>(null);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [oauthProviders, setOauthProviders] = useState<OAuthProviders>({});
  const [platformOAuthAvailable, setPlatformOAuthAvailable] = useState(false);

  // Check permissions
  const isAdmin = user?.role === 'admin';
  const isSuperAdmin = user?.role === 'super_admin';
  const canView = isAdmin || isSuperAdmin;
  const canManage = isAdmin || isSuperAdmin;

  // Derived OAuth state
  const oauthProviderKey: string | null = provider?.config?.oauth_provider || null;
  const supportsOAuth = !!oauthProviderKey;

  // Credential schema from provider
  const credentialSchema = provider?.client_metadata?.credential_schema;
  const hasCredentialSchema = !!(credentialSchema?.properties &&
    Object.keys(credentialSchema.properties).length > 0);

  // Handle OAuth callback success/error in URL
  useEffect(() => {
    const oauthSuccess = searchParams.get('oauth_success');
    const oauthError = searchParams.get('oauth_error');

    if (oauthSuccess === 'true') {
      toast({ title: 'OAuth credential connected successfully!', variant: 'success' });
      getProviderCredentials(providerId).then(setCredentials).catch((err: unknown) => { console.error('Failed to reload credentials after OAuth:', err); });
      router.replace(`/providers/${providerId}/credentials`);
    } else if (oauthError) {
      const errorMessages: Record<string, string> = {
        'invalid_state': 'OAuth session expired. Please try again.',
        'token_exchange_failed': 'Failed to exchange authorization code. Please try again.',
        'token_exchange_error': 'Error connecting to OAuth provider.',
        'credential_creation_failed': 'Connected but failed to save credential.',
        'provider_not_configured': 'OAuth not configured for this provider.',
      };
      toast({ title: 'OAuth error', description: errorMessages[oauthError] || `OAuth error: ${oauthError}`, variant: 'destructive' });
      router.replace(`/providers/${providerId}/credentials`);
    }
  }, [searchParams, providerId, router, toast]);

  // Fetch provider, credentials, and OAuth providers
  useEffect(() => {
    if (authStatus === 'loading') return;
    if (!user || !canView) {
      setLoading(false);
      return;
    }

    Promise.all([
      getProvider(providerId),
      getProviderCredentials(providerId),
      getOAuthProviders().catch(() => ({ providers: {} })),
    ])
      .then(([providerData, creds, oauthData]) => {
        setProvider(providerData);
        setCredentials(creds);
        setOauthProviders(oauthData.providers || {});
        const oauthKey = providerData?.config?.oauth_provider as string | undefined;
        const providers = oauthData.providers as Record<string, { platform_configured?: boolean }> | undefined;
        if (oauthKey && providers?.[oauthKey]?.platform_configured) {
          setPlatformOAuthAvailable(true);
        }
        setError(null);
      })
      .catch((err) => {
        let errorMessage = 'Failed to load provider credentials';
        if (err instanceof Error) {
          errorMessage = err.message;
        } else if (typeof err === 'string') {
          errorMessage = err;
        } else if (err?.detail) {
          errorMessage = err.detail;
        } else if (err?.message) {
          errorMessage = err.message;
        }
        setError(errorMessage);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- canView derived from user.role
  }, [providerId, user, canManage, authStatus]);

  // Delete credential
  const handleDeleteCredential = async (credentialId: string, name: string) => {
    if (!confirm(`Are you sure you want to delete the credential "${name}"?`)) {
      return;
    }

    try {
      await deleteProviderCredential(credentialId);
      setCredentials(prev => prev.filter(c => c.id !== credentialId));
      toast({ title: 'Credential deleted', description: 'The credential was deleted successfully.', variant: 'success' });
      return credentialId; // Caller can use to clean up revealed secrets
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete credential';
      toast({ title: 'Delete failed', description: message, variant: 'destructive' });
    }
  };

  return {
    // Data
    provider,
    credentials,
    setCredentials,
    loading,
    error,
    oauthProviders,
    platformOAuthAvailable,

    // Permissions
    user,
    canView,
    canManage,

    // Provider/OAuth derived
    oauthProviderKey,
    supportsOAuth,
    credentialSchema,
    hasCredentialSchema,

    // Actions
    handleDeleteCredential,
  };
}
