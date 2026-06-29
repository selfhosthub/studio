// ui/features/step-config/usePromptSystemOverride.ts

'use client';

import { useEffect, useState } from 'react';
import { getPrompt } from '@/shared/api/prompts';
import type { InputMapping } from './MappableParameterField/types';

/** True when any parameter on the step has an AI Prompt bound whose System
 *  box (leading system chunk) is non-empty. Fields marked `ui.system_slot`
 *  use this to disable themselves - the dispatch shaper gives the prompt's
 *  system content precedence over the step's native system parameter. */
export function usePromptSystemOverride(
  inputMappings: Record<string, InputMapping | undefined>
): boolean {
  const promptId =
    Object.values(inputMappings).find(
      (m) => m?.mappingType === 'prompt' && m.promptId
    )?.promptId ?? null;

  // State is keyed to the promptId it was computed for, so a stale answer for
  // a previous prompt never leaks (adjust during render, not in an effect).
  const [state, setState] = useState<{
    promptId: string | null;
    hasSystem: boolean;
  }>({ promptId: null, hasSystem: false });

  useEffect(() => {
    if (!promptId) return;
    let cancelled = false;
    getPrompt(promptId)
      .then((prompt) => {
        if (cancelled) return;
        // The domain invariant guarantees at most one system chunk, leading;
        // any non-blank system chunk means the prompt fills the system slot.
        const hasSystem = (prompt.chunks || []).some(
          (c) => (c.role || 'user') === 'system' && !!c.text?.trim() // defaults-ok
        );
        setState({ promptId, hasSystem });
      })
      .catch(() => {
        // Unresolvable prompt (deleted, network) - leave the field editable;
        // dispatch-time behavior is authoritative either way.
        if (!cancelled) setState({ promptId, hasSystem: false });
      });
    return () => {
      cancelled = true;
    };
  }, [promptId]);

  return state.promptId === promptId && state.hasSystem;
}
