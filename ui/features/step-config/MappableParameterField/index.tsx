// ui/features/step-config/MappableParameterField/index.tsx

'use client';

import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { Link2, Type, ChevronDown, HelpCircle, FileInput, Repeat, Sparkles } from 'lucide-react';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';
import DynamicCombobox from '@/shared/ui/DynamicCombobox';

// Extracted components
import { PromptInput } from './components/PromptInput';
import { StaticInputRenderer } from './components/StaticInputRenderer';
import { MappedFieldSelector } from './components/MappedFieldSelector';
import { ArrayItemsPanel } from './components/ArrayItemsPanel';

// Array widget registry
import { getArrayWidget } from '@/shared/lib/array-widget-registry';
import '@/features/step-config/register-builtin-widgets'; // Auto-register built-in widgets

// Utils
import { formatSampleValue } from './utils/schemaUtils';

// Types
import type { MappableParameterFieldProps, InputMapping, FieldMode } from './types';

// Re-export types for external use
export type { PropertySchema, InputMapping, UIState, MappableParameterFieldProps, FieldMode } from './types';

/**
 * A parameter field that can toggle between Static value entry and Mapped (from previous step output)
 */
export function MappableParameterField({
  paramKey,
  schema,
  value,
  mapping,
  previousSteps,
  required = false,
  onValueChange,
  onMappingChange,
  uiState,
  onUiStateChange,
  iterationConfig,
  onIterationChange,
  providerId,
  credentialId,
  allFieldValues = {},
  exampleValue,
  allInputMappings = {},
  onReorderMappings,
  onRemoveItemMappings,
  instanceFormFields,
  currentStepId,
}: MappableParameterFieldProps) {
  // Detect if value is a template string
  const detectMappingFromValue = (): { stepId: string; outputField: string } | null => {
    if (typeof value === 'string') {
      const templateMatch = value.match(/^\{\{\s*(?:steps\.)?([\w-]+)\.(.+?)\s*\}\}$/);
      if (templateMatch) {
        return { stepId: templateMatch[1], outputField: templateMatch[2] };
      }
    }
    return null;
  };

  const detectedMapping = detectMappingFromValue();
  const isMapped = mapping?.mappingType === 'mapped' || detectedMapping !== null;
  const isForm = mapping?.mappingType === 'form';
  const isPrompt = mapping?.mappingType === 'prompt';
  const currentMode = detectedMapping ? 'mapped' : (mapping?.mappingType || 'static');

  const effectiveMapping = mapping?.mappingType === 'mapped' ? mapping : detectedMapping ? {
    mappingType: 'mapped' as const,
    stepId: detectedMapping.stepId,
    outputField: detectedMapping.outputField,
  } : mapping;

  // State for mode dropdown
  const [showModeDropdown, setShowModeDropdown] = useState(false);
  const [modeDropdownPosition, setModeDropdownPosition] = useState<{ top: number; left: number } | null>(null);
  const modeDropdownButtonRef = useRef<HTMLButtonElement>(null);
  const modeDropdownMenuRef = useRef<HTMLDivElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const label = schema.title || paramKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const isArrayType = schema.type === 'array';
  const isComplexArray = isArrayType && schema.items?.properties;
  const reversedSteps = [...previousSteps].reverse();

  // Get available outputs from selected step (or instance form fields)
  const isInstanceFormSelected = effectiveMapping?.stepId === '__instance_form__';
  const selectedStep = isInstanceFormSelected ? undefined : reversedSteps.find(s => s.id === effectiveMapping?.stepId);
  const selectedStepIndex = selectedStep ? reversedSteps.indexOf(selectedStep) : -1;
  const stepsBeforeSelected = selectedStepIndex >= 0 ? reversedSteps.slice(selectedStepIndex + 1).reverse() : [];
  const availableOutputs = isInstanceFormSelected && instanceFormFields
    ? Object.fromEntries(
        Object.entries(instanceFormFields).filter(
          ([, def]) => !def._owning_step_ids?.includes(currentStepId || '')
        )
      )
    : selectedStep ? getEffectiveOutputs(selectedStep, stepsBeforeSelected) : {};

  // Get mapped output type
  const getMappedOutputType = (): string | undefined => {
    if (!effectiveMapping?.outputField) return undefined;
    const outputField = effectiveMapping.outputField;
    const nestedArrayMatch = outputField.match(/^(\w+)\[\*\]/);
    if (nestedArrayMatch) {
      const baseFieldDef = availableOutputs[nestedArrayMatch[1]] as { type?: string } | undefined;
      return baseFieldDef?.type;
    }
    const fieldDef = availableOutputs[outputField] as { type?: string } | undefined;
    return fieldDef?.type;
  };
  const mappedOutputType = getMappedOutputType();

  // Iteration detection - scan allInputMappings for nested array mappings with [*] paths
  const nestedArrayMappings = (() => {
    if (!schema.iterable || !isComplexArray) return [];
    const results: Array<{ stepId: string; outputField: string }> = [];
    for (const [key, m] of Object.entries(allInputMappings)) {
      if (key.startsWith(`${paramKey}[`) && m.mappingType === 'mapped' && m.outputField?.includes('[*]') && m.stepId) {
        results.push({ stepId: m.stepId, outputField: m.outputField });
      }
    }
    // Also detect from template strings in array values
    if (results.length === 0 && Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === 'object' && item !== null) {
          for (const fieldValue of Object.values(item)) {
            if (typeof fieldValue === 'string') {
              const m = (fieldValue as string).match(/^\{\{\s*(?:steps\.)?([\w-]+)\.(.+?\[\*\].*?)\s*\}\}$/);
              if (m) results.push({ stepId: m[1], outputField: m[2] });
            }
          }
        }
      }
    }
    return results;
  })();
  const nestedArrayMapping = nestedArrayMappings.length > 0 ? nestedArrayMappings[0] : null;
  const isIterationEnabled = iterationConfig?.enabled === true;
  const hasStarPath = isMapped && (effectiveMapping?.outputField?.includes('[*]') ?? false);
  const isIteratorMapping = isMapped && isIterationEnabled && !isArrayType && (mappedOutputType === 'array' || hasStarPath);
  const isIterationApplicable = onIterationChange && (
    (isMapped && mappedOutputType === 'array' && !isArrayType) ||
    (schema.iterable && isComplexArray && nestedArrayMappings.length > 0)
  );

  // Close mode dropdown on outside click
  useEffect(() => {
    if (!showModeDropdown) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!modeDropdownButtonRef.current?.contains(target) && !modeDropdownMenuRef.current?.contains(target)) {
        setShowModeDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModeDropdown]);

  // Handlers
  const handleModeDropdownToggle = () => {
    if (!showModeDropdown && modeDropdownButtonRef.current) {
      const rect = modeDropdownButtonRef.current.getBoundingClientRect();
      setModeDropdownPosition({ top: rect.bottom + 4, left: rect.right - 192 });
    }
    setShowModeDropdown(!showModeDropdown);
  };

  const handleModeChange = (newMode: FieldMode | 'iterate') => {
    setShowModeDropdown(false);
    if (newMode === 'static') {
      onMappingChange(paramKey, null);
      if (onIterationChange && iterationConfig?.target_parameter === paramKey) {
        onIterationChange(undefined);
      }
    } else if (newMode === 'mapped') {
      onMappingChange(paramKey, { mappingType: 'mapped', stepId: '', outputField: '', staticValue: '' });
      if (onIterationChange && iterationConfig?.target_parameter === paramKey) {
        onIterationChange(undefined);
      }
    } else if (newMode === 'form') {
      onMappingChange(paramKey, { mappingType: 'form' });
      if (onIterationChange && iterationConfig?.target_parameter === paramKey) {
        onIterationChange(undefined);
      }
    } else if (newMode === 'prompt') {
      if (Array.isArray(value) && value.length > 0) {
        const confirmed = window.confirm(
          'Switching to a prompt will replace your existing messages. This cannot be undone.\n\nContinue?'
        );
        if (!confirmed) return;
      }
      onMappingChange(paramKey, { mappingType: 'prompt', promptId: '', variableValues: {} });
      if (onIterationChange && iterationConfig?.target_parameter === paramKey) {
        onIterationChange(undefined);
      }
    } else if (newMode === 'iterate') {
      if (onIterationChange && effectiveMapping?.stepId && effectiveMapping?.outputField) {
        onIterationChange({
          enabled: true,
          source_step_id: effectiveMapping.stepId,
          source_output_field: effectiveMapping.outputField,
          target_parameter: paramKey,
          execution_mode: 'sequential',
        });
      }
    }
  };

  const handleIterationToggle = (enabled: boolean) => {
    if (!onIterationChange) return;
    const sourceMapping = effectiveMapping?.stepId && effectiveMapping?.outputField
      ? effectiveMapping : nestedArrayMapping;
    if (!sourceMapping?.stepId || !sourceMapping?.outputField) return;

    const extractBaseFieldName = (outputField: string): string => {
      const match = outputField.match(/^(\w+)\[\*\]/);
      return match ? match[1] : outputField;
    };

    if (enabled) {
      onIterationChange({
        enabled: true,
        source_step_id: sourceMapping.stepId,
        source_output_field: extractBaseFieldName(sourceMapping.outputField),
        target_parameter: paramKey,
      });
    } else {
      onIterationChange(undefined);
    }
  };

  // Drag-drop handlers
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const rawData = e.dataTransfer.getData('application/x-field-mapping');
    if (!rawData) return;
    try {
      const { stepId, fieldName } = JSON.parse(rawData);
      onMappingChange(paramKey, { mappingType: 'mapped', stepId, outputField: fieldName });
    } catch (err) {
      console.error('Failed to parse drag data:', err);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.types.includes('application/x-field-mapping')) {
      e.dataTransfer.dropEffect = 'copy';
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  };

  const handleDragOverFiltered = (e: React.DragEvent) => {
    if (isComplexArray) {
      e.dataTransfer.dropEffect = 'none';
      return;
    }
    handleDragOver(e);
  };

  const handleDropFiltered = (e: React.DragEvent) => {
    if (isComplexArray) {
      e.preventDefault();
      return;
    }
    handleDrop(e);
  };

  // Sample value display
  const getMappedSampleValue = (): any => {
    if (!effectiveMapping?.stepId || !effectiveMapping?.outputField) return null;
    const step = reversedSteps.find(s => s.id === effectiveMapping.stepId);
    if (!step) return null;
    const outputDef = step.outputs?.[effectiveMapping.outputField];
    if (outputDef && 'sample_value' in outputDef && outputDef.sample_value !== undefined) {
      return outputDef.sample_value;
    }
    if (step.sample_output && effectiveMapping.outputField in step.sample_output) {
      return step.sample_output[effectiveMapping.outputField];
    }
    return null;
  };

  const mappedSampleValue = getMappedSampleValue();
  const mappingStatus = isMapped ? (effectiveMapping?.stepId && effectiveMapping?.outputField ? 'complete' : 'incomplete') : null;

  const renderFormConfig = () => (
    <div className="flex-1 p-3 bg-info-subtle border border-info rounded-md">
      <p className="text-sm text-info">User will provide this value when running the workflow.</p>
      {schema.description && <p className="mt-1 text-xs text-secondary">Help text: {schema.description}</p>}
    </div>
  );

  return (
    <div
      className={`param-field-wrapper ${isDragOver && !isComplexArray ? 'ring-2 ring-info bg-info-subtle' : ''}`}
      onDragOver={handleDragOverFiltered}
      onDragLeave={handleDragLeave}
      onDrop={handleDropFiltered}
    >
      {isDragOver && !isComplexArray && (
        <div className="loading-overlay">
          <span className="text-sm font-medium text-info">Drop to map</span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-secondary">
            {label}{required && <span className="text-danger ml-1">*</span>}
          </label>
          {schema.description && schema.type !== 'boolean' && (
            <div className="relative group">
              <HelpCircle className="h-3.5 w-3.5 text-muted hover:text-secondary cursor-help" />
              <div className="tooltip-popover left-0 bottom-full mb-1 w-64">
                <p>{schema.description}</p>
                {schema.default !== undefined && <p className="mt-1 text-secondary">Default: <span className="font-mono">{String(schema.default)}</span></p>}
              </div>
            </div>
          )}
        </div>
        {(!isComplexArray || isPrompt || schema.ui?.prompt) && (
          <div className="relative">
            <button
              ref={modeDropdownButtonRef}
              type="button"
              onClick={handleModeDropdownToggle}
              className={`flex items-center gap-1 px-2 py-0.5 text-xs rounded-full transition-colors ${
                isIterationEnabled && isMapped && mappedOutputType === 'array' && !isArrayType ? 'bg-success-subtle text-success border border-success' :
                isMapped ? 'bg-critical-subtle text-critical border border-critical' :
                isPrompt ? 'bg-success-subtle text-success border border-success' :
                isForm ? 'bg-info-subtle text-info border border-info' :
                'bg-surface text-secondary border border-primary hover:bg-input'
              }`}
            >
              {isIterationEnabled && isMapped && mappedOutputType === 'array' && !isArrayType ? <><Repeat className="h-3 w-3" /><span>Iterate</span></> : isMapped ? <><Link2 className="h-3 w-3" /><span>Mapped</span></> : isPrompt ? <><Sparkles className="h-3 w-3" /><span>Prompt</span></> : isForm ? <><FileInput className="h-3 w-3" /><span>Form</span></> : <><Type className="h-3 w-3" /><span>Static</span></>}
              <ChevronDown className="h-3 w-3" />
            </button>
            {showModeDropdown && modeDropdownPosition && ReactDOM.createPortal(
              <div ref={modeDropdownMenuRef} data-step-config-dropdown className="fixed w-48 bg-card border border-primary rounded-md shadow-lg z-[9999]" style={{ top: modeDropdownPosition.top, left: modeDropdownPosition.left }}>
                <button type="button" onClick={(e) => { e.stopPropagation(); handleModeChange('static'); }} className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card ${currentMode === 'static' ? 'bg-surface' : ''}`}><Type className="h-4 w-4 text-secondary" /><div><div className="font-medium">Static</div><div className="text-xs text-secondary">{isComplexArray ? 'Edit items individually' : 'Fixed value set here'}</div></div></button>
                {!isComplexArray && previousSteps.length > 0 && <button type="button" onClick={(e) => { e.stopPropagation(); handleModeChange('mapped'); }} className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card ${currentMode === 'mapped' && !isIterationEnabled ? 'bg-surface' : ''}`}><Link2 className="h-4 w-4 text-critical" /><div><div className="font-medium">Mapped</div><div className="text-xs text-secondary">From previous step output</div></div></button>}
                {!isComplexArray && <button type="button" onClick={(e) => { e.stopPropagation(); handleModeChange('form'); }} className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card ${currentMode === 'form' ? 'bg-surface' : ''}`}><FileInput className="h-4 w-4 text-info" /><div><div className="font-medium">Form</div><div className="text-xs text-secondary">User provides at runtime</div></div></button>}
                {schema.ui?.prompt && <button type="button" onClick={(e) => { e.stopPropagation(); handleModeChange('prompt'); }} className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-card ${currentMode === 'prompt' ? 'bg-surface' : ''}`}><Sparkles className="h-4 w-4 text-success" /><div><div className="font-medium">Prompt</div><div className="text-xs text-secondary">From AI Agents library</div></div></button>}
              </div>,
              document.body
            )}
          </div>
        )}
      </div>
      <div className="param-field-input-row">
        {isPrompt ? (
          <PromptInput
            promptId={mapping?.promptId || ''}
            promptSlug={mapping?.promptSlug}
            variableValues={mapping?.variableValues || {}}
            onPromptChange={(promptId, newVarValues) => onMappingChange(paramKey, { mappingType: 'prompt', promptId, variableValues: newVarValues ?? mapping?.variableValues ?? {} })}
            onVariableValuesChange={(variableValues) => onMappingChange(paramKey, { ...mapping, mappingType: 'prompt', variableValues })}
            previousSteps={previousSteps}
          />
        ) : isMapped ? (
          <MappedFieldSelector
            effectiveMapping={effectiveMapping || null}
            mapping={mapping}
            reversedSteps={reversedSteps}
            availableOutputs={availableOutputs}
            isIteratorMapping={isIteratorMapping}
            mappedOutputType={mappedOutputType}
            isArrayType={isArrayType}
            isIterationEnabled={isIterationEnabled}
            paramKey={paramKey}
            instanceFormFields={instanceFormFields}
            currentStepId={currentStepId}
            onMappingChange={onMappingChange}
          />
        ) : isForm ? renderFormConfig() : isArrayType ? (
          schema.dynamicOptions && providerId ? (
            <DynamicCombobox id={paramKey} value={Array.isArray(value) ? value : (schema.default || [])} onChange={(newValue) => onValueChange(paramKey, newValue)} dynamicOptions={schema.dynamicOptions} providerId={providerId} credentialId={credentialId} formData={allFieldValues} required={required} placeholder={schema.ui?.placeholder || `Select ${schema.title || paramKey}...`} className="flex-1" multiple={true} previousSteps={previousSteps} />
          ) : (() => {
            const widgetName = schema.ui?.widget || (schema.items?.enum ? 'multiselect' : null);
            const WidgetComponent = widgetName ? getArrayWidget(widgetName) : null;

            if (WidgetComponent) {
              const commonProps = {
                value: Array.isArray(value) ? value : (schema.default || []),
                paramKey,
              };
              if (widgetName === 'tags') {
                return <WidgetComponent {...commonProps} itemType={schema.items?.type || 'string'} placeholder={schema.ui?.placeholder || 'Type and press Enter to add'} onChange={onValueChange} />;
              } else if (widgetName === 'record-editor') {
                return <div className="flex-1 w-full"><WidgetComponent {...commonProps} onChange={(newValue: any[]) => onValueChange(paramKey, newValue)} providerId={providerId} credentialId={credentialId} fieldValues={allFieldValues} config={schema.ui?.schemaConfig} previousSteps={previousSteps} /></div>;
              } else if (widgetName === 'multiselect') {
                return <WidgetComponent value={value} schema={schema} paramKey={paramKey} onValueChange={onValueChange} />;
              } else {
                return <WidgetComponent {...commonProps} schema={schema} onValueChange={onValueChange} />;
              }
            }

            return (
              <ArrayItemsPanel
                schema={schema}
                value={value}
                paramKey={paramKey}
                onValueChange={onValueChange}
                onMappingChange={onMappingChange}
                onReorderMappings={onReorderMappings}
                onRemoveItemMappings={onRemoveItemMappings}
                allInputMappings={allInputMappings}
                previousSteps={previousSteps}
                uiState={uiState}
                onUiStateChange={onUiStateChange}
                allFieldValues={allFieldValues}
                instanceFormFields={instanceFormFields}
                currentStepId={currentStepId}
              />
            );
          })()
        ) : (
          <StaticInputRenderer
            schema={schema}
            value={value}
            paramKey={paramKey}
            label={label}
            onValueChange={onValueChange}
            allFieldValues={allFieldValues}
            exampleValue={exampleValue}
            providerId={providerId}
            credentialId={credentialId}
            required={required}
            previousSteps={previousSteps}
          />
        )}
      </div>
      {isMapped && mappingStatus === 'complete' && mappedSampleValue !== null && (
        <p className="text-xs text-secondary font-mono bg-card px-2 py-1 rounded">{formatSampleValue(mappedSampleValue)}</p>
      )}
    </div>
  );
}

export default MappableParameterField;
