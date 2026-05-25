// ui/features/step-config/sections/OutputForwardingSection.tsx

'use client';

import React, { useMemo } from 'react';
import { Step, OutputForwardingConfig } from '@/entities/workflow';
import { ChevronDown, ChevronRight, AlertTriangle, ArrowRight } from 'lucide-react';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';

interface OutputForwardingSectionProps {
  step: Step;
  previousSteps: Step[];
  onUpdate: (config: OutputForwardingConfig | undefined) => void;
  defaultOpen?: boolean;
  /** Service's result_schema - used for collision detection against actual native outputs */
  outputSchema?: { properties?: Record<string, unknown> } | null;
  /** Prompt variable names from this step's prompt mapping (forwardable to downstream) */
  promptVarNames?: string[];
  /** Instance form fields to include as outputs of the first step */
  instanceFormFields?: Record<string, { description?: string; type?: string; _from_form?: boolean }>;
}

/**
 * OutputForwardingSection allows users to configure which inputs from the immediate
 * predecessor step should be forwarded to this step's outputs, enabling cleaner
 * linear workflows without "data jump" connections.
 *
 * Shows all effective outputs from the immediate predecessor, including pass-through fields.
 */
export function OutputForwardingSection({
  step,
  previousSteps,
  onUpdate,
  defaultOpen = true,  // Default to expanded
  outputSchema,
  promptVarNames,
  instanceFormFields,
}: OutputForwardingSectionProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);
  const config = step.output_forwarding || { enabled: false, mode: 'all' as const };

  // Find direct predecessors via depends_on (not array position)
  const directPredecessors = useMemo(() =>
    (step.depends_on || [])
      .map(depId => previousSteps.find(s => s.id === depId))
      .filter((s): s is Step => s != null),
    [step.depends_on, previousSteps]
  );

  // Collect available fields from ALL direct predecessors' effective outputs
  // AND this step's own template variables (which are also forwardable downstream)
  const availableFields = useMemo(() => {
    const fields: Array<{
      name: string;
      stepId: string;
      stepName: string;
      type: string;
      isForwarded?: boolean;
      isPromptVar?: boolean;
      sourceStepName?: string;
    }> = [];

    if (directPredecessors.length === 0) return fields;

    for (const predecessor of directPredecessors) {
      // For computing effective outputs, pass all previousSteps except this predecessor
      const otherSteps = previousSteps.filter(s => s.id !== predecessor.id);
      const effectiveOutputs = getEffectiveOutputs(predecessor, otherSteps);

      for (const [fieldName, fieldDef] of Object.entries(effectiveOutputs)) {
        // Skip if already added from another predecessor
        if (fields.some(f => f.name === fieldName)) continue;

        const typedField = fieldDef as { type?: string; _forwarded?: boolean; _source_step_id?: string };
        const isForwarded = typedField._forwarded || false;

        // Find the original source step name if forwarded
        let sourceStepName: string | undefined;
        if (isForwarded && typedField._source_step_id) {
          const sourceStep = previousSteps.find(s => s.id === typedField._source_step_id);
          sourceStepName = sourceStep?.name || typedField._source_step_id;
        }

        fields.push({
          name: fieldName,
          stepId: predecessor.id,
          stepName: predecessor.name || predecessor.id,
          type: typedField.type || 'string',
          isForwarded,
          sourceStepName,
        });
      }
    }

    // Add this step's own prompt variables as forwardable fields
    if (promptVarNames) {
      const stepName = step.name || step.id;
      for (const varName of promptVarNames) {
        // Skip if a predecessor field already has the same name
        if (!fields.some(f => f.name === varName)) {
          fields.push({
            name: varName,
            stepId: step.id,
            stepName: stepName,
            type: 'string',
            isPromptVar: true,
          });
        }
      }
    }

    return fields;
  }, [directPredecessors, previousSteps, promptVarNames, step]);

  // Detect name collisions with this step's native outputs
  // Uses the service's result_schema (outputSchema) as the source of truth for native outputs,
  // not step.outputs which may contain stale/polluted data
  const collisions = useMemo(() => {
    // Use outputSchema.properties if available, otherwise fall back to step.outputs
    const nativeOutputNames = outputSchema?.properties
      ? Object.keys(outputSchema.properties)
      : Object.keys(step.outputs || {});

    return availableFields.filter(f => nativeOutputNames.includes(f.name));
  }, [availableFields, outputSchema, step.outputs]);

  // Get unique field names (for "selected" mode)
  const uniqueFieldNames = useMemo(() => {
    const seen = new Set<string>();
    return availableFields.filter(f => {
      if (seen.has(f.name)) return false;
      seen.add(f.name);
      return true;
    });
  }, [availableFields]);

  const handleToggleEnabled = (enabled: boolean) => {
    if (enabled) {
      onUpdate({ enabled: true, mode: 'all' });
    } else {
      onUpdate(undefined); // Remove config entirely when disabled
    }
  };

  const handleModeChange = (mode: 'all' | 'selected') => {
    onUpdate({
      ...config,
      mode,
      selected_fields: mode === 'selected' ? [] : undefined,
    });
  };

  const handleFieldToggle = (fieldName: string, checked: boolean) => {
    const current = config.selected_fields || [];
    const updated = checked
      ? [...current, fieldName]
      : current.filter(f => f !== fieldName);
    onUpdate({
      ...config,
      selected_fields: updated,
    });
  };

  // Don't render if there are no direct predecessors
  if (directPredecessors.length === 0) {
    return null;
  }

  return (
    <div className={`border rounded-lg overflow-hidden ${
      config.enabled
        ? 'border-purple-300 dark:border-purple-700' // css-check-ignore: no semantic token
        : 'border-primary'
    }`}>
      {/* Header - Collapsible */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center justify-between px-4 py-3 transition-colors ${
          config.enabled
            ? 'bg-purple-50 dark:bg-purple-900/20 hover:bg-purple-100 dark:hover:bg-purple-900/30' // css-check-ignore: no semantic token
            : 'bg-surface hover:bg-card /50'
        }`}
      >
        <div className="flex items-center gap-2">
          {/* css-check-ignore: no semantic token for purple */}
          {isOpen ? (
            <ChevronDown className={`h-4 w-4${config.enabled ? 'text-purple-500' : 'text-secondary'}`} />
          ) : (
            <ChevronRight className={`h-4 w-4${config.enabled ? 'text-purple-500' : 'text-secondary'}`} />
          )}
          <span className={`text-sm font-medium ${
            config.enabled
              ? 'text-purple-700 dark:text-purple-300' // css-check-ignore: no semantic token
              : 'text-secondary'
          }`}>
            Output Forwarding
          </span>
          {config.enabled && (
            <span className="px-2 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded-full"> {/* css-check-ignore: no semantic token */}
              {config.mode === 'all' ? 'All fields' : `${config.selected_fields?.length || 0} fields`}
            </span>
          )}
        </div>
        <ArrowRight className={`h-4 w-4${config.enabled ? 'text-purple-400' : 'text-muted'}`} /> {/* css-check-ignore: no semantic token */}
      </button>

      {/* Content */}
      {isOpen && (
        <div className={`p-4 space-y-4 border-t ${
          config.enabled
            ? 'border-purple-200 dark:border-purple-800' // css-check-ignore: no semantic token
            : 'border-primary'
        }`}>
          {/* Enable toggle */}
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => handleToggleEnabled(e.target.checked)}
              className="h-4 w-4 text-purple-600 border-primary rounded focus:ring-purple-500" // css-check-ignore: no semantic token
            />
            <div>
              <span className="text-sm font-medium text-secondary">
                Forward inputs to outputs
              </span>
              <p className="text-muted text-xs">
                Pass fields from {directPredecessors.map(p => `"${p.name || p.id}"`).join(', ')} through to downstream steps
              </p>
            </div>
          </label>

          {config.enabled && (
            <>
              {/* Mode selector */}
              <div className="ml-7 space-y-2">
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="forwardMode"
                      checked={config.mode === 'all' || !config.mode}
                      onChange={() => handleModeChange('all')}
                      className="h-4 w-4 text-purple-600 border-primary focus:ring-purple-500" // css-check-ignore: no semantic token
                    />
                    <span className="text-sm text-secondary">All fields</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="forwardMode"
                      checked={config.mode === 'selected'}
                      onChange={() => handleModeChange('selected')}
                      className="h-4 w-4 text-purple-600 border-primary focus:ring-purple-500" // css-check-ignore: no semantic token
                    />
                    <span className="text-sm text-secondary">Selected fields</span>
                  </label>
                </div>

                {/* Field checkboxes (when mode='selected') */}
                {config.mode === 'selected' && (
                  <div className="mt-3 space-y-2 max-h-48 overflow-y-auto border border-primary rounded-md p-2">
                    {uniqueFieldNames.length === 0 ? (
                      <p className="text-xs text-secondary italic">
                        No fields available from previous steps
                      </p>
                    ) : (
                      uniqueFieldNames.map((field) => (
                        <label
                          key={field.name}
                          className={`flex items-center gap-2 cursor-pointer py-1 px-2 rounded ${
                            field.isPromptVar
                              ? 'hover:bg-teal-50 dark:hover:bg-teal-900/20' // css-check-ignore: no semantic token
                              : field.isForwarded
                                ? 'hover:bg-purple-50 dark:hover:bg-purple-900/20' // css-check-ignore: no semantic token
                                : 'hover:bg-surface /50'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={config.selected_fields?.includes(field.name) || false}
                            onChange={(e) => handleFieldToggle(field.name, e.target.checked)}
                            className="h-3.5 w-3.5 text-purple-600 border-primary rounded focus:ring-purple-500" // css-check-ignore: no semantic token
                          />
                          <span className={`text-sm flex-1 ${
                            field.isPromptVar
                              ? 'text-teal-700 dark:text-teal-300' // css-check-ignore: no semantic token
                              : field.isForwarded
                                ? 'text-purple-700 dark:text-purple-300' // css-check-ignore: no semantic token
                                : 'text-secondary'
                          }`}>
                            {field.name}
                          </span>
                          <span className="text-xs text-muted">
                            {field.isPromptVar
                              ? 'Prompt variable'
                              : field.isForwarded && field.sourceStepName
                                ? `↳ ${field.sourceStepName}`
                                : `from ${field.stepName}`
                            }
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                )}

                {/* Collision warning */}
                {collisions.length > 0 && (
                  <div className="flex items-start gap-2 mt-3 p-2 bg-warning-subtle border border-warning rounded-md">
                    <AlertTriangle className="h-4 w-4 text-warning flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-warning">
                      <span className="font-medium">Name collision:</span>{' '}
                      {collisions.map(c => c.name).join(', ')}{' '}will be overwritten by this step&apos;s native output
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default OutputForwardingSection;
