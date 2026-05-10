// ui/entities/provider/types.ts

/**
 * Provider Types
 * Type definitions for providers and their services
 */

// Re-export types that are shared with the `shared/` FSD layer.
// These canonical definitions live in `@/shared/types/provider` so that
// lower layers can import them without upward dependency violations.
export type {
  ProviderTier,
  MarketplacePackageStatus,
  PackageVersion,
  MarketplacePackage,
  MarketplaceCatalog,
  EntitlementTokenStatus,
} from '@/shared/types/provider';

// Import types from shared for use in local interfaces
import type { ProviderTier } from '@/shared/types/provider';

// ── Core service ID constants ────────────────────────────────────
// Used for conditional UI behavior in step config.
// Add new entries here instead of hardcoding service ID strings.

export const CORE_SERVICES = {
  SET_FIELDS: 'core.set_fields',
  WEBHOOK_WAIT: 'core.webhook_wait',
  POLL_SERVICE: 'core.poll_service',
  CALL_WEBHOOK: 'core.call_webhook',
  HTTP_POST: 'core.http_post',
} as const;

/** Services that render a custom editor instead of the generic parameter form */
export const SERVICES_WITH_CUSTOM_UI: Set<string> = new Set([
  CORE_SERVICES.SET_FIELDS,
  CORE_SERVICES.WEBHOOK_WAIT,
]);

/** Services that don't need the credential selector shown */
export const SERVICES_WITHOUT_CREDENTIALS: Set<string> = new Set([
  CORE_SERVICES.WEBHOOK_WAIT,
]);

/** Services that allow selecting credentials from a different provider */
export const SERVICES_WITH_CROSS_PROVIDER_CREDENTIALS: Set<string> = new Set([
  CORE_SERVICES.POLL_SERVICE,
  CORE_SERVICES.CALL_WEBHOOK,
  CORE_SERVICES.HTTP_POST,
]);

/** Services that manage their own output (no output schema section shown) */
export const SERVICES_WITH_CUSTOM_OUTPUT: Set<string> = new Set([
  CORE_SERVICES.SET_FIELDS,
]);

/** Custom parameter-section titles per service (falls back to 'Service Parameters') */
export const SERVICE_PARAMETER_TITLES: Record<string, string> = {
  [CORE_SERVICES.SET_FIELDS]: 'Edit Fields',
};

export type ProviderType = 'api' | 'infrastructure' | 'hybrid' | 'internal' | 'custom';

// ServiceType matches backend enum in app/domain/provider/models.py
// n8n-inspired categories for better organization
export type ServiceType =
  | 'flow'
  | 'ai'
  | 'productivity'
  | 'communication'
  | 'storage'
  | 'social_media'
  | 'human_in_the_loop'
  | 'transform'
  | 'network';

// Human-readable labels for ServiceType
export const SERVICE_TYPE_LABELS: Record<ServiceType, string> = {
  'flow': 'Flow',
  'ai': 'AI',
  'productivity': 'Productivity',
  'communication': 'Communication',
  'storage': 'Storage',
  'social_media': 'Social Media',
  'human_in_the_loop': 'Human in the Loop',
  'transform': 'Transform',
  'network': 'Network',
};

// ServiceType values array for dropdowns
export const SERVICE_TYPES: ServiceType[] = [
  'flow',
  'ai',
  'productivity',
  'communication',
  'storage',
  'social_media',
  'human_in_the_loop',
  'transform',
  'network',
];

export type ProviderStatus = 'active' | 'inactive' | 'error' | 'maintenance';

// Human-readable labels for ProviderTier
export const PROVIDER_TIER_LABELS: Record<ProviderTier, string> = {
  'basic': 'Basic',
  'advanced': 'Advanced',
};

export interface Provider {
  id: string;
  name: string;
  slug?: string;
  provider_type: ProviderType;
  description?: string | null;
  endpoint_url?: string | null;
  status?: ProviderStatus | string;
  config: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  client_metadata: Record<string, unknown>;
  organization_id?: string;
  created_at?: string;
  updated_at?: string;
  // Marketplace fields (extracted from client_metadata)
  tier?: ProviderTier | string;
  credential_provider?: string;
  requires?: string[];
  version?: string;
  // Included when fetching provider with services
  services?: ProviderService[];
  service_types?: ServiceType[] | string[];
}

export interface ProviderService {
  id: string;
  provider_id?: string;
  service_id: string;
  display_name: string;
  service_type: ServiceType | string;
  categories?: string[];
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, unknown>; // JSON Schema for parameters
  result_schema?: Record<string, unknown>; // JSON Schema for results
  example_parameters?: Record<string, unknown>;
  is_active?: boolean;
  client_metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  /** Derived parameters map for UI convenience */
  parameters?: Record<string, unknown>;
  /** Provider name (set when fetched via getAllServices) */
  provider_name?: string;
}

export interface ProviderCredential {
  id: string;
  provider_id: string;
  organization_id?: string;
  name: string;
  credential_type: string;
  is_active: boolean;
  expires_at?: string | null;
  created_at?: string;
  updated_at?: string;
  has_client_credentials?: boolean;
  has_access_token?: boolean;
  is_token_type?: boolean;
}

export interface ProviderResource {
  id: string;
  provider_id?: string;
  organization_id: string;
  resource_type: string;
  resource_id?: string;
  status: string;
  external_id?: string | null;
  properties?: Record<string, unknown> | null;
  requirements?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

// Request types
export interface CreateProviderRequest {
  name: string;
  provider_type: ProviderType | string;
  description?: string | null;
  endpoint_url?: string | null;
  config?: Record<string, any>;
  capabilities?: Record<string, any>;
  client_metadata?: Record<string, any>;
}

export interface UpdateProviderRequest {
  name?: string | null;
  description?: string | null;
  endpoint_url?: string | null;
  config?: Record<string, any> | null;
  capabilities?: Record<string, any> | null;
  client_metadata?: Record<string, any> | null;
  status?: string | null;
}

export interface CreateProviderServiceRequest {
  service_id: string;
  display_name: string;
  service_type: ServiceType;
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  is_active?: boolean;
  client_metadata?: Record<string, any>;
}

export interface UpdateProviderServiceRequest {
  display_name?: string;
  description?: string | null;
  endpoint?: string | null;
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  is_active?: boolean;
  client_metadata?: Record<string, any>;
}

export interface CreateProviderCredentialRequest {
  name: string;
  credential_type: string;
  secret_data: Record<string, any>;
  expires_at?: string | null;
}

export interface UpdateProviderCredentialRequest {
  name?: string;
  description?: string | null;
  secret_data?: Record<string, any>;
  is_active?: boolean;
  expires_at?: string | null;
}

export interface CreateProviderResourceRequest {
  resource_type: string;
  resource_id: string;
  status: string;
  organization_id: string;
  properties?: Record<string, any> | null;
  requirements?: Record<string, any> | null;
}

export interface UpdateProviderResourceRequest {
  status?: string;
  properties?: Record<string, any>;
  requirements?: Record<string, any>;
}

/**
 * Service definition for UI display
 * Used when fetching service details from the API
 * Supports both camelCase (UI) and snake_case (backend) field names
 * When receiving from backend, use service_id/display_name; UI code can use id/name
 */
export interface ServiceDefinition {
  id?: string;
  name?: string;
  icon?: string;
  description?: string | null;
  serviceType?: ServiceType | string;
  // Backend aliases (snake_case)
  service_id?: string;
  display_name?: string;
  service_type?: ServiceType | string;
  categories?: string[];
  is_active?: boolean;
  provider_id?: string;
  endpoint?: string | null;
  client_metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  // Parameter definitions (may be strongly-typed or generic from API)
  parameters?: Record<string, unknown>;
  // Schema fields matching the backend model
  parameter_schema?: Record<string, any>;
  result_schema?: Record<string, any>;
  example_parameters?: Record<string, any>;
  default_output_fields?: Array<{
    name: string;
    path: string;
    description: string;
    type: string;
  }>;
}

/**
 * Provider category for UI organization
 */
export interface ProviderCategory {
  id: string;
  name: string;
  icon?: string;
  description?: string;
  serviceType?: ServiceType;
  providers: Provider[];
}
