// ui/shared/defaults/instance.ts

/**
 * Fresh-state defaults for instance-view UI - the values a user sees on
 * a never-touched instance, before any persisted preference overrides.
 *
 * Every consumer that sets one of these values reads from this module;
 * nothing inlines the literal. Persisted user preferences (localStorage
 * via STORAGE_KEYS, backend via step.config / org.settings) override
 * these at load time when present. See docs/plans/defaults-consolidation.md
 * for the single-authority rationale.
 */
export interface InstanceDefaults {
  /** Instance view mode - simple (user-friendly) vs technical (full panel). */
  simpleMode: boolean;
  /** Side-panel width on large screens. */
  panelWidth: number;
  /** Minimum panel width on drag. */
  panelMinWidth: number;
  /** Maximum panel width on drag. */
  panelMaxWidth: number;
  /** Viewport width above which the side-by-side panel layout is used. */
  panelBreakpoint: number;
  /** JSON-result viewer mode when a step's output is inspected. */
  resultViewMode: 'auto' | 'tree' | 'raw';
  /** Form-data viewer mode when submitted inputs are inspected. */
  dataViewMode: 'auto' | 'tree' | 'raw';
}

export const INSTANCE_DEFAULTS: InstanceDefaults = {
  simpleMode: true,
  panelWidth: 256,
  panelMinWidth: 200,
  panelMaxWidth: 400,
  panelBreakpoint: 1024,
  resultViewMode: 'auto',
  dataViewMode: 'tree',
};
