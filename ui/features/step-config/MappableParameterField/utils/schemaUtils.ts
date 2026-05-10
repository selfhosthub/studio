// ui/features/step-config/MappableParameterField/utils/schemaUtils.ts

// Schema utility functions for MappableParameterField

import { PropertySchema } from '../types';

/**
 * Check if a field should be shown based on show_when conditions
 * Supports both single value and array of values: { "type": "video" } or { "type": ["video", "image"] }
 * Also handles checking against schema defaults when value is not yet set
 */
export function checkShowWhen(
  showWhen: Record<string, any> | undefined,
  itemData: Record<string, any>,
  itemSchema?: PropertySchema
): boolean {
  if (!showWhen) return true;
  for (const [field, expectedValue] of Object.entries(showWhen)) {
    // Get actual value, falling back to schema default if not set
    let actualValue = itemData[field];
    if (actualValue === undefined || actualValue === '') {
      // Try to get default from schema
      const fieldSchema = itemSchema?.properties?.[field] as PropertySchema | undefined;
      if (fieldSchema?.default !== undefined) {
        actualValue = fieldSchema.default;
      }
    }

    if (Array.isArray(expectedValue)) {
      // If expectedValue is an array, check if actualValue is in the array
      if (!expectedValue.includes(actualValue)) {
        return false;
      }
    } else {
      // Single value comparison
      if (actualValue !== expectedValue) {
        return false;
      }
    }
  }
  return true;
}

/**
 * Create a default item based on schema
 */
export function createDefaultItemFromSchema(itemSchema: PropertySchema | undefined): any {
  if (!itemSchema) return {};
  if (!itemSchema.properties) return {};

  const defaultItem: Record<string, any> = {};
  for (const [key, propSchema] of Object.entries(itemSchema.properties)) {
    const prop = propSchema as PropertySchema;
    if (prop.default !== undefined) {
      defaultItem[key] = prop.default;
    } else if (prop.enum && prop.enum.length > 0) {
      // Set first enum value as default for type fields
      if (key === 'type' || key === 'destination_type' || key === 'element_type') {
        defaultItem[key] = prop.enum[0];
      }
    } else if (prop.type === 'array') {
      // Initialize nested arrays to empty so they don't inherit stale data
      defaultItem[key] = [];
    }
  }
  return defaultItem;
}

/**
 * Format sample value for display
 */
export function formatSampleValue(value: any): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') {
    // Truncate long strings
    return value.length > 50 ? `"${value.slice(0, 50)}..."` : `"${value}"`;
  }
  if (typeof value === 'object') {
    const json = JSON.stringify(value);
    return json.length > 50 ? `${json.slice(0, 50)}...` : json;
  }
  return String(value);
}

/**
 * Get a display label for an array item
 */
export function getItemLabel(item: any, index: number, itemSchema?: PropertySchema): string {
  // User-provided name takes precedence
  if (item.name) return item.name;
  // Try common type fields for auto-labeling
  if (item.type) {
    const typeLabel = item.type.charAt(0).toUpperCase() + item.type.slice(1).replace(/_/g, ' ');
    return `${typeLabel} ${index + 1}`;
  }
  if (item.destination_type) {
    const typeLabel = item.destination_type.charAt(0).toUpperCase() + item.destination_type.slice(1);
    return `${typeLabel} Destination`;
  }
  if (item.text) return item.text.slice(0, 30) + (item.text.length > 30 ? '...' : '');
  if (item.src) return item.src.slice(0, 30) + (item.src.length > 30 ? '...' : '');
  return `${itemSchema?.title || 'Item'} ${index + 1}`;
}

/**
 * Group fields by their ui.group property
 */
export function groupFieldsByUIGroup(
  itemProperties: Record<string, PropertySchema>
): Map<string, Array<[string, PropertySchema]>> {
  const groups = new Map<string, Array<[string, PropertySchema]>>();
  groups.set('_ungrouped', []);

  // Sort properties by ui.order if available
  const sortedProperties = Object.entries(itemProperties)
    .sort((a, b) => {
      const orderA = (a[1] as PropertySchema).ui?.order ?? 999;
      const orderB = (b[1] as PropertySchema).ui?.order ?? 999;
      return orderA - orderB;
    });

  for (const [propKey, propSchema] of sortedProperties) {
    const schema = propSchema as PropertySchema;
    const groupId = schema.ui?.group || '_ungrouped';

    if (!groups.has(groupId)) {
      groups.set(groupId, []);
    }
    groups.get(groupId)!.push([propKey, schema]);
  }

  return groups;
}

/**
 * Get sorted group IDs based on ui_groups order
 */
export function getSortedGroupIds(
  groups: Map<string, any>,
  uiGroups: Record<string, { order: number }>
): string[] {
  const groupIds = Array.from(groups.keys());
  return groupIds.sort((a, b) => {
    if (a === '_ungrouped') return -1;
    if (b === '_ungrouped') return 1;
    const orderA = uiGroups[a]?.order ?? 999;
    const orderB = uiGroups[b]?.order ?? 999;
    return orderA - orderB;
  });
}

/**
 * Check if a single field has a non-default value
 */
export function isFieldModified(fieldValue: any, fieldSchema: PropertySchema): boolean {
  const defaultVal = fieldSchema.default;
  // If no default defined, consider empty/undefined as "not modified"
  if (defaultVal === undefined) {
    return fieldValue !== undefined && fieldValue !== '' && fieldValue !== null;
  }
  // Compare with default (handle arrays/objects with JSON stringify)
  if (typeof defaultVal === 'object' && defaultVal !== null) {
    return JSON.stringify(fieldValue) !== JSON.stringify(defaultVal);
  }
  return fieldValue !== defaultVal;
}

/**
 * Check if any field in a group has a non-default value
 */
export function isGroupModified(
  item: any,
  fieldList: Array<[string, PropertySchema]>,
  itemSchema?: PropertySchema
): boolean {
  for (const [propKey, propSchema] of fieldList) {
    // Skip fields not visible for this item type
    if (!checkShowWhen(propSchema.ui?.show_when, item, itemSchema)) continue;
    if (isFieldModified(item[propKey], propSchema)) {
      return true;
    }
  }
  return false;
}
