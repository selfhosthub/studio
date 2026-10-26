// ui/app/(authenticated)/ai-prompts/prompts/list/components/PromptsMyTab.tsx

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
import { formatPromptCategory } from '@/shared/lib/prompt-labels';

interface PromptsMyTabProps {
  loading: boolean;
  error: string | null;
  filteredPrompts: Prompt[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  onDelete: (prompt: Prompt) => void;
  deletingId: string | null;
  onRequestPublish: (prompt: Prompt) => void;
  publishingId: string | null;
  onRetry: () => void;
}

// Status badge shown for a personal prompt.
const myStatus = (prompt: Prompt) =>
  prompt.publish_status === 'pending'
    ? 'pending'
    : prompt.publish_status === 'rejected'
      ? 'rejected'
      : 'personal';

export function PromptsMyTab({
  loading,
  error,
  filteredPrompts,
  searchTerm,
  onSearchChange,
  onDelete,
  deletingId,
  onRequestPublish,
  publishingId,
  onRetry,
}: PromptsMyTabProps) {
  const router = useRouter();
  const from = useCurrentUrl();

  const columns: ResourceColumnConfig<Prompt>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (prompt) => prompt.name,
      render: (prompt) => (
        <div>
          <Link
            href={withReturnTo(`/ai-prompts/prompts/${prompt.id}/edit`, from)}
            className="text-sm font-medium link hover:underline"
          >
            {prompt.name}
          </Link>
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
      key: 'status',
      header: 'Status',
      sortValue: myStatus,
      render: (prompt) => <StatusBadge status={myStatus(prompt)} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (prompt) => (
        <div className="flex justify-center items-center gap-2 max-md:flex-col max-md:items-stretch">
          <ActionButton
            variant="change"
            onClick={() =>
              router.push(withReturnTo(`/ai-prompts/prompts/${prompt.id}/edit`, from))
            }
          >
            Edit
          </ActionButton>
          {prompt.publish_status !== 'pending' && (
            <ActionButton
              variant="active"
              onClick={() => onRequestPublish(prompt)}
              disabled={publishingId === prompt.id}
            >
              {prompt.publish_status === 'rejected' ? 'Resubmit' : 'Publish'}
            </ActionButton>
          )}
          <ActionButton
            variant="destructive"
            onClick={() => onDelete(prompt)}
            disabled={deletingId === prompt.id}
          >
            Delete
          </ActionButton>
        </div>
      ),
    },
  ];

  return (
    <ResourceTable
      data={filteredPrompts}
      getItemId={(prompt) => prompt.id}
      columns={columns}
      prefPage="prompts-my"
      pagination={{ itemLabel: 'prompt' }}
      pageResetKey={searchTerm}
      loading={loading}
      loadingMessage="Loading your prompts..."
      error={error}
      onRetry={onRetry}
      toolbar={
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={searchTerm}
            onChange={onSearchChange}
            placeholder="Search your prompts..."
          />
        </div>
      }
      emptyState={
        <EmptyState
          title="No personal prompts"
          description={
            searchTerm
              ? `No results for "${searchTerm}".`
              : 'Copy a prompt from Organization to get started, or create a new one.'
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
