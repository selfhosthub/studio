// ui/app/workflows/[id]/edit/hooks/useCredentialCheck.ts

import { useState, useCallback, useEffect } from 'react';
import { checkWorkflowCredentials, CredentialCheckResponse } from '@/shared/api';

export function useCredentialCheck(workflowId: string | undefined) {
  const [credentialCheck, setCredentialCheck] = useState<CredentialCheckResponse | null>(null);
  const [credentialCheckLoading, setCredentialCheckLoading] = useState(false);

  const refreshCredentialCheck = useCallback(async () => {
    if (!workflowId) return;

    try {
      setCredentialCheckLoading(true);
      const result = await checkWorkflowCredentials(workflowId);
      setCredentialCheck(result);
    } catch (err: unknown) {
      console.error('Failed to check workflow credentials:', err);
    } finally {
      setCredentialCheckLoading(false);
    }
  }, [workflowId]);

  // Check on mount / when workflowId changes
  useEffect(() => {
    refreshCredentialCheck();
  }, [refreshCredentialCheck]);

  return { credentialCheck, credentialCheckLoading, refreshCredentialCheck };
}
