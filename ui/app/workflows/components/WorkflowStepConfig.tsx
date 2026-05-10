// ui/app/workflows/components/WorkflowStepConfig.tsx

'use client';

import React, { useCallback, useState } from 'react';
import { Step } from '@/entities/workflow';
import { AlertTriangle, ChevronDown, ChevronRight, HelpCircle } from 'lucide-react';
import HttpHeadersEditor from '@/features/step-config/HttpHeadersEditor';
import { MappableParameterField } from '@/features/step-config/MappableParameterField';
import type { PropertySchema } from '@/features/step-config/MappableParameterField/types';
import { MappingSummary } from '@/features/step-config/sections/MappingSummary';
import { OutputForwardingSection } from '@/features/step-config/sections/OutputForwardingSection';
import {
  SERVICE_TYPES,
  SERVICE_TYPE_LABELS,
  CORE_SERVICES,
  SERVICES_WITHOUT_CREDENTIALS,
  SERVICES_WITH_CROSS_PROVIDER_CREDENTIALS,
  SERVICES_WITH_CUSTOM_OUTPUT,
  SERVICE_PARAMETER_TITLES,
} from '@/entities/provider';
import { CredentialSelector } from '@/features/providers';
import SetFieldsEditor from '@/features/step-config/sections/SetFieldsEditor';
import WebhookWaitEditor from '@/features/step-config/sections/WebhookWaitEditor';
import { createStepId } from '@/shared/lib/step-utils';
import { TIMEOUTS, STORAGE_KEYS } from '@/shared/lib/constants';
import {
  useStepConfigData,
  useEnhancedSteps,
} from './hooks';
import type { ParamConfig } from './hooks';
import { IterationToggle } from './IterationToggle';
import { OutputSchemaDisplay } from './OutputSchemaDisplay';
import { ProviderDocsSlideOver } from '@/features/provider-docs/ProviderDocsSlideOver';

interface WorkflowStepConfigProps {
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  previousSteps: Step[];
  allSteps?: Record<string, Step>;  // All steps for dependency management
  onDuplicate?: () => void;
  workflowId?: string; // Workflow ID for webhook token operations
  /** Called when the step ID needs to change (e.g., when service is first selected) */
  onStepIdChange?: (oldId: string, newId: string, serviceId?: string) => void;
}

export function WorkflowStepConfig({
  step,
  onUpdate,
  onRemove,
  previousSteps,
  allSteps,
  onDuplicate,
  workflowId,
  onStepIdChange,
}: WorkflowStepConfigProps) {
  // ── Data fetching & state management ──────────────────────────
  const data = useStepConfigData({ step, onUpdate, allSteps });
  const {
    name, setName,
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
    paramSchema,
    outputSchema,
    serviceRequiresCredentials, setServiceRequiresCredentials,
    serviceExampleParameters,
    serviceMetadata,
    fieldRules,
    serviceParametersExpanded, setServiceParametersExpanded,
    outputFieldsExpanded, setOutputFieldsExpanded,
    outputViewMode, setOutputViewMode,
    promptVarNames,
    instanceFormFields,
    collapsedGroups, setCollapsedGroups,
    parameterUiState, setParameterUiState,
  } = data;

  // ── Provider docs slide-over ────────────────────────────────
  const [isDocsOpen, setIsDocsOpen] = useState(false);
  const [docsSlug, setDocsSlug] = useState<string | null>(null);

  // ── Enhanced steps & param sectioning ─────────────────────────
  const enhanced = useEnhancedSteps({
    previousSteps,
    paramSchema,
    serviceMetadata,
    parameters,
    parameterUiState,
    setParameterUiState,
    collapsedGroups,
    setCollapsedGroups,
  });
  const {
    enhancedPreviousSteps,
    sectionConfigs,
    passesShowWhenConditions,
    isSectionCollapsed,
    isParamVisible,
    sectionedParams,
    sortedSectionNames,
    toggleSection,
    isGroupCollapsed,
    toggleGroup,
    sectionHasNonDefaultValues,
  } = enhanced;

  // Modal states removed - no trigger exists in this component to open them.

  // ── Change handlers ───────────────────────────────────────────
  const handleProviderTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newProviderType = e.target.value;
    if (providerId) {
      const currentProvider = providers.find((p: Record<string, any>) => p.id === providerId);      if (currentProvider && !currentProvider.service_types?.includes(newProviderType)) {
        setProviderId('');
        setServiceId('');
        setParameters({});
        setOutputFields({});
        setInputMappings({});
      }
    }
    setProviderTypeWarning(null);
    setProviderType(newProviderType);
  };

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setProviderId(e.target.value);
    setServiceId('');
    setParameters({});
    setOutputFields({});
    setInputMappings({});
    setProviderTypeWarning(null);
  };

  const handleServiceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newServiceId = e.target.value;
    setServiceId(newServiceId);

    if (newServiceId) {
      const selectedService = services.find((s: Record<string, any>) => s.service_id === newServiceId);
      const requiresCreds = selectedService?.client_metadata?.requires_credentials;
      setServiceRequiresCredentials(requiresCreds !== undefined ? requiresCreds : true);
    } else {
      setServiceRequiresCredentials(null);
    }

    setParameters({});
    setOutputFields({});
    setInputMappings({});

    if (newServiceId && !step.service_id && onStepIdChange) {
      const hasNoIncomingConnections = !step.depends_on || step.depends_on.length === 0;
      if (hasNoIncomingConnections) {
        onStepIdChange(step.id, createStepId(newServiceId), newServiceId);
      }
    }
  };

  const handleParameterChange = (key: string, value: any) => {    setParameters({ ...parameters, [key]: value });
  };

  const handleParameterMappingChange = (key: string, mapping: any | null) => {    if (mapping === null) {
      const newMappings = { ...inputMappings };
      delete newMappings[key];
      setInputMappings(newMappings);
    } else {
      const newMappings = { ...inputMappings, [key]: mapping };

      // Auto-sync _prompt_variable: entries for prompt mappings
      if (mapping.mappingType === 'prompt' && mapping.variableValues) {
        const exprRegex = /^\{\{\s*(\w+)\.(.+?)\s*\}\}$/;
        for (const [varName, value] of Object.entries(mapping.variableValues as Record<string, string>)) {
          const tplKey = `_prompt_variable:${varName}`;
          if (typeof value === 'string') {
            const match = value.match(exprRegex);
            if (match) {
              newMappings[tplKey] = { mappingType: 'mapped', stepId: match[1], outputField: match[2] };
            } else {
              delete newMappings[tplKey];
            }
          }
        }
      }
      setInputMappings(newMappings);
    }
  };

  const handleReorderMappings = (paramKey: string, fromIndex: number, toIndex: number) => {
    const fromPrefix = `${paramKey}[${fromIndex}]`;
    const toPrefix = `${paramKey}[${toIndex}]`;
    const newMappings: Record<string, any> = {};    for (const [key, value] of Object.entries(inputMappings)) {
      if (key.startsWith(fromPrefix + '.') || key === fromPrefix) {
        newMappings[toPrefix + key.slice(fromPrefix.length)] = value;
      } else if (key.startsWith(toPrefix + '.') || key === toPrefix) {
        newMappings[fromPrefix + key.slice(toPrefix.length)] = value;
      } else {
        newMappings[key] = value;
      }
    }
    setInputMappings(newMappings);
  };

  const handleRemoveItemMappings = (paramKey: string, removedIndex: number, arrayLength: number) => {
    const newMappings: Record<string, any> = {};    const removedPrefix = `${paramKey}[${removedIndex}]`;
    for (const [key, value] of Object.entries(inputMappings)) {
      if (key.startsWith(removedPrefix + '.') || key === removedPrefix) continue;
      let newKey = key;
      for (let i = removedIndex + 1; i <= arrayLength; i++) {
        const oldPrefix = `${paramKey}[${i}]`;
        if (key.startsWith(oldPrefix + '.') || key === oldPrefix) {
          newKey = `${paramKey}[${i - 1}]` + key.slice(oldPrefix.length);
          break;
        }
      }
      newMappings[newKey] = value;
    }
    setInputMappings(newMappings);
  };

  const scrollToParameterField = useCallback((paramKey: string) => {
    const scrollAndHighlight = () => {
      const element = document.getElementById(`param-field-${paramKey}`);
      if (element) {
        const scrollContainer = element.closest('.overflow-y-auto');
        if (scrollContainer) {
          scrollContainer.scrollTo({ top: 0, behavior: 'auto' });
          requestAnimationFrame(() => {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            element.classList.add('ring-2', 'ring-orange-500');
            setTimeout(() => element.classList.remove('ring-2', 'ring-orange-500'), TIMEOUTS.HIGHLIGHT_RING);
          });
        } else {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          element.classList.add('ring-2', 'ring-orange-500');
          setTimeout(() => element.classList.remove('ring-2', 'ring-orange-500'), TIMEOUTS.HIGHLIGHT_RING);
        }
      }
    };
    if (!serviceParametersExpanded) {
      setServiceParametersExpanded(true);
      localStorage.setItem(STORAGE_KEYS.SERVICE_PARAMETERS_EXPANDED, 'true');
      setTimeout(scrollAndHighlight, TIMEOUTS.LAYOUT_SETTLE);
    } else {
      scrollAndHighlight();
    }
  }, [serviceParametersExpanded, setServiceParametersExpanded]);

  // ── Param field render helpers ────────────────────────────────
  const renderParamField = (key: string, config: ParamConfig) => {
    if (!isParamVisible(config)) return null;
    if (config.ui?.inlineWith) return null;

    // Find inline children that should render within this field's container
    const inlineChildren = Object.entries(paramSchema!.properties)
      .filter(([, childConfig]) => {
        const childUi = (childConfig as ParamConfig).ui;
        if (childUi?.inlineWith !== key) return false;
        if (childUi?.visibleWhen) {
          const { field, condition, value: condValue } = childUi.visibleWhen;
          const fieldValue = parameters[field];
          switch (condition) {
            case 'lengthGreaterThan': return Array.isArray(fieldValue) && fieldValue.length > (condValue ?? 0);
            case 'equals': return fieldValue === condValue;
            case 'notEquals': return fieldValue !== condValue;
            case 'notEmpty': return Array.isArray(fieldValue) ? fieldValue.length > 0 : !!fieldValue;
            default: return true;
          }
        }
        return true;
      })
      .map(([childKey, childConfig]) => ({ key: childKey, config: childConfig as ParamConfig }));

    // Special handling for 'headers' field - keep the custom editor
    if (key === 'headers') {
      const label = config.title || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return (
        <div key={key} id={`param-field-${key}`} className="p-3 bg-info-subtle border border-info rounded-md transition-all">
          <p className="block text-sm font-medium text-secondary mb-1">{label}</p>
          <HttpHeadersEditor headers={parameters[key] || {}} onChange={(headers) => handleParameterChange(key, headers)} />
        </div>
      );
    }

    const exampleValue = config.dynamicOptions ? serviceExampleParameters?.[key] : undefined;

    return (
      <div key={key} id={`param-field-${key}`} className="p-3 bg-info-subtle border border-info rounded-md transition-all">
        <MappableParameterField
          paramKey={key}
          schema={config as unknown as PropertySchema}          value={parameters[key]}
          mapping={inputMappings[key]}
          previousSteps={enhancedPreviousSteps}
          required={paramSchema?.required?.includes(key)}
          onValueChange={handleParameterChange}
          onMappingChange={handleParameterMappingChange}
          uiState={parameterUiState}
          onUiStateChange={setParameterUiState}
          iterationConfig={step.iteration_config}
          onIterationChange={(iterConfig) => onUpdate({ ...step, iteration_config: iterConfig })}
          providerId={providerId}
          credentialId={credentialId}
          allFieldValues={parameters}
          exampleValue={exampleValue}
          allInputMappings={inputMappings}
          onReorderMappings={handleReorderMappings}
          onRemoveItemMappings={handleRemoveItemMappings}
          instanceFormFields={instanceFormFields}
          currentStepId={step.id}
        />
        {inlineChildren.map(({ key: childKey, config: childConfig }) => {
          const childLabel = childConfig.title || childKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
          const hint = childConfig.ui?.hint;
          if (childConfig.enum && childConfig.enum.length > 0) {
            return (
              <div key={childKey} className="mt-3 pt-3 border-t border-info">
                <label htmlFor={`param-${childKey}`} className="block text-sm text-secondary mb-1">
                  {childLabel}
                  {hint && <HintIcon hint={hint} />}
                </label>
                <select id={`param-${childKey}`} value={parameters[childKey] ?? childConfig.default ?? ''} onChange={(e) => handleParameterChange(childKey, e.target.value)} className="w-full p-2 border rounded bg-card border-primary text-sm">
                  {childConfig.enum!.map((enumValue, index) => (
                    <option key={String(enumValue)} value={String(enumValue)}>{childConfig.enumNames?.[index] ?? String(enumValue)}</option>
                  ))}
                </select>
              </div>
            );
          }
          if (childConfig.type === 'boolean') {
            return (
              <div key={childKey} className="mt-3 pt-3 border-t border-info">
                <label className="inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={parameters[childKey] ?? childConfig.default ?? false} onChange={(e) => handleParameterChange(childKey, e.target.checked)} className="h-4 w-4 text-info border-primary rounded focus:ring-blue-500" />
                  <span className="ml-2 text-sm text-secondary">{childLabel}</span>
                  {hint && <HintIcon hint={hint} />}
                </label>
              </div>
            );
          }
          return null;
        })}
      </div>
    );
  };

  const renderGroup = (sectionName: string, groupName: string, groupParams: { key: string; config: ParamConfig }[]) => {
    const groupKey = `${sectionName}:${groupName}`;
    const visibleParams = groupParams.filter(({ config }) => passesShowWhenConditions(config));
    if (visibleParams.length === 0) return null;
    return (
      <div key={groupKey} className="mt-4">
        <button type="button" onClick={() => toggleGroup(groupKey)} className="w-full group-header-warning -mx-3">
          <span className="text-xs font-semibold text-warning uppercase tracking-wide">{groupName.toUpperCase()}</span>
          <span className="text-xs text-warning hover:text-warning">{isGroupCollapsed(sectionName, groupName) ? 'Show' : 'Hide'}</span>
        </button>
        {!isGroupCollapsed(sectionName, groupName) && (
          <div className="space-y-4 mt-3">{visibleParams.map(({ key, config }) => renderParamField(key, config))}</div>
        )}
      </div>
    );
  };

  const renderSection = (sectionName: string, params: { key: string; config: ParamConfig }[]) => {
    const sectionConfig = sectionConfigs[sectionName];
    const isCollapsed = isSectionCollapsed(sectionName);
    const ungroupedParams = params.filter(({ config }) => !config.ui?.group);
    const grouped = params.filter(({ config }) => config.ui?.group);
    const groups: string[] = [];
    grouped.forEach(({ config }) => { const g = config.ui?.group; if (g && !groups.includes(g)) groups.push(g); });

    if (sectionName === 'basic' || sectionName === 'default') {
      const visibleUngrouped = ungroupedParams.filter(({ config }) => passesShowWhenConditions(config));
      const hasContent = visibleUngrouped.length > 0 || groups.some(g => grouped.filter(({ config }) => config.ui?.group === g && passesShowWhenConditions(config)).length > 0);
      if (!hasContent) return null;
      return (
        <div key={sectionName} className="space-y-4">
          {visibleUngrouped.map(({ key, config }) => renderParamField(key, config))}
          {groups.map(g => renderGroup(sectionName, g, grouped.filter(({ config }) => config.ui?.group === g)))}
        </div>
      );
    }

    const potentiallyVisible = params.filter(({ config }) => passesShowWhenConditions(config));
    if (potentiallyVisible.length === 0) return null;
    const hasCustomValues = isCollapsed && sectionHasNonDefaultValues(potentiallyVisible);

    return (
      <div key={sectionName} className="border border-primary rounded-md overflow-hidden">
        <button type="button" onClick={() => toggleSection(sectionName)} className="w-full flex items-center justify-between px-4 py-3 text-left bg-surface hover:bg-card">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-secondary">{sectionConfig?.title || sectionName}</span>
            {hasCustomValues && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-info-subtle text-info" title="This section has customized values">Modified</span>}
            {sectionConfig?.description && <span className="text-xs text-secondary">{sectionConfig.description}</span>}
          </div>
          {isCollapsed ? <ChevronRight className="h-5 w-5 text-secondary flex-shrink-0" /> : <ChevronDown className="h-5 w-5 text-secondary flex-shrink-0" />}
        </button>
        {!isCollapsed && (
          <div className="p-4 space-y-4">
            {ungroupedParams.filter(({ config }) => passesShowWhenConditions(config)).map(({ key, config }) => renderParamField(key, config))}
            {groups.map(g => renderGroup(sectionName, g, grouped.filter(({ config }) => config.ui?.group === g)))}
          </div>
        )}
      </div>
    );
  };

  // ── JSX ───────────────────────────────────────────────────────
  return (
    <div>
      <div className="bg-card shadow-sm rounded-lg border p-6">
        <div className="space-y-6">
          <div>
          {/* Step Configuration Section */}
          <div className="mb-6">
            <div className="bg-input shadow-sm rounded-t-lg p-3 border border-primary">
              <h2 className="text-lg font-semibold text-primary">Step Configuration</h2>
            </div>
            <div className="@container bg-card shadow-sm rounded-b-lg p-4 border border-t-0 border-primary">
              <div className="space-y-4">
                {/* Step Name and Execution Mode Row */}
                <div className="flex flex-col @sm:flex-row gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <label htmlFor="step-name" className="form-label whitespace-nowrap">Step Name</label>
                      <code className="text-xs text-muted font-mono truncate ml-2" title="Step ID">{step.id}</code>
                    </div>
                    <input id="step-name" type="text" value={name} onChange={(e) => setName(e.target.value)} className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary" placeholder="Enter step name" />
                  </div>
                  <div className="w-full @sm:w-32">
                    <label htmlFor="step-execution-mode" className="block text-sm font-medium text-secondary mb-1">Mode</label>
                    <select
                      id="step-execution-mode"
                      value={step.execution_mode || 'enabled'}
                      onChange={(e) => { const mode = e.target.value as 'enabled' | 'skip' | 'stop'; onUpdate({ ...step, execution_mode: mode === 'enabled' ? undefined : mode }); }}
                      className={`block w-full border rounded-md shadow-sm p-2 text-sm${step.execution_mode === 'skip' ? 'border-secondary bg-card /50 text-secondary' : step.execution_mode === 'stop' ? 'border-danger bg-danger-subtle text-danger' : 'border-primary bg-card text-primary'}`}
                    >
                      <option value="enabled">Enabled</option>
                      <option value="skip">Skip</option>
                      <option value="stop">Stop</option>
                    </select>
                  </div>
                </div>

                {(step.execution_mode === 'skip' || step.execution_mode === 'stop') && (
                  <div className={`text-xs p-2 rounded ${step.execution_mode === 'skip' ? 'bg-card/50 text-secondary' : 'bg-danger-subtle text-danger'}`}>
                    {step.execution_mode === 'skip' ? 'This step will be skipped. Data flows through but no action is taken.' : 'Workflow execution will stop at this step.'}
                  </div>
                )}

                {/* Manual Trigger Toggle */}
                <div className="flex items-center justify-between p-2 bg-surface rounded-md border border-primary">
                  <div className="flex items-center gap-2">
                    <span id="manual-trigger-label" className="text-sm font-medium text-secondary">Manual Trigger</span>
                    <span className="text-muted text-xs">Pause workflow and wait for manual trigger</span>
                  </div>
                  <button type="button" role="switch" aria-checked={step.trigger_type === 'manual'} aria-labelledby="manual-trigger-label" onClick={() => { const newTriggerType = step.trigger_type === 'manual' ? 'auto' : 'manual'; onUpdate({ ...step, trigger_type: newTriggerType === 'auto' ? undefined : newTriggerType }); }} className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${step.trigger_type === 'manual' ? 'bg-blue-600' : 'bg-input'}`}> {/* css-check-ignore: no semantic token */}
                    <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-card shadow ring-0 transition duration-200 ease-in-out ${step.trigger_type === 'manual' ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                </div>
                {step.trigger_type === 'manual' && (
                  <div className="text-xs p-2 rounded bg-info-subtle text-info">Workflow will pause before this step. You can review inputs and trigger execution from the instance detail page.</div>
                )}

                {/* Service Type / Provider / Service Selection */}
                {fieldRules.showServiceType && (
                  <div>
                    <label htmlFor="step-service-type" className="block text-sm font-medium text-secondary mb-1">Service Type {fieldRules.serviceTypeRequired && <span className="text-danger">*</span>}</label>
                    <select id="step-service-type" value={providerType} onChange={handleProviderTypeChange} className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary" required={fieldRules.serviceTypeRequired}>
                      <option value="">Select Service Type</option>
                      {SERVICE_TYPES.map((type) => (<option key={type} value={type}>{SERVICE_TYPE_LABELS[type]}</option>))}
                    </select>
                    {!providerType && <p className="mt-1 text-xs text-secondary">Choose what category of service this step needs (e.g., AI, Storage, Core)</p>}
                  </div>
                )}
                {providerTypeWarning && (
                  <div className="bg-warning-subtle border border-warning rounded-md p-3 flex items-start gap-2">
                    <AlertTriangle className="text-warning flex-shrink-0 mt-0.5" size={16} />
                    <p className="text-sm text-warning">{providerTypeWarning}</p>
                  </div>
                )}
                {fieldRules.showProvider && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-1">
                      <label htmlFor="step-provider" className="block text-sm font-medium text-secondary">Provider {fieldRules.providerRequired && <span className="text-danger">*</span>}</label>
                      {providerId && (() => {
                        const currentProvider = providers.find((p: Record<string, any>) => p.id === providerId);
                        const slug = (currentProvider?.client_metadata as Record<string, unknown>)?.slug as string;
                        if (!slug) return null;
                        return (
                          <button type="button" onClick={() => { setDocsSlug(slug); setIsDocsOpen(true); }} className="text-muted hover:text-info transition-colors" title="Provider documentation">
                            <HelpCircle className="w-4 h-4" />
                          </button>
                        );
                      })()}
                    </div>
                    <select id="step-provider" value={providerId} onChange={handleProviderChange} className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary" disabled={!providerType || providersLoading} required={fieldRules.providerRequired}>
                      <option value="">{providersLoading ? 'Loading providers\u2026' : 'Select Provider'}</option>
                      {providers.map((provider) => (<option key={provider.id} value={provider.id}>{provider.name}</option>))}
                    </select>
                    {providerType && !providersLoading && providers.length === 0 && <p className="mt-1 text-xs text-critical">No providers available for {providerType.replace(/_/g, ' ')}</p>}
                  </div>
                )}
                {/* Version mismatch indicator */}
                {(() => {
                  const pinnedVersion = step.job?.provider_version;
                  const currentProvider = providers.find((p: Record<string, any>) => p.id === providerId);
                  const installedVersion = currentProvider?.version;
                  if (pinnedVersion && installedVersion && pinnedVersion !== installedVersion) {
                    return (
                      <div className="flex items-center justify-between gap-1.5 px-2 py-1 bg-warning-subtle border border-warning rounded-md text-xs text-warning">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle size={14} />
                          <span>Pinned to v{pinnedVersion} - installed: v{installedVersion}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => onUpdate({ ...step, job: { ...step.job, provider_version: installedVersion, service_version: installedVersion } })}
                          className="px-2 py-0.5 bg-amber-600 text-white rounded hover:bg-amber-700 transition-colors" // css-check-ignore: no semantic token
                        >
                          Upgrade
                        </button>
                      </div>
                    );
                  }
                  return null;
                })()}
                {fieldRules.showService && providerId && (
                  <div>
                    <label htmlFor="step-service" className="block text-sm font-medium text-secondary mb-1">Service {fieldRules.serviceRequired && <span className="text-danger">*</span>}</label>
                    <select id="step-service" value={serviceId} onChange={handleServiceChange} className="block w-full border border-primary rounded-md shadow-sm p-2 bg-card text-primary" disabled={servicesLoading} required={fieldRules.serviceRequired}>
                      <option value="">{servicesLoading ? 'Loading services\u2026' : 'Select Service'}</option>
                      {services.map((service) => (<option key={service.id} value={service.service_id}>{service.display_name}</option>))}
                    </select>
                  </div>
                )}
                {fieldRules.showProvider && providerId && !SERVICES_WITHOUT_CREDENTIALS.has(serviceId) && (
                  <CredentialSelector
                    providerId={providerId} selectedCredentialId={credentialId} onSelect={(id) => setCredentialId(id || '')}
                    label={serviceRequiresCredentials === false ? 'Provider Credentials (Optional)' : 'Provider Credentials'}
                    required={false} disabled={!serviceId} disabledReason={!serviceId ? 'Select a service first' : undefined}
                    allowCrossProvider={SERVICES_WITH_CROSS_PROVIDER_CREDENTIALS.has(serviceId)}
                    selectedProviderId={credentialProviderId} onProviderChange={(newProviderId) => setCredentialProviderId(newProviderId)}
                  />
                )}
              </div>
            </div>
          </div>
          </div>

          {/* Service Parameters Section */}
          {serviceId && (
            <div className="mt-6">
              <button type="button" className="w-full flex justify-between items-center cursor-pointer p-3 bg-blue-800 rounded-t-md" onClick={() => { const newState = !serviceParametersExpanded; localStorage.setItem(STORAGE_KEYS.SERVICE_PARAMETERS_EXPANDED, String(newState)); setServiceParametersExpanded(newState); }}> {/* css-check-ignore: no semantic token */}
                <div className="flex items-center gap-2">
                  <h3 className="text-md font-medium text-white">{SERVICE_PARAMETER_TITLES[serviceId] || 'Service Parameters'}</h3>
                  <span title="When this section is collapsed, all parameters use default values. Expand to configure custom settings.">
                    <HelpCircle size={16} className="text-white/70 hover:text-white cursor-help" onClick={(e) => e.stopPropagation()} />
                  </span>
                </div>
                <span className="text-white">{serviceParametersExpanded ? '\u25BC' : '\u25BA'}</span>
              </button>
              {serviceParametersExpanded && (
                <div className="p-4 bg-info-subtle rounded-b-lg">
                  <IterationToggle step={step} inputMappings={inputMappings} parameters={parameters} enhancedPreviousSteps={enhancedPreviousSteps} serviceMetadata={serviceMetadata} onUpdate={onUpdate} />
                  {serviceId === CORE_SERVICES.SET_FIELDS ? (
                    <SetFieldsEditor parameters={parameters} outputFields={outputFields} onParametersChange={setParameters} onOutputFieldsChange={setOutputFields} />
                  ) : serviceId === CORE_SERVICES.WEBHOOK_WAIT && workflowId ? (
                    <WebhookWaitEditor workflowId={workflowId} stepId={step.id} parameters={parameters} onParametersChange={setParameters} />
                  ) : paramSchema && paramSchema.properties ? (
                    <div className="space-y-4">{sortedSectionNames.map(sectionName => renderSection(sectionName, sectionedParams[sectionName]))}</div>
                  ) : (
                    <p className="text-muted">No parameter schema available for this service.</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Mapping Summary */}
          {serviceId && Object.keys(inputMappings).some(k => inputMappings[k]?.mappingType === 'mapped') && (
            <div className="mt-6"><MappingSummary inputMappings={inputMappings} previousSteps={enhancedPreviousSteps} onFieldClick={scrollToParameterField} /></div>
          )}

          {/* Output Schema Section */}
          {serviceId && !SERVICES_WITH_CUSTOM_OUTPUT.has(serviceId) && (
            <div className="mt-6">
              <button type="button" className="w-full flex justify-between items-center cursor-pointer p-3 bg-purple-800 dark:bg-purple-900 rounded-t-md" onClick={() => setOutputFieldsExpanded(!outputFieldsExpanded)}> {/* css-check-ignore: no semantic token */}
                <div className="flex items-center gap-2">
                  <h3 className="text-md font-medium text-white">Output Schema</h3>
                  {(outputSchema?.properties || promptVarNames.length > 0) && (
                    /* css-check-ignore: no semantic token for purple */
                    <span className="text-xs text-purple-200">{(() => { const c = outputSchema?.properties ? Object.keys(outputSchema.properties).length : 0; const t = c + promptVarNames.length; return `${t} field${t !== 1 ? 's' : ''}`; })()}</span>
                  )}
                </div>
                <span className="text-white">{outputFieldsExpanded ? '\u25BC' : '\u25BA'}</span>
              </button>
              {outputFieldsExpanded && (
                <div className="p-4 bg-purple-100 dark:bg-purple-900/40 rounded-b-lg"> {/* css-check-ignore: no semantic token */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex gap-1">
                      <button onClick={() => setOutputViewMode('schema')} className={`px-2 py-1 text-xs rounded${outputViewMode === 'schema' ? 'bg-purple-600 text-white' : 'bg-input text-secondary'}`}>Schema</button> {/* css-check-ignore: no semantic token */}
                      <button onClick={() => setOutputViewMode('json')} className={`px-2 py-1 text-xs rounded${outputViewMode === 'json' ? 'bg-purple-600 text-white' : 'bg-input text-secondary'}`}>JSON</button> {/* css-check-ignore: no semantic token */}
                    </div>
                  </div>
                  <OutputSchemaDisplay outputSchema={outputSchema} promptVarNames={promptVarNames} outputViewMode={outputViewMode} />
                </div>
              )}
            </div>
          )}

          {/* Output Forwarding Section */}
          {serviceId && previousSteps.length > 0 && (
            <div className="mt-4">
              <OutputForwardingSection step={step} previousSteps={enhancedPreviousSteps} promptVarNames={promptVarNames} instanceFormFields={instanceFormFields} onUpdate={(forwardingConfig) => onUpdate({ ...step, output_forwarding: forwardingConfig })} />
            </div>
          )}

          {/* Buttons */}
          <div className="mt-6 flex justify-between">
            <div className="space-x-2">
              <button onClick={onRemove} className="btn-danger text-sm">Remove Step</button>
              {onDuplicate && <button onClick={onDuplicate} className="btn-secondary text-sm">Duplicate</button>}
            </div>
          </div>
        </div>
      </div>

      {/* Modals removed - no trigger exists in this component to open them */}

      {/* Provider docs slide-over */}
      {docsSlug && (
        <ProviderDocsSlideOver
          slug={docsSlug}
          isOpen={isDocsOpen}
          onClose={() => setIsDocsOpen(false)}
          alternateProviders={providers
            .filter((p: Record<string, any>) => {
              if (p.id === providerId) return false;
              const s = (p.client_metadata as Record<string, unknown>)?.slug as string;
              return !!s;
            })
            .map((p: Record<string, any>) => ({
              slug: (p.client_metadata as Record<string, unknown>)?.slug as string,
              name: p.name,
            }))}
        />
      )}
    </div>
  );
}

/** Small hint icon with tooltip, used for inline parameter fields */
function HintIcon({ hint }: { hint: string }) {
  return (
    <span className="relative ml-1 group inline-block">
      <span className="inline-flex items-center justify-center w-4 h-4 text-xs text-secondary border border-secondary rounded-full cursor-help">?</span>
      <span className="tooltip-popover -left-28 top-6 w-64 rounded">{hint}</span>
    </span>
  );
}
