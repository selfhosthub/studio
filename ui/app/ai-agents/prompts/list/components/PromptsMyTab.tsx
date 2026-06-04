// ui/app/ai-agents/prompts/list/components/PromptsMyTab.tsx

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

const PAGE_SIZE_KEY = 'my-prompts-pageSize';

interface PromptsMyTabProps {
  loading: boolean;
  error: string | null;
  filteredPrompts: Prompt[];
  paginatedPrompts: Prompt[];
  searchTerm: string;
  onSearchChange: (term: string) => void;
  currentPage: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onDelete: (prompt: Prompt) => void;
  deletingId: string | null;
  onRequestPublish: (prompt: Prompt) => void;
  publishingId: string | null;
  onRetry: () => void;
}

export function PromptsMyTab({
  loading,
  error,
  filteredPrompts,
  paginatedPrompts,
  searchTerm,
  onSearchChange,
  currentPage,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  onDelete,
  deletingId,
  onRequestPublish,
  publishingId,
  onRetry,
}: PromptsMyTabProps) {
  const router = useRouter();

  if (loading) return <LoadingState message="Loading your prompts..." />;
  if (error) return <ErrorState title="Error" message={error} onRetry={onRetry} />;

  return (
    <>
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="w-full sm:w-auto sm:flex-1">
          <SearchInput
            value={searchTerm}
            onChange={onSearchChange}
            placeholder="Search your prompts..."
          />
        </div>
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
          title="No personal prompts"
          description={
            searchTerm
              ? 'No prompts match your search.'
              : 'Copy a prompt from Organization to get started, or create a new one.'
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
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell align="center">Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedPrompts.map((prompt) => (
                  <TableRow key={prompt.id}>
                    <TableCell>
                      <div>
                        <Link
                          href={`/ai-agents/prompts/${prompt.id}/edit`}
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
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-secondary">
                        {prompt.category.replace(/_/g, ' ')}
                      </span>
                    </TableCell>
                    <TableCell>
                      {prompt.publish_status === 'pending' ? (
                        <StatusBadge status="pending" />
                      ) : prompt.publish_status === 'rejected' ? (
                        <StatusBadge status="rejected" />
                      ) : (
                        <StatusBadge status="personal" />
                      )}
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center space-x-2">
                        <ActionButton
                          variant="change"
                          onClick={() =>
                            router.push(`/ai-agents/prompts/${prompt.id}/edit`)
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
                            Publish
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
