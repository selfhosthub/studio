// ui/features/step-config/PreviousStepOutputsPanel/components/JsonView.tsx

'use client';

import { Step } from '@/entities/workflow';
import { FilterType } from '../utils/panelUtils';
import { getSampleValue } from '../utils/panelUtils';

/**
 * JSON view - shows key/value structure with sample values
 * Steps are shown in reverse order (most recent first)
 * Shows full paths to variables which is valuable for mapping
 */
export function JsonView({
  previousSteps,
  typeFilter
}: {
  previousSteps: Step[];
  typeFilter: FilterType | null;
}) {
  // Reverse steps so immediate previous step is first
  const reversedSteps = [...previousSteps].reverse();
  const outputData: Record<string, any> = {};

  reversedSteps.forEach((step) => {
    const stepKey = step.name || step.id;
    const outputs = step.outputs || {};
    const stepOutputs: Record<string, any> = {};

    Object.entries(outputs).forEach(([fieldName, fieldDef]) => {
      const typedField = fieldDef as { type?: string; items?: any };
      const fieldType = typedField.type || 'string';

      // Apply type filter if active
      if (typeFilter) {
        const matchesFilter = typeFilter === 'number'
          ? (fieldType === 'number' || fieldType === 'integer')
          : fieldType === typeFilter;
        if (!matchesFilter) return;
      }

      // Show sample value based on type, pass items for array nested structure
      stepOutputs[fieldName] = getSampleValue(fieldType, fieldName, typedField.items);
    });

    // Only include step if it has outputs (after filtering)
    if (Object.keys(stepOutputs).length > 0) {
      outputData[stepKey] = stepOutputs;
    }
  });

  // Show message if filter results in no data
  if (typeFilter && Object.keys(outputData).length === 0) {
    return (
      <div className="text-center py-8 text-secondary">
        <p className="text-sm">No fields match the selected type filter</p>
      </div>
    );
  }

  return (
    <pre className="text-xs font-mono bg-card p-3 rounded-md overflow-auto min-h-[200px] max-h-[60vh] text-primary">
      {JSON.stringify(outputData, null, 2)}
    </pre>
  );
}
