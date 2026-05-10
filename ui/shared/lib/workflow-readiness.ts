// ui/shared/lib/workflow-readiness.ts

/** Client-side dependency check - avoids per-workflow credential round-trips when only provider/prompt presence matters. */

import type { WorkflowResponse, WorkflowStep, InputMapping } from '@/shared/types/api';

export interface WorkflowIssue {
  stepId: string;
  stepName: string;
  type: 'provider_missing' | 'prompt_missing';
  message: string;
}

function formatProviderSlug(slug: string): string {
  return slug
    .split(/[-_]/)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** `activeProviderIds` must include both UUIDs and slugs - copied workflows may still reference a slug until the provider is installed. */
export function checkWorkflowReadiness(
  workflow: WorkflowResponse,
  activeProviderIds: Set<string>,
  activePromptIds: Set<string>,
): WorkflowIssue[] {
  const issues: WorkflowIssue[] = [];

  // Steps may be an array or a {step_id: step_config} dict depending on the API path.
  const rawSteps = workflow.steps || [];
  const steps: WorkflowStep[] = Array.isArray(rawSteps)
    ? rawSteps
    : Object.values(rawSteps);

  for (const step of steps) {
    // provider_id / service_id may be at step level or nested in job (catalog-imported).
    const job = (step as any).job as
      | { provider_id?: string; service_id?: string }
      | undefined;
    const providerId = step.provider_id || job?.provider_id;
    const serviceId = step.service_id || job?.service_id;

    if (providerId && !activeProviderIds.has(providerId)) {
      let providerName = step.name;
      if (serviceId && serviceId.includes('.')) {
        providerName = formatProviderSlug(serviceId.split('.')[0]);
      }

      issues.push({
        stepId: step.id,
        stepName: step.name,
        type: 'provider_missing',
        message: providerName,
      });
    }

    if (step.input_mappings) {
      for (const [, mapping] of Object.entries(step.input_mappings)) {
        if (mapping?.mappingType === 'prompt') {
          const slug = (mapping as { promptSlug?: string }).promptSlug;
          const label = slug ? `prompt:${slug}` : 'Prompt';
          if (!mapping.promptId) {
            issues.push({
              stepId: step.id,
              stepName: step.name,
              type: 'prompt_missing',
              message: label,
            });
          } else if (!activePromptIds.has(mapping.promptId)) {
            issues.push({
              stepId: step.id,
              stepName: step.name,
              type: 'prompt_missing',
              message: label,
            });
          }
        }
      }
    }
  }

  return issues;
}
