// ui/widgets/instance-view/InstanceSimpleView/utils/selection.ts

import type { SelectedItem, WorkflowStep } from '../types';

interface PickInitialSelectionArgs {
  /** True when the user is in simple (user-friendly) view mode. */
  simpleMode: boolean;
  /**
   * True when the workflow has form fields AND no jobs have been created
   * yet - i.e. the instance exists but has not been submitted. This
   * happens right after Run Again clones a prior instance, or on any
   * fresh instance before the first Run click. In that state we want to
   * surface the form even in simple mode, since the form *is* the
   * primary UI for a not-yet-submitted instance. Once jobs exist, simple
   * mode goes back to hiding inputs as intended.
   */
  isPreSubmission: boolean;
  /**
   * True when the workflow has form fields OR the instance's input_data
   * is non-empty. Gates whether the Inputs pane is even meaningful.
   */
  hasInputs: boolean;
  /** Steps in workflow order - fallback target when inputs aren't shown. */
  orderedSteps: WorkflowStep[];
}

/**
 * Decides which item the instance-view mounts with.
 *
 * Technical mode: prefer the Inputs pane whenever the workflow has
 * inputs, so the user can verify what was submitted.
 *
 * Simple mode: normally hide Inputs and jump to the first step
 * (execution view is what the user cares about). The exception is
 * pre-submission state, where the form IS the page - show Inputs first.
 */
export function pickInitialSelection({
  simpleMode,
  isPreSubmission,
  hasInputs,
  orderedSteps,
}: PickInitialSelectionArgs): SelectedItem {
  if (!simpleMode || isPreSubmission) {
    if (hasInputs) return { type: 'inputs' };
  }
  if (orderedSteps.length > 0) {
    return { type: 'step', stepId: orderedSteps[0].step_id };
  }
  return { type: 'details' };
}
