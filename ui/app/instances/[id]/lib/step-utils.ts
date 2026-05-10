// ui/app/instances/[id]/lib/step-utils.ts

/**
 * Utility functions for the instance detail page.
 *
 * The server emits ordered+enriched StepExecutionResponse[] via
 * InstanceResponse.steps (see api/app/application/dtos/instance_dto.py),
 * so each step row carries the worker-attempt fields directly. The merged
 * DTO already carries `name` from server enrichment, and the worker-attempt
 * fields are surfaced via `useStepData.selectedStepExecution` which reads
 * the parallel `jobs: Job[]` collection by step_id.
 */

import type { StepExecutionResponse } from '@/shared/types/api';
import type { WorkflowStep } from './types';

/**
 * Check if a service is expected to produce file outputs (images, videos, etc.)
 * Used to show split layout even while step is running.
 */
export function serviceProducesFiles(serviceId?: string, providerId?: string, serviceType?: string): boolean {
  // Service type based detection (most reliable)
  if (serviceType) {
    const fileProducingServiceTypes = [
      'image_generation',
      'video_generation',
      'audio_generation',
      'text_to_speech',
      'speech_to_text',
      'storage',
    ];
    const normalizedType = serviceType.toLowerCase().replace(/-/g, '_');
    if (fileProducingServiceTypes.some(t => normalizedType.includes(t))) {
      return true;
    }
  }

  // Service ID based detection (check for file-producing service patterns)
  if (serviceId) {
    const fileProducingServicePatterns = [
      'txt2img',
      'img2img',
      'image_generation',
      'video_generation',
      'create_video',
      'render',
      'generate_image',
      'text_to_speech',
      'tts',
      'audio',
      'video',
      'image',
    ];
    const normalizedService = serviceId.toLowerCase();
    if (fileProducingServicePatterns.some(s => normalizedService.includes(s))) {
      return true;
    }
  }

  // Provider name based detection (fallback for provider-specific patterns)
  if (providerId) {
    const fileProducingProviders = [
      'comfyui',
    ];
    const normalizedProvider = providerId.toLowerCase();
    if (fileProducingProviders.some(p => normalizedProvider.includes(p))) {
      return true;
    }
  }

  return false;
}

const ALLOWED_STEP_STATUSES = new Set<WorkflowStep['status']>([
  'pending',
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
  'waiting_for_approval',
  'waiting_for_manual_trigger',
  'stopped',
]);

function coerceStepStatus(raw: string): WorkflowStep['status'] {
  const normalized = (raw || '').toLowerCase() as WorkflowStep['status'];
  return ALLOWED_STEP_STATUSES.has(normalized) ? normalized : 'pending';
}

/**
 * Coerce the server-emitted `InstanceResponse.steps` (already ordered and
 * enriched with depends_on / service_id / provider_id / parameters / status
 * sourced from the oracle) into the UI-local `WorkflowStep[]` shape.
 *
 * The shapes are nearly identical - this helper exists solely to coerce
 * `status: string` to the typed `WorkflowStep['status']` union and to
 * substitute defaults for nullable enrichment fields the UI treats as
 * `undefined`. No data join, no name override, no status mutation.
 */
export function coerceWorkflowSteps(
  steps: StepExecutionResponse[]
): WorkflowStep[] {
  return steps.map((step): WorkflowStep => ({
    step_id: step.step_id,
    name: (step.name || step.step_id) as string,
    depends_on: step.depends_on ?? [],
    service_id: step.service_id ?? undefined,
    provider_id: step.provider_id ?? undefined,
    service_type: step.service_type ?? undefined,
    status: coerceStepStatus(step.status),
    execution_mode: step.execution_mode as WorkflowStep['execution_mode'] | undefined,
    trigger_type: step.trigger_type as WorkflowStep['trigger_type'] | undefined,
    parameters: step.parameters ?? {},
    // input_mappings value shape is richer than Record<string,string> in
    // practice - server permits mapping-config dicts; UI consumers only
    // iterate entries so the cast is safe for the existing WorkflowStep shape.
    input_mappings: (step.input_mappings ?? {}) as Record<string, string>,
  }));
}

/**
 * Calculate human-readable duration string between two timestamps.
 */
export function calculateDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return "N/A";
  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const durationMs = end.getTime() - start.getTime();

  const minutes = Math.floor(durationMs / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(durationMs / 1000)}s`;
}
