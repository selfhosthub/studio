// ui/entities/workflow/lib/connection-utils.ts

// Pure utility functions for connection graph operations

import type { Step, Connection } from '../types';

/**
 * Build a map of target step IDs to their connected source step IDs.
 */
export function buildConnectionSourcesMap(connections: Connection[]): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>();
  connections.forEach(conn => {
    const sourceId = conn.source_id || (conn as any).source;
    const targetId = conn.target_id || (conn as any).target;
    if (sourceId && targetId) {
      if (!map.has(targetId)) {
        map.set(targetId, new Set());
      }
      map.get(targetId)!.add(sourceId);
    }
  });
  return map;
}

/**
 * Clean template strings that reference disconnected steps.
 * Template pattern: {{ step_id.field }}
 * Returns the original params object if nothing changed (reference equality check).
 */
export function cleanTemplateStrings(
  params: Record<string, any> | undefined,
  connectedSources: Set<string>
): Record<string, any> | undefined {
  if (!params) return params;
  let changed = false;
  const cleaned: Record<string, any> = {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === 'string') {
      const templateMatch = value.match(/\{\{\s*(\w+)\.\w+\s*\}\}/);
      if (templateMatch && !connectedSources.has(templateMatch[1])) {
        cleaned[key] = '';
        changed = true;
      } else {
        cleaned[key] = value;
      }
    } else {
      cleaned[key] = value;
    }
  }
  return changed ? cleaned : params;
}

/**
 * Clean input_mappings that reference disconnected steps.
 * Resets mapped entries whose stepId is no longer in connectedSources to static.
 * Returns the original mappings object if nothing changed (reference equality check).
 */
export function cleanInputMappings(
  mappings: Record<string, any> | undefined,
  connectedSources: Set<string>
): Record<string, any> | undefined {
  if (!mappings) return mappings;
  let changed = false;
  const cleaned: Record<string, any> = {};
  for (const [key, mapping] of Object.entries(mappings)) {
    if (mapping?.mappingType === 'mapped' && mapping?.stepId) {
      if (!connectedSources.has(mapping.stepId)) {
        cleaned[key] = { mappingType: 'static' };
        changed = true;
      } else {
        cleaned[key] = mapping;
      }
    } else {
      cleaned[key] = mapping;
    }
  }
  return changed ? cleaned : mappings;
}

/**
 * Sync a step's depends_on, iteration_config, parameters, job.parameters,
 * and input_mappings based on its current connections.
 * Returns the original step if nothing changed (reference equality).
 */
export function syncStepWithConnections(
  step: Step,
  connectedSources: Set<string>
): { step: Step; changed: boolean } {
  const newDependsOn = Array.from(connectedSources);

  // Check if depends_on changed
  const currentDependsOn = step.depends_on || [];
  const dependsOnChanged =
    newDependsOn.length !== currentDependsOn.length ||
    newDependsOn.some(d => !currentDependsOn.includes(d));

  // Check if iteration_config needs cleanup
  let iterationConfig = step.iteration_config;
  let iterationChanged = false;
  if (iterationConfig?.enabled && iterationConfig?.source_step_id) {
    if (!connectedSources.has(iterationConfig.source_step_id)) {
      iterationConfig = undefined;
      iterationChanged = true;
    }
  }

  // Clean template strings in parameters
  const cleanedParams = cleanTemplateStrings(step.parameters, connectedSources);
  const paramsChanged = cleanedParams !== step.parameters;

  // Clean job.parameters
  let cleanedJob = step.job;
  let jobParamsChanged = false;
  if (step.job?.parameters) {
    const cleanedJobParams = cleanTemplateStrings(step.job.parameters, connectedSources);
    if (cleanedJobParams !== step.job.parameters) {
      cleanedJob = { ...step.job, parameters: cleanedJobParams };
      jobParamsChanged = true;
    }
  }

  // Clean input_mappings
  const cleanedInputMappings = cleanInputMappings(step.input_mappings, connectedSources);
  const inputMappingsChanged = cleanedInputMappings !== step.input_mappings;

  if (!dependsOnChanged && !iterationChanged && !paramsChanged && !jobParamsChanged && !inputMappingsChanged) {
    return { step, changed: false };
  }

  return {
    step: {
      ...step,
      depends_on: newDependsOn.length > 0 ? newDependsOn : [],
      ...(iterationChanged ? { iteration_config: iterationConfig } : {}),
      ...(paramsChanged ? { parameters: cleanedParams } : {}),
      ...(jobParamsChanged ? { job: cleanedJob } : {}),
      ...(inputMappingsChanged ? { input_mappings: cleanedInputMappings } : {}),
    },
    changed: true,
  };
}
