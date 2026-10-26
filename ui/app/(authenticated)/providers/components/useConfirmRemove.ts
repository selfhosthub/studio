// ui/app/(authenticated)/providers/components/useConfirmRemove.ts

'use client';

import { useCallback } from 'react';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { providerWorkflowCount, workflowsNoun } from './providerUsage';

// Checks a provider package's workflow usage, then asks to confirm removing it
export function useConfirmRemove(): (name: string, slug: string) => Promise<boolean> {
  const confirm = useConfirm();
  return useCallback(
    async (name: string, slug: string) => {
      const count = await providerWorkflowCount(slug);
      const usageLine = count > 0
        ? `\n\nUsed by ${workflowsNoun(count)}. It cannot be removed until no workflow uses it.`
        : '';
      return confirm({
        title: 'Remove provider',
        message:
          `Remove ${name}? Its services are deleted for all organizations and it returns to Providers > Marketplace > Available, where it can be installed again.` +
          usageLine,
        confirmLabel: 'Remove',
        variant: 'danger',
      });
    },
    [confirm]
  );
}
