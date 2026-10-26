// ui/app/(authenticated)/workflows/list/components/WorkflowsOrganizationTab.tsx

'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ActionButton,
  ResourceTable,
  SearchInput,
  EmptyState,
  StatusBadge,
} from '@/shared/ui';
import type { ResourceColumnConfig } from '@/shared/ui';
import type { WorkflowResponse } from '@/shared/types/api';
import type { WorkflowIssue } from '@/shared/lib/workflow-readiness';
import { useCurrentUrl, withReturnTo } from '@/shared/hooks/useReturnTo';
import { formatDate } from '@/shared/lib/dateFormatter';

interface WorkflowsOrganizationTabProps {
  loading: boolean;
  error: string | null;
  workflows: WorkflowResponse[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  statusFilter: "all" | "pending" | "published";
  onStatusChange: (status: "all" | "pending" | "published") => void;
  pendingCount: number;
  /** The table returns to page 1 when this value changes. */
  pageResetKey?: string;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  onRun: (w: WorkflowResponse) => void;
  onDelete: (w: WorkflowResponse) => void;
  onArchive: (w: WorkflowResponse) => void;
  onCopy: (w: WorkflowResponse) => void;
  onSetVisibility?: (
    w: WorkflowResponse,
    visibility: 'private' | 'staging' | 'public',
  ) => void;
  copyingId: string | null;
  onApprovePublish: (w: WorkflowResponse) => void;
  onRejectPublish: (w: WorkflowResponse) => void;
  approvingId: string | null;
  rejectingId: string | null;
  getIssues: (w: WorkflowResponse) => WorkflowIssue[];
  onRetry: () => void;
}

export function WorkflowsOrganizationTab({
  loading,
  error,
  workflows,
  searchTerm,
  onSearchChange,
  statusFilter,
  onStatusChange,
  pendingCount,
  pageResetKey,
  isAdmin,
  isSuperAdmin,
  onRun,
  onDelete,
  onArchive,
  onCopy,
  onSetVisibility,
  copyingId,
  onApprovePublish,
  onRejectPublish,
  approvingId,
  rejectingId,
  getIssues,
  onRetry,
}: WorkflowsOrganizationTabProps) {
  const router = useRouter();
  const from = useCurrentUrl();

  const formatDateTime = (dateStr: string | null | undefined) =>
    dateStr ? formatDate(dateStr) : 'N/A';

  const columns: ResourceColumnConfig<WorkflowResponse>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (w) => w.name,
      render: (w) => {
        const issues = getIssues(w);
        return (
          <div>
            <Link
              href={withReturnTo(`/workflows/${w.id}/edit`, from)}
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
        );
      },
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (w) => w.status,
      render: (w) => <StatusBadge status={w.status || 'active'} />, // defaults-ok
    },
    {
      key: 'updated_at',
      header: 'Updated',
      sortValue: (w) => w.updated_at,
      render: (w) => (
        <span className="text-xs text-muted">
          {formatDateTime(w.updated_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (w) => {
        // Null-safety for the optional field; backend always sets it.
        const currentVisibility = w.visibility || 'private'; // defaults-ok
        return (
          <div className="flex justify-center items-center gap-2 max-md:flex-col max-md:items-stretch">
            {isAdmin && w.publish_status === 'pending' && (
              <>
                <ActionButton
                  variant="active"
                  onClick={() => onApprovePublish(w)}
                  disabled={approvingId === w.id}
                >
                  {approvingId === w.id ? 'Approving...' : 'Approve'}
                </ActionButton>
                <ActionButton
                  variant="warning"
                  onClick={() => onRejectPublish(w)}
                  disabled={rejectingId === w.id}
                >
                  {rejectingId === w.id ? 'Rejecting...' : 'Reject'}
                </ActionButton>
              </>
            )}
            {isSuperAdmin && onSetVisibility && (
              <select
                aria-label="Marketplace visibility"
                className="form-input text-xs py-1"
                value={currentVisibility}
                onChange={(e) =>
                  onSetVisibility(
                    w,
                    e.target.value as 'private' | 'staging' | 'public',
                  )
                }
              >
                <option value="private">Private</option>
                <option value="staging">Staging</option>
                <option value="public">Public</option>
              </select>
            )}
            {isAdmin && (
              <ActionButton
                variant="change"
                onClick={() => router.push(withReturnTo(`/workflows/${w.id}/edit`, from))}
              >
                Edit
              </ActionButton>
            )}
            {!isSuperAdmin && (w.status ?? 'active') === 'active' && ( // defaults-ok
              <ActionButton variant="active" onClick={() => onRun(w)}>
                Run
              </ActionButton>
            )}
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
            {/* Hidden while pending; Reject is how an admin declines. */}
            {isAdmin && w.publish_status !== 'pending' && w.status !== 'inactive' && w.status !== 'archived' && (
              <ActionButton variant="warning" onClick={() => onArchive(w)}>
                Archive
              </ActionButton>
            )}
            {isAdmin && w.publish_status !== 'pending' && w.can_be_deleted !== false && (w.status === 'inactive' || w.status === 'archived') && (
              <ActionButton
                variant="destructive"
                onClick={() => onDelete(w)}
              >
                Delete
              </ActionButton>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <ResourceTable
      data={workflows}
      getItemId={(w) => w.id}
      columns={columns}
      prefPage="workflows"
      pagination={{ itemLabel: 'workflow' }}
      pageResetKey={pageResetKey}
      loading={loading}
      loadingMessage="Loading organization workflows..."
      error={error}
      onRetry={onRetry}
      toolbar={
        <>
          <div className="w-full sm:w-auto sm:flex-1">
            <SearchInput
              value={searchTerm}
              onChange={onSearchChange}
              placeholder="Search workflows..."
            />
          </div>
          {isAdmin && (
            <select
              value={statusFilter}
              onChange={(e) => onStatusChange(e.target.value as typeof statusFilter)}
              className="form-select text-sm w-auto"
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending ({pendingCount})</option>
              <option value="published">Published</option>
            </select>
          )}
        </>
      }
      emptyState={
        <EmptyState
          title="No organization workflows"
          description={
            searchTerm
              ? `No results for "${searchTerm}".`
              : isSuperAdmin
              ? 'Install workflows from the Marketplace.'
              : 'No workflows are shared in your organization yet.'
          }
          action={searchTerm ? (
            <button type="button" className="btn-secondary" onClick={() => onSearchChange('')}>
              Clear search
            </button>
          ) : undefined}
        />
      }
    />
  );
}
