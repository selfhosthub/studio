// ui/features/step-config/PreviousStepOutputsPanel/hooks/useEnhancedStepOutputs.ts

import { useState, useEffect, useMemo } from 'react';
import { Step } from '@/entities/workflow';
import { getProviderService, getPrompt } from '@/shared/api';
import { schemaPropertiesToOutputs, isFieldMapped, FilterType } from '../utils/panelUtils';
import type { InputMapping } from '../utils/panelUtils';

/**
 * Hook that enhances step outputs with fetched service schemas and prompt variables.
 * Returns enhanced steps with complete output metadata for display.
 */
export function useEnhancedStepOutputs(
  previousSteps: Step[],
  inputMappings?: Record<string, InputMapping>
) {
  // Cache for service result_schemas (keyed by service_id)
  const [serviceSchemas, setServiceSchemas] = useState<Record<string, Record<string, any>>>({});

  // Cache for prompt variable names (keyed by promptId)
  const [promptVarCache, setPromptVarCache] = useState<Record<string, string[]>>({});

  // Fetch prompt variables for steps with prompt mappings
  useEffect(() => {
    const promptIdsToFetch: string[] = [];

    previousSteps.forEach(step => {
      if (!step.input_mappings) return;
      for (const mapping of Object.values(step.input_mappings)) {
        if (mapping.mappingType === 'prompt' && mapping.promptId) {
          if (!promptVarCache[mapping.promptId]) {
            promptIdsToFetch.push(mapping.promptId);
          }
        }
      }
    });

    if (promptIdsToFetch.length === 0) return;

    const fetchPrompts = async () => {
      const newCache: Record<string, string[]> = {};
      await Promise.all(
        [...new Set(promptIdsToFetch)].map(async (promptId) => {
          try {
            const prompt = await getPrompt(promptId);
            if (prompt?.variables) {
              newCache[promptId] = prompt.variables.map((v: any) => v.name);
            }
          } catch {
            // Prompt may not exist or not be accessible
          }
        })
      );
      if (Object.keys(newCache).length > 0) {
        setPromptVarCache(prev => ({ ...prev, ...newCache }));
      }
    };

    fetchPrompts();
  }, [previousSteps, promptVarCache]);

  // Fetch result_schema for each step's service to ensure we have complete outputs
  useEffect(() => {
    const fetchMissingSchemas = async () => {
      const servicesToFetch: Array<{ serviceId: string }> = [];

      // Find steps that have a service but we don't have the schema cached
      previousSteps.forEach(step => {
        if (step.service_id && !serviceSchemas[step.service_id]) {
          servicesToFetch.push({ serviceId: step.service_id });
        }
      });

      if (servicesToFetch.length === 0) return;

      // Fetch schemas for services we don't have
      const newSchemas: Record<string, Record<string, any>> = {};

      await Promise.all(
        servicesToFetch.map(async ({ serviceId }) => {
          try {
            const data = await getProviderService(serviceId);
            if (data?.result_schema?.properties) {
              newSchemas[serviceId] = schemaPropertiesToOutputs(data.result_schema.properties);
            }
          } catch {
            // Silently ignore schema fetch errors - panel will work without enhanced schema
          }
        })
      );

      if (Object.keys(newSchemas).length > 0) {
        setServiceSchemas(prev => ({ ...prev, ...newSchemas }));
      }
    };

    fetchMissingSchemas();
  }, [previousSteps, serviceSchemas]);

  // Enhance steps with fetched schemas and prompt variables
  const enhancedSteps = useMemo(() => {
    return previousSteps.map(step => {
      // Inject fetched prompt variable names into input_mappings so
      // getPromptVariableOutputs (called by getEffectiveOutputs) can discover them.
      let enhancedStep = step;
      if (step.input_mappings && Object.keys(promptVarCache).length > 0) {
        for (const mapping of Object.values(step.input_mappings)) {
          if (mapping.mappingType === 'prompt' && mapping.promptId) {
            const varNames = promptVarCache[mapping.promptId];
            if (varNames && varNames.length > 0) {
              // Ensure variableValues has entries for all prompt vars
              const existingVars = mapping.variableValues || {};
              const needsUpdate = varNames.some(name => !(name in existingVars));
              if (needsUpdate) {
                const mergedVars = { ...existingVars };
                for (const name of varNames) {
                  if (!(name in mergedVars)) {
                    mergedVars[name] = '';  // empty placeholder so discovery finds it
                  }
                }
                // Create a shallow clone of the step with updated variableValues
                const updatedMappings = { ...step.input_mappings };
                for (const [key, m] of Object.entries(updatedMappings)) {
                  if (m === mapping) {
                    updatedMappings[key] = { ...m, variableValues: mergedVars };
                  }
                }
                enhancedStep = { ...step, input_mappings: updatedMappings };
              }
            }
          }
        }
      }

      if (!enhancedStep.service_id || !serviceSchemas[enhancedStep.service_id]) {
        return enhancedStep;
      }

      // Deep merge: schema outputs provide the base, step outputs override but preserve nested 'items'
      const schemaOutputs = serviceSchemas[enhancedStep.service_id!];
      const stepOutputs = enhancedStep.outputs || {};
      const mergedOutputs: Record<string, any> = {};

      // Start with all schema outputs
      for (const [key, schemaField] of Object.entries(schemaOutputs)) {
        const stepField = stepOutputs[key] as Record<string, any> | undefined;
        if (stepField) {
          // Merge: step field takes precedence, but preserve 'items' from schema if step doesn't have it
          mergedOutputs[key] = {
            ...schemaField,
            ...stepField,
            // Preserve items from schema if step field doesn't have it (for nested array properties)
            ...(schemaField.items && !stepField.items ? { items: schemaField.items } : {})
          };
        } else {
          mergedOutputs[key] = schemaField;
        }
      }

      // Add any step outputs not in schema
      for (const [key, stepField] of Object.entries(stepOutputs)) {
        if (!mergedOutputs[key]) {
          mergedOutputs[key] = stepField;
        }
      }

      return {
        ...enhancedStep,
        outputs: mergedOutputs
      };
    });
  }, [previousSteps, serviceSchemas, promptVarCache]);

  // Count outputs by type for filter buttons (using enhanced steps)
  const typeCounts = useMemo(() => {
    const counts: Record<FilterType, number> = {
      string: 0,
      number: 0,
      boolean: 0,
      array: 0,
      object: 0
    };

    enhancedSteps.forEach(step => {
      Object.values(step.outputs || {}).forEach((fieldDef: any) => {
        const fieldType = fieldDef.type || 'string';
        if (fieldType === 'integer') {
          counts.number++;
        } else if (fieldType in counts) {
          counts[fieldType as FilterType]++;
        }
      });
    });

    return counts;
  }, [enhancedSteps]);

  // Count unmapped outputs (using enhanced steps)
  const unmappedCount = useMemo(() => {
    let count = 0;
    enhancedSteps.forEach(step => {
      Object.keys(step.outputs || {}).forEach(fieldName => {
        if (!isFieldMapped(step.id, fieldName, inputMappings)) {
          count++;
        }
      });
    });
    return count;
  }, [enhancedSteps, inputMappings]);

  const totalOutputs = enhancedSteps.reduce((count, step) => {
    return count + Object.keys(step.outputs || {}).length;
  }, 0);

  return {
    enhancedSteps,
    typeCounts,
    unmappedCount,
    totalOutputs,
  };
}
