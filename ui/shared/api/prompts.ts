// ui/shared/api/prompts.ts

import type {
  Prompt,
  PromptCreate,
  PromptUpdate,
  AssembleResponse,
} from '@/shared/types/prompt';
import { apiRequest } from './core';

export async function getPersonalPrompts(skip = 0, limit = 100): Promise<Prompt[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  return apiRequest<Prompt[]>(`/prompts/personal?${params}`);
}

export async function getPendingPublishPrompts(skip = 0, limit = 100): Promise<Prompt[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  return apiRequest<Prompt[]>(`/prompts/pending-publish?${params}`);
}

export async function requestPublishPrompt(id: string): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}/request-publish`, { method: 'POST' });
}

export async function approvePublishPrompt(id: string): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}/approve-publish`, { method: 'POST' });
}

export async function rejectPublishPrompt(id: string): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}/reject-publish`, { method: 'POST' });
}

export async function getPrompts(category?: string): Promise<Prompt[]> {
  const params = new URLSearchParams();
  if (category) params.append('category', category);
  const qs = params.toString();
  return apiRequest<Prompt[]>(`/prompts/${qs ? `?${qs}` : ''}`);
}

export async function getPrompt(id: string): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}`);
}

export async function createPrompt(data: PromptCreate): Promise<Prompt> {
  return apiRequest<Prompt>('/prompts/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updatePrompt(id: string, data: PromptUpdate): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deletePrompt(id: string): Promise<void> {
  await apiRequest<void>(`/prompts/${id}`, { method: 'DELETE' });
}

export async function copyPrompt(id: string): Promise<Prompt> {
  return apiRequest<Prompt>(`/prompts/${id}/copy`, { method: 'POST' });
}

/** Live preview - renders the prompt with the given variable values. */
export async function assemblePrompt(
  id: string,
  variableValues: Record<string, string>,
): Promise<AssembleResponse> {
  return apiRequest<AssembleResponse>(`/prompts/${id}/assemble`, {
    method: 'POST',
    body: JSON.stringify({ variable_values: variableValues }),
  });
}

export interface MarketplacePrompt {
  id: string;
  display_name: string;
  version: string;
  tier: string;
  category: string;
  description: string;
  author: string;
  chunks: Array<{
    text: string;
    variable: string | null;
    order: number;
    role: string | null;
  }>;
  variables: Array<{
    name: string;
    label: string;
    type: string;
    options: string[] | null;
    default: string | null;
  }>;
}

export interface PromptsCatalogResponse {
  version: string;
  prompts: MarketplacePrompt[];
  filter_options: {
    tier: string[];
    category: string[];
  };
  warnings?: string[];
}

export interface PromptInstallResponse {
  success: boolean;
  prompt_id: string | null;
  prompt_name: string | null;
  message: string;
  already_installed: boolean;
}

export interface InstalledPromptInfo {
  marketplace_id: string;
  prompt_id: string;
  name: string;
  category: string;
}

export interface InstalledPromptsResponse {
  installed_ids: string[];
  installed_prompts: InstalledPromptInfo[];
}

export interface PromptCatalogUploadResponse {
  success: boolean;
  version: string;
  prompt_count: number;
  message: string;
}

export async function getPromptsCatalog(
  category?: string,
  tier?: string,
): Promise<PromptsCatalogResponse> {
  const params = new URLSearchParams();
  if (category) params.append('category', category);
  if (tier) params.append('tier', tier);
  const qs = params.toString();
  return apiRequest<PromptsCatalogResponse>(
    `/prompts/marketplace/catalog${qs ? `?${qs}` : ''}`,
  );
}

export async function getInstalledPrompts(): Promise<InstalledPromptsResponse> {
  return apiRequest<InstalledPromptsResponse>(
    '/prompts/marketplace/installed',
  );
}

export async function installPrompt(
  promptId: string,
): Promise<PromptInstallResponse> {
  return apiRequest<PromptInstallResponse>(
    `/prompts/marketplace/install/${promptId}`,
    { method: 'POST' },
  );
}

export async function uninstallPrompt(
  promptId: string,
): Promise<{ success: boolean; message: string }> {
  return apiRequest<{ success: boolean; message: string }>(
    `/prompts/marketplace/uninstall/${promptId}`,
    { method: 'POST' },
  );
}

/** Catalog of super-admin-authored prompts. */
export async function getCustomPromptsCatalog(
  category?: string,
): Promise<PromptsCatalogResponse> {
  const params = new URLSearchParams();
  if (category) params.append('category', category);
  const qs = params.toString();
  return apiRequest<PromptsCatalogResponse>(
    `/prompts/marketplace/custom-catalog${qs ? `?${qs}` : ''}`,
  );
}

export async function installCustomPrompt(
  promptId: string,
): Promise<PromptInstallResponse> {
  return apiRequest<PromptInstallResponse>(
    `/prompts/marketplace/install-custom/${promptId}`,
    { method: 'POST' },
  );
}

/** Super admin only. */
export async function uploadPromptsCatalog(
  file: File,
): Promise<PromptCatalogUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiRequest<PromptCatalogUploadResponse>(
    '/prompts/marketplace/catalog/upload',
    {
      method: 'POST',
      body: formData,
      headers: {},
    },
  );
}

/** Super admin only. */
export async function refreshPromptsCatalog(): Promise<PromptCatalogUploadResponse> {
  return apiRequest<PromptCatalogUploadResponse>(
    '/prompts/marketplace/catalog/refresh',
    { method: 'POST' },
  );
}