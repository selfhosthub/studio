// ui/widgets/instance-view/step-config/InstanceStepConfig.tsx

'use client';

import React, { useEffect, useState } from 'react';
import { BaseStepConfig } from '@/features/step-config';
import { Step } from '@/entities/workflow';
import { Provider } from '@/entities/provider';
import { providerService } from '@/shared/api';

interface InstanceStepConfigProps {
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  previousSteps: Step[];
  onDuplicate?: () => void;
  className?: string;
  workflowId: string; // Reference to the original workflow
}

export default function InstanceStepConfig({
  step,
  onUpdate,
  onRemove,
  previousSteps,
  onDuplicate,
  className,
  workflowId
}: InstanceStepConfigProps) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const getProviders = async (): Promise<Provider[]> => {
    try {
      // For instances, the provider is locked based on workflow selection
      // We still need to fetch providers to get the service information
      const fetchedProviders = await providerService.getAllProviders();
      setProviders(fetchedProviders);
      setIsLoading(false);
      return fetchedProviders;
    } catch (error) {
      console.error('Failed to fetch providers for instance:', error);
      setIsLoading(false);
      return [];
    }
  };

  useEffect(() => {
    getProviders(); // eslint-disable-line react-hooks/set-state-in-effect
  }, []);

  if (isLoading) {
    return <div className="p-4">Loading instance configuration...</div>;
  }

  return (
    <BaseStepConfig
      step={step}
      onUpdate={onUpdate}
      onRemove={onRemove}
      previousSteps={previousSteps}
      onDuplicate={onDuplicate}
      className={className}
      initialProviders={providers}
      // In instances, we typically hide provider selection as it's locked from workflow
      showProviderSection={false}
      // Instance-specific section titles
      generalSectionTitle="Instance Step"
      serviceSectionTitle="Service Configuration"
      inputMappingsSectionTitle="Runtime Input Mapping"
      outputFieldsSectionTitle="Runtime Outputs"
    />
  );
}