// ui/features/step-config/PreviousStepOutputsPanel/utils/panelUtils.ts

export interface InputMapping {
  mappingType?: 'mapped' | 'static';
  stepId?: string;
  outputField?: string;
  source_step_id?: string;
  source_output_field?: string;
  loop?: boolean;
}

// Simplified to just Schema and JSON (Table rarely used)
export type ViewMode = 'schema' | 'json';

// Available filter types
export type FilterType = 'string' | 'number' | 'boolean' | 'array' | 'object';

// Type filter configuration matching TypeBadge styles
export const TYPE_FILTER_CONFIG: Record<FilterType, { bg: string; activeBg: string; text: string; activeText: string; label: string }> = {
  string: { bg: 'bg-card', activeBg: 'bg-success', text: 'text-secondary', activeText: 'text-white', label: 'AB' },
  number: { bg: 'bg-card', activeBg: 'bg-info', text: 'text-secondary', activeText: 'text-white', label: '123' },
  boolean: { bg: 'bg-card', activeBg: 'bg-purple-500 dark:bg-purple-600', text: 'text-secondary', activeText: 'text-white', label: 'T/F' }, // css-check-ignore: no semantic token
  array: { bg: 'bg-card', activeBg: 'bg-critical', text: 'text-secondary', activeText: 'text-white', label: '[ ]' },
  object: { bg: 'bg-card', activeBg: 'bg-warning', text: 'text-secondary', activeText: 'text-white', label: '{ }' },
};

/**
 * Convert result_schema properties to step output format
 */
export function schemaPropertiesToOutputs(properties: Record<string, any>): Record<string, any> {
  const outputs: Record<string, any> = {};
  for (const [key, schema] of Object.entries(properties)) {
    const propSchema = schema as { type?: string; description?: string; items?: any };
    outputs[key] = {
      path: key,
      description: propSchema.description || `${key} field`,
      type: propSchema.type || 'string',
      ...(propSchema.items ? { items: propSchema.items } : {})
    };
  }
  return outputs;
}

/**
 * Helper to check if an output field is mapped
 */
export function isFieldMapped(
  stepId: string,
  fieldName: string,
  inputMappings: Record<string, InputMapping> | undefined
): boolean {
  if (!inputMappings) return false;
  return Object.values(inputMappings).some(mapping => {
    const mappedStepId = mapping.stepId || mapping.source_step_id;
    const mappedField = mapping.outputField || mapping.source_output_field;
    return mapping.mappingType === 'mapped' && mappedStepId === stepId && mappedField === fieldName;
  });
}

/**
 * Get a sample value for a given field type
 */
export function getSampleValue(fieldType: string, fieldName: string, items?: any): any {
  switch (fieldType) {
    case 'string':
      return `{{${fieldName}}}`;
    case 'number':
    case 'integer':
      return 0;
    case 'boolean':
      return true;
    case 'array':
      // If array has items with properties, show nested structure
      if (items?.properties) {
        const nestedObj: Record<string, any> = {};
        Object.entries(items.properties).forEach(([propName, propDef]) => {
          const propType = (propDef as any)?.type || 'string';
          nestedObj[propName] = getSampleValue(propType, `${fieldName}[*].${propName}`);
        });
        return [nestedObj];
      }
      return [];
    case 'object':
      return {};
    default:
      return `{{${fieldName}}}`;
  }
}
