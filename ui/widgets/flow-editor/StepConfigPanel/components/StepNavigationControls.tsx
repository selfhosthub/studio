// ui/widgets/flow-editor/StepConfigPanel/components/StepNavigationControls.tsx

'use client';

import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, ChevronDown, Link } from 'lucide-react';
import type { Step } from '@/entities/workflow';

interface StepNavigationControlsProps {
  allSteps?: Record<string, Step>;
  currentStepId: string;
  currentStepDependsOn: string[];
  onSelectStep: (stepId: string) => void;
}

export function StepNavigationControls({
  allSteps,
  currentStepId,
  currentStepDependsOn,
  onSelectStep,
}: StepNavigationControlsProps) {
  const [showStepDropdown, setShowStepDropdown] = useState<'prev' | 'next' | false>(false);

  const stepsArray = allSteps ? Object.values(allSteps) : [];
  if (stepsArray.length <= 1) return null;

  const currentStepIndex = stepsArray.findIndex(s => s.id === currentStepId);
  const dependsOn = currentStepDependsOn;

  // Previous steps: all steps before current in workflow order
  const prevSteps = currentStepIndex > 0 ? stepsArray.slice(0, currentStepIndex) : [];
  // Next steps: all steps after current in workflow order
  const nextSteps = currentStepIndex < stepsArray.length - 1 ? stepsArray.slice(currentStepIndex + 1) : [];

  // Immediate predecessor: direct dependency closest in workflow order
  const immediatePredecessorId = currentStepIndex > 0
    ? stepsArray.slice(0, currentStepIndex).reverse().find(s => dependsOn.includes(s.id))?.id
    : null;

  // Immediate successor: step that directly depends on us, closest in workflow order
  const immediateSuccessorId = currentStepIndex < stepsArray.length - 1
    ? stepsArray.slice(currentStepIndex + 1).find(s => s.depends_on?.includes(currentStepId))?.id
    : null;

  const hasPrev = prevSteps.length > 0;
  const hasNext = nextSteps.length > 0;
  const hasMultiplePrev = prevSteps.length > 1;
  const hasMultipleNext = nextSteps.length > 1;

  return (
    <div className="relative flex items-center gap-1 text-xs text-secondary">
      {/* Previous step label - always navigates to nearest previous step */}
      <button
        type="button"
        onClick={() => {
          if (!hasPrev) return;
          // Navigate to the nearest previous step (last in prevSteps array)
          onSelectStep(prevSteps[prevSteps.length - 1].id);
        }}
        disabled={!hasPrev}
        className={`hover:text-secondary transition-colors ${hasPrev ? 'cursor-pointer' : 'opacity-30 cursor-not-allowed'}`}
        title={hasPrev ? `Go to ${prevSteps[prevSteps.length - 1].name || prevSteps[prevSteps.length - 1].id}` : 'No previous step'}
      >
        prev
      </button>

      {/* Previous step arrow - dropdown if multiple, navigate if single */}
      {hasMultiplePrev ? (
        <button
          type="button"
          onClick={() => setShowStepDropdown(showStepDropdown === 'prev' ? false : 'prev')}
          className="flex items-center gap-0.5 p-1 rounded-md text-muted hover:text-secondary hover:bg-card transition-colors"
          title="Select from previous steps"
        >
          <ChevronLeft size={16} />
          <ChevronDown size={10} />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => hasPrev && onSelectStep(prevSteps[0].id)}
          disabled={!hasPrev}
          className="p-1 rounded-md text-muted hover:text-secondary hover:bg-card transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title={hasPrev ? `Go to ${prevSteps[0].name || prevSteps[0].id}` : 'No previous step'}
        >
          <ChevronLeft size={16} />
        </button>
      )}

      {/* Next step arrow - dropdown if multiple, navigate if single */}
      {hasMultipleNext ? (
        <button
          type="button"
          onClick={() => setShowStepDropdown(showStepDropdown === 'next' ? false : 'next')}
          className="flex items-center gap-0.5 p-1 rounded-md text-muted hover:text-secondary hover:bg-card transition-colors"
          title="Select from next steps"
        >
          <ChevronRight size={16} />
          <ChevronDown size={10} />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => hasNext && onSelectStep(nextSteps[0].id)}
          disabled={!hasNext}
          className="p-1 rounded-md text-muted hover:text-secondary hover:bg-card transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title={hasNext ? `Go to ${nextSteps[0].name || nextSteps[0].id}` : 'No next step'}
        >
          <ChevronRight size={16} />
        </button>
      )}

      {/* Next step label - always navigates to nearest next step */}
      <button
        type="button"
        onClick={() => {
          if (!hasNext) return;
          // Navigate to the nearest next step (first in nextSteps array)
          onSelectStep(nextSteps[0].id);
        }}
        disabled={!hasNext}
        className={`hover:text-secondary transition-colors ${hasNext ? 'cursor-pointer' : 'opacity-30 cursor-not-allowed'}`}
        title={hasNext ? `Go to ${nextSteps[0].name || nextSteps[0].id}` : 'No next step'}
      >
        next
      </button>

      {/* Dropdown for prev steps - reverse order so nearest is first */}
      {showStepDropdown === 'prev' && hasMultiplePrev && (
        <div className="absolute left-0 top-full mt-1 bg-card border border-primary rounded-md shadow-lg z-50 min-w-[150px]">
          {[...prevSteps].reverse().map(s => (
            <button
              type="button"
              key={s.id}
              onClick={() => {
                onSelectStep(s.id);
                setShowStepDropdown(false);
              }}
              className="w-full text-left px-3 py-2 text-sm text-secondary hover:bg-card first:rounded-t-md last:rounded-b-md flex items-center gap-2"
            >
              {s.id === immediatePredecessorId && (
                <Link size={12} className="text-info flex-shrink-0" />
              )}
              {s.name || s.id}
            </button>
          ))}
        </div>
      )}

      {/* Dropdown for next steps - already in order (nearest first) */}
      {showStepDropdown === 'next' && hasMultipleNext && (
        <div className="absolute right-0 top-full mt-1 bg-card border border-primary rounded-md shadow-lg z-50 min-w-[150px]">
          {nextSteps.map(s => (
            <button
              type="button"
              key={s.id}
              onClick={() => {
                onSelectStep(s.id);
                setShowStepDropdown(false);
              }}
              className="w-full text-left px-3 py-2 text-sm text-secondary hover:bg-card first:rounded-t-md last:rounded-b-md flex items-center gap-2"
            >
              {s.id === immediateSuccessorId && (
                <Link size={12} className="text-info flex-shrink-0" />
              )}
              {s.name || s.id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
