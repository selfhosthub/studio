// ui/widgets/instance-view/InstanceSimpleView/utils/helpers.ts

import { FormFieldConfig, FormFieldType } from "@/entities/workflow";
import { OrgFile } from "@/shared/types/api";
import { OutputViewConfig } from "@/shared/ui";
import { GroupedResources } from "../types";

/** Normalize API snake_case form-field config into the camelCase shape the UI consumes. */
export function normalizeConfig(config: any): FormFieldConfig {  // eslint-disable-line @typescript-eslint/no-explicit-any
  return {
    label: config.label,
    placeholder: config.placeholder,
    description: config.description,
    required: config.required,
    fieldType: (config.field_type ?? 'text') as FormFieldType,
    defaultValue: config.default_value,
    options: config.options,
    minLength: config.min_length,
    maxLength: config.max_length,
    min: config.min,
    max: config.max,
    acceptedFileTypes: config.accepted_file_types,
    maxFileSizeMB: config.max_file_size_mb,
    size: config.size as FormFieldConfig["size"],
    itemType: config.item_type,
    keyPlaceholder: config.key_placeholder,
    valuePlaceholder: config.value_placeholder,
    addLabel: config.add_label,
  };
}

/**
 * Format a parameter key like "step_id.scenes[0].fade_in" to a human-readable label.
 * Handles nested array notation and snake_case conversion.
 */
export function formatParamKey(key: string): string {
  // Remove step_id prefix (e.g., "generate_images.scenes[0].fade_in" -> "scenes[0].fade_in")
  const parts = key.split('.');
  let paramPart = parts.length > 1 ? parts.slice(1).join('.') : key;

  // Handle nested array field notation like "scenes[0].fade_in" -> "Scene 1: Fade In"
  const arrayMatch = paramPart.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.(.+)$/);
  if (arrayMatch) {
    const baseName = arrayMatch[1]; // e.g., "scenes"
    const index = parseInt(arrayMatch[2], 10); // e.g., 0
    const fieldName = arrayMatch[3]; // e.g., "fade_in"

    // Convert base name to singular form (simple heuristic)
    const singularBase = baseName.endsWith('s') && baseName.length > 2
      ? baseName.slice(0, -1)
      : baseName;
    const formattedBase = singularBase.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const formattedField = fieldName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

    // Use 1-based indexing for user-friendliness
    return `${formattedBase} ${index + 1}: ${formattedField}`;
  }

  // Simple key - just format it nicely
  return paramPart.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Extract display values from instance.input_data.
 * Handles form_values object and flattens nested structures.
 */
export function extractDisplayValues(inputData: Record<string, any>): Array<{ key: string; label: string; value: any }> {
  const results: Array<{ key: string; label: string; value: any }> = [];

  // If form_values exists, extract from there (Experience View format)
  const formValues = inputData?.form_values;
  if (formValues && typeof formValues === 'object') {
    for (const [key, value] of Object.entries(formValues)) {
      results.push({
        key,
        label: formatParamKey(key),
        value,
      });
    }
  }

  // Also add any direct values (not form_values or internal fields)
  const seenKeys = new Set(results.map((r) => r.key));
  for (const [key, value] of Object.entries(inputData)) {
    // Skip form_values (already processed), internal fields, and duplicates
    if (key === 'form_values' || key.startsWith('_') || seenKeys.has(key)) continue;

    // If value is an object with step-like keys, skip it (it's already in form_values)
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      continue;
    }

    results.push({
      key,
      label: formatParamKey(key),
      value,
    });
  }

  return results;
}

/**
 * Auto-detect output view configuration from result data.
 * Returns a table view config if the data looks like tabular data (array of objects).
 */
export function detectOutputView(result: any): OutputViewConfig | null {
  if (!result || typeof result !== 'object') return null;

  // Check for common patterns that indicate tabular data

  // Pattern 1: { records: [...] } (Airtable-style)
  if (result.records && Array.isArray(result.records) && result.records.length > 0) {
    const firstRecord = result.records[0];
    if (firstRecord && typeof firstRecord === 'object' && firstRecord.fields) {
      return {
        type: 'table',
        source: 'records',
        row_path: 'fields',
        columns: 'auto',
        id_field: 'id',
      };
    }
  }

  // Pattern 2: { data: [...] } (generic API response)
  if (result.data && Array.isArray(result.data) && result.data.length > 0) {
    const firstItem = result.data[0];
    if (firstItem && typeof firstItem === 'object') {
      return {
        type: 'table',
        source: 'data',
        columns: 'auto',
      };
    }
  }

  // Pattern 3: { items: [...] }
  if (result.items && Array.isArray(result.items) && result.items.length > 0) {
    const firstItem = result.items[0];
    if (firstItem && typeof firstItem === 'object') {
      return {
        type: 'table',
        source: 'items',
        columns: 'auto',
      };
    }
  }

  // Pattern 4: Direct array at top level
  if (Array.isArray(result) && result.length > 0) {
    const firstItem = result[0];
    if (firstItem && typeof firstItem === 'object') {
      return {
        type: 'table',
        source: undefined,  // No source path needed, data is the array itself
        columns: 'auto',
      };
    }
  }

  // Pattern 5: OpenAI Chat Completion response
  // Detect: { choices: [{ message: { content: "..." } }], ... }
  if (result.choices && Array.isArray(result.choices) && result.choices.length > 0) {
    const firstChoice = result.choices[0];
    if (firstChoice?.message?.content !== undefined) {
      return {
        type: 'key_value',
        source: undefined,
        fields: [
          { key: 'choices.0.message.content', label: 'Response' },
          { key: 'choices.0.message.role', label: 'Role' },
          { key: 'model', label: 'Model' },
          { key: 'choices.0.finish_reason', label: 'Finish Reason' },
          { key: 'usage.total_tokens', label: 'Total Tokens' },
        ],
      };
    }
  }

  // Pattern 6: Simple key-value object (like set_fields output)
  // Detect objects where most values are displayable (primitives or arrays of primitives)
  const keys = Object.keys(result);
  if (keys.length > 0 && keys.length <= 20) {
    const isDisplayableValue = (value: any): boolean => {
      // Primitives are displayable
      if (value === null || value === undefined ||
          typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        return true;
      }
      // Arrays of primitives are displayable (KeyValueOutputView renders them as comma-separated)
      if (Array.isArray(value)) {
        return value.every(v =>
          typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
        );
      }
      return false;
    };

    const displayableCount = keys.filter(key => isDisplayableValue(result[key])).length;

    // If at least half the values are displayable, treat as key-value
    if (displayableCount >= keys.length / 2) {
      return {
        type: 'key_value',
        source: undefined,
      };
    }
  }

  return null;
}

/**
 * Calculate human-readable duration between two timestamps
 */
export function calculateDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return "N/A";
  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const durationMs = end.getTime() - start.getTime();
  const minutes = Math.floor(durationMs / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(durationMs / 1000)}s`;
}

/**
 * Group resources by iteration_index from metadata.
 * Also calculates which iterations are pending/incomplete.
 */
export function groupResourcesByIteration(
  resources: OrgFile[],
  iterationCount: number | null,
  filesPerIteration: number
): GroupedResources {
  if (!iterationCount) {
    // No iteration data - return single group with all resources
    return {
      hasIterations: false,
      groups: [{ iterationIndex: null, resources, expectedCount: resources.length, isComplete: true }]
    };
  }

  // Group resources by iteration_index
  const groupMap = new Map<number, OrgFile[]>();
  for (const resource of resources) {
    const idx = resource.metadata?.iteration_index ?? -1;
    if (idx >= 0) {
      if (!groupMap.has(idx)) groupMap.set(idx, []);
      groupMap.get(idx)!.push(resource);
    }
  }

  // Build groups for ALL iterations (including those with no resources yet)
  const groups: GroupedResources['groups'] = [];

  for (let i = 0; i < iterationCount; i++) {
    const iterResources = groupMap.get(i) || [];
    groups.push({
      iterationIndex: i,
      resources: iterResources,
      expectedCount: filesPerIteration,
      isComplete: iterResources.length >= filesPerIteration,
    });
  }

  // Add any resources without iteration_index (shouldn't happen, but handle gracefully)
  const ungroupedResources = resources.filter(r => r.metadata?.iteration_index === undefined);
  if (ungroupedResources.length > 0) {
    groups.push({
      iterationIndex: null,
      resources: ungroupedResources,
      expectedCount: ungroupedResources.length,
      isComplete: true,
    });
  }

  return { hasIterations: true, groups };
}

/**
 * Get filename from resource - prefer virtual_path filename which already has unique ID
 */
export function getFilename(resource: OrgFile): string {
  // Extract filename from virtual_path (e.g., "generated_images_d8f06d83.png")
  if (resource.virtual_path) {
    const parts = resource.virtual_path.split('/');
    const filename = parts[parts.length - 1];
    if (filename) return filename;
  }
  // Fallback: construct from display_name + short ID
  let baseName = resource.display_name || 'file';
  const lastDot = baseName.lastIndexOf('.');
  if (lastDot > 0) {
    baseName = baseName.substring(0, lastDot);
  }
  baseName = baseName.replace(/[^a-zA-Z0-9]/g, '_').replace(/_+/g, '_');
  const shortId = resource.id.slice(-8);
  const ext = resource.file_extension || '.bin';
  return `${baseName}_${shortId}${ext.startsWith('.') ? ext : '.' + ext}`;
}
