// ui/app/(authenticated)/providers/components/providerUsage.ts

import { checkPackageUsage } from '@/shared/api';

// Workflow count for a provider package, or 0 when the usage check fails
export async function providerWorkflowCount(slug: string): Promise<number> {
  try {
    return (await checkPackageUsage(slug)).workflow_count;
  } catch (err) {
    console.error('Failed to check package usage:', err);
    return 0;
  }
}

// "N workflow(s)" with the noun matching the count
export function workflowsNoun(count: number): string {
  return `${count} ${count === 1 ? 'workflow' : 'workflows'}`;
}

// Why Remove is unavailable while workflows use the provider, or null when none do
export function removeBlockedReason(count: number): string | null {
  return count > 0 ? `Used by ${workflowsNoun(count)}. Remove its nodes from those workflows first.` : null;
}
