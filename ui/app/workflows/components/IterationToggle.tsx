// ui/app/workflows/components/IterationToggle.tsx

'use client';

import { useState } from 'react';
import { Step } from '@/entities/workflow';
import { Repeat } from 'lucide-react';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';
import { getWorkflowDocContent } from '@/shared/api';

// Same loose record type used by the parent component and APIs
type AnyRecord = Record<string, any>;

interface ArrayMappedField {
  paramKey: string;
  stepId: string;
  outputField: string;
  stepName: string;
}

interface IterationToggleProps {
  step: Step;
  inputMappings: AnyRecord;
  parameters: AnyRecord;
  enhancedPreviousSteps: Step[];
  serviceMetadata: AnyRecord | null;
  onUpdate: (updatedStep: Step) => void;
}

/**
 * Detects array-mapped fields and renders the iteration enable/disable toggle.
 * Extracted from WorkflowStepConfig to reduce main component size.
 */
export function IterationToggle({
  step,
  inputMappings,
  parameters,
  enhancedPreviousSteps,
  serviceMetadata,
  onUpdate,
}: IterationToggleProps) {
  const arrayMappedFields: ArrayMappedField[] = [];

  // Check inputMappings for array-mapped fields
  Object.entries(inputMappings).forEach(([paramKey, mapping]) => {
    const typedMapping = mapping as { mappingType?: string; stepId?: string; outputField?: string } | undefined;
    if (typedMapping?.mappingType === 'mapped' && typedMapping.stepId && typedMapping.outputField) {
      const prevStepIndex = enhancedPreviousSteps.findIndex(s => s.id === typedMapping.stepId);
      const prevStep = prevStepIndex >= 0 ? enhancedPreviousSteps[prevStepIndex] : null;
      if (prevStep) {
        const stepsBeforePrevStep = enhancedPreviousSteps.slice(0, prevStepIndex);
        const effectiveOutputs = getEffectiveOutputs(prevStep, stepsBeforePrevStep);
        const baseFieldMatch = typedMapping.outputField.match(/^(\w+)(?:\[\*\])?/);
        const baseField = baseFieldMatch ? baseFieldMatch[1] : typedMapping.outputField;
        const outputDef = effectiveOutputs[baseField] as { type?: string } | undefined;
        if (outputDef?.type === 'array') {
          arrayMappedFields.push({
            paramKey,
            stepId: typedMapping.stepId,
            outputField: typedMapping.outputField,
            stepName: prevStep.name || prevStep.id,
          });
        }
      }
    }
  });

  // Also scan parameters for template expressions (with or without [*])
  const scanForArrayTemplates = (obj: unknown, path: string = ''): void => {
    if (typeof obj === 'string') {
      const matches = obj.matchAll(/\{\{\s*(\w+)\.(\w+)(?:\[\*\])?(?:\.(\w+))?\s*\}\}/g);
      for (const match of matches) {
        const [fullMatch, stepId, fieldName, nestedField] = match;
        const prevStepIndex = enhancedPreviousSteps.findIndex(s => s.id === stepId);
        const prevStep = prevStepIndex >= 0 ? enhancedPreviousSteps[prevStepIndex] : null;
        if (!prevStep) continue;

        const stepsBeforePrevStep = enhancedPreviousSteps.slice(0, prevStepIndex);
        const effectiveOutputs = getEffectiveOutputs(prevStep, stepsBeforePrevStep);

        const outputDef = effectiveOutputs[fieldName] as { type?: string } | undefined;
        if (outputDef?.type !== 'array') continue;

        const hasIterMarker = fullMatch.includes('[*]');
        const outputFieldPath = hasIterMarker
          ? (nestedField ? `${fieldName}[*].${nestedField}` : `${fieldName}[*]`)
          : `${fieldName}[*]`;

        if (!arrayMappedFields.some(f => f.stepId === stepId && f.outputField === outputFieldPath)) {
          arrayMappedFields.push({
            paramKey: path,
            stepId,
            outputField: outputFieldPath,
            stepName: prevStep.name || prevStep.id,
          });
        }
      }
    } else if (Array.isArray(obj)) {
      obj.forEach((item, i) => scanForArrayTemplates(item, `${path}[${i}]`));
    } else if (obj && typeof obj === 'object') {
      Object.entries(obj as Record<string, unknown>).forEach(([k, v]) => scanForArrayTemplates(v, path ? `${path}.${k}` : k));
    }
  };
  scanForArrayTemplates(parameters);

  // Deduplicate by base field name (strip [*] for comparison)
  const uniqueFields = arrayMappedFields.filter((f, i, arr) =>
    arr.findIndex(x => x.stepId === f.stepId && x.outputField.replace('[*]', '') === f.outputField.replace('[*]', '')) === i
  );

  const hasArrayMappings = uniqueFields.length > 0;
  const isIterationEnabled = step.iteration_config?.enabled === true;

  // Service-level iterable flag (default true). When false, the service
  // handles array expansion internally - hide the iteration checkbox.
  const serviceIterable = serviceMetadata?.iterable !== false;

  const [docsOpen, setDocsOpen] = useState(false);

  if (!hasArrayMappings || !serviceIterable) return null;

  return (
    <>
      <div className={`mb-4 p-3 rounded-lg border${isIterationEnabled ? 'bg-success-subtle border-success' : 'bg-surface border-primary'}`}>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 cursor-pointer flex-1">
            <input
              type="checkbox"
              checked={isIterationEnabled}
              onChange={(e) => {
                if (e.target.checked) {
                  onUpdate({
                    ...step,
                    iteration_config: {
                      enabled: true,
                      source_step_id: uniqueFields[0].stepId,
                      source_output_field: uniqueFields[0].outputField,
                      target_parameter: uniqueFields[0].paramKey,
                    },
                  });
                } else {
                  onUpdate({
                    ...step,
                    iteration_config: undefined,
                  });
                }
              }}
              className="h-4 w-4 text-success border-primary rounded focus:ring-emerald-500"
            />
            <Repeat className={`h-4 w-4${isIterationEnabled ? 'text-success' : 'text-muted'}`} />
            <span className={`text-sm font-medium${isIterationEnabled ? 'text-success' : 'text-secondary'}`}>
              Run once per item
            </span>
          </label>
          <button
            type="button"
            onClick={() => setDocsOpen(true)}
            className="text-xs text-link hover:underline"
          >
            Learn more
          </button>
        </div>
        <div className="mt-2 text-xs">
          {isIterationEnabled ? (
            <p className="text-success">
              Runs once for each item in:{' '}
              {uniqueFields.map((f, i) => (
                <span key={f.outputField}>
                  {i > 0 && ', '}
                  <code className="px-1 py-0.5 bg-success-subtle rounded">
                    {f.stepName} &rarr; {f.outputField.replace('[*]', '[]')}
                  </code>
                </span>
              ))}
            </p>
          ) : (
            <p className="text-warning">
              &#9888;&#65039; A list is connected. Check this to run the step once for each item.
            </p>
          )}
        </div>
      </div>
      <ProviderDocsSlideOver
        slug="item-groups"
        isOpen={docsOpen}
        onClose={() => setDocsOpen(false)}
        fetchContent={getWorkflowDocContent}
      />
    </>
  );
}
