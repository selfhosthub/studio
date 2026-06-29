// ui/features/step-config/ui/input-mapping/BaseMappingItem.tsx

'use client';

import React from 'react';
import { ChevronDown, ChevronRight, Trash2, Info } from 'lucide-react';
import { Step } from '@/entities/workflow';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';

interface BaseMappingItemProps {
  mappingKey: string;
  mapping: {
    source_step_id: string;
    source_output_field: string;
    transform?: string;
  };
  previousSteps: Step[];
  isCollapsed: boolean;
  onUpdate: (mappingKey: string, updatedMapping: any) => void;
  onRemove: (mappingKey: string) => void;
  onToggleCollapse: (mappingKey: string) => void;
  showTransform?: boolean;
}

export default function BaseMappingItem({
  mappingKey,
  mapping,
  previousSteps,
  isCollapsed,
  onUpdate,
  onRemove,
  onToggleCollapse,
  showTransform = true
}: BaseMappingItemProps) {
  const handleRemove = () => {
    onRemove(mappingKey);
  };

  const handleSourceStepChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdate(mappingKey, {
      ...mapping,
      source_step_id: e.target.value,
      source_output_field: ''  // Reset output field when step changes
    });
  };

  const handleSourceOutputFieldChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdate(mappingKey, {
      ...mapping,
      source_output_field: e.target.value
    });
  };

  const handleTransformChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onUpdate(mappingKey, {
      ...mapping,
      transform: e.target.value
    });
  };

  // Get selected step and compute effective outputs (including pass-through fields)
  // previousSteps is in workflow order [oldest, ..., newest]
  const selectedStep = previousSteps.find(step => step.id === mapping.source_step_id);
  const selectedStepIdx = selectedStep ? previousSteps.indexOf(selectedStep) : -1;
  const stepsBeforeSelected = selectedStepIdx >= 0 ? previousSteps.slice(0, selectedStepIdx) : [];
  const availableOutputFields = selectedStep ? getEffectiveOutputs(selectedStep, stepsBeforeSelected) : {};

  return (
    <div className="border rounded-md p-3 bg-card">
      <div className="flex items-center justify-between mb-2">
        <div 
          className="flex items-center cursor-pointer" 
          onClick={() => onToggleCollapse(mappingKey)}
        >
          {isCollapsed ? (
            <ChevronRight className="h-5 w-5 mr-1" />
          ) : (
            <ChevronDown className="h-5 w-5 mr-1" />
          )}
          <span className="font-medium">{mappingKey}</span>
        </div>
        <button 
          onClick={handleRemove}
          className="text-danger hover:text-danger"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {!isCollapsed && (
        <div className="space-y-4 mt-3">
          <div>
            <label className="block text-sm font-medium mb-1">Source Step</label>
            <select
              value={mapping.source_step_id}
              onChange={handleSourceStepChange}
              className="w-full p-2 border rounded-md bg-card"
            >
              <option value="">Select source step</option>
              {previousSteps.map(step => (
                <option key={step.id} value={step.id}>
                  {step.name || `Step ${step.id}`}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Source Field</label>
            <select
              value={mapping.source_output_field}
              onChange={handleSourceOutputFieldChange}
              className="w-full p-2 border rounded-md bg-card"
              disabled={!mapping.source_step_id}
            >
              <option value="">Select output field</option>
              {Object.keys(availableOutputFields).map(fieldKey => (
                <option key={fieldKey} value={fieldKey}>
                  {fieldKey}
                </option>
              ))}
            </select>
          </div>

          {showTransform && (
            <div>
              <div className="flex items-center mb-1">
                <label className="block text-sm font-medium">Transform (Optional)</label>
                <div className="ml-1 text-secondary cursor-help" title="JavaScript expression to transform the value. Use 'value' to reference the source value.">
                  <Info className="h-4 w-4" />
                </div>
              </div>
              <textarea
                value={mapping.transform || ''}
                onChange={handleTransformChange}
                placeholder="e.g. value.toUpperCase()"
                className="w-full p-2 border rounded-md bg-card min-h-[80px]"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}