// ui/features/step-config/MappableParameterField/components/ArrayItemsPanel.tsx

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Step } from '@/entities/workflow';
import { Link2, Type, ChevronDown, HelpCircle, FileInput, Plus, Trash2, ChevronRight, Sparkles, ArrowUp, ArrowDown, Repeat } from 'lucide-react';
import { getEffectiveOutputs } from '@/shared/lib/step-utils';
import { FieldInput } from './FieldInput';
import { NestedArrayField } from './NestedArrayField';
import { PromptInput } from './PromptInput';
import { getArrayWidget } from '@/shared/lib/array-widget-registry';
import { useItemFieldState } from '../hooks/useItemFieldState';
import { checkShowWhen, createDefaultItemFromSchema, getItemLabel, isGroupModified } from '../utils/schemaUtils';
import type { PropertySchema, InputMapping, UIState, UIGroupConfig } from '../types';

interface ArrayItemsPanelProps {
  schema: PropertySchema;
  value: any;
  paramKey: string;
  onValueChange: (key: string, value: any) => void;
  onMappingChange: (key: string, mapping: InputMapping | null) => void;
  onReorderMappings?: (paramKey: string, fromIndex: number, toIndex: number) => void;
  onRemoveItemMappings?: (paramKey: string, removedIndex: number, arrayLength: number) => void;
  allInputMappings: Record<string, InputMapping>;
  previousSteps: Step[];
  uiState?: UIState;
  onUiStateChange?: (uiState: UIState) => void;
  allFieldValues?: Record<string, any>;
  instanceFormFields?: Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }>;
  currentStepId?: string;
}

export function ArrayItemsPanel({
  schema,
  value,
  paramKey,
  onValueChange,
  onMappingChange,
  onReorderMappings,
  onRemoveItemMappings,
  allInputMappings,
  previousSteps,
  uiState,
  onUiStateChange,
  allFieldValues,
  instanceFormFields,
  currentStepId,
}: ArrayItemsPanelProps) {
  const arrayValue = Array.isArray(value) ? value : [];
  const itemSchema = schema.items;
  const itemProperties = itemSchema?.properties || {};
  const uiGroups = (itemSchema?.ui_groups || {}) as UIGroupConfig;

  // Stable IDs for array items - prevents React DOM reuse on reorder
  const nextItemIdRef = useRef(0);
  const itemIdsRef = useRef<string[]>([]);
  const ensureItemIds = (arr: any[]): string[] => {
    const ids = itemIdsRef.current;
    while (ids.length < arr.length) {
      ids.push(`item-${nextItemIdRef.current++}`);
    }
    if (ids.length > arr.length) {
      ids.length = arr.length;
    }
    return ids;
  };
  const itemIds = ensureItemIds(arrayValue);
  const [expandedArrayItems, setExpandedArrayItems] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    if (arrayValue.length > 0) {
      const ids = ensureItemIds(arrayValue);
      initial[ids[0]] = true;
    }
    return initial;
  });
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [dragOverField, setDragOverField] = useState<string | null>(null);

  const {
    showItemModeDropdown,
    setShowItemModeDropdown,
    getItemFieldMode,
    setItemFieldMode,
    getItemFieldMapping,
    setItemFieldMapping,
  } = useItemFieldState(value, paramKey, allInputMappings);

  // Auto-add items when minItems requires it
  useEffect(() => {
    if (schema.type === 'array' && schema.minItems && schema.minItems > 0) {
      const currentLength = arrayValue.length;
      if (currentLength < schema.minItems) {
        const itemsToAdd = schema.minItems - currentLength;
        const newItems = [];
        for (let i = 0; i < itemsToAdd; i++) {
          newItems.push(createDefaultItemFromSchema(schema.items));
        }
        const newArray = [...arrayValue, ...newItems];
        onValueChange(paramKey, newArray);
        setExpandedArrayItems({ 0: true });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Initialize array only when schema changes
  }, [schema.type, schema.minItems]);
  const addItem = () => {
    const newItem = createDefaultItemFromSchema(itemSchema);
    const newArray = [...arrayValue, newItem];
    onValueChange(paramKey, newArray);
    const newIds = ensureItemIds(newArray);
    setExpandedArrayItems(prev => ({ ...prev, [newIds[newIds.length - 1]]: true }));
  };
  const removeItem = (index: number) => {
    if (schema.minItems && arrayValue.length <= schema.minItems) return;
    onRemoveItemMappings?.(paramKey, index, arrayValue.length);
    itemIdsRef.current.splice(index, 1);
    onValueChange(paramKey, arrayValue.filter((_, i) => i !== index));
  };

  const canRemoveItem = !schema.minItems || arrayValue.length > schema.minItems;

  const moveItem = (index: number, direction: 'up' | 'down') => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= arrayValue.length) return;
    const newArray = [...arrayValue];
    [newArray[index], newArray[newIndex]] = [newArray[newIndex], newArray[index]];
    onValueChange(paramKey, newArray);
    onReorderMappings?.(paramKey, index, newIndex);
    const ids = itemIdsRef.current;
    [ids[index], ids[newIndex]] = [ids[newIndex], ids[index]];
  };

  const updateItem = (index: number, itemKey: string, itemValue: any) => {
    const newArray = [...arrayValue];
    newArray[index] = { ...newArray[index], [itemKey]: itemValue };
    onValueChange(paramKey, newArray);
  };

  const toggleExpand = (index: number) => {
    const id = itemIds[index];
    setExpandedArrayItems(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Group fields by their ui.group property
  const groupFields = (item: any): Map<string, Array<[string, PropertySchema]>> => {
    const groups = new Map<string, Array<[string, PropertySchema]>>();
    groups.set('_ungrouped', []);
    const sortedProperties = Object.entries(itemProperties).sort((a, b) => {
      const orderA = (a[1] as PropertySchema).ui?.order ?? 999;
      const orderB = (b[1] as PropertySchema).ui?.order ?? 999;
      return orderA - orderB;
    });
    for (const [propKey, propSchema] of sortedProperties) {
      const s = propSchema as PropertySchema;
      const groupId = s.ui?.group || '_ungrouped';
      if (!groups.has(groupId)) groups.set(groupId, []);
      groups.get(groupId)!.push([propKey, s]);
    }
    return groups;
  };

  const getSortedGroupIds = (groups: Map<string, any>): string[] => {
    return Array.from(groups.keys()).sort((a, b) => {
      if (a === '_ungrouped') return -1;
      if (b === '_ungrouped') return 1;
      return (uiGroups[a]?.order ?? 999) - (uiGroups[b]?.order ?? 999);
    });
  };

  const shouldShowGroup = (groupId: string, item: any): boolean => {
    if (groupId === '_ungrouped') return true;
    const groupConfig = uiGroups[groupId];
    if (!groupConfig?.show_when) return true;
    return checkShowWhen(groupConfig.show_when, item, itemSchema);
  };

  const isSceneGroupCollapsed = (itemIndex: number, groupId: string): boolean => {
    const id = itemIds[itemIndex];
    const key = `${id}:${groupId}`;
    if (collapsedGroups[key] !== undefined) return collapsedGroups[key];
    const groupConfig = uiGroups[groupId];
    return groupConfig?.collapsed ?? false;
  };

  const toggleSceneGroupCollapsed = (itemIndex: number, groupId: string) => {
    const id = itemIds[itemIndex];
    const key = `${id}:${groupId}`;
    setCollapsedGroups(prev => ({
      ...prev,
      [key]: !isSceneGroupCollapsed(itemIndex, groupId),
    }));
  };

  const renderCollapsibleGroupDivider = (groupTitle: string, itemIndex: number, groupId: string, isCollapsed: boolean, hasModified: boolean) => (
    <div
      className="group-header-warning -mx-3 mt-3 mb-1"
      onClick={() => toggleSceneGroupCollapsed(itemIndex, groupId)}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-warning uppercase tracking-wide">{groupTitle}</span>
        {isCollapsed && hasModified && (
          <span className="text-[10px] font-medium text-info bg-info-subtle px-1.5 py-0.5 rounded">
            Modified
          </span>
        )}
      </div>
      <span className="text-xs text-warning hover:text-warning">
        {isCollapsed ? 'Show' : 'Hide'}
      </span>
    </div>
  );

  // Render a single item field (static, mapped, form, or prompt mode)
  const renderItemField = (
    fieldKey: string,
    fieldSchema: PropertySchema,
    fieldValue: any,
    itemIndex: number,
    itemData: Record<string, any>,
    onFieldChange: (key: string, val: any) => void,
    itemSchemaForDefaults?: PropertySchema,
    keyPrefix?: string
  ) => {
    if (!checkShowWhen(fieldSchema.ui?.show_when, itemData, itemSchemaForDefaults)) return null;

    const fieldLabel = fieldSchema.title || fieldKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const stateKey = keyPrefix ? `${keyPrefix}:${itemIndex}:${fieldKey}` : `${itemIndex}:${fieldKey}`;
    const fieldMode = getItemFieldMode(itemIndex, fieldKey, keyPrefix);
    const fieldMapping = getItemFieldMapping(itemIndex, fieldKey, keyPrefix);
    const isDropdownOpen = showItemModeDropdown === stateKey;

    const isInstanceFormSelected = fieldMapping.stepId === '__instance_form__';
    const selStep = isInstanceFormSelected ? undefined : previousSteps.find(s => s.id === fieldMapping.stepId);
    const selStepIdx = selStep ? previousSteps.indexOf(selStep) : -1;
    const stepsBeforeSelStep = selStepIdx >= 0 ? previousSteps.slice(0, selStepIdx) : [];
    const outputs = isInstanceFormSelected && instanceFormFields
      ? Object.fromEntries(
          Object.entries(instanceFormFields).filter(
            ([, def]) => !def._owning_step_ids?.includes(currentStepId || '')
          )
        )
      : selStep ? getEffectiveOutputs(selStep, stepsBeforeSelStep) : {};
    const showInstanceFormOption = !!instanceFormFields && Object.keys(instanceFormFields).some(
      k => !instanceFormFields[k]._owning_step_ids?.includes(currentStepId || '')
    );

    const renderStaticFieldInput = () => {
      if (fieldSchema.type === 'array') {
        const widgetName = fieldSchema.ui?.widget || (fieldSchema.items?.enum ? 'multiselect' : null);
        const WidgetComponent = widgetName ? getArrayWidget(widgetName) : null;
        if (WidgetComponent) {
          const commonProps = {
            value: Array.isArray(fieldValue) ? fieldValue : (fieldSchema.default || []),
            paramKey: fieldKey,
          };
          if (widgetName === 'tags') {
            return (
              <WidgetComponent
                {...commonProps}
                itemType={fieldSchema.items?.type || 'string'}
                placeholder={fieldSchema.ui?.placeholder || 'Type and press Enter to add'}
                onChange={(_key: string, newValue: any[]) => onFieldChange(fieldKey, newValue)}
              />
            );
          } else if (widgetName === 'multiselect') {
            return (
              <WidgetComponent
                value={fieldValue}
                schema={fieldSchema}
                paramKey={fieldKey}
                onValueChange={(_key: string, v: any) => onFieldChange(fieldKey, v)}
              />
            );
          } else {
            return (
              <WidgetComponent
                {...commonProps}
                schema={fieldSchema}
                onValueChange={(_key: string, v: any) => onFieldChange(fieldKey, v)}
              />
            );
          }
        }
        return (
          <NestedArrayField
            fieldKey={fieldKey}
            parentKey={paramKey}
            parentItemIndex={itemIndex}
            schema={fieldSchema}
            value={fieldValue || []}
            onChange={(newValue) => onFieldChange(fieldKey, newValue)}
            uiState={uiState}
            onUiStateChange={onUiStateChange}
            renderItemField={renderItemField}
          />
        );
      }

      // Array items infer URI media type from the sibling `type` field (used by
      // providers like JSON2Video where each item declares image/video/audio).
      const elementType = itemData?.type as string | undefined;
      const uriMediaHint = elementType === 'image' || elementType === 'video' || elementType === 'audio'
        ? elementType
        : undefined;

      // Colour picker inherits a value from the parent form context when the
      // local field is empty (used by scene-level defaults).
      const effectiveColor = fieldValue ?? fieldSchema.default ?? '';
      const inheritedColor = (!effectiveColor && allFieldValues?.[fieldKey])
        ? String(allFieldValues[fieldKey])
        : undefined;

      return (
        <FieldInput
          schema={fieldSchema}
          value={fieldValue}
          onChange={(v) => onFieldChange(fieldKey, v)}
          size="compact"
          paramKey={fieldKey}
          uriMediaHint={uriMediaHint}
          colorFallback={inheritedColor}
          label={fieldLabel}
        />
      );
    };

    const buildNestedParamPath = (): string => {
      if (!keyPrefix) return `${paramKey}[${itemIndex}].${fieldKey}`;
      const parts = keyPrefix.split(':');
      let path = parts[0];
      for (let i = 1; i < parts.length; i += 2) {
        path += `[${parts[i]}]`;
        if (parts[i + 1]) path += `.${parts[i + 1]}`;
      }
      return `${path}[${itemIndex}].${fieldKey}`;
    };

    const renderMappedFieldInput = () => {
      const normalizedOutputField = fieldMapping.outputField?.replace(/\[\*\]$/, '') || '';
      const handleStepChange = (newStepId: string) => {
        setItemFieldMapping(itemIndex, fieldKey, { stepId: newStepId, outputField: '' }, keyPrefix);
        if (newStepId === '__instance_form__') {
          // Instance-form refs don't resolve as template strings - persist via input_mappings instead.
          onMappingChange(buildNestedParamPath(), { mappingType: 'mapped', stepId: newStepId, outputField: '' });
        } else {
          onFieldChange(fieldKey, `{{ ${newStepId}. }}`);
        }
      };
      const handleOutputChange = (newOutputField: string) => {
        setItemFieldMapping(itemIndex, fieldKey, { ...fieldMapping, outputField: newOutputField }, keyPrefix);
        if (fieldMapping.stepId === '__instance_form__') {
          onMappingChange(buildNestedParamPath(), { mappingType: 'mapped', stepId: fieldMapping.stepId, outputField: newOutputField });
        } else {
          onFieldChange(fieldKey, `{{ ${fieldMapping.stepId}.${newOutputField} }}`);
        }
      };
      return (
        <div className="param-field-input-row">
          <select value={fieldMapping.stepId} onChange={(e) => handleStepChange(e.target.value)} className="p-1.5 border rounded text-xs">
            <option value="">Step...</option>
            {showInstanceFormOption && <option value="__instance_form__" className="font-semibold">Instance Form</option>}
            {previousSteps.map((step) => <option key={step.id} value={step.id}>{step.name || step.id}</option>)}
          </select>
          <select value={normalizedOutputField} onChange={(e) => handleOutputChange(e.target.value)} disabled={!fieldMapping.stepId} className="p-1.5 border rounded text-xs disabled:opacity-50">
            <option value="">Output...</option>
            {Object.entries(outputs).flatMap(([outputName, outputDef]) => {
              const typedOutput = outputDef as { type?: string; items?: { properties?: Record<string, { type?: string }> } };
              const opts = [<option key={outputName} value={outputName}>{outputName}</option>];
              if (typedOutput.type === 'array' && typedOutput.items?.properties) {
                Object.entries(typedOutput.items.properties).forEach(([nestedKey]) => {
                  opts.push(<option key={`${outputName}[*].${nestedKey}`} value={`${outputName}[*].${nestedKey}`}>↳ {nestedKey}</option>);
                });
              }
              return opts;
            })}
          </select>
        </div>
      );
    };

    const supportsDragDrop = fieldSchema.type !== 'boolean' && fieldSchema.type !== 'array';
    const isItemDragOver = dragOverField === stateKey;

    const handleItemFieldDragOver = (e: React.DragEvent) => {
      if (!supportsDragDrop) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer.types.includes('application/x-field-mapping')) {
        e.dataTransfer.dropEffect = 'copy';
        setDragOverField(stateKey);
      }
    };

    const handleItemFieldDragLeave = (e: React.DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) {
        setDragOverField(null);
      }
    };

    const handleItemFieldDrop = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOverField(null);
      const rawData = e.dataTransfer.getData('application/x-field-mapping');
      if (!rawData) return;
      try {
        const { stepId, fieldName } = JSON.parse(rawData);
        setItemFieldMode(itemIndex, fieldKey, 'mapped', keyPrefix, onMappingChange);
        setItemFieldMapping(itemIndex, fieldKey, { stepId, outputField: fieldName }, keyPrefix);
        onFieldChange(fieldKey, `{{ ${stepId}.${fieldName} }}`);
        let paramPath: string;
        if (keyPrefix) {
          const parts = keyPrefix.split(':');
          paramPath = parts[0];
          for (let i = 1; i < parts.length; i += 2) {
            paramPath += `[${parts[i]}]`;
            if (parts[i + 1]) paramPath += `.${parts[i + 1]}`;
          }
        } else {
          paramPath = paramKey;
        }
        onMappingChange(`${paramPath}[${itemIndex}].${fieldKey}`, { mappingType: 'mapped', stepId, outputField: fieldName });
      } catch (err) {
        console.error('Failed to parse item field drag data:', err);
      }
    };

    return (
      <div
        key={fieldKey}
        className={`space-y-1 relative rounded transition-all ${isItemDragOver ? 'ring-2 ring-info bg-info-subtle' : ''}`}
        onDragOver={handleItemFieldDragOver}
        onDragLeave={handleItemFieldDragLeave}
        onDrop={handleItemFieldDrop}
      >
        {isItemDragOver && (
          <div className="loading-overlay">
            <span className="text-xs font-medium text-info">Drop to map</span>
          </div>
        )}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <label className="text-xs font-medium text-secondary">{fieldLabel}</label>
            {fieldSchema.description && fieldSchema.type !== 'boolean' && (
              <div className="relative group">
                <HelpCircle className="h-3 w-3 text-muted hover:text-secondary cursor-help" />
                <div className="tooltip-popover left-0 bottom-full mb-1 w-56">
                  <p>{fieldSchema.description}</p>
                  {fieldSchema.default !== undefined && <p className="mt-1 text-secondary">Default: <span className="font-mono">{String(fieldSchema.default)}</span></p>}
                </div>
              </div>
            )}
          </div>
          {fieldSchema.type !== 'boolean' && (fieldSchema.type !== 'array' || !fieldSchema.items?.properties) && (
            <div className="relative">
              {/* css-check-ignore: no semantic token - purple used for item field mapped mode badge */}
              <button type="button" onClick={(e) => { e.stopPropagation(); setShowItemModeDropdown(isDropdownOpen ? null : stateKey); }} className={`flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] rounded-full transition-colors ${fieldMode === 'mapped' && fieldMapping?.outputField?.includes('[*]') ? 'bg-success-subtle text-success border border-success' : fieldMode === 'mapped' ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700' : fieldMode === 'prompt' ? 'bg-success-subtle text-success border border-success' : fieldMode === 'form' ? 'bg-info-subtle text-info border border-info' : 'bg-card text-secondary border border-primary'}`}>
                {fieldMode === 'mapped' && fieldMapping?.outputField?.includes('[*]') ? <><Repeat className="h-2.5 w-2.5" /><span>Iterate</span></> : fieldMode === 'mapped' ? <><Link2 className="h-2.5 w-2.5" /><span>Map</span></> : fieldMode === 'prompt' ? <><Sparkles className="h-2.5 w-2.5" /><span>Prompt</span></> : fieldMode === 'form' ? <><FileInput className="h-2.5 w-2.5" /><span>Form</span></> : <><Type className="h-2.5 w-2.5" /><span>Static</span></>}
                <ChevronDown className="h-2.5 w-2.5" />
              </button>
              {isDropdownOpen && (
                <div data-step-config-dropdown className="absolute right-0 mt-1 w-36 bg-card border border-primary rounded shadow-lg z-50">
                  <button type="button" onClick={(e) => { e.stopPropagation(); setItemFieldMode(itemIndex, fieldKey, 'static', keyPrefix, onMappingChange); }} className={`w-full flex items-center gap-2 px-2 py-1.5 text-xs text-left hover:bg-card ${fieldMode === 'static' ? 'bg-surface' : ''}`}><Type className="h-3 w-3 text-secondary" /><span>Static</span></button>
                  {previousSteps.length > 0 && <button type="button" onClick={(e) => { e.stopPropagation(); setItemFieldMode(itemIndex, fieldKey, 'mapped', keyPrefix, onMappingChange); }} className={`w-full flex items-center gap-2 px-2 py-1.5 text-xs text-left hover:bg-card ${fieldMode === 'mapped' ? 'bg-surface' : ''}`}><Link2 className="h-3 w-3 text-critical" /><span>Mapped</span></button>}
                  <button type="button" onClick={(e) => { e.stopPropagation(); setItemFieldMode(itemIndex, fieldKey, 'form', keyPrefix, onMappingChange); }} className={`w-full flex items-center gap-2 px-2 py-1.5 text-xs text-left hover:bg-card ${fieldMode === 'form' ? 'bg-surface' : ''}`}><FileInput className="h-3 w-3 text-info" /><span>Form</span></button>
                  {fieldSchema.ui?.prompt && <button type="button" onClick={(e) => { e.stopPropagation(); setItemFieldMode(itemIndex, fieldKey, 'prompt', keyPrefix, onMappingChange); }} className={`w-full flex items-center gap-2 px-2 py-1.5 text-xs text-left hover:bg-card ${fieldMode === 'prompt' ? 'bg-surface' : ''}`}><Sparkles className="h-3 w-3 text-success" /><span>Prompt</span></button>}
                </div>
              )}
            </div>
          )}
        </div>
        {fieldMode === 'prompt' ? (() => {
          const nestedKey = `${paramKey}[${itemIndex}].${fieldKey}`;
          const savedMapping = allInputMappings?.[nestedKey];
          return (
            <PromptInput
              promptId={savedMapping?.promptId || ''}
              variableValues={savedMapping?.variableValues || {}}
              onPromptChange={(promptId, newVarValues) => onMappingChange(nestedKey, { mappingType: 'prompt', promptId, variableValues: newVarValues ?? savedMapping?.variableValues ?? {} })}
              onVariableValuesChange={(variableValues) => onMappingChange(nestedKey, { ...savedMapping, mappingType: 'prompt', variableValues })}
              previousSteps={previousSteps}
            />
          );
        })() : fieldMode === 'mapped' ? renderMappedFieldInput() : fieldMode === 'form' ? <div className="p-2 bg-info-subtle border border-info rounded text-xs text-info">User provides at runtime</div> : renderStaticFieldInput()}
      </div>
    );
  };

  return (
    <div className="flex-1 space-y-2">
      {arrayValue.map((item, index) => {
        const itemId = itemIds[index];
        const fieldGroups = groupFields(item);
        const sortedGroupIds = getSortedGroupIds(fieldGroups);
        return (
          <div key={itemId} className="border border-primary rounded-lg">
            <div role="button" tabIndex={0} className="flex w-full items-center justify-between px-3 py-2 bg-surface cursor-pointer hover:bg-card /50 rounded-t-lg" onClick={() => toggleExpand(index)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(index); } }}>
              <div className="flex items-center gap-2">
                <ChevronRight className={`h-4 w-4 text-secondary transition-transform ${expandedArrayItems[itemId] ? 'rotate-90' : ''}`} />
                <span className="text-sm font-medium text-secondary">{getItemLabel(item, index, itemSchema)}</span>
              </div>
              <div className="flex items-center gap-1">
                {schema.reorderable && (
                  <>
                    <button type="button" onClick={(e) => { e.stopPropagation(); moveItem(index, 'up'); }} className={`p-1 rounded cursor-pointer ${index === 0 ? 'text-muted cursor-not-allowed' : 'text-secondary hover:bg-input'}`} title="Move up"><ArrowUp className="h-3.5 w-3.5" /></button>
                    <button type="button" onClick={(e) => { e.stopPropagation(); moveItem(index, 'down'); }} className={`p-1 rounded cursor-pointer ${index === arrayValue.length - 1 ? 'text-muted cursor-not-allowed' : 'text-secondary hover:bg-input'}`} title="Move down"><ArrowDown className="h-3.5 w-3.5" /></button>
                  </>
                )}
                {canRemoveItem && <button type="button" onClick={(e) => { e.stopPropagation(); removeItem(index); }} className="p-1 text-danger hover:bg-danger-subtle rounded cursor-pointer" title="Remove item"><Trash2 className="h-4 w-4" /></button>}
              </div>
            </div>
            {expandedArrayItems[itemId] && (
              <div className="p-3 space-y-1 border-t border-primary">
                {sortedGroupIds.map((groupId) => {
                  const fields = fieldGroups.get(groupId) || [];
                  const visibleFields = fields.filter(([, propSchema]) => checkShowWhen(propSchema.ui?.show_when, item, itemSchema));
                  if (visibleFields.length === 0 || !shouldShowGroup(groupId, item)) return null;
                  const groupConfig = uiGroups[groupId];
                  const isCollapsed = groupId !== '_ungrouped' && groupConfig && isSceneGroupCollapsed(index, groupId);
                  return (
                    <div key={groupId}>
                      {groupId !== '_ungrouped' && groupConfig && renderCollapsibleGroupDivider(groupConfig.title, index, groupId, !!isCollapsed, isGroupModified(item, fields, itemSchema))}
                      {!isCollapsed && (
                        <div className="space-y-3 pl-3">
                          {visibleFields.map(([propKey, propSchema]) => renderItemField(propKey, propSchema, item[propKey], index, item, (key, val) => updateItem(index, key, val), itemSchema))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {(!schema.maxItems || arrayValue.length < schema.maxItems) && (
        <button type="button" onClick={addItem} className="flex items-center gap-2 px-3 py-2 text-sm text-info hover:bg-info-subtle rounded-lg border border-dashed border-info w-full justify-center">
          <Plus className="h-4 w-4" />Add {itemSchema?.title || schema.title?.replace(/s$/, '') || 'Item'}
        </button>
      )}
    </div>
  );
}
