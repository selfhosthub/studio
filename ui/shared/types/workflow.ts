// ui/shared/types/workflow.ts

/** Mirrors WorkflowTriggerType on the backend. */
export type TriggerType =
  | 'manual'
  | 'schedule'
  | 'webhook'
  | 'event'
  | 'api';

export interface JobConfig {
  /** STORAGE, IMAGE_GENERATION, etc. */
  service_type?: string;
  provider_id?: string;
  credential_id?: string;
  /** Owning provider of the credential - set when credential and step provider differ. */
  credential_provider_id?: string;
  service_id?: string;
  timeout_seconds?: number;
  retry_policy?: {
    max_attempts: number;
    delay_seconds: number;
  };
  retry_count?: number;
  retry_delay_seconds?: number;
  parameters?: Record<string, any>;
  command?: string;
  /** @deprecated Use service_type. */
  provider_type?: string;
  provider_version?: string;
  service_version?: string;
}

/** 'enabled' = run, 'skip' = skip but flow data through, 'stop' = halt the workflow here. */
export type StepExecutionMode = 'enabled' | 'skip' | 'stop';

/**
 * Forwarding mirrors a predecessor's outputs onto this step so downstream steps can
 * map from here instead of jumping back to the original source.
 */
export interface OutputForwardingConfig {
  enabled: boolean;
  mode: 'all' | 'selected';
  selected_fields?: string[];
}

export interface Step {
  id: string;
  name: string;
  description?: string;
  category?: string;
  icon?: string;
  execution_mode?: StepExecutionMode;
  // Active: 'task', 'notification'. 'trigger' is a virtual incoming-data step.
  // 'webhook' is DEPRECATED - use the http_post service instead.
  // Future (orchestrator-dependent): 'condition', 'approval', 'decision', 'api_call', 'script', 'container', 'function'.
  type?: 'task' | 'notification' | 'webhook' | 'trigger' | 'condition' | 'approval' | 'decision' | 'api_call' | 'script' | 'container' | 'function';
  provider_id?: string;
  service_id?: string;
  credential_id?: string;
  job?: JobConfig;
  service_parameters?: Record<string, any>;
  parameters?: Record<string, any>;
  config?: Record<string, any>;
  inputs?: {
    database?: Record<string, {
      query: string;
      parameters?: Record<string, any>;
    }>;
    resource?: Record<string, {
      resourceId: string;
      resourceType: string;
    }>;
    previous_steps?: Record<string, {
      source_step_id: string;
      output_field: string;
      transform?: string;
    }>;
  };
  input_mappings?: Record<string, {
    source_step_id?: string;
    stepId?: string;
    source_output_field?: string;
    outputField?: string;
    transform?: string;
    mappingType?: 'mapped' | 'static' | 'form' | 'prompt';
    staticValue?: string;
    promptId?: string;
    variableValues?: Record<string, string>;
    /** Cycle values via index % length so this iterator matches the longest non-looping one. */
    loop?: boolean;
    /** Path syntax: ".url", "[0].url", "[-1].url", "[*].url", "[*]" (paired with elementMapping). */
    path?: string;
    /** With path "[*]", reshape each element of the source array. */
    elementMapping?: Record<string, string>;
  }>;
  output_fields?: Record<string, {
    path: string;
    description?: string;
    type?: string;
  }>;
  outputs?: Record<string, {
    path: string;
    description?: string;
    type?: string;
    /** Preview value from a test run or static config. */
    sample_value?: any;
  }>;
  /** @deprecated Use outputs[*].sample_value. */
  sample_output?: Record<string, any>;
  position?: {
    x: number;
    y: number;
  };
  ui_config?: {
    position?: {
      x: number;
      y: number;
    };
    color?: string;
    shape?: string;
    width?: number;
    height?: number;
    hidden?: boolean;
    [key: string]: any;
  };
  depends_on?: string[];

  /**
   * Array expansion: copies the target_parameter template N times (one per source-array
   * element) and substitutes mapped values into each copy. Pure expansion today; per-field
   * expression rules are not yet implemented.
   */
  iteration_config?: {
    enabled: boolean;
    source_step_id: string;
    source_output_field: string;
    target_parameter: string;
    /** From sample data, for the UI preview. */
    estimated_count?: number;
    execution_mode?: 'sequential' | 'parallel';
    /** Sequential mode only - aggregate values across iterations. */
    accumulators?: Array<{ field_name: string; expression: string }>;
  };

  output_forwarding?: OutputForwardingConfig;

  /** 'auto' (default) runs as soon as deps are satisfied; 'manual' waits for an API/UI trigger. */
  trigger_type?: TriggerType | 'auto';

  is_required?: boolean;
  timeout_seconds?: number;
  retry_count?: number;
  retry_delay_seconds?: number;
  on_failure?: 'fail_workflow' | 'continue' | 'skip_branch';
  condition?: string;
  metadata?: Record<string, any>;
  warnings?: Record<string, any>;
  /** Templates use category_id rather than provider_id. */
  category_id?: string;
  service_type?: string;
}
