// ui/app/providers/resources/[resourceId]/page.tsx

"use client";

import { useRouter, useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { DashboardLayout } from "@/widgets/layout";
import { formatDate } from "@/shared/lib/dateFormatter";
import { ArrowLeft } from "lucide-react";
import { getProviderResource } from "@/shared/api";

export default function ResourceDetailsPage() {
  // Next.js 15+: params is async, use useParams() hook for client components
  const params = useParams();
  const resourceId = params.resourceId as string;
  const router = useRouter();
  const [resource, setResource] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchResource() {
      try {
        setIsLoading(true);
        const data = await getProviderResource(resourceId);
        setResource(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch resource:', err);
        setError(err instanceof Error ? err.message : 'Failed to load resource details');
      } finally {
        setIsLoading(false);
      }
    }

    fetchResource();
  }, [resourceId]);

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
          <div className="text-center py-10">
            <div className="spinner-md"></div>
            <p className="mt-2 text-secondary">Loading resource details...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error || !resource) {
    return (
      <DashboardLayout>
        <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
          <div className="alert alert-error">
            <h3 className="text-danger font-medium">Error</h3>
            <p className="text-danger">{error || "Resource not found"}</p>
            <button
              onClick={() => router.push("/providers/resources")}
              className="mt-2 text-info hover:underline"
            >
              Back to Resources
            </button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        {/* Header with Back Button */}
        <div className="mb-8">
          <button
            onClick={() => router.push("/providers/resources")}
            className="flex items-center text-info hover:underline mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Resources
          </button>

          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-primary">
                {resource.client_metadata?.name || `Resource ${resourceId.slice(0, 8)}`}
              </h1>
              <p className="text-secondary mt-1">
                {resource.client_metadata?.description || `${resource.resource_type} resource`}
              </p>
            </div>

            <span
              className={`px-3 py-1 text-sm rounded-full ${
                resource.status === "active"
                  ? "bg-success-subtle text-success"
                  : resource.status === "pending"
                    ? "bg-warning-subtle text-warning"
                    : resource.status === "suspended" || resource.status === "inactive"
                      ? "bg-surface text-secondary"
                      : "bg-danger-subtle text-danger"
              }`}
            >
              {resource.status.charAt(0).toUpperCase() + resource.status.slice(1)}
            </span>
          </div>
        </div>

        {/* Resource Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          <div className="bg-card border border-primary rounded-lg p-6">
            <h3 className="text-sm font-medium text-secondary mb-1">Resource Type</h3>
            <p className="text-lg font-semibold text-primary capitalize">{resource.resource_type}</p>
          </div>

          <div className="bg-card border border-primary rounded-lg p-6">
            <h3 className="text-sm font-medium text-secondary mb-1">Status</h3>
            <p className="text-lg font-semibold text-primary capitalize">{resource.status}</p>
          </div>

          <div className="bg-card border border-primary rounded-lg p-6">
            <h3 className="text-sm font-medium text-secondary mb-1">Updated</h3>
            <p className="text-lg font-semibold text-primary">
              {formatDate(resource.updated_at)}
            </p>
          </div>
        </div>

        {/* Requirements */}
        {resource.requirements && (
          <div className="bg-card border border-primary rounded-lg p-6 mb-8">
            <h2 className="text-xl font-semibold text-primary mb-4">Resource Requirements</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {resource.requirements.cpu && (
                <div className="flex justify-between border-b border-primary pb-2">
                  <span className="text-secondary">CPU Cores</span>
                  <span className="text-primary font-medium">{resource.requirements.cpu}</span>
                </div>
              )}
              {resource.requirements.memory && (
                <div className="flex justify-between border-b border-primary pb-2">
                  <span className="text-secondary">Memory</span>
                  <span className="text-primary font-medium">{resource.requirements.memory} GB</span>
                </div>
              )}
              {resource.requirements.gpu && (
                <div className="flex justify-between border-b border-primary pb-2">
                  <span className="text-secondary">GPU</span>
                  <span className="text-primary font-medium">{resource.requirements.gpu}</span>
                </div>
              )}
              {resource.requirements.storage && (
                <div className="flex justify-between border-b border-primary pb-2">
                  <span className="text-secondary">Storage</span>
                  <span className="text-primary font-medium">{resource.requirements.storage} GB</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Client Metadata */}
        {resource.client_metadata && Object.keys(resource.client_metadata).length > 0 && (
          <div className="bg-card border border-primary rounded-lg p-6 mb-8">
            <h2 className="text-xl font-semibold text-primary mb-4">
              Additional Information
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(resource.client_metadata).map(([key, value]) => (
                <div key={key} className="flex justify-between border-b border-primary pb-2">
                  <span className="text-secondary capitalize">{key.replace(/_/g, ' ')}</span>
                  <span className="text-primary font-medium">{JSON.stringify(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Resource Information */}
        <div className="bg-card border border-primary rounded-lg p-6">
          <h2 className="text-xl font-semibold text-primary mb-4">Resource Details</h2>

          <div className="space-y-3">
            <div>
              <span className="text-muted">Resource ID</span>
              <p className="text-primary font-mono">{resource.id}</p>
            </div>

            <div>
              <span className="text-muted">Provider ID</span>
              <p className="text-primary font-mono">{resource.provider_id}</p>
            </div>

            <div>
              <span className="text-muted">Organization ID</span>
              <p className="text-primary font-mono">{resource.organization_id}</p>
            </div>

            {resource.external_id && (
              <div>
                <span className="text-muted">External ID</span>
                <p className="text-primary font-mono">{resource.external_id}</p>
              </div>
            )}

            <div>
              <span className="text-muted">Created At</span>
              <p className="text-primary">{formatDate(resource.created_at)}</p>
            </div>

            <div>
              <span className="text-muted">Last Updated</span>
              <p className="text-primary">{formatDate(resource.updated_at)}</p>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
