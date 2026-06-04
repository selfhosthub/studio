// ui/app/infrastructure/components/StorageTabPanel.tsx

'use client';

import Link from 'next/link';
import { HardDrive, RefreshCw, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { Pagination } from '@/shared/ui';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import type { SystemHealthResponse, PaginatedStorageResponse, StorageSortField, SortOrder } from '@/shared/api';

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

function SortIcon({ field, sortBy, sortOrder }: { field: StorageSortField; sortBy: StorageSortField; sortOrder: SortOrder }) {
  if (sortBy !== field) return <ChevronsUpDown className="w-3 h-3 ml-1 opacity-40" />;
  return sortOrder === 'asc' ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />;
}

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
            <>
              <div className="flex justify-end mb-4">
                <Pagination
                  currentPage={storagePage}
                  totalPages={storageData.total_pages || 1}
                  totalCount={storageData.total}
                  pageSize={storagePageSize}
                  onPageChange={(p) => onPageChange(p, storagePageSize)}
                  onPageSizeChange={onPageSizeChange}
                  pageSizeOptions={PAGE_SIZE_OPTIONS}
                  position="top"
                />
              </div>

              <div className="overflow-x-auto rounded-lg border border-primary">
                <table className="min-w-full divide-y divide-theme">
                  <thead className="bg-card">
                    <tr>
                      <th className="table-sort-header text-left" onClick={() => onSort('name')}>
                        <span className="inline-flex items-center">
                          Organization <SortIcon field="name" sortBy={storageSortBy} sortOrder={storageSortOrder} />
                        </span>
                      </th>
                      <th className="table-sort-header text-right" onClick={() => onSort('files')}>
                        <span className="inline-flex items-center justify-end">
                          Files <SortIcon field="files" sortBy={storageSortBy} sortOrder={storageSortOrder} />
                        </span>
                      </th>
                      <th className="table-sort-header text-right" onClick={() => onSort('size_bytes')}>
                        <span className="inline-flex items-center justify-end">
                          Usage <SortIcon field="size_bytes" sortBy={storageSortBy} sortOrder={storageSortOrder} />
                        </span>
                      </th>
                      <th className="px-4 py-2.5 text-right text-xs font-medium text-muted uppercase">Limit</th>
                      <th className="table-sort-header text-right min-w-[180px]" onClick={() => onSort('usage_percent')}>
                        <span className="inline-flex items-center justify-end">
                          Usage <SortIcon field="usage_percent" sortBy={storageSortBy} sortOrder={storageSortOrder} />
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-page divide-y divide-theme">
                    {storageData.items.length > 0 ? (
                      storageData.items.map((org) => (
                        <tr key={org.organization_id}>
                          <td className="px-4 py-2">
                            <Link
                              href={`/organizations/${org.organization_id}`}
                              className="block hover:bg-hover rounded -m-1 p-1 transition-colors"
                            >
                              <div className="text-sm font-medium text-primary hover:text-info">{org.organization_name}</div>
                              <div className="text-xs text-muted">{org.organization_slug}</div>
                            </Link>
                          </td>
                          <td className="px-4 py-2 text-sm text-right text-secondary">{org.files.toLocaleString()}</td>
                          <td className="px-4 py-2 text-sm text-right text-secondary">{org.size_formatted}</td>
                          <td className="px-4 py-2 text-sm text-right text-secondary">{org.storage_limit_formatted || '-'}</td>
                          <td className="px-4 py-2 text-sm">
                            {org.usage_percent !== null && org.usage_percent !== undefined ? (
                              <div className="flex items-center gap-2">
                                <div className="flex-1 h-2 bg-input rounded-full overflow-hidden">
                                  <div
                                    className={`h-full rounded-full transition-all ${ // css-check-ignore: no semantic token for yellow
                                      org.usage_percent > 90 ? 'bg-danger' :
                                      org.usage_percent > 75 ? 'bg-yellow-500' :
                                      'bg-success'
                                    }`}
                                    style={{ width: `${Math.min(org.usage_percent, 100)}%` }}
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
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="px-4 py-8 text-center text-muted">No organizations found</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <Pagination
                currentPage={storagePage}
                totalPages={storageData.total_pages || 1}
                totalCount={storageData.total}
                pageSize={storagePageSize}
                onPageChange={(p) => onPageChange(p, storagePageSize)}
                itemLabel="organization"
                position="bottom"
              />
            </>
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
