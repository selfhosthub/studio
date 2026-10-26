// ui/app/(authenticated)/ai-prompts/prompts/list/components/PromptsOrganizationTab.tsx

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
import type { Prompt } from '@/shared/types/prompt';
import { useCurrentUrl, withReturnTo } from '@/shared/hooks/useReturnTo';
import {
  formatPromptCategory,
  promptCategoryOptions,
  promptSourceLabel,
} from '@/shared/lib/prompt-labels';

const CATEGORY_OPTIONS = [{ value: '', label: 'All Categories' }, ...promptCategoryOptions()];

const SOURCE_BADGE_VARIANT = { Plus: 'warning', Community: 'default', Yours: 'info', Custom: 'info' } as const;

interface PromptsOrganizationTabProps {
  loading: boolean;
  error: string | null;
  currentUserId?: string | null;
  filteredPrompts: Prompt[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  categoryFilter: string;
  onCategoryChange: (cat: string) => void;
  statusFilter: "all" | "pending" | "published";
  onStatusChange: (status: "all" | "pending" | "published") => void;
  pendingCount: number;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  onDelete: (prompt: Prompt) => void;
  deletingId: string | null;
  onCopy: (prompt: Prompt) => void;
  copyingId: string | null;
  onApprovePublish: (prompt: Prompt) => void;
  onRejectPublish: (prompt: Prompt) => void;
  publishingId: string | null;
  onSetVisibility?: (prompt: Prompt, visibility: 'private' | 'staging' | 'public') => void;
  onRetry: () => void;
}

export function PromptsOrganizationTab({
  loading,
  error,
  currentUserId,
  filteredPrompts,
  searchTerm,
  onSearchChange,
  categoryFilter,
  onCategoryChange,
  statusFilter,
  onStatusChange,
  pendingCount,
  isAdmin,
  isSuperAdmin,
  onDelete,
  deletingId,
  onCopy,
  copyingId,
  onApprovePublish,
  onRejectPublish,
  publishingId,
  onSetVisibility,
  onRetry,
}: PromptsOrganizationTabProps) {
  const router = useRouter();
  const from = useCurrentUrl();

  const columns: ResourceColumnConfig<Prompt>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (prompt) => prompt.name,
      render: (prompt) => (
        <div>
          {isAdmin ? (
            <Link
              href={withReturnTo(`/ai-prompts/prompts/${prompt.id}/edit`, from)}
              className="text-sm font-medium link hover:underline"
            >
              {prompt.name}
            </Link>
          ) : (
            <span className="text-sm font-medium">
              {prompt.name}
            </span>
          )}
          {prompt.description && (
            <div className="text-muted line-clamp-2">
              {prompt.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      cellClassName: 'wrap-anywhere',
      sortValue: (prompt) => formatPromptCategory(prompt.category),
      render: (prompt) => (
        <span className="text-sm text-secondary">
          {formatPromptCategory(prompt.category)}
        </span>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      sortValue: (prompt) => promptSourceLabel(prompt, currentUserId),
      render: (prompt) => {
        const label = promptSourceLabel(prompt, currentUserId);
        return <StatusBadge status={label} variant={SOURCE_BADGE_VARIANT[label]} />;
      },
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (prompt) => (
        <div className="flex justify-center items-center gap-2 max-md:flex-col max-md:items-stretch">
          {isSuperAdmin && onSetVisibility && (
            <select
              aria-label="Marketplace visibility"
              className="form-input text-xs py-1"
              value={prompt.visibility || 'private'} // defaults-ok
              onChange={(e) =>
                onSetVisibility(
                  prompt,
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
            <>
              {prompt.publish_status === 'pending' ? (
                <>
                  <ActionButton
                    variant="active"
                    onClick={() => onApprovePublish(prompt)}
                    disabled={publishingId === prompt.id}
                  >
                    Approve
                  </ActionButton>
                  <ActionButton
                    variant="warning"
                    onClick={() => onRejectPublish(prompt)}
                    disabled={publishingId === prompt.id}
                  >
                    Reject
                  </ActionButton>
                </>
              ) : (
                <>
                  <ActionButton
                    variant="change"
                    onClick={() =>
                      router.push(withReturnTo(`/ai-prompts/prompts/${prompt.id}/edit`, from))
                    }
                  >
                    Edit
                  </ActionButton>
                  <ActionButton
                    variant="active"
                    onClick={() => onCopy(prompt)}
                    disabled={copyingId === prompt.id}
                  >
                    Copy to My Prompts
                  </ActionButton>
                  <ActionButton
                    variant="destructive"
                    onClick={() => onDelete(prompt)}
                    disabled={deletingId === prompt.id}
                  >
                    Delete
                  </ActionButton>
                </>
              )}
            </>
          )}
          {!isAdmin && (
            <ActionButton
              variant="active"
              onClick={() => onCopy(prompt)}
              disabled={copyingId === prompt.id}
            >
              Copy to My Prompts
            </ActionButton>
          )}
        </div>
      ),
    },
  ];

  return (
    <ResourceTable
      data={filteredPrompts}
      getItemId={(prompt) => prompt.id}
      columns={columns}
      prefPage="prompts"
      pagination={{ itemLabel: 'prompt' }}
      pageResetKey={`${searchTerm}|${categoryFilter}|${statusFilter}`}
      loading={loading}
      loadingMessage="Loading prompts..."
      error={error}
      onRetry={onRetry}
      toolbar={
        <>
          <div className="w-full sm:w-auto sm:flex-1">
            <SearchInput
              value={searchTerm}
              onChange={onSearchChange}
              placeholder="Search prompts..."
            />
          </div>
          <select
            value={categoryFilter}
            onChange={(e) => onCategoryChange(e.target.value)}
            className="form-select text-sm w-auto"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
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
          title="No prompts"
          description={
            searchTerm
              ? `No results for "${searchTerm}".`
              : categoryFilter
              ? 'No prompts match your filters.'
              : isSuperAdmin
                ? 'Upload your own custom prompts.'
                : 'Create your first prompt or install one from the Marketplace.'
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
