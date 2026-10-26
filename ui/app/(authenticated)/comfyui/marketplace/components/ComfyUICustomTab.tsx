// ui/app/(authenticated)/comfyui/marketplace/components/ComfyUICustomTab.tsx

'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import {
  ResourceTable,
  SearchInput,
  LoadingState,
  ErrorState,
  EmptyState,
  type ResourceColumnConfig,
} from '@/shared/ui';
import { Trash2, Upload } from 'lucide-react';
import { useListPref, isString } from '@/shared/hooks/useListPref';
import type { MarketplaceComfyUI } from '@/shared/api';
import { useComfyUIMarketplace } from './useComfyUIMarketplace';

const VISIBILITY_OPTIONS = [
  { value: 'private', label: 'Private' },
  { value: 'staging', label: 'Staging' },
  { value: 'public', label: 'Public' },
] as const;

export function ComfyUICustomTab() {
  const mp = useComfyUIMarketplace();
  const [search, setSearch] = useListPref('comfyui-custom', 'search', '', isString);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return mp.customWorkflows
      .filter(
        (w) =>
          !q ||
          w.display_name.toLowerCase().includes(q) ||
          w.id.toLowerCase().includes(q) ||
          w.description.toLowerCase().includes(q)
      )
      .sort((a, b) => a.display_name.localeCompare(b.display_name, undefined, { sensitivity: 'base' }));
  }, [mp.customWorkflows, search]);

  const columns: ResourceColumnConfig<MarketplaceComfyUI>[] = [
    {
      key: 'display_name',
      header: 'Name',
      sortValue: (w) => w.display_name,
      render: (w) => (
        <>
          <div className="font-medium text-primary">{w.display_name}</div>
          <div className="text-xs text-muted">{w.id}</div>
        </>
      ),
    },
    {
      key: 'version',
      header: 'Version',
      sortValue: (w) => w.version,
      cellClassName: 'text-secondary',
      render: (w) => w.version,
    },
    {
      key: 'category',
      header: 'Category',
      sortValue: (w) => w.category,
      cellClassName: 'text-secondary wrap-anywhere',
      render: (w) => w.category || '-', // defaults-ok: display placeholder
    },
    {
      key: 'visibility',
      header: 'Visibility',
      sortValue: (w) => w.visibility || 'private', // defaults-ok: null-safety, API always sends it
      render: (w) => (
        <select
          aria-label="Marketplace visibility"
          value={w.visibility || 'private'} // defaults-ok: null-safety, API always sends it
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
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'center',
      render: (w) => (
        <div className="flex justify-center gap-2 items-center max-md:flex-col max-md:items-stretch">
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
      ),
    },
  ];

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
    <ResourceTable
      data={filtered}
      getItemId={(w) => w.id}
      columns={columns}
      prefPage="comfyui-custom"
      pagination={{ itemLabel: 'workflow' }}
      pageResetKey={search}
      emptyState={
        <EmptyState
          title="No matches"
          description={search ? `No results for "${search}".` : 'No custom workflows match your search.'}
          action={search ? (
            <button type="button" className="btn-secondary" onClick={() => setSearch('')}>
              Clear search
            </button>
          ) : undefined}
        />
      }
      toolbar={
        <div className="flex-1 max-w-md">
          <SearchInput value={search} onChange={setSearch} placeholder="Search custom workflows..." />
        </div>
      }
    />
  );
}
