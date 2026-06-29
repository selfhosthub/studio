// ui/features/step-config/MappableParameterField/components/NestedArrayField.tsx

'use client';

import React, { useState } from 'react';
import { ChevronRight, Trash2, Plus } from 'lucide-react';
import { NestedArrayFieldProps, PropertySchema, UIGroupConfig } from '../types';
import { checkShowWhen, createDefaultItemFromSchema, isFieldModified, isGroupModified } from '../utils/schemaUtils';

/**
 * Nested array field component for handling arrays within array items.
 * Extracted to module level to prevent focus loss on parent re-render.
 * Supports ui_groups with collapsible sections (n8n-style Show/Hide).
 */
export const NestedArrayField = React.memo(function NestedArrayField({
  fieldKey,
  parentKey,
  parentItemIndex,
  schema: nestedSchema,
  value: nestedValue,
  onChange,
  uiState,
  onUiStateChange,
  renderItemField,
}: NestedArrayFieldProps) {
  // Construct unique key prefix for nested fields to avoid collisions
  // e.g., "scenes:0:elements" for elements within scenes[0]
  const keyPrefix = `${parentKey}:${parentItemIndex}:${fieldKey}`;
  // Use persisted UI state if available, otherwise use local state
  const getExpandedItemKey = (idx: number) => `${parentKey}:${fieldKey}:${idx}`;
  const getExpandedGroupKey = (itemIdx: number, groupId: string) => `${parentKey}:${fieldKey}:${itemIdx}:${groupId}`;

  // Local state as fallback when persistence isn't wired up
  const [localExpandedItems, setLocalExpandedItems] = useState<Record<number, boolean>>({ 0: true });
  const [localCollapsedGroups, setLocalCollapsedGroups] = useState<Record<string, boolean>>({});

  const itemSchema = nestedSchema.items;
  const itemProperties = itemSchema?.properties || {};
  const uiGroups = (itemSchema?.ui_groups || {}) as UIGroupConfig;

  // Check if an item is expanded (using persisted state if available)
  const isItemExpanded = (idx: number): boolean => {
    const key = getExpandedItemKey(idx);
    if (uiState?.expandedItems?.[key] !== undefined) {
      return uiState.expandedItems[key];
    }
    // Fallback to local state
    return localExpandedItems[idx] ?? (idx === 0);  // First item expanded by default
  };

  // Check if a group is collapsed (using persisted state if available)
  const isGroupCollapsed = (itemIndex: number, groupId: string): boolean => {
    const key = getExpandedGroupKey(itemIndex, groupId);
    if (uiState?.expandedGroups?.[key] !== undefined) {
      return !uiState.expandedGroups[key];
    }
    // Fallback to local state
    if (localCollapsedGroups[`${itemIndex}:${groupId}`] !== undefined) {
      return localCollapsedGroups[`${itemIndex}:${groupId}`];
    }
    // Default: timing and layout are fundamental - always show by default
    if (groupId === 'timing' || groupId === 'layout') {
      return false;
    }
    return true;  // Default: collapsed
  };

  const addNestedItem = () => {
    const newItem = createDefaultItemFromSchema(nestedSchema.items);
    onChange([...nestedValue, newItem]);
    const newIdx = nestedValue.length;
    if (onUiStateChange) {
      const key = getExpandedItemKey(newIdx);
      onUiStateChange({
        ...uiState,
        expandedItems: { ...uiState?.expandedItems, [key]: true }
      });
    } else {
      setLocalExpandedItems(prev => ({ ...prev, [newIdx]: true }));
    }
  };

  const removeNestedItem = (index: number) => {
    if (nestedSchema.minItems && nestedValue.length <= nestedSchema.minItems) {
      return;
    }
    const updated = nestedValue.filter((_, i) => i !== index);
    onChange(updated);
  };

  const canRemoveItem = !nestedSchema.minItems || nestedValue.length > nestedSchema.minItems;

  const updateNestedItem = (index: number, key: string, fieldValue: any) => {
    const updated = [...nestedValue];
    updated[index] = { ...updated[index], [key]: fieldValue };
    onChange(updated);
  };

  const toggleExpand = (index: number) => {
    const key = getExpandedItemKey(index);
    const currentlyExpanded = isItemExpanded(index);
    if (onUiStateChange) {
      onUiStateChange({
        ...uiState,
        expandedItems: { ...uiState?.expandedItems, [key]: !currentlyExpanded }
      });
    } else {
      setLocalExpandedItems(prev => ({ ...prev, [index]: !prev[index] }));
    }
  };

  const toggleGroupCollapsed = (itemIndex: number, groupId: string) => {
    const key = getExpandedGroupKey(itemIndex, groupId);
    const currentlyCollapsed = isGroupCollapsed(itemIndex, groupId);
    const newExpanded = currentlyCollapsed;

    if (onUiStateChange) {
      onUiStateChange({
        ...uiState,
        expandedGroups: { ...uiState?.expandedGroups, [key]: newExpanded }
      });
    } else {
      const localKey = `${itemIndex}:${groupId}`;
      setLocalCollapsedGroups(prev => {
        const defaultCollapsed = (groupId === 'timing' || groupId === 'layout') ? false : true;
        const wasCollapsed = prev[localKey] !== undefined ? prev[localKey] : defaultCollapsed;
        return { ...prev, [localKey]: !wasCollapsed };
      });
    }
  };

  const getItemLabel = (item: any, index: number): string => {
    if (item.name) return item.name;
    if (item.type) {
      const typeLabel = item.type.charAt(0).toUpperCase() + item.type.slice(1).replace(/_/g, ' ');
      return `${typeLabel} ${index + 1}`;
    }
    if (item.text) return item.text.slice(0, 20) + (item.text.length > 20 ? '...' : '');
    return `${itemSchema?.title || 'Item'} ${index + 1}`;
  };

  // Group fields by their ui.group property
  const groupFields = (item: any): Map<string, Array<[string, PropertySchema]>> => {
    const groups = new Map<string, Array<[string, PropertySchema]>>();
    groups.set('_ungrouped', []);

    const sortedProperties = Object.entries(itemProperties)
      .sort((a, b) => {
        const orderA = (a[1] as PropertySchema).ui?.order ?? 999;
        const orderB = (b[1] as PropertySchema).ui?.order ?? 999;
        return orderA - orderB;
      });

    for (const [propKey, propSchema] of sortedProperties) {
      const propSchemaTyped = propSchema as PropertySchema;
      const groupId = propSchemaTyped.ui?.group || '_ungrouped';
      if (!groups.has(groupId)) {
        groups.set(groupId, []);
      }
      groups.get(groupId)!.push([propKey, propSchemaTyped]);
    }
    return groups;
  };

  const getSortedGroupIds = (groups: Map<string, any>): string[] => {
    const groupIds = Array.from(groups.keys());
    return groupIds.sort((a, b) => {
      if (a === '_ungrouped') return -1;
      if (b === '_ungrouped') return 1;
      const orderA = uiGroups[a]?.order ?? 999;
      const orderB = uiGroups[b]?.order ?? 999;
      return orderA - orderB;
    });
  };

  const shouldShowGroup = (groupId: string, item: any): boolean => {
    if (groupId === '_ungrouped') return true;
    const groupConfig = uiGroups[groupId];
    if (!groupConfig?.show_when) return true;
    return checkShowWhen(groupConfig.show_when, item, itemSchema);
  };

  // Check if any group in an item has a non-default value
  const isItemModified = (item: any, groups: Map<string, Array<[string, PropertySchema]>>): boolean => {
    for (const [, fields] of groups) {
      if (isGroupModified(item, fields, itemSchema)) {
        return true;
      }
    }
    return false;
  };

  const renderCollapsibleGroupHeader = (groupTitle: string, itemIndex: number, groupId: string, isCollapsed: boolean, hasModified: boolean) => (
    <div
      className="group-header-warning -mx-2 mt-3 mb-1"
      onClick={() => toggleGroupCollapsed(itemIndex, groupId)}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-warning uppercase tracking-wide">
          {groupTitle}
        </span>
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

  return (
    <div className="space-y-2">
      {nestedValue.map((item, idx) => {
        const fieldGroups = groupFields(item);
        const sortedGroupIds = getSortedGroupIds(fieldGroups);

        return (
          <div key={idx} className="bg-surface rounded border border-primary">
            <div
              className="flex items-center justify-between p-2 cursor-pointer hover:bg-card /50"
              onClick={() => toggleExpand(idx)}
            >
              <div className="flex items-center gap-2">
                <ChevronRight className={`h-4 w-4 transition-transform${isItemExpanded(idx) ? 'rotate-90' : ''}`} />
                <span className="text-sm font-medium">{getItemLabel(item, idx)}</span>
                {!isItemExpanded(idx) && isItemModified(item, fieldGroups) && (
                  <span className="text-[10px] font-medium text-info bg-info-subtle px-1.5 py-0.5 rounded">
                    Modified
                  </span>
                )}
              </div>
              {canRemoveItem && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeNestedItem(idx);
                  }}
                  className="p-1 text-danger hover:bg-danger-subtle rounded"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            {isItemExpanded(idx) && (
              <div className="p-2 pt-0 space-y-1 border-t border-primary">
                {sortedGroupIds.map((groupId) => {
                  const fields = fieldGroups.get(groupId) || [];
                  const visibleFields = fields.filter(([, propSchema]) =>
                    checkShowWhen(propSchema.ui?.show_when, item, itemSchema)
                  );

                  if (visibleFields.length === 0) return null;
                  if (!shouldShowGroup(groupId, item)) return null;

                  const groupConfig = uiGroups[groupId];
                  // Only collapse if there's a groupConfig (so user can click header to expand)
                  // Without groupConfig, always show fields (no header = no way to expand)
                  const isCollapsed = groupId !== '_ungrouped' && groupConfig && isGroupCollapsed(idx, groupId);

                  return (
                    <div key={groupId}>
                      {groupId !== '_ungrouped' && groupConfig && (
                        renderCollapsibleGroupHeader(groupConfig.title, idx, groupId, isCollapsed, isGroupModified(item, fields, itemSchema))
                      )}
                      {!isCollapsed && (
                        <div className="space-y-2 pl-2">
                          {visibleFields.map(([propKey, propSchema]) =>
                            renderItemField(
                              propKey,
                              propSchema,
                              item[propKey],
                              idx,
                              item,
                              (key, val) => updateNestedItem(idx, key, val),
                              itemSchema,
                              keyPrefix  // Pass prefix for unique key generation
                            )
                          )}
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
      {(!nestedSchema.maxItems || nestedValue.length < nestedSchema.maxItems) && (
        <button
          type="button"
          onClick={addNestedItem}
          className="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium text-info hover:bg-info-subtle rounded-md border border-dashed border-info w-full justify-center transition-colors"
        >
          <Plus className="h-3 w-3" />
          Add {itemSchema?.title || 'Item'}
        </button>
      )}
    </div>
  );
});

export default NestedArrayField;
