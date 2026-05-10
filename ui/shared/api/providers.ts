// ui/shared/api/providers.ts

import { apiRequest } from './core';
import { getCurrentUser } from './auth';

export interface Provider {
  id: string;
  name: string;
  provider_type: 'api' | 'infrastructure' | 'hybrid' | 'internal' | 'custom';
  description?: string | null;
  endpoint_url?: string | null;
  config: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  client_metadata: Record<string, unknown>;
  status?: string;
  slug?: string;
  organization_id?: string;
  created_at?: string;
  updated_at?: string;
  services?: ProviderServiceResponse[];
  service_types?: string[];
  tier?: string;
  credential_provider?: string;
  requires?: string[];
  version?: string;
}

export interface ProviderCredential {
  id: string;
  name: string;
  credential_type: string;
  provider_id: string;
  organization_id?: string;
  is_active: boolean;
  expires_at?: string | null;
  created_at?: string;
  updated_at?: string;
  has_client_credentials?: boolean;
  has_access_token?: boolean;
  is_token_type?: boolean;
}

export interface OrganizationSecret {
  id: string;
  name: string;
  secret_type: string;
  description?: string;
  secret_data?: Record<string, unknown>;
  is_active: boolean;
  is_protected?: boolean;
  expires_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ProviderServiceResponse {
  id: string;
  service_id: string;
  display_name: string;
  service_type: string;
  categories?: string[];
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  is_active: boolean;
  client_metadata?: Record<string, any>;
  provider_id?: string;
  created_at?: string;
  updated_at?: string;
  /** Derived from parameter_schema.properties for UI convenience. */
  parameters?: Record<string, unknown>;
}

export interface ProviderResource {
  id: string;
  resource_type: string;
  resource_id?: string;
  external_id?: string | null;
  status: string;
  organization_id: string;
  provider_id?: string;
  properties?: Record<string, unknown> | null;
  requirements?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface RevealCredentialResponse {
  secret_data: Record<string, unknown>;
  revealed_at: string;
  credential_id: string;
  credential_type: string;
}

export interface RevealCredentialError {
  error: string;
  reason: string;
  credential_type: string;
}

export async function getProviders(): Promise<Provider[]> {
  return apiRequest<Provider[]>('/providers/');
}

export async function createProvider(data: {
  name: string;
  provider_type: string;
  description?: string | null;
  endpoint_url?: string | null;
  config?: Record<string, any>;
  capabilities?: Record<string, any>;
  client_metadata?: Record<string, any>;
}): Promise<Provider> {
  return apiRequest<Provider>('/providers/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getProvider(providerId: string): Promise<Provider> {
  return apiRequest<Provider>(`/providers/${providerId}`);
}

export async function updateProvider(providerId: string, updates: {
  name?: string | null;
  description?: string | null;
  endpoint_url?: string | null;
  config?: Record<string, any> | null;
  capabilities?: Record<string, any> | null;
  client_metadata?: Record<string, any> | null;
  status?: string | null;
}): Promise<Provider> {
  return apiRequest<Provider>(`/providers/${providerId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

/** Original definition from the provider's package files (pre-edit source of truth). */
export async function getProviderPackageDefaults(providerId: string): Promise<{
  name: string;
  slug: string;
  provider_type: string;
  description: string | null;
  endpoint_url: string | null;
  config: Record<string, any>;
  capabilities: Record<string, any>;
  client_metadata: Record<string, any>;
}> {
  return apiRequest(`/providers/${providerId}/package-defaults`);
}

export async function deleteProvider(providerId: string): Promise<void> {
  await apiRequest(`/providers/${providerId}`, {
    method: 'DELETE',
  });
}

export async function createProviderCredential(providerId: string, data: {
  name: string;
  credential_type: string;
  secret_data: Record<string, any>;
  expires_at?: string | null;
}): Promise<ProviderCredential> {
  return apiRequest<ProviderCredential>(`/providers/${providerId}/credentials`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getProviderCredentials(providerId: string): Promise<ProviderCredential[]> {
  return apiRequest<ProviderCredential[]>(`/providers/${providerId}/credentials`);
}

/**
 * Single-call fetch of all credentials in the current user's org. Cheaper than
 * fanning out per-provider via getProviderCredentials.
 */
export async function getOrganizationCredentials(
  organizationId?: string,
  options?: {
    provider_id?: string;
    credential_type?: string;
    is_active?: boolean;
    search?: string;
  }
): Promise<ProviderCredential[]> {
  let orgId = organizationId;
  if (!orgId) {
    const user = getCurrentUser();
    if (!user || !user.org_id) {
      throw new Error('User not authenticated or missing organization');
    }
    orgId = user.org_id;
  }

  const params = new URLSearchParams();
  if (options?.provider_id) params.append('provider_id', options.provider_id);
  if (options?.credential_type) params.append('credential_type', options.credential_type);
  if (options?.is_active !== undefined) params.append('is_active', String(options.is_active));
  if (options?.search) params.append('search', options.search);

  const queryString = params.toString();
  const url = `/organizations/${orgId}/credentials${queryString ? `?${queryString}` : ''}`;

  return apiRequest<ProviderCredential[]>(url);
}

export async function getProviderCredential(credentialId: string): Promise<ProviderCredential> {
  return apiRequest<ProviderCredential>(`/providers/credentials/${credentialId}`);
}

/**
 * Reveal stored secret data. Only API-key / access-key / basic-auth / non-token custom
 * credentials are revealable; OAuth/bearer/JWT tokens are write-once.
 */
export async function revealProviderCredential(credentialId: string): Promise<RevealCredentialResponse> {
  return apiRequest<RevealCredentialResponse>(`/providers/credentials/${credentialId}/reveal`);
}

export function isCredentialTypeRevealable(credentialType: string, isTokenType?: boolean): boolean {
  const type = credentialType.toLowerCase();
  if (['oauth', 'oauth2', 'bearer', 'jwt'].includes(type)) {
    return false;
  }
  if (type === 'custom' && isTokenType) {
    return false;
  }
  return true;
}

export async function updateProviderCredential(credentialId: string, updates: {
  name?: string;
  secret_data?: Record<string, any>;
  expires_at?: string | null;
}): Promise<ProviderCredential> {
  // Frontend uses `secret_data`; the API expects `credentials`.
  const apiPayload: Record<string, unknown> = {};
  if (updates.name !== undefined) apiPayload.name = updates.name;
  if (updates.secret_data !== undefined) apiPayload.credentials = updates.secret_data;
  if (updates.expires_at !== undefined) apiPayload.expires_at = updates.expires_at;

  return apiRequest<ProviderCredential>(`/providers/credentials/${credentialId}`, {
    method: 'PATCH',
    body: JSON.stringify(apiPayload),
  });
}

export async function deleteProviderCredential(credentialId: string): Promise<void> {
  await apiRequest(`/providers/credentials/${credentialId}`, {
    method: 'DELETE',
  });
}

/**
 * Fan-out fetch of all credentials across providers - used where no single endpoint exists.
 * Per-provider failures are swallowed so one bad provider can't fail the aggregate.
 */
export async function getAllOrganizationCredentials(organizationId?: string): Promise<ProviderCredential[]> {
  try {
    const providers = await getProviders();

    const credentialPromises = providers.map(provider =>
      getProviderCredentials(provider.id).catch(() => {
        return [];
      })
    );

    const credentialArrays = await Promise.all(credentialPromises);

    const allCredentials = credentialArrays.flat();
    return allCredentials;
  } catch (error) {
    throw error;
  }
}

/** List secret metadata only - does NOT include secret_data values. */
export async function getOrganizationSecrets(): Promise<OrganizationSecret[]> {
  return apiRequest<OrganizationSecret[]>('/organizations/secrets');
}

/** SECURITY: returns decrypted secret_data. */
export async function getOrganizationSecret(secretId: string): Promise<OrganizationSecret> {
  return apiRequest<OrganizationSecret>(`/organizations/secrets/${secretId}`);
}

export async function createOrganizationSecret(data: {
  name: string;
  secret_type: string;
  secret_data: Record<string, any>;
  expires_at?: string | null;
}): Promise<OrganizationSecret> {
  return apiRequest<OrganizationSecret>('/organizations/secrets', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** Name is immutable; this only updates secret_data / is_active / expires_at. */
export async function updateOrganizationSecret(secretId: string, data: {
  secret_data: Record<string, any>;
  is_active?: boolean;
  expires_at?: string | null;
}): Promise<OrganizationSecret> {
  return apiRequest<OrganizationSecret>(`/organizations/secrets/${secretId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteOrganizationSecret(secretId: string): Promise<void> {
  await apiRequest(`/organizations/secrets/${secretId}`, {
    method: 'DELETE',
  });
}

export async function createProviderService(providerId: string, data: {
  service_id: string;
  display_name: string;
  service_type: string;
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  is_active?: boolean;
  client_metadata?: Record<string, any>;
}): Promise<ProviderServiceResponse> {
  return apiRequest<ProviderServiceResponse>(`/providers/${providerId}/services`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getProviderServices(providerId: string): Promise<ProviderServiceResponse[]> {
  return apiRequest<ProviderServiceResponse[]>(`/providers/${providerId}/services`);
}

export async function getProviderService(serviceId: string): Promise<ProviderServiceResponse> {
  return apiRequest<ProviderServiceResponse>(`/providers/services/${serviceId}`);
}

export async function updateProviderService(serviceId: string, updates: {
  display_name?: string;
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  is_active?: boolean;
  client_metadata?: Record<string, any>;
}): Promise<ProviderServiceResponse> {
  return apiRequest<ProviderServiceResponse>(`/providers/services/${serviceId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function deleteProviderService(serviceId: string): Promise<void> {
  await apiRequest(`/providers/services/${serviceId}`, {
    method: 'DELETE',
  });
}

/** Original service definition from the package files on disk (pre-edit source of truth). */
export async function getServicePackageDefaults(serviceId: string): Promise<{
  display_name: string;
  description: string | null;
  endpoint: string | null;
  parameter_schema: Record<string, any>;
  result_schema: Record<string, any>;
  example_parameters: Record<string, any>;
  client_metadata: Record<string, any>;
}> {
  return apiRequest(`/providers/services/${serviceId}/package-defaults`);
}

/** Cross-provider service catalog used by the workflow builder. */
export async function getAllServices(): Promise<Array<ProviderServiceResponse & {
  provider_id: string;
  provider_name: string;
}>> {
  try {
    const providers = await getProviders();

    const servicePromises = providers.map(async provider => {
      try {
        const services = await getProviderServices(provider.id);
        return services.map((svc) => ({
          ...svc,
          provider_id: provider.id,
          provider_name: provider.name,
        }));
      } catch {
        return [];
      }
    });

    const serviceArrays = await Promise.all(servicePromises);

    return serviceArrays.flat();
  } catch (error) {
    throw error;
  }
}

export async function createProviderResource(providerId: string, data: {
  resource_type: string;
  resource_id: string;
  status: string;
  organization_id: string;
  properties?: Record<string, any> | null;
  requirements?: Record<string, any> | null;
}): Promise<ProviderResource> {
  return apiRequest<ProviderResource>(`/providers/${providerId}/resources`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getProviderResources(providerId: string): Promise<ProviderResource[]> {
  return apiRequest<ProviderResource[]>(`/providers/${providerId}/resources`);
}

export async function getProviderResourcesByOrganization(organizationId: string): Promise<ProviderResource[]> {
  return apiRequest<ProviderResource[]>(`/providers/resources/organization/${organizationId}`);
}

export async function getProviderResource(resourceId: string): Promise<ProviderResource> {
  return apiRequest<ProviderResource>(`/providers/resources/${resourceId}`);
}

export async function updateProviderResource(resourceId: string, updates: {
  status?: string;
  properties?: Record<string, any> | null;
  requirements?: Record<string, any> | null;
}): Promise<ProviderResource> {
  return apiRequest<ProviderResource>(`/providers/resources/${resourceId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function deleteProviderResource(resourceId: string): Promise<void> {
  await apiRequest(`/providers/resources/${resourceId}`, {
    method: 'DELETE',
  });
}

export async function testProviderService(
  providerId: string,
  serviceId: string,
  parameters: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(
    `/providers/${providerId}/services/${serviceId}/test`,
    {
      method: 'POST',
      body: JSON.stringify({ parameters }),
    }
  );
}
