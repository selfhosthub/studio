// ui/app/providers/[providerId]/credentials/hooks/useOAuthFlow.ts

import { useState } from 'react';
import {
  startOAuthFlow,
  startPlatformOAuthFlow,
  reauthorizePlatformOAuth,
  refreshOAuthTokens,
  getProviderCredentials,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import type { Credential } from '../types';

interface UseOAuthFlowOptions {
  providerId: string;
  oauthProviderKey: string | null;
  setCredentials: React.Dispatch<React.SetStateAction<Credential[]>>;
}

export function useOAuthFlow({
  providerId,
  oauthProviderKey,
  setCredentials,
}: UseOAuthFlowOptions) {
  const { toast } = useToast();
  const [oauthLoading, setOauthLoading] = useState(false);
  const [refreshingCredential, setRefreshingCredential] = useState<string | null>(null);

  /** Check if a credential needs OAuth authorization */
  const credentialNeedsOAuth = (cred: Credential): boolean => {
    return !!cred.has_client_credentials && !cred.has_access_token;
  };

  /** Check if a credential has completed OAuth */
  const credentialHasOAuth = (cred: Credential): boolean => {
    return !!cred.has_access_token;
  };

  /** Start OAuth authorization for an existing credential */
  const handleOAuthAuthorize = async (credentialId: string) => {
    if (!oauthProviderKey) return;

    setOauthLoading(true);

    try {
      const response = await startOAuthFlow(oauthProviderKey, credentialId);
      window.location.href = response.authorization_url;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start OAuth flow';
      toast({ title: 'OAuth error', description: message, variant: 'destructive' });
      setOauthLoading(false);
    }
  };

  /** Refresh OAuth tokens */
  const handleRefreshOAuthToken = async (credentialId: string) => {
    if (!oauthProviderKey) return;

    setRefreshingCredential(credentialId);

    try {
      await refreshOAuthTokens(oauthProviderKey, credentialId);
      toast({ title: 'Tokens refreshed successfully!', variant: 'success' });
      const updatedCreds = await getProviderCredentials(providerId);
      setCredentials(updatedCreds);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to refresh tokens';
      toast({ title: 'Refresh failed', description: message, variant: 'destructive' });
    } finally {
      setRefreshingCredential(null);
    }
  };

  /** Start platform OAuth connect (one-click, no client_id/secret needed) */
  const handlePlatformConnect = async () => {
    if (!oauthProviderKey) return;

    setOauthLoading(true);

    try {
      const response = await startPlatformOAuthFlow(oauthProviderKey, providerId);
      window.location.href = response.authorization_url;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start connection';
      toast({ title: 'Connection error', description: message, variant: 'destructive' });
      setOauthLoading(false);
    }
  };

  /** Re-authorize platform OAuth with current scopes */
  const handleReauthorize = async (credentialId: string) => {
    if (!oauthProviderKey) return;

    setOauthLoading(true);

    try {
      const response = await reauthorizePlatformOAuth(oauthProviderKey, providerId, credentialId);
      window.location.href = response.authorization_url;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start re-authorization';
      toast({ title: 'Re-authorization error', description: message, variant: 'destructive' });
      setOauthLoading(false);
    }
  };

  return {
    oauthLoading,
    refreshingCredential,
    credentialNeedsOAuth,
    credentialHasOAuth,
    handleOAuthAuthorize,
    handleRefreshOAuthToken,
    handlePlatformConnect,
    handleReauthorize,
  };
}
