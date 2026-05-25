// ui/app/organizations/list/page.tsx

"use client";

import React, { Suspense } from "react";
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
  ChevronUp,
  ChevronDown,
  Users,
  Workflow,
  HardDrive,
  RefreshCw,
  Building2,
} from "lucide-react";
import { PAGE_SIZE_OPTIONS, getStoredPageSize } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';

const PAGE_SIZE_KEY = listPageSizeKey('organizations');

type FilterType = 'all' | 'active' | 'inactive';
type SortField = 'name' | 'created_at' | 'member_count' | 'workflow_count' | 'storage';
type SortOrder = 'asc' | 'desc';

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

  // Sort state
  const [sortBy, setSortBy] = useState<SortField | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');

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
    fetchOrganizations();
  }, [fetchOrganizations]);

  // Reset page when search changes
  useEffect(() => {
    setPage(0);
  }, [searchTerm]);

  // Handle column sort click
  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      // Toggle order if same field
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
    setPage(0); // Reset to first page on sort change
  };

  // Sort indicator component
  const SortIndicator = ({ field }: { field: SortField }) => {
    if (sortBy !== field) return null;
    return sortOrder === 'asc' ? (
      <ChevronUp className="w-4 h-4 inline ml-1" />
    ) : (
      <ChevronDown className="w-4 h-4 inline ml-1" />
    );
  };

  // Calculate pagination
  const totalPages = Math.ceil(total / pageSize) || 1;

  if (authLoading) {
    return (
      <DashboardLayout>
        <LoadingState message="Loading..." />
      </DashboardLayout>
    );
  }

  if (!hasAccess) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <h2 className="text-xl font-semibold text-danger mb-2">Access Denied</h2>
            <p className="text-secondary">
              Only super administrators can access the organizations list.
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
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

        {/* Search and Pagination Controls */}
        <div className="flex items-center justify-between gap-4 mb-4">
          <SearchInput
            value={searchTerm}
            onChange={setSearchTerm}
            placeholder="Search organizations..."
          />
          <Pagination
            currentPage={page + 1}
            totalPages={totalPages}
            totalCount={total}
            pageSize={pageSize}
            onPageChange={(p) => setPage(p - 1)}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(0);
              localStorage.setItem(PAGE_SIZE_KEY, String(size));
            }}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            position="top"
          />
        </div>

        {/* Loading State */}
        {loading && (
          <LoadingState message="Loading organizations..." />
        )}

        {/* Error State */}
        {!loading && error && (
          <ErrorState
            title="Error Loading Organizations"
            message={error}
            onRetry={fetchOrganizations}
            retryLabel="Try Again"
          />
        )}

        {/* Content */}
        {!loading && !error && (
          <>
            {/* Table */}
            <TableContainer>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>
                      <button
                        onClick={() => handleSort('name')}
                        className="flex items-center hover:text-info"
                      >
                        Name <SortIndicator field="name" />
                      </button>
                    </TableHeaderCell>
                    <TableHeaderCell align="center">Status</TableHeaderCell>
                    <TableHeaderCell align="center">
                      <button
                        onClick={() => handleSort('member_count')}
                        className="flex items-center justify-center w-full hover:text-info"
                      >
                        <Users className="w-4 h-4 mr-1" />
                        Members <SortIndicator field="member_count" />
                      </button>
                    </TableHeaderCell>
                    <TableHeaderCell align="center">
                      <button
                        onClick={() => handleSort('workflow_count')}
                        className="flex items-center justify-center w-full hover:text-info"
                      >
                        <Workflow className="w-4 h-4 mr-1" />
                        Workflows <SortIndicator field="workflow_count" />
                      </button>
                    </TableHeaderCell>
                    <TableHeaderCell align="center">
                      <button
                        onClick={() => handleSort('storage')}
                        className="flex items-center justify-center w-full hover:text-info"
                      >
                        <HardDrive className="w-4 h-4 mr-1" />
                        Storage <SortIndicator field="storage" />
                      </button>
                    </TableHeaderCell>
                    <TableHeaderCell align="center">Plan</TableHeaderCell>
                    <TableHeaderCell align="center">
                      <button
                        onClick={() => handleSort('created_at')}
                        className="flex items-center justify-center w-full hover:text-info"
                      >
                        Created <SortIndicator field="created_at" />
                      </button>
                    </TableHeaderCell>
                    <TableHeaderCell align="center">Actions</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {organizations.map((org) => (
                    <TableRow key={org.id} className={`${!org.is_active ? 'opacity-60' : ''} ${org.is_system ? 'bg-info-subtle/50' : ''}`}>
                      <TableCell>
                        <div className="flex items-center gap-2">
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
                            <span className="badge badge-info">
                              System
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell align="center">
                        <StatusBadge
                          status={org.is_active ? 'active' : 'inactive'}
                          variant={org.is_active ? 'success' : 'default'}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <span className="text-sm">{org.member_count}</span>
                      </TableCell>
                      <TableCell align="center">
                        <span className="text-sm">{org.workflow_count}</span>
                      </TableCell>
                      <TableCell align="center">
                        <div className="text-sm">
                          <div>{org.storage.size_formatted}</div>
                          <div className="text-muted text-xs">
                            {org.storage.files} files
                          </div>
                        </div>
                      </TableCell>
                      <TableCell align="center">
                        <span className="text-sm">
                          {org.plan_name || <span className="text-muted">-</span>}
                        </span>
                      </TableCell>
                      <TableCell align="center">
                        <span className="text-muted">
                          {org.created_at
                            ? new Date(org.created_at).toLocaleDateString()
                            : '-'}
                        </span>
                      </TableCell>
                      <TableCell align="center">
                        <div className="flex justify-center space-x-2">
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
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Empty State */}
            {organizations.length === 0 && (
              <EmptyState
                icon={<Building2 className="h-12 w-12" />}
                title="No organizations found"
                description={
                  searchTerm || activeFilter !== 'all'
                    ? 'Try adjusting your search or filters.'
                    : 'Create your first organization to get started.'
                }
              />
            )}

            {/* Pagination - Bottom */}
            {organizations.length > 0 && (
              <Pagination
                currentPage={page + 1}
                totalPages={totalPages}
                totalCount={total}
                pageSize={pageSize}
                onPageChange={(p) => setPage(p - 1)}
                itemLabel="organization"
                position="bottom"
              />
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}

export default function OrganizationsList() {
  return (
    <Suspense fallback={
      <DashboardLayout>
        <LoadingState message="Loading..." />
      </DashboardLayout>
    }>
      <OrganizationsListContent />
    </Suspense>
  );
}
