// ui/app/workflows/components/ServiceBasedWorkflowStepConfig.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { Step, JobConfig } from '@/entities/workflow';
import { XCircle, Copy } from 'lucide-react';
import ProviderServiceSelector from './ProviderServiceSelector';
import { SERVICE_TYPES, type ServiceType } from '@/entities/provider';

const convertToServiceType = (type?: string): ServiceType | undefined => {
  if (!type) return undefined;
  return SERVICE_TYPES.includes(type as ServiceType)
    ? type as ServiceType
    : undefined;
};

const ensureValidJobConfig = (job?: Partial<JobConfig>): JobConfig => {
  if (!job) {
    return {
      timeout_seconds: 30, // Default timeout
      parameters: {}
    };
  }
  
  return {
    ...job,
    timeout_seconds: job.timeout_seconds || 30,
    parameters: job.parameters || {}
  };
};

interface WorkflowStepConfigProps {
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  previousSteps: Step[];
  onDuplicate?: () => void;
}

export function ServiceBasedWorkflowStepConfig({
  step,
  onUpdate,
  onRemove,
  previousSteps,
  onDuplicate,
}: WorkflowStepConfigProps) {
  const [name, setName] = useState(step.name || '');
  
  const [jobConfig, setJobConfig] = useState<JobConfig>(() => {
    const initialConfig = ensureValidJobConfig(step.job);
    if (initialConfig.service_type) {
      initialConfig.service_type = convertToServiceType(initialConfig.service_type) || initialConfig.service_type;
    }
    return initialConfig;
  });
  
  useEffect(() => {
    onUpdate({
      ...step,
      name,
      job: jobConfig,
      // Keep legacy fields in sync.
      provider_id: jobConfig.provider_id,
      service_id: jobConfig.service_id,
      parameters: jobConfig.parameters,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onUpdate/step excluded to prevent infinite loop
  }, [name, jobConfig]);

  const updateJobConfig = (updates: Partial<JobConfig>) => {
    setJobConfig(prev => ({
      ...prev,
      ...updates,
    }));
  };

  const handleProviderChange = (providerId: string) => {
    updateJobConfig({
      provider_id: providerId,
      service_id: undefined,
    });
  };

  const handleServiceChange = (serviceId: string) => {
    updateJobConfig({
      service_id: serviceId,
      parameters: {},
    });
  };

  const serviceType = convertToServiceType(jobConfig.service_type);

  return (
    <div className="bg-card border border-primary rounded-lg shadow-sm p-6 animate-slideIn">
      {/* Header with controls */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Configure Step</h3>
        <div className="flex space-x-2">
          {onDuplicate && (
            <button
              onClick={onDuplicate}
              className="text-secondary hover:text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
              aria-label="Duplicate step"
            >
              <Copy size={20} />
            </button>
          )}
          <button
            onClick={onRemove}
            className="text-secondary hover:text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
            aria-label="Remove step"
          >
            <XCircle size={20} />
          </button>
        </div>
      </div>
      
      {/* Step name */}
      <div className="mb-4">
        <label htmlFor="step-name" className="block text-sm font-medium text-secondary mb-1">
          Step Name
        </label>
        <input
          id="step-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="block w-full border border-primary rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          placeholder="Enter a descriptive name for this step"
        />
      </div>
      
      {/* Provider and Service Selection */}
      <div className="mb-6">
        <h4 className="font-medium text-sm text-secondary mb-2">Provider & Service</h4>
        <ProviderServiceSelector
          serviceType={serviceType}
          providerId={jobConfig.provider_id}
          serviceId={jobConfig.service_id}
          onProviderChange={handleProviderChange}
          onServiceChange={handleServiceChange}
        />
      </div>
      
      {/* Display service type if available */}
      {jobConfig.service_type && (
        <div className="mb-4 rounded-md bg-info-subtle p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-info">Service Type Required</h3>
              <div className="mt-2 text-sm text-info">
                <p>This step requires a {jobConfig.service_type} service.</p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Parameters section - will be expanded later */}
      {jobConfig.service_id && (
        <div className="mt-4">
          <h4 className="font-medium text-sm text-secondary mb-2">Parameters</h4>
          <div className="bg-surface p-4 rounded-md">
            <p className="text-sm text-secondary">
              Parameter configuration will be implemented in a future update.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}