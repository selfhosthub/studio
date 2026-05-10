// ui/shared/lib/schema-utils.ts

interface PropertyWithDynamicOptions {
  dynamicOptions?: {
    service: string;
    optionsPath: string;
    valueField: string;
    labelField: string;
    dependsOn?: {
      field: string;
      param: string;
    };
  };
  [key: string]: any;
}

/**
 * Strip example values for fields with dynamicOptions - those examples are format hints
 * (e.g. "appXXXXXXXXXXXXXX") that would cause API errors if used as real values.
 */
export function getSafeExampleParameters(
  schema: { properties?: Record<string, PropertyWithDynamicOptions> } | null | undefined,
  exampleParameters: Record<string, any> | null | undefined
): Record<string, any> {
  if (!schema?.properties || !exampleParameters) {
    return {};
  }

  const safeParams: Record<string, any> = {};

  for (const [key, value] of Object.entries(exampleParameters)) {
    const propertySchema = schema.properties[key];

    if (propertySchema?.dynamicOptions) {
      continue;
    }

    safeParams[key] = value;
  }

  return safeParams;
}

export function getExamplePlaceholder(
  fieldKey: string,
  exampleParameters: Record<string, any> | null | undefined,
  defaultPlaceholder?: string
): string {
  const exampleValue = exampleParameters?.[fieldKey];

  if (exampleValue !== undefined && exampleValue !== null) {
    const displayValue = typeof exampleValue === 'string'
      ? exampleValue
      : JSON.stringify(exampleValue);
    return `e.g. ${displayValue}`;
  }

  return defaultPlaceholder || '';
}
