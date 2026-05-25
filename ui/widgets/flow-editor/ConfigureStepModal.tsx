// ui/widgets/flow-editor/ConfigureStepModal.tsx

'use client';

import { useEffect, useState } from 'react';
import { X, AlertCircle, CheckCircle } from 'lucide-react';
import { Modal } from '@/shared/ui';
import { Step } from '@/entities/workflow';
import { getProviders, getProviderServices, getProviderService, getProviderCredentials } from '@/shared/api';
import type { Provider, ProviderServiceResponse, ProviderCredential } from '@/shared/api/providers';

type Service = ProviderServiceResponse;
type Credential = ProviderCredential;

interface ConfigureStepModalProps {
  isOpen: boolean;
  step: Step | null;
  onClose: () => void;
  onSave: (updatedStep: Step) => void;
}

export default function ConfigureStepModal({
  isOpen,
  step,
  onClose,
  onSave,
}: ConfigureStepModalProps) {
  const [selectedProviderId, setSelectedProviderId] = useState<string>('');
  const [selectedServiceId, setSelectedServiceId] = useState<string>('');
  const [selectedCredentialId, setSelectedCredentialId] = useState<string>('');

  const [providers, setProviders] = useState<Provider[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [serviceDetails, setServiceDetails] = useState<Service | null>(null);
  const [credentials, setCredentials] = useState<Credential[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingServices, setLoadingServices] = useState(false);
  const [loadingServiceDetails, setLoadingServiceDetails] = useState(false);
  const [loadingCredentials, setLoadingCredentials] = useState(false);

  // Reset state when modal opens with new step
  useEffect(() => {
    if (isOpen && step) {
      setSelectedProviderId(step.provider_id || '');
      setSelectedServiceId(step.service_id || '');
      setSelectedCredentialId(step.credential_id || '');
      setError(null);

      // Fetch providers on mount
      fetchProviders();

      // If step already has provider, fetch its services
      if (step.provider_id) {
        fetchServices(step.provider_id);
        fetchCredentials(step.provider_id);
      }

      // If step already has service, fetch details
      if (step.service_id) {
        fetchServiceDetails(step.service_id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- step fields accessed for initial load only
  }, [isOpen, step?.id]);

  const fetchProviders = async () => {
    try {
      setLoading(true);
      const data = await getProviders();
      setProviders(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load providers');
    } finally {
      setLoading(false);
    }
  };

  const fetchServices = async (providerId: string) => {
    try {
      setLoadingServices(true);
      const data = await getProviderServices(providerId);
      setServices(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load services');
    } finally {
      setLoadingServices(false);
    }
  };

  const fetchServiceDetails = async (serviceId: string) => {
    try {
      setLoadingServiceDetails(true);
      const data = await getProviderService(serviceId);
      setServiceDetails(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load service details');
    } finally {
      setLoadingServiceDetails(false);
    }
  };

  const fetchCredentials = async (providerId: string) => {
    try {
      setLoadingCredentials(true);
      const data = await getProviderCredentials(providerId);
      setCredentials(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load credentials');
    } finally {
      setLoadingCredentials(false);
    }
  };

  const handleProviderChange = (providerId: string) => {
    setSelectedProviderId(providerId);
    setSelectedServiceId(''); // Reset service selection
    setSelectedCredentialId(''); // Reset credential selection
    setServices([]);
    setServiceDetails(null);
    setCredentials([]);

    if (providerId) {
      fetchServices(providerId);
      fetchCredentials(providerId);
    }
  };

  const handleServiceChange = (serviceId: string) => {
    setSelectedServiceId(serviceId);
    setServiceDetails(null);

    if (serviceId) {
      fetchServiceDetails(serviceId);
    }
  };

  const handleSave = () => {
    if (!step) return;

    // Build updated step
    const updatedStep: Step = {
      ...step,
      provider_id: selectedProviderId || undefined,
      service_id: selectedServiceId || undefined,
      credential_id: selectedCredentialId || undefined,
    };

    // Auto-populate outputs from result_schema if service details are loaded
    if (serviceDetails?.result_schema?.properties) {
      const outputs: Record<string, any> = {};

      Object.entries(serviceDetails.result_schema.properties).forEach(([fieldName, fieldDef]: [string, any]) => {
        outputs[fieldName] = {
          path: fieldName,
          type: fieldDef.type || 'string',
          description: fieldDef.description || '',
        };
      });

      updatedStep.outputs = outputs;
    }

    onSave(updatedStep);
    onClose();
  };

  const isComplete = selectedProviderId && selectedServiceId;
  const isFullyConfigured = isComplete && selectedCredentialId;

  if (!step) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <div className="px-4 pb-4 pt-5 sm:px-6 sm:pb-6 sm:pt-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-lg font-semibold leading-6 text-primary">
            Configure Step: {step.name}
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted hover:text-secondary"
          >
            <X size={20} />
          </button>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-4 p-3 bg-danger-subtle rounded-md flex items-start gap-2">
            <AlertCircle className="text-danger flex-shrink-0 mt-0.5" size={16} />
            <p className="text-sm text-danger">{error}</p>
          </div>
        )}

        {/* Content */}
        <div className="space-y-4">
          {/* Provider Selection */}
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Provider <span className="text-danger">*</span>
            </label>
            {loading ? (
              <div className="text-muted text-sm">Loading providers...</div>
            ) : (
              <select
                value={selectedProviderId}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="w-full p-2 text-sm border border-primary rounded-md bg-card text-primary"
              >
                <option value="">-- Select Provider --</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            )}
            {providers.length === 0 && !loading && (
              <p className="mt-1 text-xs text-secondary">
                No providers available. Please configure providers first.
              </p>
            )}
          </div>

          {/* Service Selection */}
          {selectedProviderId && (
            <div>
              <label className="block text-sm font-medium text-secondary mb-2">
                Service <span className="text-danger">*</span>
              </label>
              {loadingServices ? (
                <div className="text-muted text-sm">Loading services...</div>
              ) : (
                <select
                  value={selectedServiceId}
                  onChange={(e) => handleServiceChange(e.target.value)}
                  className="w-full p-2 text-sm border border-primary rounded-md bg-card text-primary"
                  disabled={!selectedProviderId}
                >
                  <option value="">-- Select Service --</option>
                  {services.map((service) => (
                    <option key={service.id} value={service.service_id}>
                      {service.display_name || service.service_id}
                    </option>
                  ))}
                </select>
              )}
              {services.length === 0 && !loadingServices && (
                <p className="mt-1 text-xs text-secondary">
                  No services available for this provider.
                </p>
              )}
            </div>
          )}

          {/* Credential Selection */}
          {selectedProviderId && (
            <div>
              <label className="block text-sm font-medium text-secondary mb-2">
                Credential <span className="text-muted text-xs">(Optional - can add later)</span>
              </label>
              {loadingCredentials ? (
                <div className="text-muted text-sm">Loading credentials...</div>
              ) : (
                <>
                  <select
                    value={selectedCredentialId}
                    onChange={(e) => setSelectedCredentialId(e.target.value)}
                    className="w-full p-2 text-sm border border-primary rounded-md bg-card text-primary"
                    disabled={!selectedProviderId}
                  >
                    <option value="">-- Select Credential (Optional) --</option>
                    {credentials.map((credential) => (
                      <option key={credential.id} value={credential.id}>
                        {credential.name}
                        {credential.expires_at && ` (expires: ${new Date(credential.expires_at).toLocaleDateString()})`}
                      </option>
                    ))}
                  </select>
                  {credentials.length === 0 && !loadingCredentials && (
                    <p className="mt-1 text-xs text-warning">
                      No credentials found. You can configure the step and add credentials later.
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {/* Service Details Preview */}
          {loadingServiceDetails && (
            <div className="p-3 bg-card rounded-md">
              <p className="text-muted text-sm">Loading service details...</p>
            </div>
          )}

          {serviceDetails && (
            <div className="p-3 bg-card rounded-md border border-primary">
              <h4 className="text-sm font-medium text-primary mb-2">
                Service Information
              </h4>
              <p className="text-xs text-secondary mb-3">
                {serviceDetails.display_name}
              </p>

              {/* Output Fields Preview */}
              {serviceDetails.result_schema?.properties && (
                <div className="mt-3">
                  <h5 className="text-xs font-medium text-secondary mb-2">
                    Available Output Fields (for mapping):
                  </h5>
                  <div className="space-y-1">
                    {Object.entries(serviceDetails.result_schema.properties).map(([fieldName, fieldDef]: [string, any]) => (
                      <div key={fieldName} className="flex items-start gap-2 text-xs">
                        <CheckCircle size={12} className="text-success mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="font-mono text-info">{fieldName}</span>
                          <span className="text-muted"> ({fieldDef.type || 'any'})</span>
                          {fieldDef.description && (
                            <span className="text-secondary"> - {fieldDef.description}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Configuration Status */}
          {isComplete && (
            <div className={`p-3 rounded-md ${isFullyConfigured ? 'bg-success-subtle' : 'bg-warning-subtle'}`}>
              <p className={`text-sm ${isFullyConfigured ? 'text-success' : 'text-warning'}`}>
                {isFullyConfigured
                  ? '✓ Step fully configured. You can now map fields to other steps.'
                  : '⚠️ Step partially configured. Add a credential to complete configuration.'}
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-secondary bg-card border border-primary rounded-md hover:bg-surface"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!isComplete}
            className={`btn-primary ${!isComplete ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Save Configuration
          </button>
        </div>
      </div>
    </Modal>
  );
}
