// ui/shared/api/workflows.ts

import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import type { WorkflowResponse } from '@/shared/types/api';
import type { FormFieldType } from '@/entities/workflow';
import { apiRequest, getToken } from './core';

export interface CredentialIssue {
  step_id: string;
  step_name: string;
  provider_id: string;
  provider_name: string;
  status: 'not_connected' | 'reauthorize_required' | 'inactive' | 'provider_not_installed' | 'prompt_missing';
  message: string;
  action_url: string;
}

export interface CredentialCheckResponse {
  ready: boolean;
  issues: CredentialIssue[];
}

export interface FormFieldConfigResponse {
  label: string;
  placeholder?: string;
  description?: string;
  required: boolean;
  field_type: FormFieldType;
  default_value?: any;
  options?: { value: string; label: string }[];
  item_type?: string;
  key_placeholder?: string;
  value_placeholder?: string;
  add_label?: string;
  min_length?: number;
  max_length?: number;
  min?: number;
  max?: number;
  accepted_file_types?: string[];
  max_file_size_mb?: number;
  /** Layout hint; 'half' pairs with the next adjacent half-sized field on the same row. */
  size?: 'small' | 'medium' | 'large' | 'full' | 'half';
}

export interface FormFieldResponse {
  parameter_key: string;
  step_id: string;
  step_name: string;
  step_order: number;
  config: FormFieldConfigResponse;
}

export interface WorkflowFormSchemaResponse {
  workflow_id: string;
  workflow_name: string;
  has_form_fields: boolean;
  fields: FormFieldResponse[];
}

export async function getWorkflows(orgId?: string, skip = 0, limit = 100, scope?: string): Promise<WorkflowResponse[]> {
  const params = new URLSearchParams();
  if (orgId) params.append('organization_id', orgId);
  if (scope) params.append('scope', scope);
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());
  return apiRequest<WorkflowResponse[]>(`/workflows/?${params.toString()}`);
}

export async function getPersonalWorkflows(skip = 0, limit = 100): Promise<WorkflowResponse[]> {
  return getWorkflows(undefined, skip, limit, 'personal');
}

export async function getOrganizationWorkflows(skip = 0, limit = 100): Promise<WorkflowResponse[]> {
  return getWorkflows(undefined, skip, limit, 'organization');
}

export async function getWorkflowsByBlueprint(blueprintId: string, skip = 0, limit = 100): Promise<any[]> {
  return apiRequest<any[]>(`/workflows/by-blueprint/${blueprintId}?skip=${skip}&limit=${limit}`);
}

export async function createWorkflow(workflowData: { name: string } & Record<string, unknown>): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>('/workflows/', {
    method: 'POST',
    body: JSON.stringify(workflowData),
  });
}

export async function getWorkflow(workflowId: string): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}`);
}

export async function updateWorkflow(workflowId: string, updates: Record<string, unknown>): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await apiRequest(`/workflows/${workflowId}`, { method: 'DELETE' });
}

export async function generateWorkflowWebhookToken(workflowId: string): Promise<{
  webhook_token: string;
  webhook_secret: string;
  webhook_url: string;
}> {
  return apiRequest<any>(`/workflows/${workflowId}/webhook-token`, {
    method: 'POST',
  });
}

/** Regenerate invalidates the old token immediately. */
export async function regenerateWorkflowWebhookToken(workflowId: string): Promise<{
  webhook_token: string;
  webhook_secret: string;
  webhook_url: string;
}> {
  return apiRequest<any>(`/workflows/${workflowId}/webhook-token/regenerate`, {
    method: 'POST',
  });
}

export async function deleteWorkflowWebhookToken(workflowId: string): Promise<void> {
  await apiRequest(`/workflows/${workflowId}/webhook-token`, {
    method: 'DELETE',
  });
}

export async function generateStepWebhookToken(workflowId: string, stepId: string): Promise<{
  step_id: string;
  webhook_token: string;
  webhook_secret: string;
  webhook_url: string;
}> {
  return apiRequest<any>(`/workflows/${workflowId}/steps/${stepId}/webhook-token`, {
    method: 'POST',
  });
}

/** Regenerate invalidates the old token immediately. */
export async function regenerateStepWebhookToken(workflowId: string, stepId: string): Promise<{
  step_id: string;
  webhook_token: string;
  webhook_secret: string;
  webhook_url: string;
}> {
  return apiRequest<any>(`/workflows/${workflowId}/steps/${stepId}/webhook-token/regenerate`, {
    method: 'POST',
  });
}

/** Returns null on 404 so callers can branch on "no token configured yet". */
export async function getStepWebhookToken(workflowId: string, stepId: string): Promise<{
  step_id: string;
  webhook_token: string;
  webhook_secret: string;
  webhook_url: string;
} | null> {
  try {
    return await apiRequest<any>(`/workflows/${workflowId}/steps/${stepId}/webhook-token`);
  } catch (error: unknown) {
    if (error instanceof Error && 'status' in error && (error as Error & { status: number }).status === 404) {
      return null;
    }
    throw error;
  }
}

export async function checkWorkflowCredentials(workflowId: string): Promise<CredentialCheckResponse> {
  return apiRequest<CredentialCheckResponse>(`/workflows/${workflowId}/credentials/check`);
}

export async function getWorkflowFormSchema(workflowId: string): Promise<WorkflowFormSchemaResponse> {
  return apiRequest<WorkflowFormSchemaResponse>(`/workflows/${workflowId}/form-schema`);
}

/** formValues are keyed by "{step_id}.{parameter_key}". */
export async function submitFormAndStart(instanceId: string, formValues: Record<string, any>): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/instances/${instanceId}/submit-form`, {
    method: 'POST',
    body: JSON.stringify({ form_values: formValues }),
  });
}

export async function exportWorkflow(workflowId: string, workflowName: string): Promise<void> {
  const token = getToken();
  const url = `${getApiUrl()}${API_VERSION}/workflows/${workflowId}/export`;
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to export workflow: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `${workflowName}.json`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(downloadUrl);
  document.body.removeChild(a);
}

export async function importWorkflow(file: File, organizationId?: string): Promise<{
  workflow: any;
  warnings: string[];
}> {
  const token = getToken();
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  if (organizationId) params.append('organization_id', organizationId);

  const url = `${getApiUrl()}${API_VERSION}/workflows/import${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to import workflow: ${response.status}`);
  }

  return response.json();
}

/** Copy a workflow into the current user's personal scope. */
export async function copyWorkflow(workflowId: string): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}/copy`, {
    method: 'POST',
  });
}

export async function requestPublish(workflowId: string): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}/request-publish`, {
    method: 'POST',
  });
}

/** Admin only. */
export async function approvePublish(workflowId: string): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}/approve-publish`, {
    method: 'POST',
  });
}

/** Admin only. */
export async function rejectPublish(workflowId: string): Promise<WorkflowResponse> {
  return apiRequest<WorkflowResponse>(`/workflows/${workflowId}/reject-publish`, {
    method: 'POST',
  });
}

/** Admin only. */
export async function getPendingPublish(skip = 0, limit = 100): Promise<WorkflowResponse[]> {
  return apiRequest<WorkflowResponse[]>(`/workflows/pending-publish?skip=${skip}&limit=${limit}`);
}

export interface MarketplaceWorkflow {
  id: string;
  display_name: string;
  version: string;
  tier: string;
  category: string;
  description: string;
  requires: string[];
  requires_prompts?: string[];
  author: string;
  download_url?: string;
  requirements_met: boolean;
  missing_packages: string[];
  missing_prompts?: string[];
}

export interface WorkflowsCatalog {
  version: string;
  workflows: MarketplaceWorkflow[];
  filter_options: { [key: string]: string[] };
  warnings?: string[];
}

export interface InstalledWorkflowInfo {
  marketplace_id: string;
  workflow_id: string;
  name: string;
}

export interface InstalledWorkflowsResponse {
  installed_ids: string[];
  installed_workflows: InstalledWorkflowInfo[];
}

export interface WorkflowInstallResponse {
  success: boolean;
  workflow_id?: string;
  workflow_name?: string;
  message: string;
  missing_packages: string[];
  missing_prompts?: string[];
  already_installed: boolean;
}

export async function getWorkflowsCatalog(): Promise<WorkflowsCatalog> {
  return apiRequest<WorkflowsCatalog>('/workflows/marketplace/catalog');
}

export async function getInstalledWorkflows(): Promise<InstalledWorkflowsResponse> {
  return apiRequest<InstalledWorkflowsResponse>('/workflows/marketplace/installed');
}

export async function installWorkflowFromMarketplace(workflowId: string): Promise<WorkflowInstallResponse> {
  return apiRequest<WorkflowInstallResponse>(`/workflows/marketplace/install/${workflowId}`, {
    method: 'POST',
  });
}

export async function uninstallMarketplaceWorkflow(workflowId: string): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>(`/workflows/marketplace/uninstall/${workflowId}`, {
    method: 'POST',
  });
}

/** Super admin only. */
export async function refreshWorkflowsCatalog(): Promise<{ success: boolean; version: string; workflow_count: number; message: string }> {
  return apiRequest<{ success: boolean; version: string; workflow_count: number; message: string }>('/workflows/marketplace/catalog/refresh', {
    method: 'POST',
  });
}
