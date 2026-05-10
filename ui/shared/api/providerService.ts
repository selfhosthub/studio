// ui/shared/api/providerService.ts

import {
  getProviders,
  getProvider,
  getProviderServices,
  getProviderService,
  testProviderService,
} from '@/shared/api';

export const providerService = {
  async getAllProviders() {
    return await getProviders();
  },

  async getProvider(providerId: string) {
    return await getProvider(providerId);
  },

  async getProviderServices(providerId: string) {
    return await getProviderServices(providerId);
  },

  // providerId is accepted for symmetry / error logging; the underlying lookup is serviceId-only.
  async getProviderService(providerId: string, serviceId: string) {
    return await getProviderService(serviceId);
  },

  async testService(providerId: string, serviceId: string, parameters: Record<string, unknown>) {
    return await testProviderService(providerId, serviceId, parameters);
  }
};
