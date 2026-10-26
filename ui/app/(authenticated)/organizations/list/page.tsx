// ui/app/(authenticated)/organizations/list/page.tsx

"use client";

import React, { Suspense } from "react";
import {
  ActionButton,
  StatusBadge,
  SearchInput,
  LoadingState,
  EmptyState,
  ResourceTable,
  type ResourceColumnConfig,
  type SortState,
} from "@/shared/ui";
import { useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  getOrganizationStats,
  type OrganizationStats,
  type GetOrganizationStatsParams,
} from "@/shared/api";
import { useUser } from "@/entities/user";
import { useRoleAccess } from "@/features/roles";
import {
  Users,
  Workflow,
  HardDrive,
  RefreshCw,
  Building2,
} from "lucide-react";
import { getStoredPageSize } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';
import { useListPref, oneOf } from '@/shared/hooks/useListPref';
import { formatDate } from '@/shared/lib/dateFormatter';

const PAGE_SIZE_KEY = listPageSizeKey('organizations');

type FilterType = 'all' | 'active' | 'inactive';
type SortField = NonNullable<GetOrganizationStatsParams['sort_by']>;
type SortOrder = 'asc' | 'desc';

const SORT_FIELDS: readonly SortField[] = ['name', 'created_at', 'member_count', 'workflow_count', 'storage'];
const SORT_ORDERS: readonly SortOrder[] = ['asc', 'desc'];
const isSortField = oneOf<string>(['', 'status', 'plan_name', ...SORT_FIELDS]);

const COLUMNS: ResourceColumnConfig<OrganizationStats>[] = [
  {
    key: 'name',
    header: 'Name',
    sortValue: (org) => org.name,
    render: (org) => (
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <Link
            href={`/organizations/${org.id}`}
            className="text-sm font-medium link hover:underline"
          >
            {org.name}
          </Link>
          <div className="text-muted text-xs">
            {org.slug}
          </div>
        </div>
        {org.is_system && (
          <span className="badge badge-info whitespace-nowrap shrink-0">
            System
          </span>
        )}
      </div>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    align: 'center',
    sortValue: (org) => org.is_active,
    render: (org) => (
      <StatusBadge
        status={org.is_active ? 'active' : 'inactive'}
        variant={org.is_active ? 'success' : 'default'}
      />
    ),
  },
  {
    key: 'member_count',
    header: <><Users className="w-4 h-4 mr-1" />Users</>,
    align: 'center',
    sortValue: (org) => org.member_count,
    render: (org) => <span className="text-sm">{org.member_count}</span>,
  },
  {
    key: 'workflow_count',
    header: <><Workflow className="w-4 h-4 mr-1" />Workflows</>,
    align: 'center',
    sortValue: (org) => org.workflow_count,
    render: (org) => <span className="text-sm">{org.workflow_count}</span>,
  },
  {
    key: 'storage',
    header: <><HardDrive className="w-4 h-4 mr-1" />Storage</>,
    align: 'center',
    sortValue: (org) => org.storage.size_bytes,
    render: (org) => (
      <div className="text-sm">
        <div>{org.storage.size_formatted}</div>
        <div className="text-muted text-xs">
          {org.storage.files} files
        </div>
      </div>
    ),
  },
  {
    key: 'created_at',
    header: 'Created',
    align: 'center',
    sortValue: (org) => org.created_at,
    render: (org) => (
      <span className="text-muted">
        {org.created_at
          ? formatDate(org.created_at)
          : '-'}
      </span>
    ),
  },
];

function isServerSortField(field: string | null): field is SortField {
  return field !== null && (SORT_FIELDS as readonly string[]).includes(field);
}

function OrganizationsListContent() {
  const { hasAccess, isLoading: authLoading } = useRoleAccess(['super_admin']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useUser();

  // Get filter from URL
  const activeFilter = (searchParams.get('filter') || 'all') as FilterType;

  // Data state
  const [organizations, setOrganizations] = useState<OrganizationStats[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [searchTerm, setSearchTerm] = useState('');

  // Pagination state (0-indexed for API, but display as 1-indexed)
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(() => getStoredPageSize(PAGE_SIZE_KEY));

  // Sort state; the API sorts its own fields, Status and Plan sort within the loaded page
  const [sortField, setSortField] = useListPref<string>('organizations', 'sortField', '', isSortField);
  const [sortOrder, setSortOrder] = useListPref<SortOrder>('organizations', 'sortDirection', 'asc', oneOf(SORT_ORDERS));
  const sortBy = isServerSortField(sortField) ? sortField : null;

  // Fetch organizations with current params
  const fetchOrganizations = useCallback(async () => {
    if (user?.role !== 'super_admin') return;

    try {
      setLoading(true);
      setError(null);

      const params: GetOrganizationStatsParams = {
        skip: page * pageSize,
        limit: pageSize,
      };

      if (activeFilter !== 'all') {
        params.filter = activeFilter;
      }
      if (sortBy) {
        params.sort_by = sortBy;
        params.sort_order = sortOrder;
      }
      if (searchTerm) {
        params.search = searchTerm;
      }

      const data = await getOrganizationStats(params);
      setOrganizations(data.organizations);
      setTotal(data.total);
    } catch (err: unknown) {
      console.error('Failed to fetch organizations:', err);
      setError(err instanceof Error ? err.message : 'Failed to load organizations');
    } finally {
      setLoading(false);
    }
  }, [user?.role, page, pageSize, activeFilter, sortBy, sortOrder, searchTerm]);

  useEffect(() => {
    // IIFE so the deferred setState inside fetchOrganizations isn't read as a synchronous set.
    void (async () => { await fetchOrganizations(); })();
  }, [fetchOrganizations]);

  // Reset page when search changes (adjust during render, not in an effect).
  const [prevSearchTerm, setPrevSearchTerm] = useState(searchTerm);
  if (searchTerm !== prevSearchTerm) {
    setPrevSearchTerm(searchTerm);
    setPage(0);
  }

  const handleSort = (next: SortState) => {
    setSortField(next.field ?? '');
    setSortOrder(next.direction);
    setPage(0);
  };

  if (authLoading) {
    return (
      <>
        <LoadingState message="Loading..." />
      </>
    );
  }

  if (!hasAccess) {
    return (
      <>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-danger mb-2">Access Denied</h2>
            <p className="text-secondary">
              Only super administrators can access the organizations list.
            </p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="sm:flex sm:items-center mb-6">
          <div className="sm:flex-auto">
            <h1 className="text-2xl font-semibold text-primary">
              Organizations
            </h1>
            <p className="mt-1 section-subtitle">
              Manage all organizations and their resources
            </p>
          </div>
          <div className="mt-4 sm:mt-0 sm:ml-16 sm:flex-none flex gap-2">
            <button
              onClick={fetchOrganizations}
              disabled={loading}
              className="btn-secondary inline-flex items-center text-sm disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <Link
              href="/organizations/create"
              className="btn-primary inline-flex items-center"
            >
              Create Organization
            </Link>
          </div>
        </div>

        {/* Filter Links */}
        <div className="bg-card shadow overflow-hidden sm:rounded-md mb-4">
          <div className="border-b border-primary bg-card px-4 py-4 sm:px-6">
            <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 sm:mx-0 sm:px-0">
              <button
                onClick={() => { router.push('/organizations/list?filter=all'); setPage(0); }}
                className={`filter-pill ${activeFilter === 'all' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
              >
                All
              </button>
              <button
                onClick={() => { router.push('/organizations/list?filter=active'); setPage(0); }}
                className={`filter-pill ${activeFilter === 'active' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
              >
                Active
              </button>
              <button
                onClick={() => { router.push('/organizations/list?filter=inactive'); setPage(0); }}
                className={`filter-pill ${activeFilter === 'inactive' ? 'filter-pill-active' : 'filter-pill-inactive'}`}
              >
                Inactive
              </button>
            </div>
          </div>
        </div>

        <ResourceTable
          data={organizations}
          getItemId={(org) => org.id}
          columns={[
            ...COLUMNS,
            {
              key: 'actions',
              header: 'Actions',
              align: 'center',
              render: (org) => (
                <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
                  <ActionButton
                    variant="navigate"
                    onClick={() => router.push(`/organizations/${org.id}`)}
                  >
                    View
                  </ActionButton>
                  <ActionButton
                    variant="change"
                    onClick={() => router.push(`/organizations/${org.id}/users`)}
                  >
                    Users
                  </ActionButton>
                </div>
              ),
            },
          ]}
          prefPage="organizations"
          sort={{
            field: sortField || null,
            direction: sortOrder,
            onChange: handleSort,
            server: sortBy !== null,
          }}
          pagination={{
            itemLabel: 'organization',
            server: {
              currentPage: page + 1,
              totalCount: total,
              pageSize,
              onPageChange: (p) => setPage(p - 1),
              onPageSizeChange: (size) => {
                setPageSize(size);
                setPage(0);
                localStorage.setItem(PAGE_SIZE_KEY, String(size));
              },
            },
          }}
          toolbar={
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Search organizations..."
            />
          }
          loading={loading}
          loadingMessage="Loading organizations..."
          error={error}
          errorTitle="Error Loading Organizations"
          onRetry={fetchOrganizations}
          rowClassName={(org) => `${!org.is_active ? 'opacity-60' : ''} ${org.is_system ? 'bg-info-subtle/50' : ''}`}
          emptyState={
            <EmptyState
              icon={<Building2 className="h-12 w-12" />}
              title="No organizations found"
              description={
                searchTerm || activeFilter !== 'all'
                  ? 'Try adjusting your search or filters.'
                  : 'Create your first organization to get started.'
              }
            />
          }
        />
      </div>
    </>
  );
}

export default function OrganizationsList() {
  return (
    <Suspense fallback={
      <>
        <LoadingState message="Loading..." />
      </>
    }>
      <OrganizationsListContent />
    </Suspense>
  );
}
