// ui/app/providers/components/ServiceConfigForm.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { ServiceDefinition } from '@/entities/provider';
import JsonSchemaForm from '@/shared/ui/JsonSchemaForm';
import { ParameterSchema, serviceParametersToSchema } from '@/shared/types/schema';
import { getProviderService, testProviderService } from '@/shared/api';

interface ServiceConfigFormProps {
  providerId: string;
  serviceId: string;
  initialParameters?: Record<string, any>;
  onParametersChange?: (parameters: Record<string, any>) => void;
  onSubmit?: (parameters: Record<string, any>) => void;
  readOnly?: boolean;
  showTest?: boolean;
}

export default function ServiceConfigForm({
  providerId,
  serviceId,
  initialParameters = {},
  onParametersChange,
  onSubmit,
  readOnly = false,
  showTest = true
}: ServiceConfigFormProps) {
  const [service, setService] = useState<ServiceDefinition | null>(null);
  const [parameterSchema, setParameterSchema] = useState<ParameterSchema | null>(null);
  const [parameters, setParameters] = useState<Record<string, any>>(initialParameters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);

  // Fetch service details
  useEffect(() => {
    async function fetchServiceDetails() {
      try {
        setLoading(true);
        const data = await getProviderService(serviceId);
        setService(data);

        // Generate parameter schema from service parameters
        if (data && data.parameters) {
          const schema = serviceParametersToSchema(data.parameters as Record<string, { type: string; required?: boolean; default?: unknown; description?: string; enum?: unknown[]; properties?: Record<string, unknown> }>);
          setParameterSchema(schema);
        }
        
        setError(null);
      } catch (err) {
        console.error('Failed to fetch service details:', err);
        setError('Failed to load service configuration. Please try again later.');
      } finally {
        setLoading(false);
      }
    }
    
    fetchServiceDetails();
  }, [providerId, serviceId]);

  // Handle parameter changes
  const handleParametersChange = (newParameters: Record<string, any>) => {
    setParameters(newParameters);
    onParametersChange?.(newParameters);
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSubmit) {
      onSubmit(parameters);
    }
  };

  // Test service with current parameters
  const handleTestService = async () => {
    try {
      setTestLoading(true);
      setTestResult(null);
      setTestError(null);
      
      const data = await testProviderService(providerId, serviceId, parameters);
      setTestResult(data);
    } catch (err: unknown) {
      console.error('Service test failed:', err);
      setTestError(err instanceof Error ? err.message : 'Service test failed. Please try again.');
    } finally {
      setTestLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-center">
        <div className="spinner-md mx-auto"></div>
        <p className="mt-2 text-secondary">Loading service configuration...</p>
      </div>
    );
  }

  if (error || !service) {
    return (
      <div className="p-4 bg-danger-subtle border border-danger rounded-md">
        <h3 className="text-danger font-medium">Error</h3>
        <p className="text-danger">{error || 'Service not found'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-card shadow-sm rounded-lg p-6 border">
        <div className="mb-4">
          <h3 className="text-lg font-medium">{service.name}</h3>
          <p className="text-secondary text-sm">{service.description}</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          {parameterSchema ? (
            <JsonSchemaForm 
              schema={parameterSchema}
              initialData={initialParameters}
              exampleParameters={service.example_parameters || {}}
              onChange={handleParametersChange}
              className={readOnly ? 'opacity-70 pointer-events-none' : ''}
            />
          ) : (
            <div className="p-4 bg-surface rounded-md">
              <p className="text-secondary text-sm">No parameters available for this service.</p>
            </div>
          )}
          
          <div className="mt-6 flex justify-between items-center">
            {showTest && (
              <button
                type="button"
                onClick={handleTestService}
                disabled={testLoading || readOnly}
                className="px-4 py-2 bg-card text-primary rounded-md hover:bg-input disabled:opacity-50"
              >
                {testLoading ? 'Testing...' : 'Test Service'}
              </button>
            )}
            
            {onSubmit && (
              <button
                type="submit"
                disabled={readOnly}
                className="btn-primary"
              >
                Save Configuration
              </button>
            )}
          </div>
        </form>
      </div>
      
      {/* Test Results */}
      {testResult && (
        <div className="bg-card shadow-sm rounded-lg p-6 border">
          <h3 className="text-lg font-medium mb-2">Test Results</h3>
          <div className="bg-surface p-4 rounded-md">
            <pre className="text-sm overflow-auto max-h-60">
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </div>
        </div>
      )}
      
      {testError && (
        <div className="alert alert-error">
          <h3 className="text-danger font-medium mb-2">Test Failed</h3>
          <p className="text-danger">{testError}</p>
        </div>
      )}
      
      {/* Service Info */}
      <div className="bg-card shadow-sm rounded-lg p-6 border">
        <h3 className="text-lg font-medium mb-4">Service Information</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-muted text-sm">Service ID</p>
            <p className="font-mono text-sm">{service.id}</p>
          </div>
          <div>
            <p className="text-muted text-sm">Provider ID</p>
            <p className="font-mono text-sm">{providerId}</p>
          </div>
          <div>
            <p className="text-muted text-sm">Service Type</p>
            <p>{service.serviceType || 'Not specified'}</p>
          </div>
          <div>
            <p className="text-muted text-sm">Status</p>
            <p className="capitalize">Active</p>
          </div>
        </div>
      </div>
    </div>
  );
}