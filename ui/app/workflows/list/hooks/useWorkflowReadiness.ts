// ui/app/workflows/list/hooks/useWorkflowReadiness.ts

import { useEffect, useState, useCallback } from 'react';
import { getProviders, getPrompts } from '@/shared/api';
import type { WorkflowResponse } from '@/shared/types/api';
import { checkWorkflowReadiness, type WorkflowIssue } from '@/shared/lib/workflow-readiness';

/** Fetches active providers and prompts once; returns a stable function to check any workflow's readiness. */
export function useWorkflowReadiness() {
  const [activeProviderIds, setActiveProviderIds] = useState<Set<string>>(new Set());
  const [activePromptIds, setActivePromptIds] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function fetch() {
      try {
        const [providers, prompts] = await Promise.all([
          getProviders(),
          getPrompts(),
        ]);
        if (cancelled) return;
        setActiveProviderIds(new Set(
          providers.flatMap(p => p.slug ? [p.id, p.slug] : [p.id])
        ));
        setActivePromptIds(new Set(prompts.map(p => p.id)));
        setLoaded(true);
      } catch {
        // Non-critical - readiness indicators just won't show
        setLoaded(true);
      }
    }
    fetch();
    return () => { cancelled = true; };
  }, []);

  const getIssues = useCallback(
    (workflow: WorkflowResponse): WorkflowIssue[] => {
      if (!loaded) return [];
      return checkWorkflowReadiness(workflow, activeProviderIds, activePromptIds);
    },
    [loaded, activeProviderIds, activePromptIds]
  );

  return { getIssues, loaded };
}
