// ui/app/providers/[providerId]/services/[serviceId]/page.tsx

"use client";

import React, { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/widgets/layout';
import { getProviderService, updateProviderService, getServicePackageDefaults } from '@/shared/api';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { ChevronDown, ChevronRight, Eye, X } from 'lucide-react';
import { Modal } from '@/shared/ui';

// Collapsible Section Component
function CollapsibleSection({
  title,
  description,
  isExpanded,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-primary rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface hover:bg-card transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-secondary" />
          ) : (
            <ChevronRight className="h-4 w-4 text-secondary" />
          )}
          <span className="text-sm font-medium text-primary">{title}</span>
          {description && (
            <span className="text-muted text-xs">- {description}</span>
          )}
        </div>
      </button>
      {isExpanded && (
        <div className="px-4 py-4 bg-card">
          {children}
        </div>
      )}
    </div>
  );
}

export default function ServiceConfigPage({
  params
}: {
  params: Promise<{ providerId: string; serviceId: string }>
}) {
  const { providerId, serviceId } = use(params);
  const router = useRouter();
  const { user } = useUser();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [service, setService] = useState<any>(null);

  // Collapsible section states
  const [paramSchemaExpanded, setParamSchemaExpanded] = useState(false);
  const [resultSchemaExpanded, setResultSchemaExpanded] = useState(false);
  const [workerConfigExpanded, setWorkerConfigExpanded] = useState(false);

  // Example parameters modal state
  const [exampleModalOpen, setExampleModalOpen] = useState(false);

  // Reset to defaults state
  const [resetting, setResetting] = useState(false);

  const [formData, setFormData] = useState({
    display_name: '',
    description: '',
    endpoint: '',
    parameter_schema: '{}',
    result_schema: '{}',
    example_parameters: '{}',
    is_active: true,
    client_metadata: '{}',
  });

  useEffect(() => {
    async function fetchService() {
      try {
        setLoading(true);
        const serviceData = await getProviderService(serviceId);
        setService(serviceData);

        // Populate form with existing data
        setFormData({
          display_name: serviceData.display_name || '',
          description: serviceData.description || '',
          endpoint: serviceData.endpoint || '',
          parameter_schema: JSON.stringify(serviceData.parameter_schema || {}, null, 2),
          result_schema: JSON.stringify(serviceData.result_schema || {}, null, 2),
          example_parameters: JSON.stringify(serviceData.example_parameters || {}, null, 2),
          is_active: serviceData.is_active !== false,
          client_metadata: JSON.stringify(serviceData.client_metadata || {}, null, 2),
        });

        setError(null);
      } catch (err: unknown) {
        console.error('Failed to load service:', err);
        setError(err instanceof Error ? err.message : 'Failed to load service');
      } finally {
        setLoading(false);
      }
    }

    fetchService();
  }, [serviceId]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;

    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setFormData(prev => ({
        ...prev,
        [name]: checked
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Confirm system-wide change
    const confirmed = window.confirm(
      '⚠️ WARNING: System-Wide Change\n\n' +
      'This service configuration is shared across ALL organizations.\n\n' +
      'Any changes you make will immediately affect all users and workflows using this service.\n\n' +
      'Are you sure you want to save these changes?'
    );

    if (!confirmed) {
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Parse JSON fields
      let parameter_schema = {};
      let result_schema = {};
      let example_parameters = {};
      let client_metadata = {};

      try {
        if (formData.parameter_schema.trim()) {
          parameter_schema = JSON.parse(formData.parameter_schema);
        }
      } catch (err) {
        throw new Error('Invalid JSON in parameter schema field');
      }

      try {
        if (formData.result_schema.trim()) {
          result_schema = JSON.parse(formData.result_schema);
        }
      } catch (err) {
        throw new Error('Invalid JSON in result schema field');
      }

      try {
        if (formData.example_parameters.trim()) {
          example_parameters = JSON.parse(formData.example_parameters);
        }
      } catch (err) {
        throw new Error('Invalid JSON in example parameters field');
      }

      try {
        if (formData.client_metadata.trim()) {
          client_metadata = JSON.parse(formData.client_metadata);
        }
      } catch (err) {
        throw new Error('Invalid JSON in client metadata field');
      }

      await updateProviderService(serviceId, {
        display_name: formData.display_name || undefined,
        description: formData.description || null,
        endpoint: formData.endpoint || null,
        parameter_schema: Object.keys(parameter_schema).length > 0 ? parameter_schema : undefined,
        result_schema: Object.keys(result_schema).length > 0 ? result_schema : undefined,
        example_parameters: Object.keys(example_parameters).length > 0 ? example_parameters : undefined,
        is_active: formData.is_active,
        client_metadata: Object.keys(client_metadata).length > 0 ? client_metadata : undefined,
      });

      toast({ title: 'Service updated', description: 'Service configuration updated successfully!', variant: 'success' });
      router.push(`/providers/${providerId}`);
    } catch (err: unknown) {
      console.error('Failed to update service:', err);
      setError(err instanceof Error ? err.message : 'Failed to update service');
      setSaving(false);
    }
  };

  // Reset form to package defaults (reads original values from disk)
  const handleResetToDefaults = async () => {
    // Confirm with warning about system-wide impact
    const confirmed = window.confirm(
      '⚠️ Reset to Package Defaults\n\n' +
      'This will reset the form to the original values from the provider package.\n\n' +
      'Note: This only updates the form. You must click "Save Changes" to apply the reset, ' +
      'which will affect ALL organizations using this service.\n\n' +
      'Continue?'
    );

    if (!confirmed) {
      return;
    }

    setResetting(true);
    setError(null);

    try {
      const defaults = await getServicePackageDefaults(serviceId);

      setFormData({
        display_name: defaults.display_name || '',
        description: defaults.description || '',
        endpoint: defaults.endpoint || '',
        parameter_schema: JSON.stringify(defaults.parameter_schema || {}, null, 2),
        result_schema: JSON.stringify(defaults.result_schema || {}, null, 2),
        example_parameters: JSON.stringify(defaults.example_parameters || {}, null, 2),
        is_active: formData.is_active, // Keep current active status
        client_metadata: JSON.stringify(defaults.client_metadata || {}, null, 2),
      });

      toast({ title: 'Form reset', description: 'Reset to package defaults. Click "Save Changes" to apply.', variant: 'default' });
    } catch (err: unknown) {
      console.error('Failed to fetch package defaults:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch package defaults. The package files may not be available.');
    } finally {
      setResetting(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="spinner-lg mx-auto"></div>
              <p className="mt-4 text-secondary">Loading service...</p>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // Check if user is super_admin (for editing permissions)
  const isSuperAdmin = user?.role === 'super_admin';

  if (error && !service) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
          <div className="alert alert-error">
            <h1 className="text-2xl font-bold text-danger mb-2">Error</h1>
            <p className="text-danger">{error}</p>
            <button
              onClick={() => router.push(`/providers/${providerId}`)}
              className="mt-4 text-info hover:text-info"
            >
              Back to provider
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-primary">
            Configure Service: {service?.service_id}
          </h1>
          <p className="text-sm mt-1 text-secondary">
            Update service configuration and settings
          </p>
        </div>

        {/* System-wide warning banner */}
        {isSuperAdmin && (
          <div className="mb-6 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <svg className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <h3 className="text-sm font-semibold text-warning">
                  System-Wide Configuration
                </h3>
                <p className="text-sm text-warning mt-1">
                  This service is shared across <strong>all organizations</strong>. Changes will immediately affect all users and workflows using this service.
                </p>
              </div>
            </div>
          </div>
        )}

        {!isSuperAdmin && (
          <div className="mb-6 bg-info-subtle border border-info rounded-md p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-info" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-info">
                  Viewing service configuration (read-only).
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 bg-danger-subtle border border-danger rounded-md p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-danger" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-danger">{error}</p>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-card shadow rounded-lg p-6">
          <div className="space-y-6">
            {/* ===== BASIC INFO SECTION (Always Visible) ===== */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-primary uppercase tracking-wide">
                Basic Information
              </h3>

              {/* Display Name */}
              <div>
                <label htmlFor="display_name" className="form-label">
                  Display Name
                </label>
                <input
                  type="text"
                  id="display_name"
                  name="display_name"
                  value={formData.display_name}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="mt-1 block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder="e.g., HTTP GET Request"
                />
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="form-label">
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={2}
                  value={formData.description}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="mt-1 block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder="Describe what this service does"
                />
              </div>

              {/* Endpoint */}
              <div>
                <label htmlFor="endpoint" className="form-label">
                  Endpoint
                </label>
                <input
                  type="text"
                  id="endpoint"
                  name="endpoint"
                  value={formData.endpoint}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="mt-1 block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder="e.g., /api/v1/get"
                />
              </div>

              {/* Is Active */}
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  name="is_active"
                  checked={formData.is_active}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="h-4 w-4 text-info focus:ring-blue-500 border-primary rounded disabled:opacity-60 disabled:cursor-not-allowed"
                />
                <label htmlFor="is_active" className="ml-2 block text-sm text-secondary">
                  Service is active
                </label>
              </div>

              {/* View Example Parameters Button */}
              {formData.example_parameters && formData.example_parameters !== '{}' && (
                <div>
                  <button
                    type="button"
                    onClick={() => setExampleModalOpen(true)}
                    className="inline-flex items-center gap-2 text-sm text-info hover:text-info dark:hover:text-info"
                  >
                    <Eye className="h-4 w-4" />
                    View Example Parameters
                  </button>
                </div>
              )}
            </div>

            {/* ===== COLLAPSIBLE SECTIONS ===== */}
            <div className="space-y-3 pt-4 border-t border-primary">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-primary uppercase tracking-wide">
                  Schema Configuration
                </h3>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs text-warning">
                    <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span>These settings are managed by the provider package. Edit with caution.</span>
                  </div>
                  {isSuperAdmin && (
                    <button
                      type="button"
                      onClick={handleResetToDefaults}
                      disabled={resetting}
                      className="text-xs text-info hover:text-info dark:hover:text-info hover:underline disabled:opacity-50"
                    >
                      {resetting ? 'Loading defaults...' : 'Reset to Package Defaults'}
                    </button>
                  )}
                </div>
              </div>

              {/* Parameter Schema (Collapsible) */}
              <CollapsibleSection
                title="Parameter Schema"
                description="JSON Schema defining input parameters"
                isExpanded={paramSchemaExpanded}
                onToggle={() => setParamSchemaExpanded(!paramSchemaExpanded)}
              >
                <textarea
                  id="parameter_schema"
                  name="parameter_schema"
                  rows={12}
                  value={formData.parameter_schema}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"type": "object", "properties": {...}}'
                />
              </CollapsibleSection>

              {/* Result Schema (Collapsible) */}
              <CollapsibleSection
                title="Result Schema"
                description="JSON Schema defining output structure"
                isExpanded={resultSchemaExpanded}
                onToggle={() => setResultSchemaExpanded(!resultSchemaExpanded)}
              >
                <textarea
                  id="result_schema"
                  name="result_schema"
                  rows={12}
                  value={formData.result_schema}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"type": "object", "properties": {...}}'
                />
              </CollapsibleSection>

              {/* Worker Configuration (Collapsible) */}
              <CollapsibleSection
                title="Worker Configuration"
                description="System settings for job execution"
                isExpanded={workerConfigExpanded}
                onToggle={() => setWorkerConfigExpanded(!workerConfigExpanded)}
              >
                <textarea
                  id="client_metadata"
                  name="client_metadata"
                  rows={8}
                  value={formData.client_metadata}
                  onChange={handleChange}
                  disabled={!isSuperAdmin}
                  className="block w-full rounded-md border-primary shadow-sm focus:border-info focus:ring-blue-500 sm:text-sm px-3 py-2 font-mono text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder='{"method": "POST", "requires_credentials": true}'
                />
              </CollapsibleSection>
            </div>
          </div>

          {/* Example Parameters Modal */}
          <Modal
            isOpen={exampleModalOpen}
            onClose={() => setExampleModalOpen(false)}
            title="Example Parameters"
            size="lg"
          >
            <div className="p-6">
              <div className="overflow-y-auto max-h-[60vh]">
                <pre className="bg-surface rounded-md p-4 overflow-x-auto text-xs font-mono text-primary">
                  {formData.example_parameters}
                </pre>
              </div>
              <div className="flex justify-end mt-4">
                <button
                  type="button"
                  onClick={() => setExampleModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-secondary bg-card rounded-md hover:bg-input"
                >
                  Close
                </button>
              </div>
            </div>
          </Modal>

          {/* Form Actions */}
          {isSuperAdmin && (
            <div className="mt-8 flex items-center justify-end space-x-4">
              <button
                type="button"
                onClick={() => router.push(`/providers/${providerId}`)}
                disabled={saving}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="btn-primary"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}

          {/* Back button for non-super_admin users */}
          {!isSuperAdmin && (
            <div className="mt-8 flex items-center justify-end">
              <button
                type="button"
                onClick={() => router.push(`/providers/${providerId}`)}
                className="px-4 py-2 border border-primary rounded-md shadow-sm text-sm font-medium text-secondary bg-card hover:bg-surface focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Back to Provider
              </button>
            </div>
          )}
        </form>
      </div>
    </DashboardLayout>
  );
}
