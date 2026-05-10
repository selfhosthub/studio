// ui/app/instances/[id]/lib/types.ts

/**
 * Shared types for the instance detail page and its hooks/components.
 */

export interface Job {
  id: string;
  workflow_instance_id?: string;
  instance_id?: string;
  instance_step_id?: string | null;
  step_id: string;
  step_name?: string;
  status: string;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  retry_count?: number;
  execution_data?: Record<string, unknown>;
  // Per-iteration request params (set at enqueue time)
  iteration_requests?: Record<string, unknown>[] | null;
  // Input/Request data for debugging
  input_data?: Record<string, unknown>;  // Resolved inputs from mappings
  request_body?: Record<string, unknown> | null;  // Actual API request sent to provider
  created_at: string | null;
  updated_at: string | null;
}

// Represents a workflow step with its execution status
export interface WorkflowStep {
  step_id: string;
  name: string;
  depends_on: string[];
  service_id?: string;
  provider_id?: string;
  service_type?: string;  // SERVICE_TYPE from job config (e.g., IMAGE_GENERATION, VIDEO_GENERATION)
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'waiting_for_approval' | 'waiting_for_manual_trigger' | 'stopped';
  execution_mode?: 'enabled' | 'skip' | 'stop';  // From workflow_snapshot
  trigger_type?: 'auto' | 'manual';  // From workflow_snapshot
  // Step config data for preview before execution
  parameters?: Record<string, unknown>;
  input_mappings?: Record<string, string>;
}

