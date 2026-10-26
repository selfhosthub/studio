// ui/app/(authenticated)/workflows/list/components/WorkflowsMyTab.tsx

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
import { canRunWorkflow } from '@/entities/workflow';

interface WorkflowsMyTabProps {
  loading: boolean;
  error: string | null;
  workflows: WorkflowResponse[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  onRun: (w: WorkflowResponse) => void;
  onDelete: (w: WorkflowResponse) => void;
  onArchive: (w: WorkflowResponse) => void;
  onRequestPublish: (w: WorkflowResponse) => void;
  publishingId: string | null;
  onRetry: () => void;
  getIssues: (w: WorkflowResponse) => WorkflowIssue[];
  currentUserId?: string;
}

export function WorkflowsMyTab({
  loading,
  error,
  workflows,
  searchTerm,
  onSearchChange,
  onRun,
  onDelete,
  onArchive,
  onRequestPublish,
  publishingId,
  onRetry,
  getIssues,
  currentUserId,
}: WorkflowsMyTabProps) {
  const router = useRouter();
  const from = useCurrentUrl();

  const formatDateTime = (dateStr: string | null | undefined) =>
    dateStr ? formatDate(dateStr) : 'N/A';

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
            {getPublishBadge(w.publish_status)}
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
      render: (w) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
          <ActionButton
            variant="change"
            onClick={() => router.push(withReturnTo(`/workflows/${w.id}/edit`, from))}
          >
            Edit
          </ActionButton>
          {canRunWorkflow(w, currentUserId) && (
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
          {w.publish_status !== 'pending' && (
            <ActionButton
              variant="navigate"
              onClick={() => onRequestPublish(w)}
              disabled={publishingId === w.id}
            >
              {publishingId === w.id
                ? 'Submitting...'
                : w.publish_status === 'rejected'
                  ? 'Resubmit'
                  : 'Publish'}
            </ActionButton>
          )}
          {w.can_be_deleted === false ? (
            <ActionButton
              variant="warning"
              onClick={() => onArchive(w)}
            >
              Archive
            </ActionButton>
          ) : (
            <ActionButton
              variant="destructive"
              onClick={() => onDelete(w)}
            >
              Delete
            </ActionButton>
          )}
        </div>
      ),
    },
  ];

  return (
    <ResourceTable
      data={workflows}
      getItemId={(w) => w.id}
      columns={columns}
      prefPage="workflows-my"
      pagination={{ itemLabel: 'workflow' }}
      pageResetKey={searchTerm}
      loading={loading}
      loadingMessage="Loading your workflows..."
      error={error}
      onRetry={onRetry}
      toolbar={
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={searchTerm}
            onChange={onSearchChange}
            placeholder="Search workflows..."
          />
        </div>
      }
      emptyState={
        <EmptyState
          title="No workflows yet"
          description={
            searchTerm
              ? `No results for "${searchTerm}".`
              : 'Create your first workflow or copy one from the Organization tab.'
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
