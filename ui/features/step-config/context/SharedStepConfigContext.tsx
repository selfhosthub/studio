// ui/features/step-config/context/SharedStepConfigContext.tsx

'use client';

import React, { createContext, useState, useContext, useEffect, ReactNode } from 'react';
import { Step } from '@/entities/workflow';
import { Provider, ServiceDefinition } from '@/entities/provider';
import { getStepProviderId, getStepServiceId } from '@/shared/lib/step-utils';
import { getProviders, getProviderServices, getProviderService } from '@/shared/api';

interface SharedStepConfigContextType {
  // Step data
  step: Step;
  updatedStep: Step;
  
  // Required props
  previousSteps: Step[];
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  onDuplicate?: () => void;
  
  // Step properties
  name: string;
  setName: (name: string) => void;
  description: string;
  setDescription: (description: string) => void;
  providerId: string;
  setProviderId: (providerId: string) => void;
  serviceId: string;
  setServiceId: (serviceId: string) => void;
  parameters: Record<string, any>;
  setParameters: (parameters: Record<string, any>) => void;
  inputMappings: Record<string, any>;
  setInputMappings: (inputMappings: Record<string, any>) => void;
  outputFields: Record<string, any>;
  setOutputFields: (outputFields: Record<string, any>) => void;
  
  // Step inputs data
  inputs: Step['inputs'];
  setInputs: (inputs: Step['inputs']) => void;
  updateStep: (updatedStep: Partial<Step>) => void;
  
  // Provider and service data
  providers: Provider[];
  setProviders: (providers: Provider[]) => void;
  services: ServiceDefinition[];
  setServices: (services: ServiceDefinition[]) => void;
  service: ServiceDefinition | null; // Current selected service details
  
  // Service parameter schema
  paramSchema: Record<string, any> | null;
  setParamSchema: (schema: Record<string, any> | null) => void;
  
  // Loading state
  loading: boolean;
  setLoading: (loading: boolean) => void;
  
  // Utility functions
  handleUpdateStep: () => void;
  addInputMapping: (paramName: string) => void;
  removeInputMapping: (paramName: string) => void;
  updateInputMapping: (paramName: string, mapping: any) => void;
  addOutputField: (fieldName: string, field: any) => void;
  removeOutputField: (fieldName: string) => void;
}

export const SharedStepConfigContext = createContext<SharedStepConfigContextType | null>(null);

interface SharedStepConfigProviderProps {
  children: ReactNode;
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  previousSteps: Step[];
  onDuplicate?: () => void;
  initialProviders?: Provider[];
}

export function SharedStepConfigProvider({
  children,
  step,
  onUpdate,
  onRemove,
  previousSteps,
  onDuplicate,
  initialProviders = []
}: SharedStepConfigProviderProps) {
  // State for step properties
  const [name, setName] = useState(step.name);
  const [description, setDescription] = useState(step.description || '');
  // Use utility functions to read from step level OR job fallback (for legacy/seeded data)
  const [providerId, setProviderId] = useState(getStepProviderId(step) || '');
  const [serviceId, setServiceId] = useState(getStepServiceId(step) || '');
  
  // We handle both naming conventions for backward compatibility
  // Also check job.parameters for seeded/legacy data where parameters are nested in job object
  const [parameters, setParameters] = useState<Record<string, any>>(
    step.parameters || step.service_parameters || (step as any).job?.parameters || {}
  );
  const [outputFields, setOutputFields] = useState<Record<string, any>>(step.outputs || step.output_fields || {});
  const [inputMappings, setInputMappings] = useState<Record<string, any>>(step.input_mappings || {});
  const [inputs, setInputs] = useState<Step['inputs']>(step.inputs || {
    database: {},
    resource: {},
    previous_steps: {}
  });
  
  // State for providers and services
  const [providers, setProviders] = useState<Provider[]>(initialProviders);
  const [services, setServices] = useState<ServiceDefinition[]>([]);
  const [service, setService] = useState<ServiceDefinition | null>(null);
  
  // State for loading and parameter schema
  const [loading, setLoading] = useState(true);
  const [paramSchema, setParamSchema] = useState<Record<string, any> | null>(null);
  
  // Combined updated step object that reflects current state
  const updatedStep: Step = {
    ...step,
    name,
    description,
    provider_id: providerId,
    service_id: serviceId,
    parameters,
    service_parameters: parameters, // Include both for backward compatibility
    outputs: outputFields,
    output_fields: outputFields, // Include both for backward compatibility
    input_mappings: inputMappings,
    inputs
  };
  
  // Effect to fetch providers if not provided
  useEffect(() => {
    async function fetchProviders() {
      if (initialProviders.length === 0) {
        try {
          const data = await getProviders();
          setProviders(data);
        } catch {
          // Silently fail - providers will remain empty
        } finally {
          setLoading(false);
        }
      } else {
        setLoading(false);
      }
    }

    fetchProviders();
  }, [initialProviders]);
  
  // Effect to fetch services when provider changes
  useEffect(() => {
    async function fetchServices() {
      if (providerId) {
        try {
          setLoading(true);
          const data = await getProviderServices(providerId);
          setServices(data);
        } catch {
          // Silently fail - services will remain empty
        } finally {
          setLoading(false);
        }
      } else {
        setServices([]);
      }
    }

    fetchServices();
  }, [providerId]);
  
  // Effect to fetch service schema when service changes
  useEffect(() => {
    async function fetchServiceSchema() {
      if (providerId && serviceId) {
        try {
          setLoading(true);
          const data = await getProviderService(serviceId);
          // Store the full service data (includes ui_hints for group ordering)
          setService(data);

          // For parameter schema, check all possible sources
          const schema = data.parameter_schema || data.parameters || null;

          // If schema has a "properties" field (JSON Schema format), use that
          // The properties contain the ui metadata (section, group, order)
          const finalSchema = schema && schema.properties ? schema.properties : schema;

          setParamSchema(finalSchema);
        } catch {
          // Silently fail - service schema will remain null
        } finally {
          setLoading(false);
        }
      } else {
        setService(null);
        setParamSchema(null);
      }
    }

    fetchServiceSchema();
  }, [providerId, serviceId]);
  
  // Utility functions
  const handleUpdateStep = () => {
    onUpdate(updatedStep);
  };
  
  // Direct update function for partial step updates
  const updateStep = (stepChanges: Partial<Step>) => {
    if (stepChanges.name !== undefined) setName(stepChanges.name);
    if (stepChanges.description !== undefined) setDescription(stepChanges.description || '');
    if (stepChanges.provider_id !== undefined) setProviderId(stepChanges.provider_id || '');
    if (stepChanges.service_id !== undefined) setServiceId(stepChanges.service_id || '');
    if (stepChanges.parameters !== undefined) setParameters(stepChanges.parameters);
    if (stepChanges.service_parameters !== undefined) setParameters(stepChanges.service_parameters);
    if (stepChanges.outputs !== undefined) setOutputFields(stepChanges.outputs);
    if (stepChanges.output_fields !== undefined) setOutputFields(stepChanges.output_fields);
    if (stepChanges.input_mappings !== undefined) setInputMappings(stepChanges.input_mappings);
    if (stepChanges.inputs !== undefined) setInputs(stepChanges.inputs);
  };
  
  // Effect to update the step whenever key properties change
  useEffect(() => {
    onUpdate(updatedStep);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onUpdate/step excluded to prevent infinite loop; state fields cover all changes
  }, [name, description, providerId, serviceId, parameters, outputFields, inputMappings, inputs]);
  
  // Input mappings functions
  const addInputMapping = (paramName: string) => {
    setInputMappings((prev) => ({
      ...prev,
      [paramName]: {
        mappingType: 'mapped',
        stepId: '',
        outputField: '',
        staticValue: ''
      }
    }));
  };
  
  const removeInputMapping = (paramName: string) => {
    setInputMappings((prev) => {
      const updatedMappings = { ...prev };
      delete updatedMappings[paramName];
      return updatedMappings;
    });
  };
  
  const updateInputMapping = (paramName: string, mapping: any) => {
    setInputMappings((prev) => ({
      ...prev,
      [paramName]: mapping
    }));
  };
  
  // Output fields functions
  const addOutputField = (fieldName: string, field: any) => {
    setOutputFields((prev) => ({
      ...prev,
      [fieldName]: field
    }));
  };
  
  const removeOutputField = (fieldName: string) => {
    setOutputFields((prev) => {
      const updatedFields = { ...prev };
      delete updatedFields[fieldName];
      return updatedFields;
    });
  };
  
  return (
    <SharedStepConfigContext.Provider
      value={{
        step,
        updatedStep,
        previousSteps,
        onUpdate,
        onRemove,
        onDuplicate,
        name,
        setName,
        description,
        setDescription,
        providerId,
        setProviderId,
        serviceId,
        setServiceId,
        parameters,
        setParameters,
        inputMappings,
        setInputMappings,
        outputFields,
        setOutputFields,
        // New inputs properties
        inputs,
        setInputs,
        updateStep,
        // Provider data
        providers,
        setProviders,
        services,
        setServices,
        service, // Current selected service data
        paramSchema,
        setParamSchema,
        loading,
        setLoading,
        handleUpdateStep,
        addInputMapping,
        removeInputMapping,
        updateInputMapping,
        addOutputField,
        removeOutputField
      }}
    >
      {children}
    </SharedStepConfigContext.Provider>
  );
}

// Custom hook to use the context
export function useSharedStepConfig() {
  const context = useContext(SharedStepConfigContext);
  if (!context) {
    throw new Error('useSharedStepConfig must be used within a SharedStepConfigProvider');
  }
  return context;
}