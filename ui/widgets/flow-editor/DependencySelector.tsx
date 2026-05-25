// ui/widgets/flow-editor/DependencySelector.tsx

'use client';

import React from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { wouldCreateCycle, getDependentSteps } from '@/shared/lib/step-utils';
import { useToast } from '@/features/toast';

interface DependencySelectorProps {
  currentStepId: string;
  currentDependencies: string[];
  allSteps: Record<string, { name: string; depends_on?: string[] }>;
  onChange: (newDependencies: string[]) => void;
  disabled?: boolean;
}

export default function DependencySelector({
  currentStepId,
  currentDependencies,
  allSteps,
  onChange,
  disabled = false
}: DependencySelectorProps) {
  const { toast } = useToast();
  // Get steps that depend on this step (for warning)
  const dependents = getDependentSteps(currentStepId, allSteps);

  // Get available steps (exclude self)
  const availableSteps = Object.entries(allSteps).filter(
    ([id]) => id !== currentStepId
  );

  const handleToggle = (depId: string) => {
    if (disabled) return;

    const isCurrentlyDependent = currentDependencies.includes(depId);

    let newDependencies: string[];
    if (isCurrentlyDependent) {
      // Removing dependency
      newDependencies = currentDependencies.filter(id => id !== depId);
    } else {
      // Adding dependency
      newDependencies = [...currentDependencies, depId];

      // Check for circular dependency
      if (wouldCreateCycle(currentStepId, newDependencies, allSteps)) {
        toast({ title: 'Circular dependency', description: `Cannot add dependency "${depId}": This would create a circular dependency.`, variant: 'destructive' });
        return;
      }
    }

    onChange(newDependencies);
  };

  if (availableSteps.length === 0) {
    return (
      <div className="text-sm text-secondary py-2">
        No other steps available to depend on.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Info message */}
      <div className="flex items-start space-x-2 p-3 bg-info-subtle border border-info rounded-md">
        <Info className="h-4 w-4 text-info mt-0.5 flex-shrink-0" />
        <div className="text-sm text-info">
          <p className="font-medium">About Dependencies</p>
          <p className="mt-1">
            This step will only run after all its dependencies have completed successfully.
            Select which steps must complete before this one runs.
          </p>
        </div>
      </div>

      {/* Dependent steps warning */}
      {dependents.length > 0 && (
        <div className="flex items-start space-x-2 p-3 bg-warning-subtle border border-warning rounded-md">
          <AlertTriangle className="h-4 w-4 text-warning mt-0.5 flex-shrink-0" />
          <div className="text-sm text-warning">
            <p className="font-medium">Steps depending on this one:</p>
            <ul className="mt-1 list-disc list-inside">
              {dependents.map(depId => (
                <li key={depId}>{allSteps[depId]?.name || depId}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Dependency checkboxes */}
      <div className="space-y-2">
        <label className="form-label">
          Dependencies ({currentDependencies.length} selected)
        </label>
        <div className="border border-primary rounded-md divide-y divide-primary max-h-64 overflow-y-auto">
          {availableSteps.map(([stepId, step]) => {
            const isSelected = currentDependencies.includes(stepId);

            return (
              <label
                key={stepId}
                className={`flex items-center space-x-3 p-3 cursor-pointer transition-colors ${
                  disabled
                    ? 'opacity-50 cursor-not-allowed'
                    : 'hover:bg-surface'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => handleToggle(stepId)}
                  disabled={disabled}
                  className="h-4 w-4 text-info focus:ring-blue-500 border-primary rounded disabled:cursor-not-allowed"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-primary">
                    {step.name}
                  </div>
                  <div className="text-xs text-secondary font-mono">
                    {stepId}
                  </div>
                  {step.depends_on && step.depends_on.length > 0 && (
                    <div className="text-xs text-secondary mt-1">
                      Depends on: {step.depends_on.join(', ')}
                    </div>
                  )}
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* Current selection summary */}
      {currentDependencies.length > 0 && (
        <div className="text-sm text-secondary">
          <p className="font-medium mb-1">This step will run after:</p>
          <ul className="list-disc list-inside space-y-1">
            {currentDependencies.map(depId => (
              <li key={depId}>
                {allSteps[depId]?.name || depId}
                <span className="text-xs font-mono ml-2 text-secondary">({depId})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
