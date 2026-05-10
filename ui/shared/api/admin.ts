// ui/shared/api/admin.ts

/** Super-admin API: system health, infrastructure, audit, marketplace/packages. */

import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import { apiRequest } from './core';
import { getAuthHeaders } from './auth';
import type {
  MarketplaceCatalog,
  MarketplacePackage,
  EntitlementTokenStatus,
} from '@/shared/types/provider';

export interface JobStats {
  total_pending: number;
  total_running: number;
  total_completed: number;
  total_failed: number;
  long_running_jobs: Array<{
    organization_name: string;
    organization_slug: string;
    instance_id: string;
    instance_name: string;
    step_id: string;
    running_minutes: number;
    started_at: string | null;
  }>;
  jobs_without_worker: Array<{
    organization_name: string;
    organization_slug: string;
    instance_id: string;
    instance_name: string;
    step_id: string;
    enqueued_at: string | null;
  }>;
  by_workflow: Record<string, {
    pending: number;
    running: number;
    completed: number;
    failed: number;
  }>;
}

export interface WebSocketStats {
  total_connections: number;
  organizations_connected: number;
  users_connected: number;
}

export interface StorageStats {
  backend: string;
  total_files: number;
  total_size_bytes: number;
  total_size_formatted: string;
  capacity_bytes?: number | null;
  capacity_formatted?: string | null;
  capacity_used_percent?: number | null;
  workspace_path?: string | null;
  by_organization: Record<string, {
    files: number;
    size_bytes: number;
    size_formatted: string;
  }>;
}

export interface WorkerStats {
  total_registered: number;
  online: number;
  offline: number;
  workers: Array<{
    worker_id: string;
    status: string;
    ttl_seconds: number;
  }>;
}

export interface PlatformStats {
  total_organizations: number;
  active_users: number;
  running_instances: number;
}

export interface SystemHealthResponse {
  timestamp: string;
  websocket: WebSocketStats;
  job_stats?: JobStats | null;
  storage: StorageStats;
  workers: WorkerStats;
  database_connected: boolean;
  platform?: PlatformStats;
}

export interface DatabaseStats {
  healthy: boolean;
  status: 'healthy' | 'degraded' | 'unhealthy';
  version?: string | null;
  uptime?: string | null;
  uptime_seconds?: number | null;
  active_connections: number;
  max_connections: number;
  connection_usage_percent?: number | null;
  database_size?: string | null;
  database_size_bytes?: number | null;
  total_organizations: number;
  total_users: number;
  total_workflows: number;
  total_blueprints: number;
  total_instances: number;
  total_providers: number;
  total_credentials: number;
  slow_queries: number;
  cache_hit_ratio?: number | null;
}

export interface OrganizationStorageItem {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  files: number;
  size_bytes: number;
  size_formatted: string;
  storage_limit_bytes?: number | null;
  storage_limit_formatted?: string | null;
  usage_percent?: number | null;
}

export interface PaginatedStorageResponse {
  items: OrganizationStorageItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  total_size_bytes: number;
  total_size_formatted: string;
  total_files: number;
}

export type StorageSortField = 'name' | 'files' | 'size_bytes' | 'usage_percent';
export type SortOrder = 'asc' | 'desc';

export async function getSystemHealth(): Promise<SystemHealthResponse> {
  return apiRequest<SystemHealthResponse>('/infrastructure/health');
}

export async function getStorageHealth(): Promise<StorageStats> {
  return apiRequest<StorageStats>('/infrastructure/health/storage');
}

export async function getWorkersHealth(): Promise<WorkerStats> {
  return apiRequest<WorkerStats>('/infrastructure/health/workers');
}

/** Worker is signalled via its next heartbeat and is expected to stop gracefully. */
export async function deregisterWorker(workerId: string): Promise<{ status: string; message: string }> {
  return apiRequest<{ status: string; message: string }>(`/infrastructure/health/workers/${workerId}/deregister`, {
    method: 'POST',
  });
}

/** @deprecated Use deregisterWorker. */
export const deleteWorker = deregisterWorker;

export async function getDatabaseStats(): Promise<DatabaseStats> {
  return apiRequest<DatabaseStats>('/infrastructure/health/database');
}

export async function getOrganizationStorage(
  page: number = 1,
  perPage: number = 10,
  sortBy: StorageSortField = 'size_bytes',
  sortOrder: SortOrder = 'desc'
): Promise<PaginatedStorageResponse> {
  return apiRequest<PaginatedStorageResponse>(
    `/infrastructure/health/storage/organizations?page=${page}&per_page=${perPage}&sort_by=${sortBy}&sort_order=${sortOrder}`
  );
}

export async function getMarketplaceCatalog(): Promise<MarketplaceCatalog> {
  return apiRequest<MarketplaceCatalog>('/marketplace/catalog');
}

export async function getMarketplacePackage(packageId: string): Promise<MarketplacePackage> {
  return apiRequest<MarketplacePackage>(`/marketplace/packages/${packageId}`);
}

/** Indicates whether ENTITLEMENT_TOKEN is set. */
export async function getEntitlementTokenStatus(): Promise<EntitlementTokenStatus> {
  return apiRequest<EntitlementTokenStatus>('/marketplace/token-status');
}

export interface CatalogRefreshResponse {
  success: boolean;
  version: string | null;
  package_count: number;
  source_url: string;
  message: string;
}

export async function refreshProvidersCatalog(): Promise<CatalogRefreshResponse> {
  return apiRequest<CatalogRefreshResponse>('/marketplace/catalog/refresh', {
    method: 'POST',
  });
}

export interface PackageInstallResponse {
  success: boolean;
  package_name: string;
  version: string;
  provider_name: string;
  provider_id: string;
  services_installed: string[];
  error?: string;
}

export interface InstallFromUrlRequest {
  url: string;
  use_token?: boolean;
}

export interface PackageUsageInfo {
  package_name: string;
  provider_slug: string | null;
  provider_id: string | null;
  workflow_count: number;
  blueprint_count: number;
  affected_orgs: string[];
  details: Array<{
    type: 'workflow' | 'blueprint';
    id: string;
    name: string;
    org_name: string;
    org_slug: string;
  }>;
}

export interface UninstallResponse {
  success: boolean;
  message: string;
  workflows_affected: number;
  blueprints_affected: number;
}

/** Uploads a JSON provider definition and installs it. */
export async function uploadPackage(file: File): Promise<PackageInstallResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const authHeaders = getAuthHeaders();
  const response = await fetch(`${getApiUrl()}${API_VERSION}/packages/upload`, {
    method: 'POST',
    headers: authHeaders,
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Upload failed: ${response.status}`);
  }

  return response.json();
}

export async function installPackageFromUrl(
  url: string,
  useToken: boolean = false
): Promise<PackageInstallResponse> {
  return apiRequest<PackageInstallResponse>('/packages/install-from-url', {
    method: 'POST',
    body: JSON.stringify({ url, use_token: useToken }),
  });
}

export async function installPackageFromPath(
  packageId: string,
  useToken: boolean = false
): Promise<PackageInstallResponse> {
  return apiRequest<PackageInstallResponse>('/packages/install-from-path', {
    method: 'POST',
    body: JSON.stringify({ package_id: packageId, use_token: useToken }),
  });
}

/** Pre-uninstall check - returns affected workflows and blueprints. */
export async function checkPackageUsage(packageName: string): Promise<PackageUsageInfo> {
  return apiRequest<PackageUsageInfo>(`/packages/${packageName}/usage`);
}

export async function uninstallPackage(packageName: string, force: boolean = false): Promise<UninstallResponse> {
  return apiRequest<UninstallResponse>(`/packages/${packageName}?force=${force}`, {
    method: 'DELETE',
  });
}

export interface AuditEvent {
  id: string;
  organization_id: string | null;
  actor_id: string;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  resource_name: string | null;
  severity: 'info' | 'warning' | 'critical';
  category: 'security' | 'configuration' | 'access' | 'audit';
  changes: Record<string, any> | null;
  metadata: Record<string, any>;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface AuditEventListResponse {
  items: AuditEvent[];
  total: number;
  skip: number;
  limit: number;
}

export interface AuditEventFilters {
  skip?: number;
  limit?: number;
  organization_id?: string;
  resource_type?: string;
  action?: string;
  severity?: string;
  category?: string;
  actor_id?: string;
  start_date?: string;
  end_date?: string;
  include_system_events?: boolean;
}

export async function getAuditEvents(filters: AuditEventFilters = {}): Promise<AuditEventListResponse> {
  const params = new URLSearchParams();
  if (filters.skip !== undefined) params.append('skip', String(filters.skip));
  if (filters.limit !== undefined) params.append('limit', String(filters.limit));
  if (filters.organization_id) params.append('organization_id', filters.organization_id);
  if (filters.resource_type) params.append('resource_type', filters.resource_type);
  if (filters.action) params.append('action', filters.action);
  if (filters.severity) params.append('severity', filters.severity);
  if (filters.category) params.append('category', filters.category);
  if (filters.actor_id) params.append('actor_id', filters.actor_id);
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.include_system_events !== undefined) {
    params.append('include_system_events', String(filters.include_system_events));
  }

  const queryString = params.toString();
  const endpoint = `/audit/${queryString ? `?${queryString}` : ''}`;
  return apiRequest<AuditEventListResponse>(endpoint);
}

/** Super-admin only. */
export async function getSystemAuditEvents(filters: Omit<AuditEventFilters, 'organization_id' | 'include_system_events'> = {}): Promise<AuditEventListResponse> {
  const params = new URLSearchParams();
  if (filters.skip !== undefined) params.append('skip', String(filters.skip));
  if (filters.limit !== undefined) params.append('limit', String(filters.limit));
  if (filters.resource_type) params.append('resource_type', filters.resource_type);
  if (filters.action) params.append('action', filters.action);
  if (filters.severity) params.append('severity', filters.severity);
  if (filters.actor_id) params.append('actor_id', filters.actor_id);
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);

  const queryString = params.toString();
  const endpoint = `/audit/system${queryString ? `?${queryString}` : ''}`;
  return apiRequest<AuditEventListResponse>(endpoint);
}

export async function getResourceAuditHistory(
  resourceType: string,
  resourceId: string,
  skip = 0,
  limit = 50
): Promise<AuditEventListResponse> {
  return apiRequest<AuditEventListResponse>(
    `/audit/resource/${resourceType}/${resourceId}?skip=${skip}&limit=${limit}`
  );
}

export async function getActorAuditHistory(
  actorId: string,
  skip = 0,
  limit = 50
): Promise<AuditEventListResponse> {
  return apiRequest<AuditEventListResponse>(
    `/audit/actor/${actorId}?skip=${skip}&limit=${limit}`
  );
}
