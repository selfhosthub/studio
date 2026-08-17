// ui/app/(authenticated)/comfyui/marketplace/components/ComfyUICustomTab.tsx

'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import {
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
} from '@/shared/ui';
import { Trash2, Upload } from 'lucide-react';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { useComfyUIMarketplace } from './useComfyUIMarketplace';

const VISIBILITY_OPTIONS = [
  { value: 'private', label: 'Private' },
  { value: 'staging', label: 'Staging' },
  { value: 'public', label: 'Public' },
] as const;

export function ComfyUICustomTab() {
  const mp = useComfyUIMarketplace();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);

  const filtered = useMemo(() => {
    if (!search) return mp.customWorkflows;
    const q = search.toLowerCase();
    return mp.customWorkflows.filter(
      (w) =>
        w.display_name.toLowerCase().includes(q) ||
        w.id.toLowerCase().includes(q) ||
        w.description.toLowerCase().includes(q)
    );
  }, [mp.customWorkflows, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  if (mp.loading) return <LoadingState message="Loading custom workflows..." />;
  if (mp.error) return <ErrorState message={mp.error} onRetry={mp.fetchMarketplace} />;
  if (mp.customWorkflows.length === 0) {
    return (
      <EmptyState
        title="No custom workflows"
        description="Workflows you upload land here, private until published."
        action={
          <Link href="/comfyui/upload" className="btn-primary inline-flex items-center gap-2">
            <Upload size={16} />
            Upload Workflow
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between mb-4">
        <div className="flex-1 max-w-md">
          <SearchInput value={search} onChange={setSearch} placeholder="Search custom workflows..." />
        </div>
        <Pagination
          currentPage={safePage}
          totalPages={totalPages}
          totalCount={filtered.length}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
          itemLabel="workflow"
        />
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No matches" description="No custom workflows match your search." />
      ) : (
        <TableContainer>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHeaderCell>Name</TableHeaderCell>
                <TableHeaderCell>Version</TableHeaderCell>
                <TableHeaderCell>Category</TableHeaderCell>
                <TableHeaderCell>Visibility</TableHeaderCell>
                <TableHeaderCell align="center">Actions</TableHeaderCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginated.map((w) => {
                const visibility = w.visibility || 'private'; // defaults-ok: null-safety, API always sends it
                const category = w.category || '-'; // defaults-ok: display placeholder
                return (
                  <TableRow key={w.id}>
                    <TableCell>
                      <div className="font-medium text-primary">{w.display_name}</div>
                      <div className="text-xs text-muted">{w.id}</div>
                    </TableCell>
                    <TableCell className="text-secondary">{w.version}</TableCell>
                    <TableCell className="text-secondary">{category}</TableCell>
                    <TableCell>
                      <select
                        aria-label="Marketplace visibility"
                        value={visibility}
                        onChange={(e) =>
                          mp.handleSetVisibility(
                            w.id,
                            e.target.value as 'private' | 'staging' | 'public'
                          )
                        }
                        className="form-input text-xs py-1"
                      >
                        {VISIBILITY_OPTIONS.map((v) => (
                          <option key={v.value} value={v.value}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                    <TableCell align="center">
                      <div className="flex justify-center gap-2">
                        <button
                          type="button"
                          onClick={() => mp.handleUninstall(w.id)}
                          disabled={mp.uninstallingId === w.id}
                          className="action-btn-uninstall"
                          aria-label={`Remove ${w.display_name}`}
                        >
                          {mp.uninstallingId === w.id ? (
                            'Removing...'
                          ) : (
                            <>
                              <Trash2 className="w-3 h-3 mr-1" />
                              Remove
                            </>
                          )}
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </div>
  );
}
