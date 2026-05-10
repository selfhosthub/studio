// ui/shared/lib/expression-utils.ts

/**
 * Design-time resolution for `{{ steps.step_id.field }}` parameter mappings.
 */

import type { Step } from '@/shared/types/workflow';

export function isExpression(value: any): boolean {
  return typeof value === 'string' && value.includes('{{');
}

export function parseExpression(value: string): { stepId: string; fieldPath: string[] } | null {
  if (!isExpression(value)) return null;

  const match = value.match(/\{\{\s*steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z0-9_.\[\]]+)\s*\}\}/);
  if (!match) return null;

  const [, stepId, fieldPathStr] = match;
  // Split on dots but preserve array notation like [0]
  const fieldPath = fieldPathStr.split(/\.(?![^\[]*\])/);

  return { stepId, fieldPath };
}

function getNestedValue(obj: any, path: string[]): any {
  let current = obj;
  for (const key of path) {
    if (current === undefined || current === null) return undefined;

    const arrayMatch = key.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]$/);
    if (arrayMatch) {
      const [, arrayKey, indexStr] = arrayMatch;
      const index = parseInt(indexStr, 10);
      current = current[arrayKey]?.[index];
    } else {
      current = current[key]; // nosemgrep
    }
  }
  return current;
}

export interface ExpressionContext {
  previousSteps?: Step[];
  formData?: Record<string, any>;
}

export interface ResolveResult {
  resolved: boolean;
  value: any;
  expression?: string;
}

export function resolveExpression(value: any, context: ExpressionContext): ResolveResult {
  if (!isExpression(value)) {
    return { resolved: true, value };
  }

  const parsed = parseExpression(value);
  if (!parsed) {
    return { resolved: false, value: undefined, expression: value };
  }

  const { stepId, fieldPath } = parsed;

  const step = context.previousSteps?.find(s => s.id === stepId);
  if (!step) {
    return { resolved: false, value: undefined, expression: value };
  }

  const params = step.job?.parameters || step.parameters || {};

  let resolvedValue = getNestedValue(params, fieldPath);

  // Dynamic-field services store values in a `fields` array keyed by name.
  if (resolvedValue === undefined && params.fields && Array.isArray(params.fields)) {
    const fieldName = fieldPath[0];
    const field = params.fields.find((f: any) => f.name === fieldName);
    if (field) {
      resolvedValue = field.value;
    }
  }

  if (resolvedValue !== undefined) {
    return { resolved: true, value: resolvedValue, expression: value };
  }

  return { resolved: false, value: undefined, expression: value };
}

export function resolveValue(
  value: any,
  context: ExpressionContext,
  fallback?: any
): any {
  const result = resolveExpression(value, context);
  if (result.resolved) {
    return result.value;
  }
  return fallback !== undefined ? fallback : value;
}

export function isUnresolvedExpression(value: any, context: ExpressionContext): boolean {
  if (!isExpression(value)) return false;
  const result = resolveExpression(value, context);
  return !result.resolved;
}
