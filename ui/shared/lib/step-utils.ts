// ui/shared/lib/step-utils.ts

import type { Step, JobConfig } from '@/shared/types/workflow';

// provider_id, service_id, service_type are canonical at the step level (design-time
// configuration). The backend injects them into the job at execution time. Reads
// fall back to job-level for legacy data; writes always go to step level.

export function getStepProviderId(step: Step | Record<string, any>): string | undefined {
  return step.provider_id ?? step.job?.provider_id;
}

export function getStepServiceId(step: Step | Record<string, any>): string | undefined {
  return step.service_id ?? step.job?.service_id;
}

export function getStepServiceType(step: Step | Record<string, any>): string | undefined {
  return (step as any).service_type ?? step.job?.service_type;
}

/**
 * Set provider/service identifiers at the step level and strip any legacy job-level copies.
 */
export function updateStepProviderService(
  step: Step | Record<string, any>,
  updates: { provider_id?: string; service_id?: string; service_type?: string }
): Step {
  const currentJob = step.job || {};
  const { provider_id: _jp, service_id: _js, service_type: _jst, ...cleanJob } = currentJob as any;

  return {
    ...step,
    ...(updates.provider_id !== undefined && { provider_id: updates.provider_id || undefined }),
    ...(updates.service_id !== undefined && { service_id: updates.service_id || undefined }),
    ...(updates.service_type !== undefined && { service_type: updates.service_type || undefined }),
    job: cleanJob,
  } as Step;
}

/**
 * Migrate legacy job-level provider/service identifiers up to the step level.
 */
export function normalizeStepProviderLocation(step: Step | Record<string, any>): Step {
  const jobProviderId = step.job?.provider_id;
  const jobServiceId = step.job?.service_id;
  const jobServiceType = step.job?.service_type;

  if ((jobProviderId || jobServiceId || jobServiceType) &&
      !step.provider_id && !step.service_id && !(step as any).service_type) {
    return updateStepProviderService(step, {
      provider_id: jobProviderId,
      service_id: jobServiceId,
      service_type: jobServiceType,
    });
  }

  return step as Step;
}

/** Reserved ID for the virtual webhook trigger step. */
export const TRIGGER_STEP_ID = '__trigger__';

/** Build a virtual Trigger step exposing the incoming webhook payload as outputs. */
export function createTriggerStep(triggerInputSchema?: Record<string, any>): Step {
  const defaultOutputs: Record<string, { path: string; description: string; type: string }> = {
    body: {
      path: '$.body',
      description: 'JSON body from POST request',
      type: 'object',
    },
    query: {
      path: '$.query',
      description: 'Query parameters from URL',
      type: 'object',
    },
    method: {
      path: '$.method',
      description: 'HTTP method (POST or GET)',
      type: 'string',
    },
  };

  // Custom schema fields are added as top-level outputs for convenience.
  let outputs = { ...defaultOutputs };

  if (triggerInputSchema?.properties) {
    for (const [key, schema] of Object.entries(triggerInputSchema.properties)) {
      const typedSchema = schema as { type?: string; description?: string };
      outputs[key] = {
        path: `$.body.${key}`,
        description: typedSchema.description || `Input field: ${key}`,
        type: typedSchema.type || 'string',
      };
    }
  }

  return {
    id: TRIGGER_STEP_ID,
    name: 'Trigger',
    description: 'Incoming webhook data',
    type: 'trigger',
    category: 'trigger',
    icon: 'webhook',
    outputs,
    depends_on: [],
    config: {
      virtual: true,
      readonly: true,
    },
    ui_config: {
      hidden: true,
    },
  };
}

export function generateStepSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s_-]/g, '')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

export function ensureUniqueStepId(
  baseId: string,
  existingSteps: Record<string, any> | any[]
): string {
  const stepsRecord = Array.isArray(existingSteps)
    ? existingSteps.reduce((acc, step) => ({ ...acc, [step.id]: step }), {})
    : existingSteps;

  let id = baseId;
  let counter = 2;

  while (stepsRecord[id]) {
    id = `${baseId}_${counter}`;
    counter++;
  }

  return id;
}

/** Strips namespace prefix (dots are delimiters in template expressions) and appends a 4-char random suffix. */
export function createStepId(serviceId: string): string {
  const suffix = crypto.randomUUID().slice(0, 4);
  const baseName = serviceId.includes('.') ? serviceId.split('.').pop()! : serviceId;
  return `${baseName}_${suffix}`;
}

/** @deprecated Use when no service is selected yet. */
export function createStepIdFromName(name: string, existingSteps: Record<string, any> | any[]): string {
  const slug = generateStepSlug(name);
  return ensureUniqueStepId(slug, existingSteps);
}

export interface DependencyValidationResult {
  valid: boolean;
  errors: string[];
}

export function validateDependencies(
  steps: Record<string, { depends_on?: string[] }>
): DependencyValidationResult {
  const errors: string[] = [];

  for (const [stepId, step] of Object.entries(steps)) {
    for (const depId of step.depends_on || []) {
      if (depId === '__instance_form__') continue; // virtual step, not a real dependency
      if (!steps[depId]) {
        errors.push(`Step "${stepId}" depends on non-existent step "${depId}"`);
      }
    }
  }

  const visited = new Set<string>();
  const recStack = new Set<string>();

  function hasCycle(stepId: string): boolean {
    if (!steps[stepId]) return false;

    visited.add(stepId);
    recStack.add(stepId);

    for (const depId of steps[stepId].depends_on || []) {
      if (!visited.has(depId)) {
        if (hasCycle(depId)) return true;
      } else if (recStack.has(depId)) {
        errors.push(`Circular dependency detected involving step "${stepId}" and "${depId}"`);
        return true;
      }
    }

    recStack.delete(stepId);
    return false;
  }

  for (const stepId of Object.keys(steps)) {
    if (!visited.has(stepId)) {
      if (hasCycle(stepId)) {
        break;
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

export function wouldCreateCycle(
  stepId: string,
  newDependencies: string[],
  steps: Record<string, { depends_on?: string[] }>
): boolean {
  const tempSteps = {
    ...steps,
    [stepId]: {
      ...steps[stepId],
      depends_on: newDependencies
    }
  };

  const result = validateDependencies(tempSteps);
  return !result.valid && result.errors.some(err => err.includes('Circular dependency'));
}

export function getDependentSteps(
  stepId: string,
  steps: Record<string, { depends_on?: string[] }>
): string[] {
  const dependents: string[] = [];

  for (const [sid, step] of Object.entries(steps)) {
    if (step.depends_on?.includes(stepId)) {
      dependents.push(sid);
    }
  }

  return dependents;
}

export function stepsArrayToDict(steps: any[]): Record<string, any> {
  return steps.reduce((acc, step) => {
    const { id, ...stepData } = step;
    acc[id] = stepData;
    return acc;
  }, {} as Record<string, any>);
}

export function stepsDictToArray(stepsDict: Record<string, any>): any[] {
  return Object.entries(stepsDict).map(([id, stepData]) => ({
    id,
    ...stepData
  }));
}

/** Prompt variables emitted as step outputs so downstream steps can reference them. */
function getPromptVariableOutputs(step: Step): Record<string, { description?: string; type?: string; _from_prompt?: boolean }> {
  const promptOutputs: Record<string, { description?: string; type?: string; _from_prompt?: boolean }> = {};
  if (!step.input_mappings) return promptOutputs;

  for (const [key, mapping] of Object.entries(step.input_mappings)) {
    if (mapping.mappingType === 'prompt' && mapping.variableValues) {
      for (const varName of Object.keys(mapping.variableValues)) {
        promptOutputs[varName] = {
          type: 'string',
          description: 'Prompt variable',
          _from_prompt: true,
        };
      }
    }

    if (key.startsWith('_prompt_variable:')) {
      const varName = key.replace('_prompt_variable:', '');
      if (varName && !promptOutputs[varName]) {
        promptOutputs[varName] = {
          type: 'string',
          description: 'Prompt variable',
          _from_prompt: true,
        };
      }
    }
  }

  return promptOutputs;
}

/** Collect form-mapped parameters and prompt variables across all steps. */
export function getInstanceFormFields(
  allSteps: Step[],
  promptVarCache?: Record<string, string[]>,
): Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }> {
  const formFields: Record<string, { description?: string; type?: string; _from_form?: boolean; _owning_step_ids?: string[]; _owning_step_name?: string }> = {};

  const addFormField = (
    fieldName: string,
    stepId: string,
    stepName: string | undefined,
    description: string,
    declaresOwnership: boolean = true,
  ) => {
    if (!fieldName) return;
    if (formFields[fieldName]) {
      // Field already registered - add this step as co-owner only if this call declares it
      if (declaresOwnership && !formFields[fieldName]._owning_step_ids!.includes(stepId)) {
        formFields[fieldName]._owning_step_ids!.push(stepId);
      }
    } else {
      formFields[fieldName] = {
        type: 'string',
        description,
        _from_form: true,
        _owning_step_ids: declaresOwnership ? [stepId] : [],
        _owning_step_name: declaresOwnership ? stepName : undefined,
      };
    }
  };

  for (const step of allSteps) {
    if (!step.input_mappings) continue;

    const mappedVarNames = new Set<string>();
    for (const [k, m] of Object.entries(step.input_mappings)) {
      if (k.startsWith('_prompt_variable:') && m.mappingType === 'mapped') {
        mappedVarNames.add(k.replace('_prompt_variable:', ''));
      }
    }

    for (const [key, mapping] of Object.entries(step.input_mappings)) {
      if (mapping.mappingType === 'form') {
        const fieldName = key.replace(/\[\d+\]\./g, '.').replace(/\[\*\]/g, '');
        addFormField(fieldName, step.id, step.name, `Form field (${step.name || step.id})`);
      }

      // mapped→__instance_form__ reads a runtime form field. Register the field name so
      // downstream pickers see it, but don't declare ownership - the reader step would
      // otherwise be filtered out of its own Output dropdown.
      if (mapping.mappingType === 'mapped' && mapping.stepId === '__instance_form__' && mapping.outputField) {
        addFormField(mapping.outputField, step.id, step.name, `Form field (${step.name || step.id})`, false);
      }

      if (key.startsWith('_prompt_variable:') && mapping.mappingType !== 'mapped') {
        const varName = key.replace('_prompt_variable:', '');
        addFormField(varName, step.id, step.name, `Prompt variable (${step.name || step.id})`);
      }

      // Prompt-variable names come from variableValues (often empty) and from the fetched
      // template-variable cache (primary source). Exclude vars mapped from a previous step.
      if (mapping.mappingType === 'prompt') {
        const varNames = new Set<string>();

        if (mapping.variableValues) {
          for (const v of Object.keys(mapping.variableValues)) varNames.add(v);
        }

        if (promptVarCache && mapping.promptId) {
          const cached = promptVarCache[mapping.promptId];
          if (cached) {
            for (const v of cached) varNames.add(v);
          }
        }

        for (const varName of varNames) {
          if (!mappedVarNames.has(varName)) {
            addFormField(varName, step.id, step.name, `Prompt variable (${step.name || step.id})`);
          }
        }
      }
    }
  }

  return formFields;
}

/** Native outputs + prompt vars + fields forwarded from direct predecessors; native outputs win on collision. */
export function getEffectiveOutputs(
  step: Step,
  previousSteps: Step[],
): Record<string, { path?: string; description?: string; type?: string; sample_value?: any; _forwarded?: boolean; _source_step_id?: string; _from_prompt?: boolean }> {
  const nativeOutputs = step.outputs || {};
  const promptOutputs = getPromptVariableOutputs(step);

  if (!step.output_forwarding?.enabled) {
    return { ...promptOutputs, ...nativeOutputs };
  }

  // In "selected" mode, prompt vars are also gated by selected_fields so users
  // control exactly what flows downstream.
  const filteredPromptOutputs: Record<string, any> = {};
  if (step.output_forwarding.mode === 'selected') {
    for (const [varName, varDef] of Object.entries(promptOutputs)) {
      if (step.output_forwarding.selected_fields?.includes(varName)) {
        filteredPromptOutputs[varName] = varDef;
      }
    }
  } else {
    Object.assign(filteredPromptOutputs, promptOutputs);
  }

  // Predecessors come from depends_on, not array position.
  const directPredecessors = (step.depends_on || [])
    .map(depId => previousSteps.find(s => s.id === depId))
    .filter((s): s is Step => s != null);

  if (directPredecessors.length === 0) {
    return { ...filteredPromptOutputs, ...nativeOutputs };
  }

  const forwarded: Record<string, any> = {};

  for (const predecessor of directPredecessors) {
    const predecessorsOfPredecessor = previousSteps.filter(s => s.id !== predecessor.id);
    const prevEffectiveOutputs = getEffectiveOutputs(predecessor, predecessorsOfPredecessor);

    for (const [fieldName, fieldDef] of Object.entries(prevEffectiveOutputs)) {
      if (step.output_forwarding.mode === 'selected') {
        if (!step.output_forwarding.selected_fields?.includes(fieldName)) {
          continue;
        }
      }

      // Preserve the original source ID across multi-hop forwards.
      const typedFieldDef = fieldDef as { _forwarded?: boolean; _source_step_id?: string };
      forwarded[fieldName] = {
        ...fieldDef,
        _forwarded: true,
        _source_step_id: typedFieldDef._source_step_id || predecessor.id,
      };
    }
  }

  return {
    ...filteredPromptOutputs,
    ...forwarded,
    ...nativeOutputs,
  };
}

/** Kahn's algorithm topo sort by depends_on; ties broken alphabetically for deterministic ordering. */
export function topologicalSortSteps<T extends { id: string; depends_on?: string[] }>(
  steps: T[]
): T[] {
  if (steps.length <= 1) return steps;

  const stepMap = new Map(steps.map(s => [s.id, s]));
  const inDegree = new Map<string, number>();
  const dependents = new Map<string, string[]>();

  for (const step of steps) {
    inDegree.set(step.id, 0);
    dependents.set(step.id, []);
  }

  for (const step of steps) {
    for (const depId of step.depends_on || []) {
      if (stepMap.has(depId)) {
        inDegree.set(step.id, (inDegree.get(step.id) || 0) + 1);
        dependents.get(depId)!.push(step.id);
      }
    }
  }

  const queue: string[] = [];
  for (const step of steps) {
    if (inDegree.get(step.id) === 0) {
      queue.push(step.id);
    }
  }
  queue.sort();

  const sorted: T[] = [];

  while (queue.length > 0) {
    const id = queue.shift()!;
    sorted.push(stepMap.get(id)!);

    const newlyFreed: string[] = [];
    for (const depId of dependents.get(id)!) {
      const newDegree = inDegree.get(depId)! - 1;
      inDegree.set(depId, newDegree);
      if (newDegree === 0) {
        newlyFreed.push(depId);
      }
    }
    newlyFreed.sort();
    queue.push(...newlyFreed);
    queue.sort();
  }

  // Append any unreachable nodes (cycle / orphan edge case) so we never lose steps.
  if (sorted.length < steps.length) {
    const sortedIds = new Set(sorted.map(s => s.id));
    for (const step of steps) {
      if (!sortedIds.has(step.id)) {
        sorted.push(step);
      }
    }
  }

  return sorted;
}

export function getUpstreamSteps<T extends { id: string; depends_on?: string[] }>(
  stepId: string,
  allSteps: T[]
): T[] {
  const upstreamStepIds = new Set<string>();

  const collectUpstream = (currentStepId: string) => {
    const step = allSteps.find((s) => s.id === currentStepId);
    if (!step?.depends_on) return;

    for (const depId of step.depends_on) {
      if (!upstreamStepIds.has(depId)) {
        upstreamStepIds.add(depId);
        collectUpstream(depId);
      }
    }
  };

  collectUpstream(stepId);

  return allSteps.filter((s) => upstreamStepIds.has(s.id));
}
