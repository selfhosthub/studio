// ui/app/workflows/components/OutputSchemaDisplay.tsx

'use client';

import React from 'react';
import { LinkedText } from '@/shared/ui';

// Same loose record type used by the parent component and APIs
type AnyRecord = Record<string, any>;

interface OutputSchemaDisplayProps {
  outputSchema: AnyRecord | null;
  promptVarNames: string[];
  outputViewMode: 'schema' | 'json';
}

const TYPE_COLORS: Record<string, string> = {
  string: 'bg-success-subtle text-success',
  number: 'bg-info-subtle text-info',
  integer: 'bg-info-subtle text-info',
  boolean: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
  array: 'bg-critical-subtle text-critical',
  object: 'bg-warning-subtle text-warning',
};

const TYPE_LABELS: Record<string, string> = {
  string: 'AB',
  number: '123',
  integer: '123',
  boolean: 'T/F',
  array: '[ ]',
  object: '{ }',
};

function renderSchemaField(
  fieldName: string,
  fieldSchema: unknown,
  depth: number,
  path: string = fieldName,
): React.ReactNode[] {
  const schema = fieldSchema as {
    type?: string;
    description?: string;
    properties?: Record<string, unknown>;
    items?: { type?: string; properties?: Record<string, unknown> };
  };
  const fieldType = schema.type || 'string';
  const indentPx = depth * 16;
  const result: React.ReactNode[] = [];

  result.push(
    <div
      key={path}
      className="flex items-center gap-2 py-1.5 px-2 bg-card rounded border border-purple-200 dark:border-purple-700" // css-check-ignore: no semantic token
      style={{ marginLeft: `${indentPx}px` }}
    >
      <span className={`px-1.5 py-0.5 text-xs font-mono rounded${TYPE_COLORS[fieldType] || TYPE_COLORS.string}`}>
        {TYPE_LABELS[fieldType] || 'AB'}
      </span>
      <span className="text-sm font-medium text-primary">
        {fieldName}
      </span>
      {schema.description && (
        <span className="text-xs text-secondary truncate">
          - <LinkedText text={schema.description} />
        </span>
      )}
    </div>
  );

  if (fieldType === 'object' && schema.properties) {
    Object.entries(schema.properties).forEach(([nestedName, nestedSchema]) => {
      result.push(...renderSchemaField(nestedName, nestedSchema, depth + 1, `${path}.${nestedName}`));
    });
  }
  if (fieldType === 'array' && schema.items?.properties) {
    Object.entries(schema.items.properties).forEach(([nestedName, nestedSchema]) => {
      result.push(...renderSchemaField(nestedName, nestedSchema, depth + 1, `${path}[].${nestedName}`));
    });
  }

  return result;
}

/**
 * Displays the output schema for a service step in either schema view or JSON view.
 * Extracted from WorkflowStepConfig to reduce main component size.
 */
export function OutputSchemaDisplay({ outputSchema, promptVarNames, outputViewMode }: OutputSchemaDisplayProps) {
  const hasSchemaProps = outputSchema?.properties && Object.keys(outputSchema.properties).length > 0;
  const hasPromptVars = promptVarNames.length > 0;

  if (!hasSchemaProps && !hasPromptVars) {
    return <p className="text-muted">No output schema defined for this service.</p>;
  }

  return (
    <>
      {outputViewMode === 'schema' ? (
        <div className="space-y-1">
          {hasSchemaProps && Object.entries(outputSchema!.properties).flatMap(([fieldName, fieldSchema]) =>
            renderSchemaField(fieldName, fieldSchema, 0)
          )}
          {hasPromptVars && (
            <>
              <div className="flex items-center gap-1.5 pt-2 pb-1 px-1">
                <span className="text-xs font-medium text-teal-600 dark:text-teal-400">Prompt variables</span> {/* css-check-ignore: no semantic token */}
              </div>
              {promptVarNames.map(varName => (
                <div
                  key={`tpl_${varName}`}
                  className="flex items-center gap-2 py-1.5 px-2 bg-teal-50 dark:bg-teal-900/20 rounded border border-teal-200 dark:border-teal-800" // css-check-ignore: no semantic token
                >
                  <span className={`px-1.5 py-0.5 text-xs font-mono rounded${TYPE_COLORS.string}`}>
                    AB
                  </span>
                  <span className="text-sm font-medium text-primary">
                    {varName}
                  </span>
                  <span className="text-xs text-teal-500 dark:text-teal-400 truncate"> {/* css-check-ignore: no semantic token */}
                    - Prompt variable
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      ) : (
        <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded overflow-auto max-h-64"> {/* css-check-ignore: code block theme */}
          {JSON.stringify(
            (() => {
              const extractKeys = (props: Record<string, unknown>): Record<string, unknown> => {
                const result: Record<string, unknown> = {};
                Object.entries(props).forEach(([key, value]) => {
                  const schema = value as { type?: string; items?: { properties?: Record<string, unknown> }; properties?: Record<string, unknown> };
                  if (schema.type === 'array' && schema.items?.properties) {
                    result[key] = [extractKeys(schema.items.properties)];
                  } else if (schema.type === 'object' && schema.properties) {
                    result[key] = extractKeys(schema.properties);
                  } else {
                    result[key] = schema.type || 'string';
                  }
                });
                return result;
              };
              const result = outputSchema?.properties
                ? extractKeys(outputSchema.properties)
                : {};
              for (const v of promptVarNames) {
                result[v] = 'string (prompt var)';
              }
              return result;
            })(),
            null,
            2
          )}
        </pre>
      )}
    </>
  );
}
