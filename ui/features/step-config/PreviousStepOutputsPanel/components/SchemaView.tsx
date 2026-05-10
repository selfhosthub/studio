// ui/features/step-config/PreviousStepOutputsPanel/components/SchemaView.tsx

'use client';

import React, { useState, useMemo } from 'react';
import { Step } from '@/entities/workflow';
import { ChevronDown, ChevronRight, Database, Link, ArrowRight, Sparkles, FileInput } from 'lucide-react';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';
import { DraggableFieldRow } from './DraggableFieldRow';
import { InputMapping, FilterType, isFieldMapped } from '../utils/panelUtils';

/** Chevron toggle button for array field expansion */
function ArrayExpandButton({
  isExpanded,
  onClick,
  colorClass = 'text-critical',
  hoverClass = 'hover:bg-input',
}: {
  isExpanded: boolean;
  onClick: () => void;
  colorClass?: string;
  hoverClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      }}
      className={`p-0 ${hoverClass} rounded`}
    >
      {isExpanded ? (
        <ChevronDown className={`h-3 w-3 ${colorClass}`} />
      ) : (
        <ChevronRight className={`h-3 w-3 ${colorClass}`} />
      )}
    </button>
  );
}

/** Renders nested array item properties */
function NestedArrayFields({
  items,
  stepId,
  stepName,
  parentFieldName,
  inputMappings,
  onFieldSelect,
  borderClass,
  hoverClass,
  textClass,
}: {
  items: { properties: Record<string, any> };
  stepId: string;
  stepName: string;
  parentFieldName: string;
  inputMappings?: Record<string, InputMapping>;
  onFieldSelect?: (field: string, stepId: string, stepName: string) => void;
  borderClass: string;
  hoverClass: string;
  textClass: string;
}) {
  return (
    <div className={`ml-6 border-l ${borderClass}`}>
      {Object.entries(items.properties).map(([nestedKey, nestedSchema]) => {
        const nestedTyped = nestedSchema as { type?: string };
        const nestedType = nestedTyped.type || 'string';
        const nestedPath = `${parentFieldName}[*].${nestedKey}`;
        const isNestedMapped = isFieldMapped(stepId, nestedPath, inputMappings);

        return (
          <DraggableFieldRow
            key={nestedKey}
            fieldName={nestedPath}
            displayName={nestedKey}
            fieldType={nestedType}
            isMapped={isNestedMapped}
            dragData={{ stepId, stepName, fieldName: nestedPath, fieldType: nestedType, isArrayItem: true, parentArray: parentFieldName }}
            onClick={() => onFieldSelect?.(nestedPath, stepId, stepName)}
            hoverClassName={hoverClass}
            textClassName={textClass}
            title={isNestedMapped ? 'Already mapped' : `Drag to map ${nestedPath}`}
          />
        );
      })}
    </div>
  );
}

/**
 * Schema view - expandable tree grouped by step (matches n8n's Schema view)
 * Steps are shown in reverse order (most recent/immediate previous step first)
 */
export function SchemaView({
  previousSteps,
  onFieldSelect,
  typeFilter,
  showUnmappedOnly,
  inputMappings,
  instanceFormFields,
  currentStepId,
}: {
  previousSteps: Step[];
  onFieldSelect?: (field: string, stepId: string, stepName: string) => void;
  typeFilter: FilterType | null;
  showUnmappedOnly: boolean;
  inputMappings?: Record<string, InputMapping>;
  instanceFormFields?: Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }>;
  currentStepId?: string;
}) {
  const reversedSteps = useMemo(() => [...previousSteps].reverse(), [previousSteps]);

  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(
    new Set(previousSteps.map(s => s.id))
  );
  const [expandedArrays, setExpandedArrays] = useState<Set<string>>(new Set());
  const [seenArrays, setSeenArrays] = useState<Set<string>>(new Set());
  const [forwardedCollapsed, setForwardedCollapsed] = useState<Set<string>>(new Set());

  // When previousSteps changes, ensure any new steps are also expanded
  React.useEffect(() => {
    setExpandedSteps(prev => {
      const newSet = new Set(prev);
      previousSteps.forEach(step => newSet.add(step.id));
      return newSet;
    });
  }, [previousSteps]);

  // Auto-expand new arrays (both native and forwarded)
  React.useEffect(() => {
    const newArrayKeys: string[] = [];

    previousSteps.forEach(step => {
      const outputs = step.outputs || {};
      Object.entries(outputs).forEach(([fieldName, fieldDef]) => {
        const typedField = fieldDef as { type?: string; items?: any };
        if (typedField.type === 'array' && typedField.items?.properties) {
          const arrayKey = `${step.id}:${fieldName}`;
          if (!seenArrays.has(arrayKey)) newArrayKeys.push(arrayKey);
        }
      });
    });

    const reversedForCheck = [...previousSteps].reverse();
    reversedForCheck.forEach((step, index) => {
      const predecessors = reversedForCheck.slice(index + 1).reverse();
      const effectiveOutputs = getEffectiveOutputs(step, predecessors);
      Object.entries(effectiveOutputs).forEach(([fieldName, fieldDef]) => {
        const typedField = fieldDef as { type?: string; items?: any; _forwarded?: boolean };
        if (typedField._forwarded && typedField.type === 'array' && typedField.items?.properties) {
          const arrayKey = `${step.id}:forwarded:${fieldName}`;
          if (!seenArrays.has(arrayKey)) newArrayKeys.push(arrayKey);
        }
      });
    });

    if (newArrayKeys.length > 0) {
      setSeenArrays(prev => { const next = new Set(prev); newArrayKeys.forEach(key => next.add(key)); return next; });
      setExpandedArrays(prev => { const next = new Set(prev); newArrayKeys.forEach(key => next.add(key)); return next; });
    }
  }, [previousSteps, seenArrays]);

  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) => {
    setter(prev => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  };

  const immediatePredecessorId = reversedSteps.length > 0 ? reversedSteps[0].id : null;

  const stepsWithEffectiveOutputs = useMemo(() => {
    return reversedSteps.map((step, index) => {
      const predecessors = reversedSteps.slice(index + 1).reverse();
      const effectiveOutputs = getEffectiveOutputs(step, predecessors);
      const nativeOutputs: Record<string, any> = {};
      const promptOutputs: Record<string, any> = {};
      const forwardedOutputs: Record<string, any> = {};

      for (const [fieldName, fieldDef] of Object.entries(effectiveOutputs)) {
        if ((fieldDef as any)._forwarded) forwardedOutputs[fieldName] = fieldDef;
        else if ((fieldDef as any)._from_prompt) promptOutputs[fieldName] = fieldDef;
        else nativeOutputs[fieldName] = fieldDef;
      }

      return { step, nativeOutputs, promptOutputs, forwardedOutputs };
    });
  }, [reversedSteps]);

  const getFilteredOutputs = (stepId: string, outputs: Record<string, any>) => {
    return Object.entries(outputs).filter(([fieldName, fieldDef]) => {
      const fieldType = (fieldDef as { type?: string }).type || 'string';
      if (typeFilter) {
        const matchesType = typeFilter === 'number' ? (fieldType === 'number' || fieldType === 'integer') : fieldType === typeFilter;
        if (!matchesType) return false;
      }
      if (showUnmappedOnly && isFieldMapped(stepId, fieldName, inputMappings)) return false;
      return true;
    });
  };

  const filteredFormFields = useMemo(() => {
    if (!instanceFormFields) return [];
    return Object.entries(instanceFormFields)
      .filter(([fieldName, def]) => {
        if (typeFilter) {
          const fieldType = def.type || 'string';
          const matchesType = typeFilter === 'number' ? (fieldType === 'number' || fieldType === 'integer') : fieldType === typeFilter;
          if (!matchesType) return false;
        }
        if (showUnmappedOnly) {
          if (def._owning_step_ids?.includes(currentStepId || '')) return false;
          if (isFieldMapped('__instance_form__', fieldName, inputMappings)) return false;
        }
        return true;
      })
      .sort(([a], [b]) => a.localeCompare(b));
  }, [instanceFormFields, currentStepId, typeFilter, showUnmappedOnly, inputMappings]);

  const hasInstanceFormFields = filteredFormFields.length > 0;

  if (previousSteps.length === 0 && !hasInstanceFormFields) {
    return (
      <div className="text-center py-8 text-secondary">
        <Database className="mx-auto h-8 w-8 mb-2 opacity-50" />
        <p className="text-sm">No previous steps</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Instance Form fields */}
      {hasInstanceFormFields && (
        <div>
          <div className="w-full flex items-center gap-1 py-1 px-1 bg-purple-50 dark:bg-purple-900/20 rounded"> {/* css-check-ignore: no semantic token */}
            <FileInput className="h-3 w-3 text-purple-500 flex-shrink-0" /> {/* css-check-ignore: no semantic token */}
            <span className="text-xs font-medium text-purple-700 dark:text-purple-300 flex-1">Instance Form</span> {/* css-check-ignore: no semantic token */}
            <span className="text-xs text-muted ml-1">{filteredFormFields.length}</span>
          </div>
          <div className="ml-3 border-l border-purple-200 dark:border-purple-800"> {/* css-check-ignore: no semantic token */}
            {filteredFormFields.map(([fieldName, fieldDef]) => {
              const fieldType = fieldDef.type || 'string';
              const isOwnField = fieldDef._owning_step_ids?.includes(currentStepId || '') ?? false;
              return (
                <DraggableFieldRow
                  key={fieldName}
                  fieldName={fieldName}
                  displayName={fieldName}
                  fieldType={fieldType}
                  isMapped={isFieldMapped('__instance_form__', fieldName, inputMappings)}
                  dragData={{ stepId: '__instance_form__', stepName: 'Instance Form', fieldName, fieldType }}
                  onClick={() => onFieldSelect?.(fieldName, '__instance_form__', 'Instance Form')}
                  disabled={isOwnField}
                  title={isOwnField ? `${fieldName} - owned by this step` : `${fieldDef.description || fieldName} (${fieldType})`}
                />
              );
            })}
          </div>
        </div>
      )}

      {stepsWithEffectiveOutputs.map(({ step, nativeOutputs, promptOutputs, forwardedOutputs }) => {
        const isExpanded = expandedSteps.has(step.id);
        const filteredOutputs = getFilteredOutputs(step.id, nativeOutputs);
        const filteredPromptOutputs = getFilteredOutputs(step.id, promptOutputs);
        const filteredForwardedOutputs = getFilteredOutputs(step.id, forwardedOutputs);
        const totalCount = Object.keys(nativeOutputs).length + Object.keys(promptOutputs).length + Object.keys(forwardedOutputs).length;
        const filteredCount = filteredOutputs.length + filteredPromptOutputs.length + filteredForwardedOutputs.length;
        const isImmediatePredecessor = step.id === immediatePredecessorId;
        const isForwardedCollapsed = forwardedCollapsed.has(step.id);
        const stepName = step.name || step.id;

        if ((typeFilter || showUnmappedOnly) && filteredCount === 0) return null;

        return (
          <div key={step.id}>
            <button
              onClick={() => toggleSet(setExpandedSteps, step.id)}
              className={`w-full flex items-center gap-1 py-1 px-1 hover:bg-surface text-left rounded ${isImmediatePredecessor ? 'bg-info-subtle' : ''}`}
            >
              {isExpanded ? <ChevronDown className="h-3 w-3 text-muted flex-shrink-0" /> : <ChevronRight className="h-3 w-3 text-muted flex-shrink-0" />}
              {isImmediatePredecessor && <span title="Directly connected"><Link className="h-3 w-3 text-info flex-shrink-0" /></span>}
              <span className={`text-xs font-medium flex-1 truncate ${isImmediatePredecessor ? 'text-info' : 'text-secondary'}`}>{stepName}</span>
              {totalCount > 0 && <span className="text-xs text-muted ml-1">{typeFilter ? `${filteredCount}/${totalCount}` : totalCount}</span>}
            </button>

            {isExpanded && (filteredOutputs.length > 0 || filteredPromptOutputs.length > 0 || filteredForwardedOutputs.length > 0) && (
              <div className={`ml-3 border-l ${isImmediatePredecessor ? 'border-info' : 'border-primary'}`}>
                {/* Native outputs */}
                {filteredOutputs.map(([fieldName, fieldDef]) => {
                  const typedField = fieldDef as { type?: string; items?: any };
                  const fieldType = typedField.type || 'string';
                  const isMapped = isFieldMapped(step.id, fieldName, inputMappings);
                  const hasNested = fieldType === 'array' && typedField.items?.properties;
                  const arrayKey = `${step.id}:${fieldName}`;
                  const isArrayExpanded = expandedArrays.has(arrayKey);

                  return (
                    <div key={fieldName}>
                      <DraggableFieldRow
                        fieldName={fieldName}
                        displayName={fieldName}
                        fieldType={fieldType}
                        isMapped={isMapped}
                        dragData={{ stepId: step.id, stepName, fieldName, fieldType }}
                        onClick={() => onFieldSelect?.(fieldName, step.id, stepName)}
                        title={isMapped ? 'Already mapped to a parameter' : `Drag to map ${fieldName}`}
                        expandButton={hasNested ? <ArrayExpandButton isExpanded={isArrayExpanded} onClick={() => toggleSet(setExpandedArrays, arrayKey)} /> : undefined}
                      />
                      {hasNested && isArrayExpanded && (
                        <NestedArrayFields
                          items={typedField.items}
                          stepId={step.id}
                          stepName={stepName}
                          parentFieldName={fieldName}
                          inputMappings={inputMappings}
                          onFieldSelect={onFieldSelect}
                          borderClass="border-critical"
                          hoverClass="hover:bg-critical-subtle"
                          textClass="text-secondary"
                        />
                      )}
                    </div>
                  );
                })}

                {/* Prompt variable outputs */}
                {filteredPromptOutputs.length > 0 && (
                  <div className="mt-1">
                    <div className="flex items-center gap-1 py-1 pl-3 pr-1">
                      <Sparkles className="h-3 w-3 text-teal-500 flex-shrink-0" /> {/* css-check-ignore: no semantic token */}
                      <span className="text-xs font-medium text-teal-600 dark:text-teal-400">Prompt variables</span> {/* css-check-ignore: no semantic token */}
                    </div>
                    <div className="border-l border-teal-200 dark:border-teal-800 ml-3"> {/* css-check-ignore: no semantic token */}
                      {filteredPromptOutputs.map(([fieldName, fieldDef]) => {
                        const fieldType = (fieldDef as { type?: string }).type || 'string';
                        return (
                          <DraggableFieldRow
                            key={fieldName}
                            fieldName={fieldName}
                            displayName={fieldName}
                            fieldType={fieldType}
                            isMapped={isFieldMapped(step.id, fieldName, inputMappings)}
                            dragData={{ stepId: step.id, stepName, fieldName, fieldType }}
                            onClick={() => onFieldSelect?.(fieldName, step.id, stepName)}
                            hoverClassName="hover:bg-teal-50 dark:hover:bg-teal-900/20" // css-check-ignore: no semantic token
                            title={isFieldMapped(step.id, fieldName, inputMappings) ? 'Already mapped to a parameter' : `Drag to map ${fieldName} (prompt variable)`}
                          />
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Forwarded outputs - collapsible section */}
                {filteredForwardedOutputs.length > 0 && (
                  <div className="mt-1">
                    <button
                      onClick={() => toggleSet(setForwardedCollapsed, step.id)}
                      className="w-full flex items-center gap-1 py-1 pl-3 pr-1 text-left hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded" // css-check-ignore: no semantic token
                    >
                      {isForwardedCollapsed ? <ChevronRight className="h-3 w-3 text-purple-400 flex-shrink-0" /> : <ChevronDown className="h-3 w-3 text-purple-400 flex-shrink-0" />} {/* css-check-ignore: no semantic token */}
                      <ArrowRight className="h-3 w-3 text-purple-500 flex-shrink-0" /> {/* css-check-ignore: no semantic token */}
                      <span className="text-xs font-medium text-purple-600 dark:text-purple-400">Pass-through</span> {/* css-check-ignore: no semantic token */}
                    </button>
                    {!isForwardedCollapsed && (
                      <div className="ml-3 border-l border-purple-200 dark:border-purple-800"> {/* css-check-ignore: no semantic token */}
                        {filteredForwardedOutputs.map(([fieldName, fieldDef]) => {
                          const typedField = fieldDef as { type?: string; items?: any };
                          const fieldType = typedField.type || 'string';
                          const isMapped = isFieldMapped(step.id, fieldName, inputMappings);
                          const hasNested = fieldType === 'array' && typedField.items?.properties;
                          const arrayKey = `${step.id}:forwarded:${fieldName}`;
                          const isArrayExpanded = expandedArrays.has(arrayKey);

                          return (
                            <div key={fieldName}>
                              <DraggableFieldRow
                                fieldName={fieldName}
                                displayName={fieldName}
                                fieldType={fieldType}
                                isMapped={isMapped}
                                dragData={{ stepId: step.id, stepName, fieldName, fieldType }}
                                onClick={() => onFieldSelect?.(fieldName, step.id, stepName)}
                                hoverClassName="hover:bg-purple-50 dark:hover:bg-purple-900/20" // css-check-ignore: no semantic token
                                textClassName="text-purple-700 dark:text-purple-300" // css-check-ignore: no semantic token
                                title={isMapped ? 'Already mapped to a parameter' : `Drag to map ${fieldName} (pass-through)`}
                                expandButton={hasNested ? <ArrayExpandButton isExpanded={isArrayExpanded} onClick={() => toggleSet(setExpandedArrays, arrayKey)} colorClass="text-purple-500" hoverClass="hover:bg-purple-200 dark:hover:bg-purple-700" /> : undefined} // css-check-ignore: no semantic token
                              />
                              {hasNested && isArrayExpanded && (
                                <NestedArrayFields
                                  items={typedField.items}
                                  stepId={step.id}
                                  stepName={stepName}
                                  parentFieldName={fieldName}
                                  inputMappings={inputMappings}
                                  onFieldSelect={onFieldSelect}
                                  borderClass="border-purple-300 dark:border-purple-700" // css-check-ignore: no semantic token
                                  hoverClass="hover:bg-purple-100 dark:hover:bg-purple-900/30" // css-check-ignore: no semantic token
                                  textClass="text-purple-600 dark:text-purple-400" // css-check-ignore: no semantic token
                                />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {isExpanded && filteredOutputs.length === 0 && filteredForwardedOutputs.length === 0 && !typeFilter && !showUnmappedOnly && (
              <div className="ml-6 py-1">
                <span className="text-xs text-muted italic">No outputs defined</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
