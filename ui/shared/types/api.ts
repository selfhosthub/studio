// ui/shared/types/api.ts

// ============================================================================
// Enums
// ============================================================================

export enum Role {
  User = 'user',
  Admin = 'admin',
  SuperAdmin = 'super_admin',
}

export enum NotificationType {
  Info = 'info',
  Success = 'success',
  Warning = 'warning',
  Error = 'error',
}

// ============================================================================
// User Types
// ============================================================================

export interface UserResponse {
  id: string; // UUID
  username: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  avatar_url?: string | null;
  role: Role;
  is_active: boolean;
  created_at?: string; // ISO 8601 datetime
  updated_at?: string; // ISO 8601 datetime
}

export interface UserCreate {
  username: string;
  email: string;
  password: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: Role;
}

export interface UserProfileUpdate {
  username?: string;
  email?: string;
  first_name?: string | null;
  last_name?: string | null;
  password?: string | null;
}

export interface UserAdminUpdate {
  role?: Role;
  is_active?: boolean;
}

// ============================================================================
// Organization Types
// ============================================================================

export interface OrganizationResponse {
  id: string; // UUID
  name: string;
  slug: string;
  description?: string | null;
  settings?: Record<string, any> | null;
  is_active: boolean;
  created_at?: string | null; // ISO 8601 datetime
  updated_at?: string | null; // ISO 8601 datetime
}

export interface OrganizationCreate {
  name: string;
  slug?: string;
  description?: string | null;
  settings?: Record<string, any> | null;
}

export interface OrganizationUpdate {
  name?: string;
  description?: string | null;
  settings?: Record<string, any> | null;
}

// ============================================================================
// Workflow Types
// ============================================================================

export interface WorkflowResponse {
  id: string; // UUID
  name: string;
  description?: string | null;
  organization_id: string; // UUID
  steps: WorkflowStep[];
  connections?: unknown[]; // Edge connections between steps
  is_active: boolean;
  status?: string; // Workflow status
  trigger_type?: string; // 'manual' | 'webhook' | 'schedule'
  // Webhook configuration
  webhook_method?: string;
  webhook_auth_type?: string;
  webhook_auth_header_value?: string;
  webhook_jwt_secret?: string;
  created_by?: string; // UUID
  scope?: string; // 'personal' | 'organization'
  publish_status?: string | null; // null | 'pending' | 'rejected'
  client_metadata?: Record<string, unknown>;
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
}

export interface WorkflowStep {
  id: string;
  name: string;
  description?: string;
  provider_id?: string;
  service_id?: string;
  parameters?: Record<string, unknown>;
  input_mappings?: Record<string, InputMapping>;
  outputs?: Record<string, OutputDefinition>;
}

export interface InputMapping {
  mappingType?: 'static' | 'mapped' | 'form' | 'prompt';
  staticValue?: any;
  stepId?: string;
  outputField?: string;
  /**
   * When true, iterator cycles values when exhausted (index % length).
   * Used for iterators that should repeat to match the longest non-looping iterator.
   */
  loop?: boolean;
  /** Path expression into the output field value. See docs/contributing/provider-development.md for syntax. */
  path?: string;

  /** Per-key field mapping when path is "[*]" - reshapes each element in the source array. */
  elementMapping?: Record<string, string>;

  // Prompt mapping fields
  promptId?: string;
  promptSlug?: string;
  variableValues?: Record<string, string>;

  // Computed/cached for UI (set during validation)
  _iterates?: boolean;      // Does this mapping trigger iteration?
  _sourceType?: string;     // Type at source (for validation display)
}

export interface OutputDefinition {
  path: string;
  description?: string;
  type?: string;
}

export interface WorkflowCreate {
  name: string;
  description?: string | null;
  steps: WorkflowStep[];
}

export interface WorkflowUpdate {
  name?: string;
  description?: string | null;
  steps?: WorkflowStep[];
  is_active?: boolean;
}

// ============================================================================
// Blueprint Types
// ============================================================================

export interface BlueprintResponse {
  id: string; // UUID
  name: string;
  description?: string | null;
  category?: string | null;
  steps: WorkflowStep[];
  connections?: unknown[]; // Edge connections between steps
  is_public: boolean;
  created_by: string; // UUID
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
  tags?: string[];
  version?: string | number;
}

export interface BlueprintCreate {
  name: string;
  description?: string | null;
  category?: string | null;
  steps: WorkflowStep[];
  is_public?: boolean;
}

// ============================================================================
// Instance Types
// ============================================================================

/** String values must match the backend's wire format exactly - the Python enum lowercases its names. */
export enum InstanceStatus {
  Pending = 'pending',
  Processing = 'processing',
  WaitingForWebhook = 'waiting_for_webhook',
  WaitingForApproval = 'waiting_for_approval',
  WaitingForManualTrigger = 'waiting_for_manual_trigger',
  DebugPaused = 'debug_paused',
  Paused = 'paused',
  Completed = 'completed',
  Failed = 'failed',
  Cancelled = 'cancelled',
  // Inactive is the default for a new unstarted instance; Active is unreachable in current
  // backend code but kept for wire compatibility.
  Inactive = 'inactive',
  Active = 'active',
}

export enum StepExecutionStatus {
  Pending = 'pending',
  Queued = 'queued',
  Running = 'running',
  Completed = 'completed',
  Failed = 'failed',
  Cancelled = 'cancelled',
  Skipped = 'skipped',
  Stopped = 'stopped',
  WaitingApproval = 'waiting_for_approval',
  WaitingForManualTrigger = 'waiting_for_manual_trigger',
  Timeout = 'timeout',
  Blocked = 'blocked',
}

export enum IterationExecutionStatus {
  Pending = 'pending',
  Queued = 'queued',
  Running = 'running',
  Completed = 'completed',
  Failed = 'failed',
  Cancelled = 'cancelled',
}

export type StepStatusMap = Record<string, string>;

export interface IterationExecutionResponse {
  id: string; // UUID
  step_execution_id: string; // UUID
  iteration_index: number;
  iteration_group_id: string | null; // UUID
  status: IterationExecutionStatus;
  parameters: Record<string, any>;
  result: Record<string, any> | null;
  error: string | null;
  started_at: string | null; // ISO 8601 datetime
  completed_at: string | null; // ISO 8601 datetime
  created_at: string | null; // ISO 8601 datetime
  updated_at: string | null; // ISO 8601 datetime
}

export interface InstanceResponse {
  id: string; // UUID
  workflow_id: string; // UUID
  organization_id: string; // UUID
  user_id: string | null; // UUID
  name: string;
  workflow_name: string;
  status: string;
  version: number;
  input_data: Record<string, any>;
  output_data: Record<string, any>;
  client_metadata: Record<string, any>;
  created_at: string | null; // ISO 8601 datetime
  updated_at: string | null; // ISO 8601 datetime
  started_at: string | null; // ISO 8601 datetime
  completed_at: string | null; // ISO 8601 datetime
  current_step_ids: string[];
  step_status: StepStatusMap;
  workflow_snapshot: Record<string, any> | null;
  error_message: string | null;
  failed_step_ids: string[];
  error_data: Record<string, any> | null;
  steps: StepExecutionResponse[] | null;
}

export interface StepExecutionResponse {
  id: string; // UUID
  instance_id: string; // UUID
  step_id: string; // workflow-definition step key (e.g. "generate_images")
  step_name: string;
  status: StepExecutionStatus;
  started_at: string | null; // ISO 8601 datetime
  completed_at: string | null; // ISO 8601 datetime
  output_data: Record<string, any>;
  error_message: string | null;
  result: Record<string, any> | null;
  retry_count: number;
  execution_data: Record<string, any>;
  input_data: Record<string, any>; // Resolved inputs from mappings (redacted)
  request_body: Record<string, any> | null; // Actual API request (redacted)
  iteration_requests: Record<string, any>[] | null;
  status_display: string;
  can_retry: boolean;
  can_rerun: boolean;
  can_approve: boolean;
  can_trigger: boolean;
  is_terminal: boolean;
  // Server carries the shape the UI needs rather than deriving it client-side from workflow_snapshot.
  name: string;
  depends_on: string[];
  service_id: string | null;
  provider_id: string | null;
  service_type: string | null;
  trigger_type: string | null;
  execution_mode: string | null;
  parameters: Record<string, any>;
  // input_mappings values are sometimes mapping-config dicts, not flat strings.
  input_mappings: Record<string, any>;
  iterations: IterationExecutionResponse[];
  created_at: string | null; // ISO 8601 datetime
  updated_at: string | null; // ISO 8601 datetime
}

// ============================================================================
// Notification Types
// ============================================================================

/** Read state is represented by `read_at` - a nullable timestamp. There is no `is_read` boolean on the wire. */
export interface NotificationResponse {
  id: string; // UUID
  organization_id: string; // UUID
  recipient_id: string; // UUID
  created_by: string; // UUID
  channel_type: string;
  channel_id: string | null;
  title: string | null;
  message: string;
  priority: string;
  status: string;
  sent_at: string | null; // ISO 8601 datetime
  read_at: string | null; // ISO 8601 datetime, null when unread
  tags: string[];
  client_metadata: Record<string, unknown>;
  created_at: string | null; // ISO 8601 datetime
  updated_at: string | null; // ISO 8601 datetime
}

export interface NotificationCreate {
  title: string;
  message: string;
  type?: NotificationType;
}

// ============================================================================
// Authentication Types
// ============================================================================

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
}

export interface JWTPayload {
  sub: string; // User ID (UUID)
  username: string;
  email: string;
  role: Role;
  org_id?: string; // UUID
  org_slug?: string;
  exp: number; // Unix timestamp
  iat: number; // Unix timestamp
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  organization_name?: string;
  first_name?: string | null;
  last_name?: string | null;
}

// ============================================================================
// Error Types
// ============================================================================

export interface APIError {
  detail: string | ValidationError[];
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

// ============================================================================
// Pagination Types
// ============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ============================================================================
// Type Guards
// ============================================================================

export function isValidationError(error: APIError): error is { detail: ValidationError[] } {
  return Array.isArray(error.detail);
}

export function isStringError(error: APIError): error is { detail: string } {
  return typeof error.detail === 'string';
}

export function isUserResponse(obj: any): obj is UserResponse {
  return (
    typeof obj === 'object' &&
    typeof obj.id === 'string' &&
    typeof obj.username === 'string' &&
    typeof obj.email === 'string' &&
    Object.values(Role).includes(obj.role) &&
    typeof obj.is_active === 'boolean'
  );
}

export function isOrganizationResponse(obj: any): obj is OrganizationResponse {
  return (
    typeof obj === 'object' &&
    typeof obj.id === 'string' &&
    typeof obj.name === 'string' &&
    typeof obj.slug === 'string' &&
    typeof obj.is_active === 'boolean'
  );
}

// ============================================================================
// Org File Types
// ============================================================================

export type ResourceSource = 'job_generated' | 'job_download' | 'user_upload';

export type ResourceStatus =
  | 'pending'
  | 'generating'
  | 'available'
  | 'failed'
  | 'orphaned'
  | 'deleted';

export interface OrgFile {
  id: string; // UUID
  job_execution_id: string; // UUID
  instance_id: string; // UUID
  organization_id: string; // UUID
  file_extension: string; // e.g., ".jpg", ".mp4"
  file_size: number; // bytes
  mime_type: string; // e.g., "image/jpeg"
  checksum: string | null; // SHA256
  virtual_path: string; // e.g., "/Invoice Processing/Run 42/"
  display_name: string; // e.g., "generated_image.jpg"
  source: ResourceSource;
  provider_id: string | null; // UUID
  provider_resource_id: string | null;
  provider_url: string | null;
  download_timestamp: string | null; // ISO 8601
  status: ResourceStatus;
  metadata: Record<string, any>; // width, height, duration, etc.
  has_thumbnail: boolean;
  display_order: number;
  download_url: string; // GET /resources/{id}/download
  preview_url: string | null; // GET /resources/{id}/preview
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
}

