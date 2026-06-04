// ui/features/step-config/sections/BaseProviderSection.tsx

'use client';

import React from 'react';
import { useSharedStepConfig } from '../context/SharedStepConfigContext';

interface BaseProviderSectionProps {
  title?: string;
}

export default function BaseProviderSection({ title = 'Provider' }: BaseProviderSectionProps) {
  const { 
    providerId,
    setProviderId,
    providers,
    loading
  } = useSharedStepConfig();

  return (
    <div>
      <h3 className="text-lg font-medium mb-4">{title}</h3>
      
      <div>
        <label htmlFor="provider-select" className="block text-sm font-medium mb-1">
          Select Provider
        </label>
        <select
          id="provider-select"
          value={providerId}
          onChange={(e) => setProviderId(e.target.value)}
          className="w-full px-3 py-2 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info"
          disabled={loading}
        >
          <option value="">Select a provider</option>
          {providers.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
        
        {loading && (
          <div className="mt-2 text-sm text-secondary">
            Loading providers...
          </div>
        )}
      </div>
    </div>
  );
}