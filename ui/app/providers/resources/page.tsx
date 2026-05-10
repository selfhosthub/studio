// ui/app/providers/resources/page.tsx

"use client";

import { useUser } from "@/entities/user";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardLayout } from "@/widgets/layout";
import { PlusCircle, Search, Filter } from "lucide-react";
import { formatDate } from "@/shared/lib/dateFormatter";
import { getProviderResourcesByOrganization } from "@/shared/api";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  TableHeaderCell,
  TableContainer,
  StatusBadge,
  ActionButton,
} from "@/shared/ui";

interface Resource {
  id: string;
  provider_id?: string;
  resource_type: string;
  resource_id?: string;
  external_id?: string | null;
  status: string;
  organization_id: string;
  properties?: Record<string, unknown> | null;
  requirements?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export default function ProviderResources() {
  const { user, status } = useUser();
  const router = useRouter();
  const [resources, setResources] = useState<Resource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.org_id) return;

    async function fetchResources() {
      try {
        setIsLoading(true);
        const fetchedResources = await getProviderResourcesByOrganization(user!.org_id!);
        setResources(fetchedResources);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch resources:', err);
        setError(err instanceof Error ? err.message : 'Failed to load resources');
      } finally {
        setIsLoading(false);
      }
    }

    fetchResources();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- user?.org_id is sufficient
  }, [user?.org_id]);

  return (
    <DashboardLayout>
      <div className="px-4 sm:px-6 lg:px-8 py-8 w-full max-w-9xl mx-auto">
        <div className="sm:flex sm:justify-between sm:items-center mb-8">
          <div className="mb-4 sm:mb-0">
            <h1 className="text-2xl md:text-3xl font-bold text-primary">
              Provider Resources
            </h1>
            <p className="text-sm text-secondary mt-1">
              Monitor and manage resources used by providers
            </p>
          </div>
          <div className="grid grid-flow-col sm:auto-cols-max justify-start sm:justify-end gap-2">
            <button
              className="btn-primary"
              onClick={async () => {
                if (!user?.org_id) return;
                try {
                  setIsLoading(true);
                  const fetchedResources = await getProviderResourcesByOrganization(user!.org_id!);
                  setResources(fetchedResources);
                  setError(null);
                } catch (err) {
                  console.error('Failed to refresh resources:', err);
                  setError(err instanceof Error ? err.message : 'Failed to refresh resources');
                } finally {
                  setIsLoading(false);
                }
              }}
            >
              <svg
                className="w-4 h-4 fill-current opacity-50 shrink-0"
                viewBox="0 0 16 16"
                style={{ maxWidth: "16px", maxHeight: "16px" }}
              >
                <path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z" />
                <path
                  fillRule="evenodd"
                  d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"
                />
              </svg>
              <span className="hidden xs:block ml-2">Refresh Status</span>
            </button>
          </div>
        </div>

        {error ? (
          <div className="alert alert-error">
            <p className="text-danger">{error}</p>
          </div>
        ) : isLoading ? (
          <div className="text-center py-10">
            <div className="spinner-md"></div>
            <p className="mt-2 text-secondary">
              Loading resources...
            </p>
          </div>
        ) : resources.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted">No resources found for your organization.</p>
          </div>
        ) : (
          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Resource ID</TableHeaderCell>
                  <TableHeaderCell>Provider ID</TableHeaderCell>
                  <TableHeaderCell>Type</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Properties</TableHeaderCell>
                  <TableHeaderCell>Created</TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resources.map((resource) => (
                  <TableRow key={resource.id}>
                    <TableCell>
                      <div className="font-medium text-sm">{resource.resource_id}</div>
                    </TableCell>
                    <TableCell>
                      <div className="text-xs text-secondary font-mono">
                        {(resource.provider_id || '').slice(0, 8)}...
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="px-2 py-1 text-xs font-medium rounded bg-info-subtle text-info">
                        {resource.resource_type}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={resource.status}
                        variant={
                          resource.status.toLowerCase() === "active" ||
                          resource.status.toLowerCase() === "available"
                            ? "success"
                            : resource.status.toLowerCase() === "in-use" ||
                                resource.status.toLowerCase() === "in_use"
                              ? "info"
                              : "warning"
                        }
                      />
                    </TableCell>
                    <TableCell>
                      {resource.properties ? (
                        <div className="text-xs">
                          {Object.entries(resource.properties).slice(0, 2).map(([key, value]) => (
                            <div key={key} className="text-secondary">
                              <span className="font-medium">{key}:</span> {String(value).slice(0, 30)}
                              {String(value).length > 30 ? '...' : ''}
                            </div>
                          ))}
                          {Object.keys(resource.properties).length > 2 && (
                            <div className="text-secondary dark:text-secondary">
                              +{Object.keys(resource.properties).length - 2} more
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted dark:text-secondary">No properties</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{formatDate(resource.created_at || '')}</div>
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center space-x-2">
                        <ActionButton
                          variant="navigate"
                          onClick={() =>
                            router.push(`/providers/resources/${resource.id}`)
                          }
                        >
                          Details
                        </ActionButton>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </div>
    </DashboardLayout>
  );
}
