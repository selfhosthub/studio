// ui/app/workflows/components/ProviderServiceSelector.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { ServiceType } from '@/entities/provider';
import { Provider, ServiceDefinition } from '@/entities/provider';
import { getProviders, getProviderServices } from '@/shared/api';

interface ProviderServiceSelectorProps {
  serviceType?: ServiceType;
  providerId?: string;
  serviceId?: string;
  onProviderChange: (providerId: string) => void;
  onServiceChange: (serviceId: string) => void;
}

export default function ProviderServiceSelector({
  serviceType,
  providerId,
  serviceId,
  onProviderChange,
  onServiceChange,
}: ProviderServiceSelectorProps) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [services, setServices] = useState<ServiceDefinition[]>([]);
  const [isLoadingProviders, setIsLoadingProviders] = useState(true);
  const [isLoadingServices, setIsLoadingServices] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch providers based on service type
  useEffect(() => {
    const fetchProviders = async () => {
      setIsLoadingProviders(true);
      setError(null);

      try {
        // Use api-client which handles auth properly
        const allProviders = await getProviders();

        // Filter providers by service type if specified
        let filteredProviders = allProviders;
        if (serviceType) {
          filteredProviders = allProviders.filter(provider =>
            provider.service_types?.includes(serviceType)
          );
        }

        setProviders(filteredProviders);

        // If we have a providerId but it's not in the filtered list, reset it
        if (providerId && !filteredProviders.find((p: Provider) => p.id === providerId)) {
          onProviderChange('');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load providers');
        console.error('Error fetching providers:', err);
      } finally {
        setIsLoadingProviders(false);
      }
    };

    fetchProviders();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- callbacks excluded to avoid refetch loops
  }, [serviceType]);

  // Fetch services when provider changes
  useEffect(() => {
    const fetchServices = async () => {
      if (!providerId) {
        setServices([]);
        return;
      }

      setIsLoadingServices(true);
      setError(null);

      try {
        const data = await getProviderServices(providerId);

        // Filter services by service type if specified (case-insensitive)
        let filteredServices = data;
        if (serviceType) {
          filteredServices = data.filter((service: ServiceDefinition) => {
            const categories: string[] = service.categories || [];
            return categories.includes(serviceType.toLowerCase());
          });
        }
        setServices(filteredServices);

        // If we have a serviceId but it's not in the filtered list, reset it
        if (serviceId && !filteredServices.find((s: ServiceDefinition) => s.service_id === serviceId)) {
          onServiceChange('');
        }
      } catch (err) {
        console.error('[ProviderServiceSelector] Error fetching services:', err);
        setError(err instanceof Error ? err.message : 'Failed to load services');
      } finally {
        setIsLoadingServices(false);
      }
    };

    fetchServices();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- callbacks excluded to avoid refetch loops
  }, [providerId, serviceType]);

  return (
    <div className="space-y-4">
      {error && (
        <div className="alert alert-error">
          {error}
        </div>
      )}

      <div className="space-y-2">
        <label htmlFor="provider-select" className="block text-sm font-medium text-secondary">
          Provider
        </label>
        <select
          id="provider-select"
          value={providerId || ''}
          onChange={(e) => onProviderChange(e.target.value)}
          className="block w-full border border-primary rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          disabled={isLoadingProviders || providers.length === 0}
        >
          <option value="">Select a provider</option>
          {providers.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
        {isLoadingProviders && (
          <div className="text-muted text-sm">Loading providers...</div>
        )}
        {!isLoadingProviders && providers.length === 0 && !error && (
          <div className="text-muted text-sm">
            {serviceType
              ? `No providers available for ${serviceType} service type`
              : 'No providers available'}
          </div>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="service-select" className="block text-sm font-medium text-secondary">
          Service
        </label>
        <select
          id="service-select"
          value={serviceId || ''}
          onChange={(e) => onServiceChange(e.target.value)}
          className="block w-full border border-primary rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          disabled={!providerId || isLoadingServices || services.length === 0}
        >
          <option value="">Select a service</option>
          {services.map((service) => (
            <option key={service.id} value={service.service_id}>
              {service.display_name || service.name}
            </option>
          ))}
        </select>
        {isLoadingServices && (
          <div className="text-muted text-sm">Loading services...</div>
        )}
        {!isLoadingServices && providerId && services.length === 0 && !error && (
          <div className="text-muted text-sm">No services available for this provider</div>
        )}
      </div>
    </div>
  );
}
