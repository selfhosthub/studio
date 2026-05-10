// ui/features/step-config/BaseStepConfig.tsx

'use client';

import React from 'react';
import { Step } from '@/entities/workflow';
import { SharedStepConfigProvider, useSharedStepConfig } from './context/SharedStepConfigContext';
import BaseGeneralSection from './sections/BaseGeneralSection';
import BaseProviderSection from './sections/BaseProviderSection';
import BaseServiceSection from './sections/BaseServiceSection';
import HttpServiceSection from './sections/HttpServiceSection';
import BaseOutputFieldsSection from './sections/BaseOutputFieldsSection';
import BaseInputMappingsSection from './sections/BaseInputMappingsSection';
import StepInputsSection from './sections/StepInputsSection';

interface BaseStepConfigProps {
  step: Step;
  onUpdate: (updatedStep: Step) => void;
  onRemove: () => void;
  previousSteps: Step[];
  onDuplicate?: () => void;
  className?: string;
  initialProviders?: any[];
  
  // Visibility flags
  showProviderSection?: boolean;
  
  // Optional section titles for customization
  generalSectionTitle?: string;
  providerSectionTitle?: string;
  serviceSectionTitle?: string;
  inputMappingsSectionTitle?: string;
  outputFieldsSectionTitle?: string;
  stepInputsSectionTitle?: string;
}

// Internal component to handle service section switching
function StepServiceSection({ serviceId, title }: { serviceId?: string, title: string }) {
  const isHttpService = serviceId && (
    serviceId === 'http-get' ||
    serviceId === 'http-post' ||
    serviceId === 'http-put' ||
    serviceId === 'http-delete' ||
    serviceId === 'http-patch' ||
    serviceId.startsWith('http-')
  );
  
  if (isHttpService) {
    return <HttpServiceSection title={title} />;
  }
  
  return <BaseServiceSection title={title} />;
}

export default function BaseStepConfig({
  step,
  onUpdate,
  onRemove,
  previousSteps,
  onDuplicate,
  className = '',
  initialProviders = [],
  
  // Visibility flags
  showProviderSection = true,
  
  // Section titles with defaults
  generalSectionTitle = 'General',
  providerSectionTitle = 'Provider',
  serviceSectionTitle = 'Service',
  inputMappingsSectionTitle = 'Input Mappings',
  outputFieldsSectionTitle = 'Output Fields',
  stepInputsSectionTitle = 'Step Inputs',
}: BaseStepConfigProps) {
  return (
    <SharedStepConfigProvider
      step={step}
      onUpdate={onUpdate}
      onRemove={onRemove}
      previousSteps={previousSteps}
      onDuplicate={onDuplicate}
      initialProviders={initialProviders}
    >
      <div className={`bg-card shadow-sm rounded-lg p-6 border border-primary${className}`}>
        <BaseGeneralSection title={generalSectionTitle} />
        
        {/* Only show provider/service sections for task-type steps */}
        {(step.type === 'task' || !step.type) && (
          <>
            {/* Provider section is conditionally shown based on showProviderSection prop */}
            {showProviderSection && (
              <>
                <div className="border-t border-primary my-6"></div>
                <BaseProviderSection title={providerSectionTitle} />
              </>
            )}
            
            {step.provider_id && (
              <>
                <div className="border-t border-primary my-6"></div>
                <StepServiceSection serviceId={step.service_id} title={serviceSectionTitle} />
              </>
            )}
          </>
        )}
        
        <div className="border-t border-primary my-6"></div>
        <StepInputsSection title={stepInputsSectionTitle} />
        
        <div className="border-t border-primary my-6"></div>
        <BaseOutputFieldsSection title={outputFieldsSectionTitle} />
        
        {previousSteps.length > 0 && (
          <>
            <div className="border-t border-primary my-6"></div>
            <BaseInputMappingsSection title={inputMappingsSectionTitle} />
          </>
        )}
      </div>
    </SharedStepConfigProvider>
  );
}