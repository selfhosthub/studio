// ui/app/(authenticated)/providers/components/useConfirmDeactivate.ts

'use client';

import { useCallback } from 'react';
import { isReservedSlug } from '@/entities/provider';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { providerWorkflowCount, workflowsNoun } from './providerUsage';

// Success toast shown after a provider is deactivated
export function deactivatedToast(name: string) {
  return { title: `"${name}" deactivated`, variant: 'success' as const };
}

// Checks a provider package's workflow usage, then asks to confirm deactivating it
export function useConfirmDeactivate(): (name: string, slug: string) => Promise<boolean> {
  const confirm = useConfirm();
  return useCallback(
    async (name: string, slug: string) => {
      const count = await providerWorkflowCount(slug);
      const usageLine = count > 0
        ? `\n\nUsed by ${workflowsNoun(count)}. They will fail until the provider is reactivated.`
        : '';
      const reactivatePath = isReservedSlug(slug) ? 'Providers > Marketplace > Deactivated' : 'Providers > Custom';
      return confirm({
        title: 'Deactivate provider',
        message:
          `Deactivate ${name}? It is deactivated for all organizations and can be reactivated from ${reactivatePath}.` +
          usageLine,
        confirmLabel: 'Deactivate',
        variant: 'warning',
      });
    },
    [confirm]
  );
}
