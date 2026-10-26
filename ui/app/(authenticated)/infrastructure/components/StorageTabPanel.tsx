// ui/app/(authenticated)/infrastructure/components/StorageTabPanel.tsx

'use client';

import Link from 'next/link';
import { HardDrive, RefreshCw } from 'lucide-react';
import { ResourceTable, type ResourceColumnConfig } from '@/shared/ui';
import type {
  SystemHealthResponse,
  PaginatedStorageResponse,
  OrganizationStorageItem,
  StorageSortField,
  SortOrder,
} from '@/shared/api';

interface StorageTabPanelProps {
  health: SystemHealthResponse;
  storageData: PaginatedStorageResponse | null;
  storagePage: number;
  storagePageSize: number;
  storageLoading: boolean;
  storageSortBy: StorageSortField;
  storageSortOrder: SortOrder;
  onSort: (field: StorageSortField) => void;
  onPageChange: (page: number, pageSize: number) => void;
  onPageSizeChange: (size: number) => void;
  onRefresh: () => void;
}

export const storageColumns: ResourceColumnConfig<OrganizationStorageItem>[] = [
  {
    key: 'name',
    header: 'Organization',
    sortValue: (org) => org.organization_name,
    render: (org) => (
      <Link
        href={`/organizations/${org.organization_id}`}
        className="block hover:bg-hover rounded -m-1 p-1 transition-colors"
      >
        <div className="text-sm font-medium text-primary hover:text-info">{org.organization_name}</div>
        <div className="text-xs text-muted">{org.organization_slug}</div>
      </Link>
    ),
  },
  { key: 'files', header: 'Files', align: 'right', cellClassName: 'text-secondary', sortValue: (org) => org.files, render: (org) => org.files.toLocaleString() },
  { key: 'size_bytes', header: 'Size', align: 'right', cellClassName: 'text-secondary', sortValue: (org) => org.size_bytes, render: (org) => org.size_formatted },
  { key: 'limit', header: 'Limit', align: 'right', headerClassName: 'text-muted', cellClassName: 'text-secondary', render: (org) => org.storage_limit_formatted || '-' }, // defaults-ok
  {
    key: 'usage_percent',
    header: 'Percent used',
    align: 'right',
    headerClassName: 'md:min-w-[180px]',
    sortValue: (org) => org.usage_percent,
    render: (org) => (
      org.usage_percent !== null && org.usage_percent !== undefined ? (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 bg-input rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${ // css-check-ignore: no semantic token for yellow
                org.usage_percent > 90 ? 'bg-danger' :
                org.usage_percent > 75 ? 'bg-yellow-500' :
                'bg-success'
              }`}
              style={{ width: `${Math.min(org.usage_percent, 100)}%` }} // css-check-ignore
            />
          </div>
          <span className={`text-xs font-medium w-12 text-right ${
            org.usage_percent > 90 ? 'text-danger' :
            org.usage_percent > 75 ? 'text-warning' :
            'text-success'
          }`}>
            {org.usage_percent.toFixed(1)}%
          </span>
        </div>
      ) : (
        <span className="text-muted text-right block">No limit</span>
      )
    ),
  },
];

export function StorageTabPanel({
  health,
  storageData,
  storagePage,
  storagePageSize,
  storageLoading,
  storageSortBy,
  storageSortOrder,
  onSort,
  onPageChange,
  onPageSizeChange,
  onRefresh,
}: StorageTabPanelProps) {
  // Limit and percent columns show once any organization has a storage limit
  const hasLimits = storageData?.items.some((org) => org.storage_limit_bytes != null) ?? false;
  const columns = storageColumns.map((col) =>
    col.key === 'limit' || col.key === 'usage_percent' ? { ...col, visible: hasLimits } : col,
  );

  return (
    <div className="space-y-6">
      {/* Storage Overview */}
      <div className="detail-section detail-section-purple">
        <div className="detail-section-header">
          <h2 className="section-title flex items-center">
            <HardDrive className="w-5 h-5 mr-2 text-purple" />
            Storage Overview
          </h2>
        </div>
        <div className="detail-section-body">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="infra-card-title">Backend</p>
              <p className="mt-1 infra-card-value capitalize">{health.storage.backend}</p>
            </div>
            <div>
              <p className="infra-card-title">Total Size</p>
              <p className="mt-1 infra-card-value">
                {storageData?.total_size_formatted || health.storage.total_size_formatted}
              </p>
            </div>
            <div>
              <p className="infra-card-title">Total Files</p>
              <p className="mt-1 infra-card-value">
                {(storageData?.total_files || health.storage.total_files).toLocaleString()}
              </p>
            </div>
          </div>
          {health.storage.workspace_path && (
            <div className="mt-6">
              <p className="infra-card-title">Workspace Path</p>
              <code className="code-inline mt-1">{health.storage.workspace_path}</code>
            </div>
          )}
        </div>
      </div>

      {/* Per-Organization Storage with Pagination */}
      <div className="detail-section detail-section-purple">
        <div className="detail-section-header flex justify-between items-center">
          <h2 className="section-title">Storage by Organization</h2>
          <button
            onClick={onRefresh}
            disabled={storageLoading}
            className="btn-secondary text-sm inline-flex items-center"
          >
            <RefreshCw className={`w-3 h-3 mr-1 ${storageLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        <div className="detail-section-body">
          {storageLoading && !storageData ? (
            <div className="text-center py-8">
              <RefreshCw className="w-8 h-8 animate-spin mx-auto text-muted" />
              <p className="mt-2 text-sm text-muted">Loading organization storage...</p>
            </div>
          ) : storageData ? (
            <ResourceTable
              data={storageData.items}
              getItemId={(org) => org.organization_id}
              columns={columns}
              prefPage="infra-storage"
              sort={{
                field: storageSortBy,
                direction: storageSortOrder,
                onChange: (next) => onSort(next.field as StorageSortField),
                server: true,
              }}
              pagination={{
                itemLabel: 'organization',
                server: {
                  currentPage: storagePage,
                  totalCount: storageData.total,
                  pageSize: storagePageSize,
                  onPageChange: (p) => onPageChange(p, storagePageSize),
                  onPageSizeChange,
                },
              }}
              emptyMessage="No organizations found"
              containerClassName="mb-0"
            />
          ) : (
            <div className="text-center py-8 text-muted">
              <HardDrive className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No organization storage data available</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
