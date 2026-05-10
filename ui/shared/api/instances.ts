// ui/shared/api/instances.ts

import type { InstanceResponse, StepExecutionResponse } from '@/shared/types/api';
import { apiRequest } from './core';
import { getCurrentUser } from './auth';

export interface PaginatedInstanceResponse {
  items: InstanceResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface InstanceStatistics {
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  pending_steps: number;
}

export async function getInstancesByWorkflow(workflowId: string, skip = 0, limit = 100): Promise<InstanceResponse[]> {
  const safeLimit = Math.min(limit, 100);
  return apiRequest<InstanceResponse[]>(`/instances/by-workflow/${workflowId}?skip=${skip}&limit=${safeLimit}`);
}

export async function getInstances(orgId?: string, status?: string, skip = 0, limit = 25): Promise<PaginatedInstanceResponse> {
  const params = new URLSearchParams();
  if (orgId) params.append('organization_id', orgId);
  if (status) params.append('status', status);
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());
  // Endpoint derives org_id from the user token if not given.
  return apiRequest<PaginatedInstanceResponse>(`/instances/?${params.toString()}`);
}

export async function getInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}`);
}

export async function createInstance(
  workflowId: string,
  inputData: Record<string, unknown> | null = null,
  metadata: Record<string, unknown> = {}
): Promise<InstanceResponse> {
  const user = getCurrentUser();
  if (!user) {
    throw new Error('User not authenticated');
  }

  return apiRequest<InstanceResponse>('/instances/', {
    method: 'POST',
    body: JSON.stringify({
      workflow_id: workflowId,
      input_data: inputData,
      client_metadata: metadata,
      created_by: user.id,
    }),
  });
}

export async function getInstanceStatistics(instanceId: string): Promise<InstanceStatistics> {
  return apiRequest<InstanceStatistics>(`/instances/${instanceId}/statistics`);
}

export async function deleteInstance(instanceId: string): Promise<void> {
  await apiRequest(`/instances/${instanceId}`, { method: 'DELETE' });
}

export async function startInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/start`, {
    method: 'POST',
  });
}

export async function pauseInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/pause`, {
    method: 'POST',
  });
}

export async function resumeInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/resume`, {
    method: 'POST',
  });
}

export async function runStoppedStep(instanceId: string, stepId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/${instanceId}/run-step/${stepId}`, {
    method: 'POST',
  });
}

export async function cancelInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/cancel`, {
    method: 'POST',
  });
}

export async function completeInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/complete`, {
    method: 'POST',
  });
}

export async function failInstance(instanceId: string): Promise<InstanceResponse> {
  return apiRequest<InstanceResponse>(`/instances/${instanceId}/fail`, {
    method: 'POST',
  });
}

export async function approveInstance(
  instanceId: string,
  approved: boolean = true,
  comment?: string
): Promise<{
  instance_id: string;
  step_id: string;
  approved: boolean;
  status: string;
  message: string;
}> {
  return apiRequest(`/instances/${instanceId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved, comment }),
  });
}

export async function triggerStep(
  instanceId: string,
  stepId: string
): Promise<{
  instance_id: string;
  step_id: string;
  status: string;
  message: string;
}> {
  return apiRequest(`/instances/${instanceId}/step_executions/${stepId}/trigger`, {
    method: 'POST',
  });
}

export async function getJobsForInstance(instanceId: string, skip = 0, limit = 100): Promise<StepExecutionResponse[]> {
  return apiRequest<StepExecutionResponse[]>(`/instances/${instanceId}/step_executions?skip=${skip}&limit=${limit}`);
}

export async function getJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}`);
}

export async function createJob(instanceId: string, jobData: Record<string, unknown>): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/${instanceId}/step_executions`, {
    method: 'POST',
    body: JSON.stringify(jobData),
  });
}

export async function startJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/start`, {
    method: 'POST',
  });
}

export async function completeJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/complete`, {
    method: 'POST',
  });
}

export async function failJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/fail`, {
    method: 'POST',
  });
}

export async function cancelJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/cancel`, {
    method: 'POST',
  });
}

export async function retryJob(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/retry`, {
    method: 'POST',
  });
}

/** Rerun this step only; downstream results stay intact. */
export async function rerunJobOnly(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/rerun-only`, {
    method: 'POST',
  });
}

/** Rerun this step and propagate to all downstream dependents. */
export async function rerunAndContinue(jobId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/rerun-and-continue`, {
    method: 'POST',
  });
}

/** Rerun all jobs for a step without triggering downstream steps. */
export async function rerunStepOnly(instanceId: string, stepId: string): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/${instanceId}/step_executions/${stepId}/rerun`, {
    method: 'POST',
  });
}

/** Edit a step's output payload for downstream consumption. */
export async function updateJobResult(jobId: string, result: Record<string, unknown>): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/step_executions/${jobId}/result`, {
    method: 'PATCH',
    body: JSON.stringify({ result }),
  });
}

/**
 * Delete the listed resources and re-queue the job with the resulting batch size.
 */
export async function regenerateResources(
  instanceId: string,
  stepId: string,
  resourceIds: string[],
  parameterOverrides: Record<string, unknown> = {}
): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(`/instances/${instanceId}/step_executions/${stepId}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ resource_ids: resourceIds, parameter_overrides: parameterOverrides }),
  });
}

/**
 * Regenerate a single iteration. Handles both the crash case (0 files) and the redo
 * case (replace existing files).
 */
export async function regenerateIteration(
  instanceId: string,
  stepId: string,
  iterationIndex: number,
  parameterOverrides: Record<string, unknown> = {}
): Promise<StepExecutionResponse> {
  return apiRequest<StepExecutionResponse>(
    `/instances/${instanceId}/step_executions/${stepId}/regenerate-iteration`,
    {
      method: 'POST',
      body: JSON.stringify({ iteration_index: iterationIndex, parameter_overrides: parameterOverrides }),
    }
  );
}
