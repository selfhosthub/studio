// ui/features/step-config/MappableParameterField/components/MappedFieldSelector.tsx

'use client';

import React, { useState, useRef, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { Repeat } from 'lucide-react';
import { Step } from '@/entities/workflow';
import type { InputMapping } from '../types';

interface MappedFieldSelectorProps {
  effectiveMapping: InputMapping | null;
  mapping: InputMapping | undefined;
  reversedSteps: Step[];
  availableOutputs: Record<string, any>;
  isIteratorMapping: boolean;
  mappedOutputType?: string;
  isArrayType: boolean;
  isIterationEnabled: boolean;
  paramKey: string;
  instanceFormFields?: Record<string, any>;
  currentStepId?: string;
  onMappingChange: (key: string, mapping: InputMapping | null) => void;
}

export function MappedFieldSelector({
  effectiveMapping,
  mapping,
  reversedSteps,
  availableOutputs,
  isIteratorMapping,
  mappedOutputType,
  isArrayType,
  isIterationEnabled,
  paramKey,
  instanceFormFields,
  currentStepId,
  onMappingChange,
}: MappedFieldSelectorProps) {
  const [showLoopSettings, setShowLoopSettings] = useState(false);
  const [loopSettingsPosition, setLoopSettingsPosition] = useState<{ top: number; left: number } | null>(null);
  const loopSettingsButtonRef = useRef<HTMLButtonElement>(null);
  const loopSettingsMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showLoopSettings) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!loopSettingsButtonRef.current?.contains(target) && !loopSettingsMenuRef.current?.contains(target)) {
        setShowLoopSettings(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showLoopSettings]);

  const handleStepChange = (stepId: string) => {
    onMappingChange(paramKey, { ...mapping, mappingType: 'mapped', stepId, outputField: '' });
  };

  const handleOutputFieldChange = (outputField: string) => {
    onMappingChange(paramKey, { ...mapping, mappingType: 'mapped', outputField });
  };

  const handleLoopChange = (loopEnabled: boolean) => {
    if (effectiveMapping) {
      onMappingChange(paramKey, { ...effectiveMapping, loop: loopEnabled });
    }
    setShowLoopSettings(false);
  };

  const handleLoopSettingsToggle = () => {
    if (!showLoopSettings && loopSettingsButtonRef.current) {
      const rect = loopSettingsButtonRef.current.getBoundingClientRect();
      setLoopSettingsPosition({ top: rect.bottom + 4, left: rect.left });
    }
    setShowLoopSettings(!showLoopSettings);
  };

  return (
    <div className="flex-1 min-w-0 space-y-2">
      <div className="param-field-input-row">
        <select
          value={effectiveMapping?.stepId || ''}
          onChange={(e) => handleStepChange(e.target.value)}
          className="p-2 border rounded text-sm"
        >
          <option value="">Select step...</option>
          {instanceFormFields && Object.keys(instanceFormFields).some(k => !instanceFormFields[k]._owning_step_ids?.includes(currentStepId || '')) && (
            <option value="__instance_form__" className="font-semibold">Instance Form</option>
          )}
          {reversedSteps.map((step) => (
            <option key={step.id} value={step.id}>{step.name || step.id}</option>
          ))}
        </select>
        <select
          value={effectiveMapping?.outputField?.replace(/\[\*\]$/, '') || ''}
          onChange={(e) => handleOutputFieldChange(e.target.value)}
          disabled={!effectiveMapping?.stepId}
          className="p-2 border rounded text-sm disabled:opacity-50"
        >
          <option value="">Select output...</option>
          {Object.entries(availableOutputs).flatMap(([fieldName, fieldDef]) => {
            const typedField = fieldDef as { type?: string; items?: { properties?: Record<string, { type?: string }> } };
            const options = [
              <option key={fieldName} value={fieldName}>{fieldName} ({typedField.type || 'string'})</option>
            ];
            if (typedField.type === 'array' && typedField.items?.properties) {
              Object.entries(typedField.items.properties).forEach(([nestedKey, nestedDef]) => {
                const nestedPath = `${fieldName}[*].${nestedKey}`;
                options.push(<option key={nestedPath} value={nestedPath}>&nbsp;&nbsp;↳ {nestedKey} ({nestedDef.type || 'string'})</option>);
              });
            }
            return options;
          })}
        </select>
        {isIteratorMapping && (
          <div className="relative">
            <button
              ref={loopSettingsButtonRef}
              type="button"
              onClick={handleLoopSettingsToggle}
              className={`p-2 border rounded transition-colors ${
                effectiveMapping?.loop
                  ? 'bg-info border-info hover:opacity-90'
                  : 'bg-card border-primary hover:bg-input'
              }`}
              title={effectiveMapping?.loop ? 'Iterator: Loop' : 'Iterator: Use once'}
            >
              <Repeat className={`h-4 w-4 ${effectiveMapping?.loop ? 'text-white' : 'text-secondary'}`} />
            </button>
            {showLoopSettings && loopSettingsPosition && ReactDOM.createPortal(
              <div
                ref={loopSettingsMenuRef}
                data-step-config-dropdown
                className="fixed bg-card border border-primary rounded-lg shadow-lg p-3 z-50 min-w-[180px]"
                style={{ top: loopSettingsPosition.top, left: loopSettingsPosition.left }}
              >
                <div className="text-xs font-medium text-secondary mb-2">Iterator Behavior</div>
                <div className="space-y-1">
                  <label className="flex items-center gap-2 p-2 rounded hover:bg-card cursor-pointer">
                    <input type="radio" name={`loop-${paramKey}`} checked={!effectiveMapping?.loop} onChange={() => handleLoopChange(false)} className="text-info" />
                    <span className="text-sm text-secondary">Use once</span>
                  </label>
                  <label className="flex items-center gap-2 p-2 rounded hover:bg-card cursor-pointer">
                    <input type="radio" name={`loop-${paramKey}`} checked={effectiveMapping?.loop === true} onChange={() => handleLoopChange(true)} className="text-info" />
                    <span className="text-sm text-secondary">Loop</span>
                  </label>
                </div>
                <div className="mt-2 pt-2 border-t border-primary">
                  <p className="text-muted text-xs">Loop cycles values when exhausted to match the longest iterator.</p>
                </div>
              </div>,
              document.body
            )}
          </div>
        )}
      </div>
      {mappedOutputType === 'array' && !isArrayType && !isIterationEnabled && (
        <div className="p-2 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-md"> {/* css-check-ignore: no semantic token */}
          <p className="text-xs text-purple-600 dark:text-purple-400"> {/* css-check-ignore: no semantic token */}
            Only the first item from this list will be used. Enable &quot;Run once per item&quot; above to process all items.
          </p>
        </div>
      )}
    </div>
  );
}
