// ui/entities/workflow/types.ts

/**
 * Type definitions for workflow steps and configurations
 */

// Import types from shared layer for use in local interfaces (Workflow, Blueprint, Instance).
import type { Step, TriggerType } from '@/shared/types/workflow';

// Re-export types that are shared with the `shared/` FSD layer.
// These canonical definitions live in `@/shared/types/workflow` so that
// lower layers can import them without upward dependency violations.
export type {
  TriggerType,
  JobConfig,
  StepExecutionMode,
  OutputForwardingConfig,
  Step,
} from '@/shared/types/workflow';

// Form field types for user-provided values at runtime
export type FormFieldType =
  | 'text'           // Single line text input
  | 'textarea'       // Multi-line text input
  | 'number'         // Numeric input
  | 'select'         // Dropdown selection
  | 'multiselect'    // Multiple selection
  | 'checkbox'       // Boolean checkbox
  | 'file'           // File upload
  | 'date'           // Date picker
  | 'datetime'       // Date and time picker
  | 'json'           // JSON editor for complex data
  | 'tags'           // Tag-chip array input (string/number items)
  | 'key-value';     // Two-column key/value object editor

export interface SelectOption {
  value: string;
  label: string;
}

/**
 * Configuration for a form field exposed to end-users at runtime.
 * Used when mappingType is 'form'.
 */
export interface FormFieldConfig {
  label: string;           // Display label for the field
  placeholder?: string;    // Placeholder text
  description?: string;    // Help text shown below field
  required: boolean;       // Is this field required?
  // Support both camelCase (frontend) and snake_case (API response)
  fieldType?: FormFieldType;
  field_type?: FormFieldType;
  defaultValue?: any;
  default_value?: any;

  // Type-specific options
  options?: SelectOption[];      // For select/multiselect
  minLength?: number;
  min_length?: number;
  maxLength?: number;
  max_length?: number;
  min?: number;                  // For number
  max?: number;                  // For number
  acceptedFileTypes?: string[];
  accepted_file_types?: string[];
  maxFileSizeMB?: number;
  max_file_size_mb?: number;

  // Tag-chip / key-value widget metadata
  itemType?: string;             // For 'tags': item primitive type (string/integer/number)
  item_type?: string;
  keyPlaceholder?: string;       // For 'key-value': key column placeholder
  key_placeholder?: string;
  valuePlaceholder?: string;     // For 'key-value': value column placeholder
  value_placeholder?: string;
  addLabel?: string;             // For 'key-value': add-row button label
  add_label?: string;

  // Layout options
  size?: 'small' | 'medium' | 'large' | 'full';  // Controls column span in grid layout
}

/**
 * Form schema for a workflow, returned by GET /workflows/{id}/form-schema
 */
export interface WorkflowFormSchema {
  workflow_id: string;
  workflow_name: string;
  has_form_fields: boolean;
  fields: FormField[];
}

export interface FormField {
  parameter_key: string;     // Original parameter name
  step_id: string;           // Which step this belongs to
  step_name: string;         // For grouping in multi-step forms
  step_order: number;        // For ordering fields
  config: FormFieldConfig;
}

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  steps: Record<string, Step> | Step[]; // Backend sends object, can also be array for compatibility
  created_at: string;
  updated_at: string;
  created_by?: string;
  status?: 'draft' | 'active' | 'inactive' | 'archived' | 'published' | 'deprecated';
  version?: string | number;
  tags?: string[];
  blueprint_id?: string;
  blueprint_version?: number;
}

export interface Blueprint {
  id: string;
  name: string;
  description?: string;
  steps: Record<string, Step> | Step[]; // Backend sends object, can also be array for compatibility
  connections?: Connection[];
  created_at: string;
  updated_at: string;
  created_by?: string;
  organization_id?: string;
  status?: 'draft' | 'active' | 'inactive' | 'archived' | 'published' | 'deprecated';
  version?: string | number;
  tags?: string[];
  category?: string;
}

export interface Instance {
  id: string;
  name: string;
  description?: string;
  workflow_id: string;
  workflow_name?: string; // Denormalized for display
  workflow_version?: string;
  steps: Step[]; // Customized from original workflow
  created_at: string;
  updated_at: string;
  created_by?: string;
  status?: 'pending' | 'processing' | 'waiting_for_approval' | 'waiting_for_manual_trigger' | 'completed' | 'failed' | 'cancelled';
  last_run?: string;
  credentials?: Record<string, any>; // Encrypted credentials storage
  schedule?: {
    type: 'manual' | 'cron' | 'interval';
    value?: string; // Cron expression or interval duration
    timezone?: string;
  };
}

export interface Connection {
  id: string;
  source: string;
  target: string;
  source_id?: string;
  target_id?: string;
  sourceHandle?: string;
  targetHandle?: string;
  // Add any additional properties needed for connections
}

/**
 * Result of a single iteration within an iterating job execution.
 */
export interface IterationResult {
  index: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  inputs: Record<string, any>;
  outputs?: Record<string, any>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  execution_time_ms?: number;
}

/**
 * Job execution tracking for a workflow step.
 */
export interface JobExecution {
  id: string;
  step_id: string;
  step_name: string;
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  result?: Record<string, any>;
  extracted_outputs?: Record<string, any>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  retry_count: number;
  max_retries: number;

  // Iteration tracking (for steps that iterate over array sources)
  iteration_count?: number;
  iteration_source?: {
    step_id: string;
    output_field: string;
    total_count: number;
  };
  iterations?: IterationResult[];
  collected_outputs?: Record<string, any[]>;
}