// ui/app/workflows/list/components/WorkflowsOrganizationTab.tsx

'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, X, ChevronUp, ChevronDown } from 'lucide-react';
import {
  ActionButton,
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
  StatusBadge,
} from '@/shared/ui';
import type { WorkflowResponse } from '@/shared/types/api';
import type { WorkflowIssue } from '@/shared/lib/workflow-readiness';
import type { WorkflowSortField, SortDirection } from '../page';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';

const PAGE_SIZE_KEY = listPageSizeKey('workflows');

interface WorkflowsOrganizationTabProps {
  loading: boolean;
  error: string | null;
  filteredWorkflows: WorkflowResponse[];
  paginatedWorkflows: WorkflowResponse[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  currentPage: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  onRun: (w: WorkflowResponse) => void;
  onDelete: (w: WorkflowResponse) => void;
  onArchive: (w: WorkflowResponse) => void;
  onCopy: (w: WorkflowResponse) => void;
  copyingId: string | null;
  pendingWorkflows: WorkflowResponse[];
  onApprovePublish: (w: WorkflowResponse) => void;
  onRejectPublish: (w: WorkflowResponse) => void;
  approvingId: string | null;
  rejectingId: string | null;
  getIssues: (w: WorkflowResponse) => WorkflowIssue[];
  onRetry: () => void;
  sortField: WorkflowSortField;
  sortDirection: SortDirection;
  onSort: (field: WorkflowSortField) => void;
}

export function WorkflowsOrganizationTab({
  loading,
  error,
  filteredWorkflows,
  paginatedWorkflows,
  searchTerm,
  onSearchChange,
  currentPage,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  isAdmin,
  isSuperAdmin,
  onRun,
  onDelete,
  onArchive,
  onCopy,
  copyingId,
  pendingWorkflows,
  onApprovePublish,
  onRejectPublish,
  approvingId,
  rejectingId,
  getIssues,
  onRetry,
  sortField,
  sortDirection,
  onSort,
}: WorkflowsOrganizationTabProps) {
  const router = useRouter();

  const formatDateTime = (dateStr: string | null | undefined) =>
    dateStr ? new Date(dateStr).toISOString().replace('T', ' ').slice(0, 16) : 'N/A';

  const sortIcon = (field: WorkflowSortField) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc'
      ? <ChevronUp className="inline w-4 h-4 ml-1" />
      : <ChevronDown className="inline w-4 h-4 ml-1" />;
  };

  if (loading) return <LoadingState message="Loading organization workflows..." />;
  if (error) return <ErrorState title="Error" message={error} onRetry={onRetry} />;

  return (
    <>
      {/* Pending Approvals Banner (admin only) */}
      {isAdmin && pendingWorkflows.length > 0 && (
        <div className="mb-6 p-4 rounded-lg bg-warning-subtle border border-warning">
          <h3 className="text-sm font-semibold text-warning mb-3">
            Pending Approvals ({pendingWorkflows.length})
          </h3>
          <div className="space-y-2">
            {pendingWorkflows.map((pw) => {
              const pendingIssues = getIssues(pw);
              return (
              <div
                key={pw.id}
                className="flex items-center justify-between p-2 rounded bg-card"
              >
                <div>
                  <span className="text-sm font-medium">{pw.name}</span>
                  {pw.description && (
                    <span className="text-xs text-muted ml-2">{pw.description}</span>
                  )}
                  {pendingIssues.length > 0 && (
                    <div className="text-warning text-xs mt-0.5">
                      {pendingIssues.map(i => i.message).filter((v, idx, arr) => arr.indexOf(v) === idx).join(', ')}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => onApprovePublish(pw)}
                    disabled={approvingId === pw.id}
                    className="inline-flex items-center gap-1 px-3 py-1 text-xs font-medium rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50" // css-check-ignore: approve action button
                  >
                    <Check className="w-3 h-3" />
                    {approvingId === pw.id ? 'Approving...' : 'Approve'}
                  </button>
                  <button
                    onClick={() => onRejectPublish(pw)}
                    disabled={rejectingId === pw.id}
                    className="inline-flex items-center gap-1 px-3 py-1 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50" // css-check-ignore: reject action button
                  >
                    <X className="w-3 h-3" />
                    {rejectingId === pw.id ? 'Rejecting...' : 'Reject'}
                  </button>
                </div>
              </div>
              ); })}
          </div>
        </div>
      )}

      {/* Search + Pagination */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={searchTerm}
            onChange={onSearchChange}
            placeholder="Search workflows..."
          />
        </div>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={filteredWorkflows.length}
          pageSize={pageSize}
          onPageChange={onPageChange}
          onPageSizeChange={(size) => {
            onPageSizeChange(size);
            localStorage.setItem(PAGE_SIZE_KEY, String(size));
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
          itemLabel="workflows"
        />
      </div>

      {filteredWorkflows.length === 0 ? (
        <EmptyState
          title="No organization workflows"
          description={
            isSuperAdmin
              ? 'Install workflows from the Marketplace.'
              : 'No workflows are shared in your organization yet.'
          }
        />
      ) : (
        <>
          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell onClick={() => onSort('name')}>
                    Name{sortIcon('name')}
                  </TableHeaderCell>
                  <TableHeaderCell onClick={() => onSort('status')}>
                    Status{sortIcon('status')}
                  </TableHeaderCell>
                  <TableHeaderCell onClick={() => onSort('updated_at')}>
                    Updated{sortIcon('updated_at')}
                  </TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedWorkflows.map((w) => {
                  const issues = getIssues(w);
                  return (
                  <TableRow key={w.id}>
                    <TableCell>
                      <div>
                        <Link
                          href={`/workflows/${w.id}`}
                          className="text-sm font-medium link hover:underline"
                        >
                          {w.name}
                        </Link>
                        {w.description && (
                          <div className="text-muted text-xs line-clamp-2">
                            {w.description}
                          </div>
                        )}
                        {issues.length > 0 && (
                          <div className="text-warning text-xs mt-0.5">
                            Missing: {issues.map(i => i.message).filter((v, idx, arr) => arr.indexOf(v) === idx).join(', ')}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={w.status || 'active'} />
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted">
                        {formatDateTime(w.updated_at)}
                      </span>
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center space-x-2">
                        {isAdmin && (
                          <ActionButton
                            variant="change"
                            onClick={() => router.push(`/workflows/${w.id}/edit`)}
                          >
                            Edit
                          </ActionButton>
                        )}
                        <ActionButton variant="active" onClick={() => onRun(w)}>
                          Run
                        </ActionButton>
                        {w.client_metadata?.experience_config != null && (
                          <ActionButton
                            variant="navigate"
                            onClick={() => router.push(`/run/${w.id}`)}
                          >
                            Experience
                          </ActionButton>
                        )}
                        {!isAdmin && (
                          <ActionButton
                            variant="navigate"
                            onClick={() => onCopy(w)}
                            disabled={copyingId === w.id}
                          >
                            {copyingId === w.id ? 'Copying...' : 'Copy'}
                          </ActionButton>
                        )}
                        {isAdmin && w.status !== 'inactive' && w.status !== 'archived' && (
                          <ActionButton variant="warning" onClick={() => onArchive(w)}>
                            Archive
                          </ActionButton>
                        )}
                        {isAdmin && (w.status === 'inactive' || w.status === 'archived') && (
                          <ActionButton
                            variant="destructive"
                            onClick={() => onDelete(w)}
                          >
                            Delete
                          </ActionButton>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                  ); })}
              </TableBody>
            </Table>
          </TableContainer>

          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalCount={filteredWorkflows.length}
            pageSize={pageSize}
            onPageChange={onPageChange}
            itemLabel="workflows"
            position="bottom"
          />
        </>
      )}
    </>
  );
}
