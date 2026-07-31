// ui/shared/api/comfyui.ts

import { apiRequest } from './core';

export interface MarketplaceComfyUI {
  id: string;
  display_name: string;
  version: string;
  tier: string;
  category: string;
  description: string;
  requires: string[];
  author: string;
  download_url?: string;
  path?: string;
  origin: 'catalog-reference' | 'managed';
  visibility?: string;
  requirements_met: boolean;
  missing_packages: string[];
  status?: string | null;
}

export interface ComfyUIGraphNode {
  class_type?: string;
  [key: string]: unknown;
}

export interface ComfyUIWorkflowPackage {
  graph?: Record<string, ComfyUIGraphNode>;
  [key: string]: unknown;
}

export interface MarketplaceComfyUIDetail extends MarketplaceComfyUI {
  installed: boolean;
  workflow: ComfyUIWorkflowPackage | null;
}

export interface ComfyUICatalogResponse {
  version: string;
  comfyui: MarketplaceComfyUI[];
  filter_options: {
    tier: string[];
    category: string[];
  };
  warnings?: string[];
}

export interface ComfyUIInstallResponse {
  success: boolean;
  workflow_id: string | null;
  workflow_name: string | null;
  message: string;
  missing_packages: string[];
  already_installed: boolean;
}

export interface InstalledComfyUIInfo {
  id: string;
  name: string;
  version: string;
  installed_at?: string;
}

export interface InstalledComfyUIResponse {
  installed_ids: string[];
  installed_workflows: InstalledComfyUIInfo[];
}

export interface ComfyUICatalogUploadResponse {
  success: boolean;
  version: string;
  workflow_count: number;
  message: string;
}

export async function getComfyUICatalog(
  category?: string,
  tier?: string,
): Promise<ComfyUICatalogResponse> {
  const params = new URLSearchParams();
  if (category) params.append('category', category);
  if (tier) params.append('tier', tier);
  const qs = params.toString();
  return apiRequest<ComfyUICatalogResponse>(
    `/comfyui/marketplace/catalog${qs ? `?${qs}` : ''}`,
  );
}

/** Super-admin: full pre-install detail (workflow package JSON) for one
 * catalog entry. The list response omits it; fetched lazily on modal-open. */
export async function getComfyUIWorkflowDetail(
  workflowId: string,
): Promise<MarketplaceComfyUIDetail> {
  return apiRequest<MarketplaceComfyUIDetail>(
    `/comfyui/marketplace/catalog/${workflowId}`,
  );
}

export async function getInstalledComfyUI(): Promise<InstalledComfyUIResponse> {
  return apiRequest<InstalledComfyUIResponse>(
    '/comfyui/marketplace/installed',
  );
}

export async function installComfyUIWorkflow(
  workflowId: string,
): Promise<ComfyUIInstallResponse> {
  return apiRequest<ComfyUIInstallResponse>(
    `/comfyui/marketplace/install/${workflowId}`,
    { method: 'POST' },
  );
}

export async function uninstallComfyUIWorkflow(
  workflowId: string,
): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>(
    `/comfyui/marketplace/uninstall/${workflowId}`,
    { method: 'POST' },
  );
}

/** Super admin only. */
export async function uploadComfyUICatalog(
  file: File,
): Promise<ComfyUICatalogUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiRequest<ComfyUICatalogUploadResponse>(
    '/comfyui/marketplace/catalog/upload',
    {
      method: 'POST',
      body: formData,
      headers: {},
    },
  );
}

/** Super admin only. */
export async function refreshComfyUICatalog(): Promise<ComfyUICatalogUploadResponse> {
  return apiRequest<ComfyUICatalogUploadResponse>(
    '/comfyui/marketplace/catalog/refresh',
    { method: 'POST' },
  );
}
