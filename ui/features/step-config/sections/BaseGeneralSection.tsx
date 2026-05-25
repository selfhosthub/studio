// ui/features/step-config/sections/BaseGeneralSection.tsx

'use client';

import React from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';

interface BaseGeneralSectionProps {
  title?: string;
}

export default function BaseGeneralSection({ title = 'General' }: BaseGeneralSectionProps) {
  const { 
    name, 
    setName, 
    description, 
    setDescription, 
    onRemove, 
    onDuplicate,
    handleUpdateStep
  } = useSharedStepConfig();

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">{title}</h3>
        <div className="flex space-x-2">
          {onDuplicate && (
            <button
              type="button"
              onClick={onDuplicate}
              className="px-3 py-1 bg-info-subtle text-info rounded text-xs font-medium hover:opacity-80 transition-colors"
            >
              Duplicate
            </button>
          )}
          <button
            type="button"
            onClick={onRemove}
            className="px-3 py-1 bg-danger-subtle text-danger rounded text-xs font-medium hover:opacity-80 transition-colors"
          >
            Remove
          </button>
        </div>
      </div>
      
      <div className="space-y-4">
        <div>
          <label htmlFor="step-name" className="block text-sm font-medium mb-1">
            Step Name
          </label>
          <input
            type="text"
            id="step-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:border-info"
            placeholder="Enter step name"
          />
        </div>
        
        <div>
          <label htmlFor="step-description" className="block text-sm font-medium mb-1">
            Description (Optional)
          </label>
          <textarea
            id="step-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:border-info"
            placeholder="Add a description to explain what this step does"
          />
        </div>
      </div>
    </div>
  );
}