// ui/app/(authenticated)/instances/list/page.tsx

"use client";

import {
  ActionButton,
  StatusBadge,
  LoadingState,
  EmptyState,
  ResourceTable,
  type ResourceColumnConfig,
  type SortState,
} from "@/shared/ui";
import { useUser } from "@/entities/user";
import { useToast } from "@/features/toast";
import { useEffect, useRef, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getInstances, deleteInstance, cancelInstance, getWorkflows, getInstanceFiles } from "@/shared/api";
import type { InstanceSortField } from "@/shared/api/instances";
import { InstanceStatus, type InstanceResponse } from "@/shared/types/api";
import { X } from "lucide-react";
import { getStoredPageSize } from '@/shared/lib/pagination';
import { listPageSizeKey, POLLING } from '@/shared/lib/constants';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { formatDate } from '@/shared/lib/dateFormatter';
import { useListPref, oneOf } from '@/shared/hooks/useListPref';
import { canControlRun } from '@/shared/lib/runControl';
const PAGE_SIZE_KEY = listPageSizeKey('instances');

// Column key to the field the API sorts by.
const SORT_BY_COLUMN: Record<string, InstanceSortField> = {
  name: 'name',
  workflow: 'workflow_name',
  status: 'status',
  updated: 'updated_at',
};
const isSortField = oneOf<string>(['', ...Object.keys(SORT_BY_COLUMN)]);
const isSortOrder = oneOf<'asc' | 'desc'>(['asc', 'desc']);

function InstancesListContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [instances, setInstances] = useState<InstanceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => getStoredPageSize(PAGE_SIZE_KEY));
  const [totalCount, setTotalCount] = useState(0);
  const [workflowName, setWorkflowName] = useState<string | null>(null);
  const [sortField, setSortField] = useListPref<string>('instances', 'sortField', '', isSortField);
  const [sortOrder, setSortOrder] = useListPref<'asc' | 'desc'>('instances', 'sortDirection', 'asc', isSortOrder);
  const sortBy = sortField ? SORT_BY_COLUMN[sortField] : undefined;
  const [refreshTick, setRefreshTick] = useState(0);
  const lastTickRef = useRef(0);

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
    const fileCount = await getInstanceFiles(instanceId).then((f) => f.length, () => null);
    const removes = fileCount === null
      ? 'all of its files and its run history'
      : fileCount === 0
        ? 'its run history (it has no files)'
        : `its ${fileCount} file${fileCount === 1 ? '' : 's'} and its run history`;
    if (!(await confirm({
      title: 'Delete instance',
      message: `Delete instance "${instanceName}"? This permanently removes ${removes}. This action cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) {
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

  const handleCancel = async (instanceId: string, instanceName: string) => {
    if (!(await confirm({
      title: 'Cancel instance',
      message: `Cancel instance "${instanceName}"? This stops the instance and cancels its non-terminal nodes.`,
      confirmLabel: 'Cancel instance',
      cancelLabel: 'Keep running',
      variant: 'danger',
    }))) {
      return;
    }
    try {
      const updated = await cancelInstance(instanceId);
      setInstances(instances.map(i => (i.id === instanceId ? updated : i)));
      toast({ title: 'Instance cancelled', variant: 'success' });
    } catch (error: unknown) {
      console.error("Error cancelling instance:", error);
      toast({ title: 'Cancel failed', description: error instanceof Error ? error.message : 'Unknown error', variant: 'destructive' });
    }
  };

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

    // A background refresh keeps the table on screen and its last good rows on error.
    const silent = refreshTick !== lastTickRef.current;
    lastTickRef.current = refreshTick;
    if (!silent) setLoading(true);
    const status = activeTab === 'all' ? undefined : activeTab;
    const skip = (currentPage - 1) * pageSize;
    let stale = false;

    getInstances(user.org_id, status, skip, pageSize, workflowFilter || undefined, sortBy, sortOrder)
      .then((response) => {
        if (stale) return;
        setTotalCount(response.total);
        setInstances(response.items);
        setError(null);
      })
      .catch((err) => {
        if (stale || silent) return;
        console.error('Failed to fetch instances:', err);
        setError('Failed to load instances');
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => {
      stale = true;
    };
  // Note: searchParams.toString() ensures React sees URL changes as dependency updates
  }, [user?.org_id, activeTab, authStatus, workflowFilter, currentPage, pageSize, searchParams, sortBy, sortOrder, refreshTick]);

  // Refetch the current page on an interval and on return to the tab, while the tab is visible.
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') setRefreshTick((t) => t + 1);
    };
    const interval = setInterval(tick, POLLING.DEFAULT);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

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
  const handleSort = (next: SortState) => {
    setSortField(next.field ?? '');
    setSortOrder(next.direction);
    setCurrentPage(1);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
    localStorage.setItem(PAGE_SIZE_KEY, String(size));
  };

  const columns: ResourceColumnConfig<InstanceResponse>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (instance) => instance.name,
      render: (instance) => (
        <Link
          href={`/instances/${instance.id}`}
          className="text-sm font-medium link hover:underline"
        >
          {instance.name}
        </Link>
      ),
    },
    {
      key: 'workflow',
      header: 'Workflow',
      sortValue: (instance) => instance.workflow_name,
      render: (instance) => (
        <Link
          href={`/instances/list?status=${activeTab}&workflow=${instance.workflow_id}`}
          className="text-sm link hover:underline"
        >
          {instance.workflow_name || 'Unknown' /* defaults-ok */}
        </Link>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (instance) => instance.status,
      render: (instance) => <StatusBadge status={instance.status} />,
    },
    {
      key: 'updated',
      header: 'Updated',
      sortValue: (instance) => (instance.updated_at ? new Date(instance.updated_at) : null),
      render: (instance) => (instance.updated_at ? formatDate(instance.updated_at) : 'N/A'),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (instance) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
          <ActionButton
            variant="navigate"
            onClick={() => router.push(`/instances/${instance.id}`)}
          >
            View
          </ActionButton>

          {canControlRun(user, instance) && ![InstanceStatus.Completed, InstanceStatus.Failed, InstanceStatus.Cancelled].includes(instance.status as InstanceStatus) && (
            <ActionButton
              variant="destructive"
              onClick={() => handleCancel(instance.id, instance.name)}
            >
              Cancel
            </ActionButton>
          )}

          {canControlRun(user, instance) && [InstanceStatus.Completed, InstanceStatus.Failed, InstanceStatus.Cancelled].includes(instance.status as InstanceStatus) && (
            <ActionButton
              variant="destructive"
              onClick={() => handleDelete(instance.id, instance.name)}
            >
              Delete
            </ActionButton>
          )}
        </div>
      ),
    },
  ];

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
    <>
      <div className="p-6">
        <div className="mb-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h1 className="text-2xl font-bold">Instances</h1>
              <p className="section-subtitle mt-1">
                View and manage workflow executions
              </p>
            </div>
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

        <ResourceTable<InstanceResponse>
          data={instances}
          getItemId={(instance) => instance.id}
          columns={columns}
          prefPage="instances"
          sort={{
            field: sortField || null,
            direction: sortOrder,
            onChange: handleSort,
            server: true,
          }}
          pagination={{
            itemLabel: 'instance',
            server: {
              currentPage,
              totalCount,
              pageSize,
              onPageChange: setCurrentPage,
              onPageSizeChange: handlePageSizeChange,
            },
          }}
          loading={loading}
          loadingMessage="Loading instances..."
          error={error}
          errorTitle="Error Loading Instances"
          onRetry={() => window.location.reload()}
          emptyState={
            <EmptyState
              title="No instances found"
              description="No instances found matching your criteria."
            />
          }
        />
      </div>
    </>
  );
}

export default function InstancesList() {
  return (
    <Suspense fallback={
      <>
        <LoadingState message="Loading..." />
      </>
    }>
      <InstancesListContent />
    </Suspense>
  );
}
