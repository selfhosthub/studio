// ui/shared/defaults/index.ts

/**
 * Barrel for fresh-state UI defaults.
 *
 * Every value in these domain modules is the "what a never-touched field
 * shows" default. Persisted user preferences (localStorage, backend
 * step.config, org settings) load on top of these - the module itself is
 * synchronous, tree-shakeable, and has no runtime state.
 *
 * Add a new domain module alongside instance.ts / step-config.ts when
 * another area of the UI accumulates enough fresh-state values to warrant
 * central ownership. Don't inline literal defaults in render paths.
 */

export { INSTANCE_DEFAULTS } from './instance';
export type { InstanceDefaults } from './instance';

export { STEP_CONFIG_DEFAULTS } from './step-config';
export type { StepConfigDefaults } from './step-config';
