// ui/app/providers/[providerId]/page.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Provider, ProviderService } from '@/entities/provider';
import { DashboardLayout } from '@/widgets/layout';
import Link from 'next/link';
import { v4 as uuidv4 } from 'uuid';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { LinkedText, Modal } from '@/shared/ui';
import { getProvider, getProviderServices, createProviderService } from '@/shared/api';
import { BookOpen } from 'lucide-react';
import { getProviderDocSlug, getProviderDocUrl } from '@/shared/lib/provider-docs';

export default function ProviderDetailsPage() {
  // Next.js 15+: params is async, use useParams() hook for client components
  const params = useParams();
  const providerId = params.providerId as string;
  const { user } = useUser();
  const { toast } = useToast();
  const [provider, setProvider] = useState<Provider | null>(null);
  const [services, setServices] = useState<ProviderService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAddingService, setIsAddingService] = useState(false);
  const [newService, setNewService] = useState<Partial<ProviderService>>({
    service_id: '',
    display_name: '',
    description: '',
    parameter_schema: {
      type: 'object',
      properties: {},
      required: []
    }
  });

  // Fetch provider details and services
  useEffect(() => {
    async function fetchProviderDetails() {
      try {
        setLoading(true);

        // Fetch provider details and services in parallel
        const [providerData, servicesData] = await Promise.all([
          getProvider(providerId),
          getProviderServices(providerId)
        ]);

        setProvider(providerData);
        setServices(servicesData || []);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch provider details:', err);
        setError('Failed to load provider details. Please try again later.');
      } finally {
        setLoading(false);
      }
    }

    fetchProviderDetails();
  }, [providerId]);

  // Handle creating a new service
  const handleCreateService = async () => {
    try {
      if (!newService.display_name || !newService.service_id) {
        toast({ title: 'Validation error', description: 'Please provide a service ID and display name', variant: 'destructive' });
        return;
      }

      const createdService = await createProviderService(providerId, {
        service_id: newService.service_id!,
        display_name: newService.display_name!,
        service_type: newService.service_type || 'ai',
        ...newService,
      });

      // Update local state with the new service
      setServices([...services, createdService]);

      // Reset form
      setNewService({
        service_id: '',
        display_name: '',
        description: '',
        parameter_schema: {
          type: 'object',
          properties: {},
          required: []
        }
      });
      
      setIsAddingService(false);
    } catch (err) {
      console.error('Error creating service:', err);
      toast({ title: 'Create failed', description: 'Failed to create service. Please try again.', variant: 'destructive' });
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
          <div className="text-center py-10">
            <div className="spinner-md"></div>
            <p className="mt-2 text-secondary">Loading provider details...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error || !provider) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
          <div className="alert alert-error">
            <h3 className="text-danger font-medium">Error</h3>
            <p className="text-danger">{error || 'Provider not found'}</p>
            <Link href="/providers/list" className="mt-2 text-info hover:underline">
              Back to Providers List
            </Link>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center mb-2">
            <Link href="/providers/list" className="text-info hover:underline mr-2">
              Providers
            </Link>
            <span className="text-muted">/</span>
            <h1 className="text-2xl md:text-3xl font-bold ml-2 text-primary">{provider.name}</h1>
            <span className={`ml-3 px-2 py-1 text-xs rounded-full ${
              provider.status === 'active' ? 'bg-success-subtle text-success' :
              provider.status === 'inactive' ? 'bg-card text-primary' :
              'bg-warning-subtle text-warning'
            }`}>
              {provider.status}
            </span>
          </div>
          <p className="text-muted">
            {provider.description ? <LinkedText text={provider.description} /> : null}
          </p>
          
          <div className="mt-4 flex items-center space-x-4">
            <div className="px-3 py-1 bg-info-subtle text-info text-sm rounded-md">
              Type: {provider.provider_type}
            </div>
            <div className="px-3 py-1 bg-card text-primary text-sm rounded-md">
              Status: {provider.status}
            </div>
            {(() => {
              const docSlug = getProviderDocSlug(provider);
              if (!docSlug) return null;
              return (
                <Link href={getProviderDocUrl(docSlug)} className="inline-flex items-center gap-1.5 text-sm text-info hover:underline">
                  <BookOpen className="w-4 h-4" />
                  Documentation
                </Link>
              );
            })()}
          </div>
        </div>
        
        {/* Services List */}
        <div className="bg-card shadow rounded-lg overflow-hidden mb-6 border border-primary">
          <div className="px-6 py-4 border-b border-primary flex justify-between items-center">
            <h2 className="text-xl font-semibold text-primary">Services</h2>
            {user?.role === 'super_admin' && (
              <button
                onClick={() => setIsAddingService(true)}
                className="btn-primary text-sm px-3 py-1"
              >
                Add Service
              </button>
            )}
          </div>
          
          {services && services.length > 0 ? (
            <div className="divide-y divide-primary">
              {services.map((service) => (
                <div key={service.id} className="px-6 py-4 hover:bg-surface /50">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-medium text-primary">{service.display_name}</h3>
                      <p className="text-muted">
                        {service.description ? <LinkedText text={service.description} /> : null}
                      </p>
                    </div>
                    {user?.role === 'super_admin' && (
                      <div className="flex space-x-2">
                        <Link
                          href={`/providers/${providerId}/services/${service.id}`}
                          className="px-3 py-1 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 text-sm rounded hover:bg-indigo-100 dark:hover:bg-indigo-900/50" // css-check-ignore: no semantic token
                        >
                          Configure
                        </Link>
                      </div>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <div className="px-2 py-1 bg-card text-primary text-xs rounded">
                      {service.service_id}
                    </div>
                    <div className="px-2 py-1 bg-card text-primary text-xs rounded">
                      {service.service_type}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="px-6 py-10 text-center">
              <p className="text-muted">No services available for this provider</p>
              {user?.role === 'super_admin' && (
                <button
                  onClick={() => setIsAddingService(true)}
                  className="btn-primary mt-2"
                >
                  Add First Service
                </button>
              )}
            </div>
          )}
        </div>
        
        {/* Provider Actions */}
        <div className="flex space-x-4">
          {user?.role === 'super_admin' && (
            <>
              <Link
                href={`/providers/${providerId}/edit`}
                className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700" // css-check-ignore: no semantic token
              >
                Edit Provider
              </Link>
              <button
                onClick={() => {
                  const confirmed = confirm(
                    `⚠️ WARNING: System-Wide Deletion\n\n` +
                    `You are about to delete the provider "${provider.name}".\n\n` +
                    `This action will:\n` +
                    `• Remove this provider for ALL organizations\n` +
                    `• Disable all services associated with this provider\n` +
                    `• Break any workflows currently using this provider\n\n` +
                    `This action cannot be undone.\n\n` +
                    `Are you sure you want to proceed?`
                  );
                  if (confirmed) {
                    // Delete provider logic would go here
                    toast({ title: 'Not implemented', description: 'Delete functionality not yet implemented', variant: 'default' });
                  }
                }}
                className="px-4 py-2 bg-danger text-white rounded hover:bg-danger"
              >
                Delete Provider
              </button>
            </>
          )}
        </div>
        
        {/* Add Service Modal */}
        <Modal
          isOpen={isAddingService}
          onClose={() => setIsAddingService(false)}
          title="Add New Service"
          size="lg"
        >
          <div className="p-6">
            <div className="space-y-4">
              <div>
                <label htmlFor="new-service-id" className="block text-sm font-medium text-secondary mb-1">
                  Service ID
                </label>
                <input
                  id="new-service-id"
                  type="text"
                  value={newService.service_id}
                  onChange={(e) => setNewService({...newService, service_id: e.target.value})}
                  className="w-full p-2 border border-primary rounded bg-surface text-primary focus:ring-blue-500 focus:border-info"
                  placeholder="e.g., core.set_fields"
                />
              </div>

              <div>
                <label htmlFor="new-service-display-name" className="block text-sm font-medium text-secondary mb-1">
                  Display Name
                </label>
                <input
                  id="new-service-display-name"
                  type="text"
                  value={newService.display_name}
                  onChange={(e) => setNewService({...newService, display_name: e.target.value})}
                  className="w-full p-2 border border-primary rounded bg-surface text-primary focus:ring-blue-500 focus:border-info"
                  placeholder="e.g., Set Fields"
                />
              </div>

              <div>
                <label htmlFor="new-service-description" className="block text-sm font-medium text-secondary mb-1">
                  Description
                </label>
                <textarea
                  id="new-service-description"
                  value={newService.description ?? ''}
                  onChange={(e) => setNewService({...newService, description: e.target.value})}
                  className="w-full p-2 border border-primary rounded bg-surface text-primary focus:ring-blue-500 focus:border-info"
                  rows={3}
                  placeholder="Describe what this service does"
                />
              </div>

              <div>
                <label htmlFor="new-service-param-schema" className="block text-sm font-medium text-secondary mb-1">
                  Parameter Schema
                </label>
                <p className="text-xs text-secondary mb-2">
                  Define the parameters this service accepts. For now, we&apos;ll create a simple schema.
                  You can edit it later for more complex configurations.
                </p>
                <textarea
                  id="new-service-param-schema"
                  value={JSON.stringify(newService.parameter_schema, null, 2)}
                  onChange={(e) => {
                    try {
                      const schema = JSON.parse(e.target.value);
                      setNewService({...newService, parameter_schema: schema});
                    } catch (err) {
                      // Invalid JSON, don't update
                    }
                  }}
                  className="w-full p-2 border border-primary rounded bg-surface text-primary font-mono text-sm focus:ring-blue-500 focus:border-info"
                  rows={10}
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                onClick={() => setIsAddingService(false)}
                className="px-4 py-2 border border-primary rounded text-secondary hover:bg-surface"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateService}
                className="btn-primary"
              >
                Create Service
              </button>
            </div>
          </div>
        </Modal>
      </div>
    </DashboardLayout>
  );
}