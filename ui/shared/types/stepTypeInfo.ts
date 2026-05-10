// ui/shared/types/stepTypeInfo.ts

/**
 * @deprecated Step types are obsolete. All steps are 'task' and execute a service;
 * orchestration (pause, branch, stop) comes from orchestrator_hints on the service.
 * Kept only for legacy workflows that still carry step_type in their JSON.
 */

import type { Step } from '@/shared/types/workflow';

/** @deprecated All steps should be 'task'. */
export type StepType = NonNullable<Step['type']>;

export interface StepTypeFieldVisibility {
  showProvider: boolean;
  showService: boolean;
  showServiceType: boolean;
  providerRequired: boolean;
  serviceRequired: boolean;
  serviceTypeRequired: boolean;
}

/** @deprecated All step types collapse to 'task' rules. Trigger is the one virtual exception. */
export const stepTypeFieldRules: Record<StepType, StepTypeFieldVisibility> = {
  task: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  notification: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  approval: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  decision: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  condition: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  webhook: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  api_call: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  script: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  container: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },
  function: {
    showProvider: true,
    showService: true,
    showServiceType: true,
    providerRequired: true,
    serviceRequired: true,
    serviceTypeRequired: true,
  },

  // Trigger is virtual - represents incoming webhook payload data, has no provider.
  trigger: {
    showProvider: false,
    showService: false,
    showServiceType: false,
    providerRequired: false,
    serviceRequired: false,
    serviceTypeRequired: false,
  },
};

/** @deprecated Always returns the task rules. */
export function getStepTypeFieldRules(stepType?: string): StepTypeFieldVisibility {
  return stepTypeFieldRules.task;
}

/** @deprecated Do not surface in new UI. */
export const stepTypeDescriptions: Record<StepType, string> = {
  task: 'Execute a service (standard step type)',
  webhook: 'DEPRECATED: Use the webhook-wait service',
  approval: 'DEPRECATED: Use the approval service',
  decision: 'DEPRECATED: Use conditional services',
  condition: 'DEPRECATED: Use conditional services',
  notification: 'DEPRECATED: Use notification services',
  api_call: 'DEPRECATED: Use the http post service',
  script: 'DEPRECATED: Use script execution services',
  container: 'DEPRECATED: Use container services',
  function: 'DEPRECATED: Use serverless services',
  trigger: 'Virtual step representing incoming data (webhook payload, etc.)',
};
