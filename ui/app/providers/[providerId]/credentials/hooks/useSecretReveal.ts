// ui/app/providers/[providerId]/credentials/hooks/useSecretReveal.ts

import { useState, useCallback } from 'react';
import {
  revealProviderCredential,
  isCredentialTypeRevealable,
} from '@/shared/api';
import { useToast } from '@/features/toast';
import { TIMEOUTS } from '@/shared/lib/constants';

export function useSecretReveal() {
  const { toast } = useToast();

  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, Record<string, unknown>>>({});
  const [revealingCredential, setRevealingCredential] = useState<string | null>(null);
  const [copiedCredential, setCopiedCredential] = useState<string | null>(null);

  /** Reveal or hide a credential secret */
  const handleRevealCredential = useCallback(async (
    credentialId: string,
    credentialType: string,
    isTokenType?: boolean,
  ) => {
    // Toggle hide if already revealed
    if (revealedSecrets[credentialId]) {
      setRevealedSecrets(prev => {
        const newState = { ...prev };
        delete newState[credentialId];
        return newState;
      });
      return;
    }

    if (!isCredentialTypeRevealable(credentialType, isTokenType)) {
      toast({
        title: 'Cannot reveal',
        description: 'This credential type can only be viewed at creation time.',
        variant: 'destructive',
      });
      return;
    }

    setRevealingCredential(credentialId);
    try {
      const result = await revealProviderCredential(credentialId);
      setRevealedSecrets(prev => ({
        ...prev,
        [credentialId]: result.secret_data,
      }));
    } catch (err: unknown) {
      const errorObj = err as Record<string, unknown> | undefined;
      const errorDetail = errorObj?.detail || errorObj?.message || 'Failed to reveal credential';
      if (typeof errorDetail === 'object' && errorDetail !== null && 'reason' in errorDetail) {
        toast({
          title: 'Cannot reveal',
          description: (errorDetail as { reason: string }).reason,
          variant: 'destructive',
        });
      } else {
        toast({
          title: 'Reveal failed',
          description: typeof errorDetail === 'string' ? errorDetail : 'Failed to reveal credential',
          variant: 'destructive',
        });
      }
    } finally {
      setRevealingCredential(null);
    }
  }, [revealedSecrets, toast]);

  /** Copy a revealed secret to clipboard */
  const handleCopySecret = useCallback(async (
    credentialId: string,
    secretData: Record<string, unknown>,
  ) => {
    try {
      const keys = Object.keys(secretData);
      let textToCopy: string;
      if (keys.length === 1 && typeof secretData[keys[0]] === 'string') {
        textToCopy = secretData[keys[0]] as string;
      } else {
        textToCopy = JSON.stringify(secretData, null, 2);
      }

      await navigator.clipboard.writeText(textToCopy);
      setCopiedCredential(credentialId);
      toast({ title: 'Copied', description: 'Secret copied to clipboard', variant: 'success' });

      setTimeout(() => setCopiedCredential(null), TIMEOUTS.COPY_FEEDBACK);
    } catch {
      toast({ title: 'Copy failed', description: 'Failed to copy to clipboard', variant: 'destructive' });
    }
  }, [toast]);

  /** Remove a credential from revealed secrets (used after update or delete) */
  const invalidateRevealedSecret = useCallback((credentialId: string) => {
    setRevealedSecrets(prev => {
      const newState = { ...prev };
      delete newState[credentialId];
      return newState;
    });
  }, []);

  return {
    revealedSecrets,
    revealingCredential,
    copiedCredential,
    handleRevealCredential,
    handleCopySecret,
    invalidateRevealedSecret,
  };
}
