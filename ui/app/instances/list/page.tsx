// ui/app/instances/list/page.tsx

"use client";

import { DashboardLayout } from "@/widgets/layout";
import {
  ActionButton,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHeader,
  TableHeaderCell,
  TableRow,
  SearchInput,
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
} from "@/shared/ui";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getInstances, getInstancesByWorkflow, deleteInstance, getWorkflows } from "@/shared/api";
import { InstanceStatus, type InstanceResponse } from "@/shared/types/api";
import { X } from "lucide-react";
import { PAGE_SIZE_OPTIONS, getStoredPageSize } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';
const PAGE_SIZE_KEY = listPageSizeKey('instances');

function InstancesListContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();
  const [instances, setInstances] = useState<InstanceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => getStoredPageSize(PAGE_SIZE_KEY, 25));
  const [totalCount, setTotalCount] = useState(0);
  const [workflowName, setWorkflowName] = useState<string | null>(null);

  // Redirect super_admin to dashboard - they don't have org-level instances
  useEffect(() => {
    if (authStatus === 'authenticated' && user?.role === 'super_admin') {
      router.push('/dashboard');
    }
  }, [authStatus, user?.role, router]);

  const activeTab = (searchParams.get('status') || 'all') as
    | "all"
    | "pending"
    | "processing"
    | "completed"
    | "failed"
    | "cancelled";
  const workflowFilter = searchParams.get('workflow');

  const tabs = [
    { id: "all", label: "All" },
    { id: "pending", label: "Pending" },
    { id: "processing", label: "Running" },
    { id: "completed", label: "Completed" },
    { id: "failed", label: "Failed" },
    { id: "cancelled", label: "Cancelled" },
  ];

  // Handler functions
  const handleDelete = async (instanceId: string, instanceName: string) => {
    if (!confirm(`Are you sure you want to delete instance "${instanceName}"? This will permanently remove all files and run history. This action cannot be undone.`)) {
      return;
    }

    try {
      await deleteInstance(instanceId);
      setInstances(instances.filter(i => i.id !== instanceId));
      setTotalCount(prev => prev - 1);
    } catch (error: unknown) {
      console.error("Error deleting instance:", error);
      toast({ title: 'Delete failed', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
    }
  };

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';

  // Fetch workflow name when filtering by workflow
  useEffect(() => {
    if (!workflowFilter || !user?.org_id) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWorkflowName(null);
      return;
    }

    getWorkflows(user.org_id)
      .then((workflows) => {
        const workflow = workflows.find((w: any) => w.id === workflowFilter);
        setWorkflowName(workflow?.name || null);
      })
      .catch(() => setWorkflowName(null));
  }, [workflowFilter, user?.org_id]);

  // Fetch instances from API with server-side pagination
  useEffect(() => {
    console.log('🔄 Instances fetch effect running, activeTab:', activeTab, 'searchParams:', searchParams.toString());

    // Wait for auth to finish loading - keep loading state true
    if (authStatus === 'loading') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(true);
      return;
    }

    if (!user?.org_id) {
      setError('No organization ID found');
      setLoading(false);
      return;
    }

    setLoading(true);
    const status = activeTab === 'all' ? undefined : activeTab;
    const skip = (currentPage - 1) * pageSize;

    // Use server-side pagination for main instances endpoint
    // Workflow filter still uses client-side filtering
    if (workflowFilter) {
      getInstancesByWorkflow(workflowFilter, 0, 100)
        .then((data) => {
          // Apply status filter client-side for workflow filtering
          let filtered = data;
          if (status) {
            filtered = data.filter((instance: InstanceResponse) => instance.status === status);
          }

          // Sort by most recent first
          filtered.sort((a: InstanceResponse, b: InstanceResponse) => {
            const aDate = a.updated_at || a.created_at;
            const bDate = b.updated_at || b.created_at;
            if (!aDate) return 1;
            if (!bDate) return -1;
            return new Date(bDate).getTime() - new Date(aDate).getTime();
          });

          setTotalCount(filtered.length);
          // Apply pagination client-side for workflow filter
          const paginated = filtered.slice(skip, skip + pageSize);
          setInstances(paginated);
          setError(null);
        })
        .catch((err) => {
          console.error('❌ Failed to fetch instances:', err);
          setError('Failed to load instances');
        })
        .finally(() => setLoading(false));
    } else {
      // Server-side pagination
      getInstances(user.org_id, status, skip, pageSize)
        .then((response) => {
          // Sort by most recent first (server should do this, but ensure client-side)
          const sorted = [...response.items].sort((a: InstanceResponse, b: InstanceResponse) => {
            const aDate = a.updated_at || a.created_at;
            const bDate = b.updated_at || b.created_at;
            if (!aDate) return 1;
            if (!bDate) return -1;
            return new Date(bDate).getTime() - new Date(aDate).getTime();
          });

          setTotalCount(response.total);
          setInstances(sorted);
          setError(null);
        })
        .catch((err) => {
          console.error('❌ Failed to fetch instances:', err);
          setError('Failed to load instances');
        })
        .finally(() => setLoading(false));
    }
  // Note: searchParams.toString() ensures React sees URL changes as dependency updates
  }, [user?.org_id, activeTab, authStatus, workflowFilter, currentPage, pageSize, searchParams]);

  // Reset page when filters change
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPage(1);
  }, [activeTab, workflowFilter]);

  const totalPages = Math.ceil(totalCount / pageSize);

  // Ensure currentPage is valid when totalPages changes
  useEffect(() => {
    if (totalPages > 0 && currentPage > totalPages) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCurrentPage(1);
    }
  }, [totalPages, currentPage]);
  const handleTabChange = (tabId: string) => {
    const params = new URLSearchParams();
    params.set('status', tabId);
    if (workflowFilter) params.set('workflow', workflowFilter);
    router.push(`/instances/list?${params.toString()}`);
  };

  const clearWorkflowFilter = () => {
    const params = new URLSearchParams();
    params.set('status', activeTab);
    router.push(`/instances/list?${params.toString()}`);
  };

  return (
    <DashboardLayout>
      <div className="p-6">
        <div className="mb-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h1 className="text-2xl font-bold">Instances</h1>
              <p className="section-subtitle mt-1">
                View and manage workflow executions
              </p>
            </div>
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalCount={totalCount}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setCurrentPage(1);
                localStorage.setItem(PAGE_SIZE_KEY, String(size));
              }}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              position="top"
            />
          </div>

          {/* Workflow filter badge */}
          {workflowFilter && workflowName && (
            <div className="mb-4 flex items-center gap-2">
              <span className="text-muted">Filtering by workflow:</span>
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-info-subtle text-info">
                {workflowName}
                <button
                  onClick={clearWorkflowFilter}
                  className="ml-1 hover:text-info"
                >
                  <X className="w-4 h-4" />
                </button>
              </span>
            </div>
          )}

          {/* Status tabs */}
          <div className="border-b border-primary">
            <nav
              className="-mb-px flex space-x-4 sm:space-x-8 overflow-x-auto scrollbar-hide"
              aria-label="Tabs"
            >
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`tab whitespace-nowrap py-4 flex-shrink-0 ${
                    activeTab === tab.id ? "tab-active" : "tab-inactive"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {loading && (
          <LoadingState message="Loading instances..." />
        )}

        {!loading && error && (
          <ErrorState
            title="Error Loading Instances"
            message={error}
            onRetry={() => window.location.reload()}
            retryLabel="Try Again"
          />
        )}

        {!loading && !error && (
          <>
            <TableContainer>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Instance</TableHeaderCell>
                    <TableHeaderCell>Workflow</TableHeaderCell>
                    <TableHeaderCell>Status</TableHeaderCell>
                    <TableHeaderCell>Last Updated</TableHeaderCell>
                    <TableHeaderCell align="center">Actions</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {instances.map((instance) => (
                    <TableRow key={instance.id}>
                      <TableCell>
                        <Link
                          href={`/instances/${instance.id}`}
                          className="text-sm font-medium link hover:underline"
                        >
                          {instance.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/instances/list?status=${activeTab}&workflow=${instance.workflow_id}`}
                          className="text-sm link hover:underline"
                        >
                          {instance.workflow_name || 'Unknown'}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          status={
                            instance.status === InstanceStatus.Processing
                              ? "running"
                              : instance.status || InstanceStatus.Pending
                          }
                          variant={
                            instance.status === InstanceStatus.Completed
                              ? "success"
                              : instance.status === InstanceStatus.Processing
                                ? "info"
                                : instance.status === InstanceStatus.Pending
                                  ? "warning"
                                  : instance.status === InstanceStatus.Failed
                                    ? "error"
                                    : instance.status === InstanceStatus.Cancelled
                                      ? "default"
                                      : "default"
                          }
                        />
                      </TableCell>
                      <TableCell>
                        {instance.updated_at ? new Date(instance.updated_at).toLocaleString() : 'N/A'}
                      </TableCell>
                      <TableCell align="center">
                        <div className="flex justify-center space-x-2">
                          <ActionButton
                            variant="navigate"
                            onClick={() => router.push(`/instances/${instance.id}`)}
                          >
                            View
                          </ActionButton>

                          {(instance.status === InstanceStatus.Processing || instance.status === InstanceStatus.Pending) && (
                            <ActionButton
                              variant="destructive"
                              onClick={() => toast({ title: 'Not implemented', description: `Cancel ${instance.name} is not yet implemented`, variant: 'default' })}
                            >
                              Cancel
                            </ActionButton>
                          )}

                          {[InstanceStatus.Completed, InstanceStatus.Failed, InstanceStatus.Cancelled].includes(instance.status as InstanceStatus) && (
                            <ActionButton
                              variant="destructive"
                              onClick={() => handleDelete(instance.id, instance.name)}
                            >
                              Delete
                            </ActionButton>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Pagination Controls - Bottom */}
            {instances.length > 0 && (
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalCount={totalCount}
                pageSize={pageSize}
                onPageChange={setCurrentPage}
                itemLabel="instance"
                position="bottom"
              />
            )}
          </>
        )}

        {instances.length === 0 && !loading && !error && (
          <EmptyState
            title="No instances found"
            description="No instances found matching your criteria."
          />
        )}
      </div>
    </DashboardLayout>
  );
}

export default function InstancesList() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <LoadingState message="Loading..." />
      </DashboardLayout>
    }>
      <InstancesListContent />
    </Suspense>
  );
}
