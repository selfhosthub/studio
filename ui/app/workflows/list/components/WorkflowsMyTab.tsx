// ui/app/workflows/list/components/WorkflowsMyTab.tsx

'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
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
import type { WorkflowSortField, SortDirection } from '../page';
import type { WorkflowIssue } from '@/shared/lib/workflow-readiness';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { listPageSizeKey } from '@/shared/lib/constants';
import { ChevronUp, ChevronDown } from 'lucide-react';

const PAGE_SIZE_KEY = listPageSizeKey('workflows');

interface WorkflowsMyTabProps {
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
  onRun: (w: WorkflowResponse) => void;
  onDelete: (w: WorkflowResponse) => void;
  onRequestPublish: (w: WorkflowResponse) => void;
  publishingId: string | null;
  onRetry: () => void;
  sortField: WorkflowSortField;
  sortDirection: SortDirection;
  onSort: (field: WorkflowSortField) => void;
  getIssues: (w: WorkflowResponse) => WorkflowIssue[];
}

export function WorkflowsMyTab({
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
  onRun,
  onDelete,
  onRequestPublish,
  publishingId,
  onRetry,
  sortField,
  sortDirection,
  onSort,
  getIssues,
}: WorkflowsMyTabProps) {
  const router = useRouter();

  const formatDateTime = (dateStr: string | null | undefined) =>
    dateStr ? new Date(dateStr).toISOString().replace('T', ' ').slice(0, 16) : 'N/A';

  const sortIcon = (field: WorkflowSortField) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc'
      ? <ChevronUp className="inline w-4 h-4 ml-1" />
      : <ChevronDown className="inline w-4 h-4 ml-1" />;
  };

  const getPublishBadge = (status: string | null | undefined) => {
    switch (status) {
      case 'pending':
        return <span className="badge bg-warning-subtle text-warning">Pending</span>;
      case 'rejected':
        return <span className="badge bg-danger-subtle text-danger">Rejected</span>;
      default:
        return null;
    }
  };

  if (loading) return <LoadingState message="Loading your workflows..." />;
  if (error) return <ErrorState title="Error" message={error} onRetry={onRetry} />;

  return (
    <>
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
          title="No workflows yet"
          description="Create your first workflow or copy one from the Organization tab."
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
                        {getPublishBadge(w.publish_status)}
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
                        <ActionButton
                          variant="change"
                          onClick={() => router.push(`/workflows/${w.id}/edit`)}
                        >
                          Edit
                        </ActionButton>
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
                        {!w.publish_status && (
                          <ActionButton
                            variant="navigate"
                            onClick={() => onRequestPublish(w)}
                            disabled={publishingId === w.id}
                          >
                            {publishingId === w.id ? 'Submitting...' : 'Publish'}
                          </ActionButton>
                        )}
                        <ActionButton
                          variant="destructive"
                          onClick={() => onDelete(w)}
                        >
                          Delete
                        </ActionButton>
                      </div>
                    </TableCell>
                  </TableRow>
                  );
                })}
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
