// ui/app/workflows/components/hooks/useStepConfigData.ts

'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { Step } from '@/entities/workflow';
import { getProviders, getProviderServices, getProviderService, getPrompt } from '@/shared/api';
import { getStepTypeFieldRules } from '@/shared/types/stepTypeInfo';
import { SERVICES_WITH_CUSTOM_UI } from '@/entities/provider';
import { getInstanceFormFields } from '@/shared/lib/step-utils';
import { STORAGE_KEYS } from '@/shared/lib/constants';
import { STEP_CONFIG_DEFAULTS } from '@/shared/defaults';
import type { ParameterUiState, SectionConfig } from '../types';

// API responses are untyped end-to-end and downstream field renderers accept `any` -
// strict typing here would require typing the API surface first.
type AnyRecord = Record<string, any>;

interface UseStepConfigDataArgs {
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  allSteps?: Record<string, Step>;
}

// Reconciles diverged prompt variable state (drag-drop or seeded data) on load.
function reverseSyncTemplateVarMappings(mappings: AnyRecord): AnyRecord {
  const synced = { ...mappings };
  const ptKey = Object.keys(synced).find(
    k => synced[k]?.mappingType === 'prompt'
  );
  if (!ptKey) return synced;

  const ptMapping = { ...synced[ptKey] };
  const variableValues: Record<string, string> = { ...(ptMapping.variableValues || {}) };
  let changed = false;

  for (const [key, mapping] of Object.entries(synced)) {
    if (!key.startsWith('_prompt_variable:') || mapping?.mappingType !== 'mapped') continue;
    const varName = key.slice('_prompt_variable:'.length);
    const expr = `{{ ${mapping.stepId}.${mapping.outputField} }}`;
    if (variableValues[varName] !== expr) {
      variableValues[varName] = expr;
      changed = true;
    }
  }

  if (changed) {
    ptMapping.variableValues = variableValues;
    synced[ptKey] = ptMapping;
  }
  return synced;
}

export function useStepConfigData({ step, onUpdate, allSteps }: UseStepConfigDataArgs) {
  const [name, setName] = useState(step.name);
  const stepType = 'task';
  const [providerType, setProviderType] = useState<string>((step as AnyRecord).service_type || step.job?.service_type || '');
  const [providerId, setProviderId] = useState(step.provider_id || '');
  const [credentialId, setCredentialId] = useState(step.job?.credential_id || '');
  const [credentialProviderId, setCredentialProviderId] = useState(step.job?.credential_provider_id || '');
  const [serviceId, setServiceId] = useState(step.service_id || '');
  const [parameters, setParameters] = useState<AnyRecord>(step.job?.parameters || {});
  const [outputFields, setOutputFields] = useState<AnyRecord>(step.outputs || {});
  const [providerTypeWarning, setProviderTypeWarning] = useState<string | null>(null);
  const [inputMappings, setInputMappings] = useState<AnyRecord>(() => reverseSyncTemplateVarMappings(step.input_mappings || {}));
  const [services, setServices] = useState<AnyRecord[]>([]);
  const [servicesProviderId, setServicesProviderId] = useState<string>('');
  const [providers, setProviders] = useState<AnyRecord[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [paramSchema, setParamSchema] = useState<AnyRecord | null>(null);
  const [outputSchema, setOutputSchema] = useState<AnyRecord | null>(null);
  const [selectedSecretId, setSelectedSecretId] = useState<string | null>(step.config?.secret_id || null);
  const [serviceRequiresCredentials, setServiceRequiresCredentials] = useState<boolean | null>(null);
  const [serviceExampleParameters, setServiceExampleParameters] = useState<AnyRecord | null>(null);
  const [serviceMetadata, setServiceMetadata] = useState<AnyRecord | null>(null);

  // Guards against update loops when the user switches steps.
  const syncedStepIdRef = useRef<string | null>(null);

  const fieldRules = getStepTypeFieldRules(stepType);

  const [serviceParametersExpanded, setServiceParametersExpanded] = useState(STEP_CONFIG_DEFAULTS.serviceParametersExpanded);

  useEffect(() => {
    const savedState = localStorage.getItem(STORAGE_KEYS.SERVICE_PARAMETERS_EXPANDED);
    if (savedState !== null) {
      setServiceParametersExpanded(savedState !== 'false');
    }
  }, []);

  const [outputFieldsExpanded, setOutputFieldsExpanded] = useState(STEP_CONFIG_DEFAULTS.outputFieldsExpanded);
  const [outputViewMode, setOutputViewMode] = useState<'schema' | 'json'>(STEP_CONFIG_DEFAULTS.outputViewMode);

  const [promptVarNames, setPromptVarNames] = useState<string[]>([]);

  useEffect(() => {
    const promptId = (Object.values(inputMappings) as AnyRecord[]).find(
      (m) => m.mappingType === 'prompt' && m.promptId
    )?.promptId;
    if (!promptId) {
      setPromptVarNames([]);
      return;
    }
    let cancelled = false;
    getPrompt(promptId)
      .then(p => {
        if (!cancelled && p?.variables) {
          setPromptVarNames(p.variables.map((v: AnyRecord) => v.name));
        }
      })
      .catch((err: unknown) => {
        console.error('Failed to fetch prompt:', err);
      });
    return () => { cancelled = true; };
  }, [inputMappings]);

  // !cache[id] guard and length-0 return prevent re-fetch loops.
  const [allStepsPromptVarCache, setAllStepsPromptVarCache] = useState<Record<string, string[]>>({});

  useEffect(() => {
    if (!allSteps) return;
    const promptIdsToFetch: string[] = [];
    for (const s of Object.values(allSteps)) {
      if (!s.input_mappings) continue;
      for (const m of Object.values(s.input_mappings)) {
        const promptId = (m as AnyRecord).promptId;
        if ((m as AnyRecord).mappingType === 'prompt' && promptId && !allStepsPromptVarCache[promptId]) {
          promptIdsToFetch.push(promptId);
        }
      }
    }
    if (promptIdsToFetch.length === 0) return;

    let cancelled = false;
    Promise.all(
      [...new Set(promptIdsToFetch)].map(async (pid) => {
        try {
          const p = await getPrompt(pid);
          if (p?.variables) return [pid, p.variables.map((v: AnyRecord) => v.name)] as const;
        } catch (err: unknown) {
          console.error('Failed to fetch prompt for step cache:', err);
        }
        return null;
      })
    ).then(results => {
      if (cancelled) return;
      const newCache: Record<string, string[]> = {};
      for (const r of results) { if (r) newCache[r[0]] = r[1]; }
      if (Object.keys(newCache).length > 0) {
        setAllStepsPromptVarCache(prev => ({ ...prev, ...newCache }));
      }
    });
    return () => { cancelled = true; };
  }, [allSteps, allStepsPromptVarCache]);

  const instanceFormFields = useMemo(() => {
    if (!allSteps) return undefined;
    const stepsArray = Object.values(allSteps);
    const fields = getInstanceFormFields(stepsArray, allStepsPromptVarCache);
    return Object.keys(fields).length > 0 ? fields : undefined;
  }, [allSteps, allStepsPromptVarCache]);

  const [advancedParamsCollapsed, setAdvancedParamsCollapsed] = useState(STEP_CONFIG_DEFAULTS.advancedParamsCollapsed);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const [parameterUiState, setParameterUiState] = useState<ParameterUiState>(
    () => step.config?.parameter_ui_state || {}
  );

  useEffect(() => {
    const fetchProviders = async () => {
      setProvidersLoading(true);
      try {
        const allProviders = await getProviders();

        if (providerType) {
          const filteredProviders = allProviders.filter((provider: AnyRecord) =>
            provider.service_types?.some((type: string) => type.toUpperCase() === providerType.toUpperCase())
          );
          setProviders(filteredProviders);
        } else {
          const genericProviders = allProviders.filter((provider: AnyRecord) =>
            provider.name === 'Mock Service' ||
            provider.service_types?.includes('CUSTOM') ||
            provider.service_types?.includes('DATA_PROCESSING') ||
            provider.type === 'internal'
          );
          setProviders(genericProviders.length > 0 ? genericProviders : []);
        }
      } catch (err: unknown) {
        console.error('Failed to fetch providers:', err);
      } finally {
        setProvidersLoading(false);
      }
    };

    fetchProviders();
  }, [providerType]);

  useEffect(() => {
    const fetchServices = async () => {
      if (!providerId) {
        setServices([]);
        setServicesProviderId('');
        return;
      }

      setServicesLoading(true);
      try {
        const data = await getProviderServices(providerId);

        if (providerType) {
          const filteredServices = data.filter((service: AnyRecord) => {
            const categories: string[] = service.categories || [];
            return categories.includes(providerType.toLowerCase());
          });
          setServices(filteredServices);
        } else {
          setServices(data);
        }
        setServicesProviderId(providerId);
      } catch (err: unknown) {
        console.error('Failed to fetch services:', err);
        setServices([]);
        setServicesProviderId('');
      } finally {
        setServicesLoading(false);
      }
    };

    fetchServices();
  }, [providerId, providerType]);

  useEffect(() => {
    const fetchServiceDetails = async () => {
      if (!providerId || !serviceId) {
        setParamSchema(null);
        setOutputSchema(null);
        setServiceExampleParameters(null);
        return;
      }

      // Custom-UI services render their own form, so backend schema is irrelevant.
      if (SERVICES_WITH_CUSTOM_UI.has(serviceId)) {
        setParamSchema(null);
        setOutputSchema(null);
        setServiceExampleParameters(null);
        setLoading(false);
        return;
      }

      if (services.length === 0 || servicesProviderId !== providerId) {
        return;
      }

      const selectedService = services.find((s: AnyRecord) => s.service_id === serviceId);
      if (!selectedService?.id) {
        setParamSchema(null);
        setOutputSchema(null);
        return;
      }

      const requiresCreds = selectedService?.client_metadata?.requires_credentials;
      setServiceRequiresCredentials(requiresCreds !== undefined ? requiresCreds : true);

      try {
        const data = await getProviderService(selectedService.id);

        if (data) {
          setParamSchema(data.parameter_schema || null);
          setOutputSchema(data.result_schema || null);
          const metadata = data.client_metadata || null;
          setServiceMetadata(metadata);
          // Service no longer supports iteration - purge any stale iteration_config.
          if (metadata?.iterable === false && step.iteration_config?.enabled) {
            onUpdate({ ...step, iteration_config: undefined });
          }
          setServiceExampleParameters(data.example_parameters || null);

          const uiHints = data.client_metadata?.ui_hints || {};
          const sections = uiHints.sections || {};
          const paramProps = data.parameter_schema?.properties || {};
          const currentParams = step.job?.parameters || {};

          const sectionsWithData = new Set<string>();
          Object.entries(paramProps).forEach(([paramKey, paramConfig]) => {
            const config = paramConfig as AnyRecord;
            const section = config.ui?.section || 'basic';
            const value = currentParams[paramKey];
            const defaultValue = config.default;

            const hasValue = value !== undefined && value !== null && value !== '';
            const isDifferentFromDefault = hasValue && JSON.stringify(value) !== JSON.stringify(defaultValue);

            if (hasValue && (defaultValue === undefined || isDifferentFromDefault)) {
              sectionsWithData.add(section);
            }
          });

          const initialCollapsed: Record<string, boolean> = {};
          Object.entries(sections).forEach(([sectionName, config]) => {
            const sectionConfig = config as SectionConfig;
            if (sectionConfig.collapsed !== undefined) {
              if (sectionsWithData.has(sectionName)) {
                initialCollapsed[sectionName] = false;
              } else {
                initialCollapsed[sectionName] = sectionConfig.collapsed;
              }
            }
          });
          setParameterUiState(prev => {
            const prevCollapsed = prev.collapsedSections || {};
            const merged = { ...initialCollapsed, ...prevCollapsed };
            sectionsWithData.forEach(sectionName => {
              merged[sectionName] = false;
            });
            return { ...prev, collapsedSections: merged };
          });

          if (data.result_schema?.properties) {
            const schemaOutputs: AnyRecord = {};

            Object.entries(data.result_schema.properties).forEach(([key, schema]) => {
              const propSchema = schema as { type?: string; description?: string; items?: AnyRecord };
              schemaOutputs[key] = {
                path: key,
                description: propSchema.description || `${key} field`,
                type: propSchema.type || 'string',
                ...(propSchema.items ? { items: propSchema.items } : {})
              };
            });

            if (Object.keys(schemaOutputs).length > 0) {
              setOutputFields((prev: AnyRecord) => ({
                ...schemaOutputs,
                ...prev
              }));
            }
          }
        } else {
          setParamSchema(null);
          setOutputSchema(null);
          setServiceExampleParameters(null);
        }
      } catch (err: unknown) {
        console.error('Failed to fetch service details:', err);
        setParamSchema(null);
        setOutputSchema(null);
        setServiceExampleParameters(null);
      }

      setLoading(false);
    };

    fetchServiceDetails();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- step.job.parameters excluded to prevent loop
  }, [providerId, serviceId, services, servicesProviderId]);

  // Materialize schema defaults - untouched fields won't get saved unless written to state.
  useEffect(() => {
    if (!paramSchema?.properties) return;

    const props = paramSchema.properties as Record<string, AnyRecord>;
    const defaults: AnyRecord = {};

    for (const [key, schema] of Object.entries(props)) {
      if (schema.default !== undefined && parameters[key] === undefined) {
        defaults[key] = schema.default;
      }
    }

    if (Object.keys(defaults).length > 0) {
      setParameters(prev => ({ ...defaults, ...prev }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- parameters excluded to prevent infinite loop
  }, [paramSchema]);

  // Reset local state when the user switches steps. Keyed on step.id only to avoid update loops.
  useEffect(() => {
    setName(step.name);
    setProviderType((step as AnyRecord).service_type || step.job?.service_type || '');
    setProviderId(step.provider_id || '');
    setCredentialId(step.job?.credential_id || '');
    setCredentialProviderId(step.job?.credential_provider_id || '');
    setServiceId(step.service_id || '');
    setParameters(step.job?.parameters || {});
    setOutputFields(step.outputs || {});
    setInputMappings(reverseSyncTemplateVarMappings(step.input_mappings || {}));
    setParameterUiState(step.config?.parameter_ui_state || {});

    // Set loading only when provider actually changed, otherwise the services
    // fetch effect's deps [providerId, providerType] won't fire and the spinner
    // gets stuck (e.g., on a pure rename of the step).
    const incomingProviderId = step.provider_id || '';
    if (incomingProviderId && incomingProviderId !== providerId) {
      setServicesLoading(true);
    }

    // Do NOT update syncedStepIdRef here. The onUpdate effect runs in the same
    // render cycle and would see the bumped ref with STALE local state (setState
    // is queued). The ref is bumped on the next render via the skip path below.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally step.id only
  }, [step.id]);

  useEffect(() => {
    if (syncedStepIdRef.current !== step.id) {
      // Step just switched - bump ref so the next render proceeds with fresh state.
      syncedStepIdRef.current = step.id;
      return;
    }

    const outputsMatch = JSON.stringify(step.outputs || {}) === JSON.stringify(outputFields);
    const uiStateMatch = JSON.stringify(step.config?.parameter_ui_state || {}) === JSON.stringify(parameterUiState);
    const inputMappingsMatch = JSON.stringify(step.input_mappings || {}) === JSON.stringify(inputMappings);

    if (step.name === name &&
        ((step as AnyRecord).service_type || step.job?.service_type || '') === providerType &&
        (step.provider_id || '') === providerId &&
        (step.job?.credential_id || '') === credentialId &&
        (step.job?.credential_provider_id || '') === credentialProviderId &&
        (step.service_id || '') === serviceId &&
        (step.config?.secret_id || null) === selectedSecretId &&
        JSON.stringify(step.job?.parameters || {}) === JSON.stringify(parameters) &&
        outputsMatch &&
        uiStateMatch &&
        inputMappingsMatch) {
      return;
    }
    onUpdate({
      ...step,
      name,
      type: stepType as Step['type'],
      provider_id: providerId,
      service_id: serviceId,
      parameters,
      outputs: outputFields,
      input_mappings: inputMappings,
      config: {
        ...step.config,
        secret_id: selectedSecretId,
        parameter_ui_state: parameterUiState,
      },
      job: {
        ...step.job,
        service_type: providerType,
        provider_id: providerId,
        credential_id: credentialId,
        credential_provider_id: credentialProviderId || undefined,
        service_id: serviceId,
        parameters,
        timeout_seconds: step.job?.timeout_seconds || 30,
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onUpdate/step excluded to prevent infinite loop
  }, [name, providerId, credentialId, credentialProviderId, serviceId, selectedSecretId, parameters, outputFields, inputMappings, providerType, parameterUiState]);

  return {
    name, setName,
    stepType,
    providerType, setProviderType,
    providerId, setProviderId,
    credentialId, setCredentialId,
    credentialProviderId, setCredentialProviderId,
    serviceId, setServiceId,
    parameters, setParameters,
    outputFields, setOutputFields,
    providerTypeWarning, setProviderTypeWarning,
    inputMappings, setInputMappings,
    services,
    servicesLoading,
    providers,
    providersLoading,
    loading,
    paramSchema,
    outputSchema,
    selectedSecretId, setSelectedSecretId,
    serviceRequiresCredentials, setServiceRequiresCredentials,
    serviceExampleParameters,
    serviceMetadata,
    fieldRules,
    serviceParametersExpanded, setServiceParametersExpanded,
    outputFieldsExpanded, setOutputFieldsExpanded,
    outputViewMode, setOutputViewMode,
    promptVarNames,
    instanceFormFields,
    advancedParamsCollapsed, setAdvancedParamsCollapsed,
    collapsedGroups, setCollapsedGroups,
    parameterUiState, setParameterUiState,
  };
}
