// ui/shared/api/files.ts

import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import { apiRequest, apiFetchBlob } from './core';
import { getCurrentUser } from './auth';

export interface FileResource {
  id: string;
  filename?: string;
  file_extension?: string;
  file_size?: number;
  mime_type?: string;
  content_type?: string;
  size_bytes?: number;
  checksum?: string | null;
  virtual_path?: string;
  display_name?: string;
  display_order?: number;
  source?: string;
  status?: string;
  job_execution_id?: string;
  instance_id?: string;
  job_id?: string;
  step_id?: string;
  organization_id?: string;
  provider_id?: string | null;
  provider_resource_id?: string | null;
  provider_url?: string | null;
  download_timestamp?: string | null;
  download_url?: string;
  preview_url?: string | null;
  metadata?: Record<string, unknown>;
  has_thumbnail?: boolean;
  created_at?: string;
  updated_at?: string;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

export interface DashboardStats {
  workflows: number;
  blueprints: number;
  members: number;
  canViewMembers: boolean;
}

export async function getDashboardStats(orgId?: string): Promise<DashboardStats> {
  const currentUser = getCurrentUser();
  const effectiveOrgId = orgId || currentUser?.org_id;

  if (!effectiveOrgId) {
    throw new Error('Organization ID required for dashboard statistics');
  }

  // Members requires admin; swallow that failure so non-admin users still see workflows.
  const [workflows, membersResult] = await Promise.all([
    apiRequest<Array<{ status: string }>>('/workflows/'),
    apiRequest<unknown[]>(`/organizations/${effectiveOrgId}/members`).catch(() => null),
  ]);

  const activeWorkflows = workflows.filter((w) => w.status === 'active');

  return {
    workflows: activeWorkflows.length,
    blueprints: 0,
    members: membersResult?.length ?? 0,
    canViewMembers: membersResult !== null,
  };
}

export async function getFiles(page: number = 1, limit: number = 20): Promise<FileResource[]> {
  const skip = (page - 1) * limit;
  return apiRequest<FileResource[]>(`/files?skip=${skip}&limit=${limit}`);
}

export async function getInstanceFiles(instanceId: string, status?: string, source?: string): Promise<FileResource[]> {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (source) params.append('source', source);
  const query = params.toString();
  return apiRequest<FileResource[]>(`/instances/${instanceId}/files${query ? `?${query}` : ''}`);
}

export async function getJobFiles(jobId: string): Promise<FileResource[]> {
  return apiRequest<FileResource[]>(`/jobs/${jobId}/files`);
}

export async function downloadFile(fileId: string): Promise<Blob> {
  return apiFetchBlob(`${API_VERSION}/files/${fileId}/download`);
}

/** Admin only. */
export async function deleteFile(fileId: string): Promise<void> {
  await apiRequest(`/files/${fileId}`, { method: 'DELETE' });
}

export async function reorderJobFiles(jobId: string, resourceIds: string[]): Promise<FileResource[]> {
  return apiRequest<FileResource[]>(`/jobs/${jobId}/files/reorder`, {
    method: 'PATCH',
    body: JSON.stringify({ resource_ids: resourceIds }),
  });
}

/**
 * Reorder files across all iteration jobs of a step. Use this for iteration workflows
 * where resources span multiple jobs but must be reordered together.
 */
export async function reorderStepFiles(stepId: string, resourceIds: string[]): Promise<FileResource[]> {
  return apiRequest<FileResource[]>(`/steps/${stepId}/files/reorder`, {
    method: 'PATCH',
    body: JSON.stringify({ resource_ids: resourceIds }),
  });
}

export async function replaceFile(fileId: string, file: File): Promise<FileResource> {
  const token = getToken();
  const url = `${getApiUrl()}${API_VERSION}/files/${fileId}/replace`;

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to replace file: ${response.status} ${errorText}`);
  }

  return response.json();
}

export async function uploadFiles(files: File | File[]): Promise<FileResource[]> {
  const token = getToken();
  const url = `${getApiUrl()}${API_VERSION}/files/upload`;

  const formData = new FormData();
  const fileArray = Array.isArray(files) ? files : [files];
  for (const file of fileArray) {
    formData.append('files', file);
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to upload files: ${response.status} ${errorText}`);
  }

  return response.json();
}

/** Legacy single-file alias for uploadFiles. */
export async function uploadFile(file: File): Promise<FileResource> {
  const results = await uploadFiles(file);
  return results[0];
}

export async function uploadFilesToStep(instanceId: string, stepId: string, files: File[]): Promise<FileResource[]> {
  const token = getToken();
  const url = `${getApiUrl()}${API_VERSION}/instances/${instanceId}/step_executions/${stepId}/upload`;

  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to upload files: ${response.status} ${errorText}`);
  }

  return response.json();
}

export async function addFilesFromLibraryToStep(
  instanceId: string,
  stepId: string,
  resourceIds: string[]
): Promise<FileResource[]> {
  return apiRequest<FileResource[]>(`/instances/${instanceId}/step_executions/${stepId}/add-from-library`, {
    method: 'POST',
    body: JSON.stringify({ resource_ids: resourceIds }),
  });
}

/** Bridge the type gap - runtime shape is identical between the two. */
export function asOutputResources(files: FileResource[]): import('@/shared/types/api').OrgFile[] {
  return files as unknown as import('@/shared/types/api').OrgFile[];
}

export function asOutputResource(file: FileResource): import('@/shared/types/api').OrgFile {
  return file as unknown as import('@/shared/types/api').OrgFile;
}

export const getResources = getFiles;
export const getInstanceResources = getInstanceFiles;
export const getJobResources = getJobFiles;
export const downloadResource = downloadFile;
export const deleteResource = deleteFile;
