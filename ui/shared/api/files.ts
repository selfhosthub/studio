// ui/shared/api/files.ts

import { API_VERSION } from '@/shared/lib/config';
import { apiRequest, apiFetchBlob } from './core';
import { getCurrentUser } from './auth';
import { getOrganizationWorkflows } from './workflows';

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
  is_selected?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface DashboardStats {
  workflows: number;
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
    getOrganizationWorkflows(),
    apiRequest<Array<{ is_active: boolean }>>(`/organizations/${effectiveOrgId}/members`).catch(() => null),
  ]);

  return {
    workflows: workflows.length,
    members: membersResult?.filter((m) => m.is_active).length ?? 0,
    canViewMembers: membersResult !== null,
  };
}

export interface FileListResponse {
  items: FileResource[];
  total: number;
  skip: number;
  limit: number;
}

export type FileSortField = 'name' | 'date' | 'size' | 'type' | 'source' | 'thumb' | 'status';

export interface FileListQuery {
  search?: string;
  fileType?: string;
  source?: string;
  sortBy?: FileSortField;
  sortDir?: 'asc' | 'desc';
}

export async function getFiles(page: number = 1, limit: number = 20, query: FileListQuery = {}): Promise<FileListResponse> {
  const params = new URLSearchParams({ skip: String((page - 1) * limit), limit: String(limit) });
  const search = query.search?.trim();
  if (search) params.set('search', search);
  if (query.fileType && query.fileType !== 'all') params.set('file_type', query.fileType);
  if (query.source && query.source !== 'all') params.set('source', query.source);
  if (query.sortBy) params.set('sort_by', query.sortBy);
  if (query.sortDir) params.set('sort_dir', query.sortDir);
  return apiRequest<FileListResponse>(`/files?${params.toString()}`);
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

export interface FileRunUsage {
  instance_id: string;
  instance_name: string;
  step_name: string | null;
  file_count: number;
}

/** Run steps holding any of the given files; files in no run are absent. */
export async function getFilesUsage(fileIds: string[]): Promise<FileRunUsage[]> {
  const params = new URLSearchParams();
  fileIds.forEach((id) => params.append('ids', id));
  const usage = await apiRequest<{ runs: FileRunUsage[] }>(`/files/usage?${params.toString()}`);
  return usage.runs;
}

/** Admin only. */
export async function deleteFile(fileId: string): Promise<void> {
  await apiRequest(`/files/${fileId}`, { method: 'DELETE' });
}

/** Keep-variants: make this file the selected variant for its slot; deselects siblings. */
export async function selectFile(fileId: string): Promise<FileResource> {
  return apiRequest<FileResource>(`/files/${fileId}/select`, { method: 'PATCH' });
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
  const formData = new FormData();
  formData.append('file', file);
  return apiRequest<FileResource>(`/files/${fileId}/replace`, { method: 'POST', body: formData });
}

export async function uploadFiles(files: File | File[]): Promise<FileResource[]> {
  const formData = new FormData();
  for (const file of Array.isArray(files) ? files : [files]) {
    formData.append('files', file);
  }
  return apiRequest<FileResource[]>('/files/upload', { method: 'POST', body: formData });
}

/** Legacy single-file alias for uploadFiles. */
export async function uploadFile(file: File): Promise<FileResource> {
  const results = await uploadFiles(file);
  return results[0];
}

export async function uploadFilesToStep(instanceId: string, stepId: string, files: File[]): Promise<FileResource[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }
  return apiRequest<FileResource[]>(
    `/instances/${instanceId}/step_executions/${stepId}/upload`,
    { method: 'POST', body: formData },
  );
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
export const selectResource = selectFile;
