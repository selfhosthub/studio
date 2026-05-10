// ui/shared/defaults/step-config.ts

/**
 * Fresh-state defaults for step-configuration UI - what a user sees on
 * a never-touched step. Persisted preferences (serviceParametersExpanded
 * via localStorage; parameter_ui_state via the backend step.config) and
 * schema-driven ui_hints override these when present.
 *
 * See docs/plans/defaults-consolidation.md for the rationale.
 */
export interface StepConfigDefaults {
  /** Service-parameters section - expanded by default. */
  serviceParametersExpanded: boolean;
  /** Output-fields section - expanded by default. */
  outputFieldsExpanded: boolean;
  /** Output-fields viewer - schema tree by default (not raw JSON). */
  outputViewMode: 'schema' | 'json';
  /** Advanced-parameters sub-section - collapsed by default. */
  advancedParamsCollapsed: boolean;
  /**
   * Fallback files-per-iteration when neither num_images nor batch_size
   * is set on the step (or when the value coerces to NaN). Used when the
   * instance UI infers iteration grouping.
   */
  filesPerIteration: number;
}

export const STEP_CONFIG_DEFAULTS: StepConfigDefaults = {
  serviceParametersExpanded: true,
  outputFieldsExpanded: true,
  outputViewMode: 'schema',
  advancedParamsCollapsed: true,
  filesPerIteration: 1,
};
