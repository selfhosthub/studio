// ui/app/ai-agents/prompts/list/components/PromptsOrganizationTab.tsx

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
import type { Prompt } from '@/shared/types/prompt';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';

const PAGE_SIZE_KEY = 'prompt-templates-pageSize';

const CATEGORY_OPTIONS = [
  { value: '', label: 'All Categories' },
  { value: 'general', label: 'General' },
  { value: 'story_generation', label: 'Story Generation' },
  { value: 'scene_description', label: 'Scene Description' },
  { value: 'summarization', label: 'Summarization' },
  { value: 'classification', label: 'Classification' },
  { value: 'extraction', label: 'Extraction' },
  { value: 'rewriting', label: 'Rewriting' },
];

interface PromptsOrganizationTabProps {
  loading: boolean;
  error: string | null;
  filteredPrompts: Prompt[];
  paginatedPrompts: Prompt[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  categoryFilter: string;
  onCategoryChange: (cat: string) => void;
  currentPage: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  onDelete: (prompt: Prompt) => void;
  deletingId: string | null;
  onCopy: (prompt: Prompt) => void;
  copyingId: string | null;
  onApprovePublish: (prompt: Prompt) => void;
  onRejectPublish: (prompt: Prompt) => void;
  publishingId: string | null;
  onRetry: () => void;
}

export function PromptsOrganizationTab({
  loading,
  error,
  filteredPrompts,
  paginatedPrompts,
  searchTerm,
  onSearchChange,
  categoryFilter,
  onCategoryChange,
  currentPage,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  isAdmin,
  isSuperAdmin,
  onDelete,
  deletingId,
  onCopy,
  copyingId,
  onApprovePublish,
  onRejectPublish,
  publishingId,
  onRetry,
}: PromptsOrganizationTabProps) {
  const router = useRouter();

  if (loading) return <LoadingState message="Loading prompts..." />;
  if (error) return <ErrorState title="Error" message={error} onRetry={onRetry} />;

  return (
    <>
      {/* Search + Category Filter + Pagination */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
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
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalCount={filteredPrompts.length}
          pageSize={pageSize}
          onPageChange={onPageChange}
          onPageSizeChange={(size) => {
            onPageSizeChange(size);
            localStorage.setItem(PAGE_SIZE_KEY, String(size));
          }}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          position="top"
          itemLabel="prompt"
        />
      </div>

      {filteredPrompts.length === 0 ? (
        <EmptyState
          title="No prompts"
          description={
            searchTerm || categoryFilter
              ? 'No prompts match your filters.'
              : isSuperAdmin
                ? 'Upload your own custom prompts.'
                : 'Create your first prompt or install one from the Marketplace.'
          }
        />
      ) : (
        <>
          <TableContainer>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Name</TableHeaderCell>
                  <TableHeaderCell>Category</TableHeaderCell>
                  <TableHeaderCell>Source</TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedPrompts.map((prompt) => (
                  <TableRow key={prompt.id}>
                    <TableCell>
                      <div>
                        {isAdmin ? (
                          <Link
                            href={`/ai-agents/prompts/${prompt.id}/edit`}
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
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-secondary">
                        {prompt.category.replace(/_/g, ' ')}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={prompt.source} />
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center space-x-2">
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
                                    router.push(`/ai-agents/prompts/${prompt.id}/edit`)
                                  }
                                >
                                  Edit
                                </ActionButton>
                                <ActionButton
                                  variant="active"
                                  onClick={() => onCopy(prompt)}
                                  disabled={copyingId === prompt.id}
                                >
                                  Copy
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
                            Copy
                          </ActionButton>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalCount={filteredPrompts.length}
            pageSize={pageSize}
            onPageChange={onPageChange}
            itemLabel="prompt"
            position="bottom"
          />
        </>
      )}
    </>
  );
}
