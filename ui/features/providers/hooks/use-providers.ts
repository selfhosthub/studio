// ui/features/providers/hooks/use-providers.ts

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as apiClient from '@/shared/api';
import type {
  Provider,
  ProviderService,
  CreateProviderRequest,
  UpdateProviderRequest,
  CreateProviderServiceRequest,
  UpdateProviderServiceRequest,
} from '@/entities/provider';

// Query keys
export const providerKeys = {
  all: ['providers'] as const,
  lists: () => [...providerKeys.all, 'list'] as const,
  list: (filters?: any) => [...providerKeys.lists(), filters] as const,
  details: () => [...providerKeys.all, 'detail'] as const,
  detail: (id: string) => [...providerKeys.details(), id] as const,
  services: (providerId: string) => [...providerKeys.detail(providerId), 'services'] as const,
  service: (serviceId: string) => [...providerKeys.all, 'service', serviceId] as const,
};

// Providers Hooks

export function useProviders() {
  return useQuery<Provider[]>({
    queryKey: providerKeys.lists(),
    queryFn: () => apiClient.getProviders(),
  });
}

export function useProvider(providerId: string) {
  return useQuery<Provider>({
    queryKey: providerKeys.detail(providerId),
    queryFn: () => apiClient.getProvider(providerId),
    enabled: !!providerId,
  });
}

export function useCreateProvider() {
  const queryClient = useQueryClient();

  return useMutation<Provider, Error, CreateProviderRequest>({
    mutationFn: (data) => apiClient.createProvider(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.lists() });
    },
  });
}

export function useUpdateProvider() {
  const queryClient = useQueryClient();

  return useMutation<Provider, Error, { providerId: string; updates: UpdateProviderRequest }>({
    mutationFn: ({ providerId, updates }) => apiClient.updateProvider(providerId, updates),
    onSuccess: (_, { providerId }) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.detail(providerId) });
      queryClient.invalidateQueries({ queryKey: providerKeys.lists() });
    },
  });
}

export function useDeleteProvider() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (providerId) => apiClient.deleteProvider(providerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: providerKeys.lists() });
    },
  });
}

// Provider Services Hooks

export function useProviderServices(providerId: string) {
  return useQuery<ProviderService[]>({
    queryKey: providerKeys.services(providerId),
    queryFn: () => apiClient.getProviderServices(providerId),
    enabled: !!providerId,
  });
}

export function useProviderService(serviceId: string) {
  return useQuery<ProviderService>({
    queryKey: providerKeys.service(serviceId),
    queryFn: () => apiClient.getProviderService(serviceId),
    enabled: !!serviceId,
  });
}

export function useCreateProviderService() {
  const queryClient = useQueryClient();

  return useMutation<
    ProviderService,
    Error,
    { providerId: string; data: CreateProviderServiceRequest }
  >({
    mutationFn: ({ providerId, data }) => apiClient.createProviderService(providerId, data),
    onSuccess: (_, { providerId }) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.services(providerId) });
    },
  });
}

export function useUpdateProviderService() {
  const queryClient = useQueryClient();

  return useMutation<
    ProviderService,
    Error,
    { serviceId: string; updates: UpdateProviderServiceRequest }
  >({
    mutationFn: ({ serviceId, updates }) => apiClient.updateProviderService(serviceId, updates),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.service(data.id) });
      queryClient.invalidateQueries({ queryKey: providerKeys.services(data.provider_id || '') });
    },
  });
}

export function useDeleteProviderService() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, { serviceId: string; providerId: string }>({
    mutationFn: ({ serviceId }) => apiClient.deleteProviderService(serviceId),
    onSuccess: (_, { providerId }) => {
      queryClient.invalidateQueries({ queryKey: providerKeys.services(providerId) });
    },
  });
}

// Convenience hooks for template builder

export function useProvidersWithServices() {
  const { data: providers, ...providersQuery } = useProviders();

  return {
    providers,
    ...providersQuery,
  };
}

export function useServiceByServiceId(providerId: string, serviceId: string) {
  const { data: services, ...servicesQuery } = useProviderServices(providerId);

  const service = services?.find((s) => s.service_id === serviceId);

  return {
    service,
    ...servicesQuery,
  };
}
