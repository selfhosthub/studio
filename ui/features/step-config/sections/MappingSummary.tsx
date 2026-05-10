// ui/features/step-config/sections/MappingSummary.tsx

'use client';

import React from 'react';
import { Step } from '@/entities/workflow';
import { Link2, ArrowRight, Sparkles } from 'lucide-react';

interface InputMapping {
  mappingType?: 'mapped' | 'static';
  stepId?: string;
  outputField?: string;
  source_step_id?: string;
  source_output_field?: string;
  staticValue?: string;
  loop?: boolean;
}

interface MappingSummaryProps {
  inputMappings: Record<string, InputMapping>;
  previousSteps: Step[];
  onFieldClick?: (paramKey: string) => void;
}

/**
 * Compact summary of current mappings
 * Shows which parameters are mapped and their sources
 * Clicking a mapping scrolls to that field in Service Parameters
 */
export function MappingSummary({
  inputMappings,
  previousSteps,
  onFieldClick,
}: MappingSummaryProps) {
  // Get only active mappings (mappingType === 'mapped')
  const activeMappings = Object.entries(inputMappings).filter(
    ([_, mapping]) => mapping.mappingType === 'mapped'
  );

  if (activeMappings.length === 0) {
    return null; // Don't show anything if no mappings
  }

  // Helper to get step name from ID
  const getStepName = (stepId: string | undefined) => {
    if (!stepId) return 'Unknown';
    const step = previousSteps.find(s => s.id === stepId);
    return step?.name || stepId;
  };

  return (
    <div className="mb-4 p-3 bg-critical-subtle border border-critical rounded-lg">
      <div className="flex items-center gap-2 mb-2">
        <Link2 className="h-4 w-4 text-critical" />
        <span className="text-sm font-medium text-critical">
          {activeMappings.length} Mapped Parameter{activeMappings.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-1">
        {activeMappings.map(([paramKey, mapping]) => {
          const stepId = mapping.stepId || mapping.source_step_id;
          const outputField = mapping.outputField || mapping.source_output_field;
          const stepName = getStepName(stepId);

          return (
            <button
              key={paramKey}
              onClick={() => onFieldClick?.(paramKey)}
              className="w-full flex items-center gap-2 px-2 py-1 text-left text-sm rounded hover:bg-critical-subtle transition-colors group"
              title={`Click to scroll to ${paramKey}`}
            >
              <span className="font-mono text-critical group-hover:underline flex items-center gap-1">
                {paramKey.startsWith('_prompt_variable:') ? (
                  <><Sparkles className="h-3 w-3 text-success flex-shrink-0" />{paramKey.replace('_prompt_variable:', '')}</>
                ) : paramKey}
              </span>
              <ArrowRight className="h-3 w-3 text-critical flex-shrink-0" />
              <span className="text-critical truncate">
                {stepName}
              </span>
              <span className="text-critical">→</span>
              <span className="font-mono text-critical truncate">
                {outputField || '(not set)'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default MappingSummary;
