// ui/app/workflows/components/hooks/useEnhancedSteps.ts

'use client';

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Step } from '@/entities/workflow';
import { getProviderService, getPrompt } from '@/shared/api';
import type { ParamConfig, SectionConfig, ParameterUiState } from '../types';

// Same loose record type used by the parent component and APIs
type AnyRecord = Record<string, any>;

interface UseEnhancedStepsArgs {
  previousSteps: Step[];
  paramSchema: AnyRecord | null;
  serviceMetadata: AnyRecord | null;
  parameters: AnyRecord;
  parameterUiState: ParameterUiState;
  setParameterUiState: (updater: ParameterUiState | ((prev: ParameterUiState) => ParameterUiState)) => void;
  collapsedGroups: Record<string, boolean>;
  setCollapsedGroups: (updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => void;
}

export function useEnhancedSteps({
  previousSteps,
  paramSchema,
  serviceMetadata,
  parameters,
  parameterUiState,
  setParameterUiState,
  collapsedGroups,
  setCollapsedGroups,
}: UseEnhancedStepsArgs) {
  // Refs avoid feedback loops; bumping cacheVersion forces a re-render when they update.
  const prevStepSchemasRef = useRef<Record<string, AnyRecord>>({});
  const prevStepPromptVarsRef = useRef<Record<string, string[]>>({});
  const [, setCacheVersion] = useState(0);

  useEffect(() => {
    const idsToFetch: string[] = [];
    previousSteps.forEach(s => {
      if (!s.input_mappings) return;
      for (const m of Object.values(s.input_mappings)) {
        if ((m as AnyRecord).mappingType === 'prompt' && (m as AnyRecord).promptId) {
          const pid = (m as AnyRecord).promptId;
          if (!prevStepPromptVarsRef.current[pid]) idsToFetch.push(pid);
        }
      }
    });
    if (idsToFetch.length === 0) return;
    const fetchAll = async () => {
      const newCache: Record<string, string[]> = {};
      await Promise.all([...new Set(idsToFetch)].map(async pid => {
        try {
          const prompt = await getPrompt(pid);
          if (prompt?.variables) newCache[pid] = prompt.variables.map((v: AnyRecord) => v.name);
        } catch (err: unknown) {
          console.error('Failed to fetch prompt variables for previous step:', err);
        }
      }));
      if (Object.keys(newCache).length > 0) {
        prevStepPromptVarsRef.current = { ...prevStepPromptVarsRef.current, ...newCache };
        setCacheVersion(v => v + 1);
      }
    };
    fetchAll();
  }, [previousSteps]);

  useEffect(() => {
    const fetchMissingSchemas = async () => {
      const servicesToFetch: string[] = [];

      previousSteps.forEach(step => {
        if (step.service_id && !prevStepSchemasRef.current[step.service_id]) {
          servicesToFetch.push(step.service_id);
        }
      });

      if (servicesToFetch.length === 0) return;

      const newSchemas: Record<string, AnyRecord> = {};

      await Promise.all(
        servicesToFetch.map(async (serviceId) => {
          try {
            const data = await getProviderService(serviceId);
            if (data?.result_schema?.properties) {
              const outputs: AnyRecord = {};
              for (const [key, schema] of Object.entries(data.result_schema.properties)) {
                const propSchema = schema as { type?: string; description?: string; items?: AnyRecord };
                outputs[key] = {
                  path: key,
                  description: propSchema.description || `${key} field`,
                  type: propSchema.type || 'string',
                  ...(propSchema.items ? { items: propSchema.items } : {})
                };
              }
              newSchemas[serviceId] = outputs;
            }
          } catch (err: unknown) {
            console.error('Failed to fetch schema for previous step service:', err);
          }
        })
      );

      if (Object.keys(newSchemas).length > 0) {
        prevStepSchemasRef.current = { ...prevStepSchemasRef.current, ...newSchemas };
        setCacheVersion(v => v + 1);
      }
    };

    fetchMissingSchemas();
  }, [previousSteps]);

  /* eslint-disable react-hooks/refs -- refs intentionally read in useMemo; cacheVersion forces re-render */
  const enhancedPreviousSteps = useMemo(() => {
    const prevStepSchemas = prevStepSchemasRef.current;
    const prevStepPromptVars = prevStepPromptVarsRef.current;

    return previousSteps.map(step => {
      let enhanced = step;

      // Inject fetched prompt variable names into variableValues so they appear in effective outputs.
      if (step.input_mappings && Object.keys(prevStepPromptVars).length > 0) {
        for (const mapping of Object.values(step.input_mappings)) {
          const m = mapping as AnyRecord;
          if (m.mappingType === 'prompt' && m.promptId) {
            const varNames = prevStepPromptVars[m.promptId];
            if (varNames && varNames.length > 0) {
              const existing = m.variableValues || {};
              if (varNames.some((n: string) => !(n in existing))) {
                const merged = { ...existing };
                for (const n of varNames) {
                  if (!(n in merged)) merged[n] = '';
                }
                const updatedMappings = { ...step.input_mappings };
                for (const [key, val] of Object.entries(updatedMappings)) {
                  if (val === mapping) updatedMappings[key] = { ...m, variableValues: merged };
                }
                enhanced = { ...step, input_mappings: updatedMappings };
              }
            }
          }
        }
      }

      if (enhanced.service_id && prevStepSchemas[enhanced.service_id]) {
        const schemaOutputs = prevStepSchemas[enhanced.service_id];
        const stepOutputs = enhanced.outputs || {};
        const mergedOutputs: AnyRecord = {};

        for (const [key, schemaField] of Object.entries(schemaOutputs)) {
          const stepField = stepOutputs[key];
          const schemaFieldAny = schemaField as AnyRecord;
          const stepFieldAny = stepField as AnyRecord | undefined;
          if (stepFieldAny) {
            mergedOutputs[key] = {
              ...schemaFieldAny,
              ...stepFieldAny,
              ...(schemaFieldAny.items && !stepFieldAny.items ? { items: schemaFieldAny.items } : {})
            };
          } else {
            mergedOutputs[key] = schemaFieldAny;
          }
        }

        for (const [key, stepField] of Object.entries(stepOutputs)) {
          if (!mergedOutputs[key]) mergedOutputs[key] = stepField;
        }

        enhanced = { ...enhanced, outputs: mergedOutputs };
      }

      return enhanced;
    });
  }, [previousSteps]);
  /* eslint-enable react-hooks/refs */

  const collapsedSections = useMemo(
    () => parameterUiState.collapsedSections || {},
    [parameterUiState.collapsedSections]
  );
  const setCollapsedSections = (updater: (prev: Record<string, boolean>) => Record<string, boolean>) => {
    setParameterUiState((prev: ParameterUiState) => ({
      ...prev,
      collapsedSections: updater(prev.collapsedSections || {})
    }));
  };

  const sectionConfigs: Record<string, SectionConfig> = useMemo(() => {
    return serviceMetadata?.ui_hints?.sections || {};
  }, [serviceMetadata]);

  const passesShowWhenConditions = useCallback((config: ParamConfig): boolean => {
    if (!config.ui?.show_when) return true;

    for (const [field, expectedValue] of Object.entries(config.ui.show_when)) {
      const actualValue = parameters[field];
      if (Array.isArray(expectedValue)) {
        if (!expectedValue.includes(actualValue)) {
          return false;
        }
      } else if (actualValue !== expectedValue) {
        return false;
      }
    }
    return true;
  }, [parameters]);

  const isSectionCollapsed = useCallback((sectionName: string): boolean => {
    if (sectionName === 'basic' || sectionName === 'default') return false;
    const sectionConfig = sectionConfigs[sectionName];
    return collapsedSections[sectionName] ?? (sectionConfig?.collapsed ?? false);
  }, [collapsedSections, sectionConfigs]);

  const isParamVisible = useCallback((config: ParamConfig): boolean => {
    const section = config.ui?.section || 'basic';
    if (isSectionCollapsed(section)) {
      return false;
    }
    return passesShowWhenConditions(config);
  }, [isSectionCollapsed, passesShowWhenConditions]);

  const sectionedParams = useMemo(() => {
    if (!paramSchema?.properties || Object.keys(paramSchema.properties).length === 0) {
      return {};
    }

    const sections: Record<string, { key: string; config: ParamConfig }[]> = {};

    const sortedEntries = Object.entries(paramSchema.properties).sort((a, b) => {
      const orderA = (a[1] as ParamConfig)?.ui?.order ?? 999;
      const orderB = (b[1] as ParamConfig)?.ui?.order ?? 999;
      return orderA - orderB;
    });

    for (const [paramKey, paramConfig] of sortedEntries) {
      const config = paramConfig as ParamConfig;
      const section = config.ui?.section || 'basic';
      if (config.ui?.hidden) continue;
      const rawSchema = paramConfig as Record<string, any>;
      if (rawSchema['x-ui-hints']?.format === 'credential_field') continue;
      if (!sections[section]) {
        sections[section] = [];
      }
      sections[section].push({ key: paramKey, config });
    }

    return sections;
  }, [paramSchema]);

  const sortedSectionNames = useMemo(() => {
    const names = Object.keys(sectionedParams);
    return names.sort((a, b) => {
      const orderA = sectionConfigs[a]?.order ?? 999;
      const orderB = sectionConfigs[b]?.order ?? 999;
      return orderA - orderB;
    });
  }, [sectionedParams, sectionConfigs]);

  const hasAdvancedParams = sortedSectionNames.some(name => name !== 'basic' && name !== 'default');

  const toggleSection = (sectionName: string) => {
    const currentlyCollapsed = isSectionCollapsed(sectionName);
    setCollapsedSections(prev => ({
      ...prev,
      [sectionName]: !currentlyCollapsed
    }));
  };

  const isGroupCollapsed = useCallback((sectionName: string, groupName: string): boolean => {
    const groupKey = `${sectionName}:${groupName}`;
    return collapsedGroups[groupKey] ?? (groupName === 'advanced');
  }, [collapsedGroups]);

  const toggleGroup = (groupKey: string) => {
    setCollapsedGroups((prev: Record<string, boolean>) => ({
      ...prev,
      [groupKey]: !prev[groupKey]
    }));
  };

  const sectionHasNonDefaultValues = useCallback((params: { key: string; config: ParamConfig }[]): boolean => {
    return params.some(({ key, config }) => {
      const value = parameters[key];
      const defaultVal = config.default;

      if (!passesShowWhenConditions(config)) return false;
      if (value === undefined && defaultVal === undefined) return false;
      if (value !== undefined && value !== defaultVal) {
        if (value === '' && (defaultVal === undefined || defaultVal === null)) return false;
        return true;
      }
      return false;
    });
  }, [parameters, passesShowWhenConditions]);

  const groupedParams = useMemo(() => {
    return {
      basic: sectionedParams['basic'] || [],
      advanced: {} as Record<string, { key: string; config: ParamConfig }[]>
    };
  }, [sectionedParams]);

  return {
    enhancedPreviousSteps,
    sectionConfigs,
    passesShowWhenConditions,
    isSectionCollapsed,
    isParamVisible,
    sectionedParams,
    sortedSectionNames,
    hasAdvancedParams,
    toggleSection,
    isGroupCollapsed,
    toggleGroup,
    sectionHasNonDefaultValues,
    groupedParams,
  };
}
