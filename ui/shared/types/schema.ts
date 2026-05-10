// ui/shared/types/schema.ts

/** JSON Schema subset used for form generation. */
export interface ParameterSchema {
  type: string;
  title?: string;
  description?: string;
  properties: Record<string, PropertySchema>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface DynamicOptionsConfig {
  /** Service ID to call (e.g. 'list_items'). */
  service: string;
  /** JSONPath to the array in the response (e.g. 'bases'). */
  optionsPath: string;
  /** Field name on each option used as the value. */
  valueField: string;
  /** Field name on each option used as the display label. */
  labelField: string;
  /** Multi-level cascading uses an array (e.g. views depend on base AND table). */
  dependsOn?: DependsOnConfig | DependsOnConfig[];
}

export interface DependsOnConfig {
  field: string;
  /** Parameter name to send the dependency value as. */
  param: string;
}

export interface PropertySchema {
  type: string;
  title?: string;
  description?: string;
  default?: any;
  format?: string;
  enum?: any[];
  enumNames?: string[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  items?: PropertySchema;
  properties?: Record<string, PropertySchema>;
  required?: string[];
  multiline?: boolean;
  rows?: number;
  placeholder?: string;
  hidden?: boolean;
  dependsOn?: {
    field: string;
    value: any;
  };

  /** Renders as a combobox fetching remote options; accepts manual entry and variable mappings. */
  dynamicOptions?: DynamicOptionsConfig;
}

export function serviceParametersToSchema(
  parameters?: Record<string, {
    type: string;
    required?: boolean;
    default?: any;
    description?: string;
    enum?: any[];
    properties?: Record<string, any>;
  }>
): ParameterSchema {
  if (!parameters) {
    return {
      type: 'object',
      title: 'Parameters',
      properties: {},
    };
  }

  const properties: Record<string, PropertySchema> = {};
  const required: string[] = [];

  for (const [key, param] of Object.entries(parameters)) {
    properties[key] = {
      type: param.type,
      title: key,
      description: param.description,
      default: param.default,
    };

    if (param.enum) {
      properties[key].enum = param.enum;
    }

    if (param.type === 'object' && param.properties) {
      properties[key].properties = {};

      for (const [propKey, propValue] of Object.entries(param.properties)) {
        (properties[key].properties as Record<string, PropertySchema>)[propKey] = {
          type: propValue.type || 'string',
          title: propKey,
          description: propValue.description,
          default: propValue.default,
        };
        
        if (propValue.enum) {
          (properties[key].properties as Record<string, PropertySchema>)[propKey].enum = propValue.enum;
        }
      }
    }

    if (param.required) {
      required.push(key);
    }
  }

  return {
    type: 'object',
    title: 'Parameters',
    properties,
    required: required.length > 0 ? required : undefined,
  };
}