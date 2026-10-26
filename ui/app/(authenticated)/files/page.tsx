// ui/app/(authenticated)/files/page.tsx

"use client";

import { useState, useEffect, useRef, createElement } from 'react';
import { ResourceCard } from '@/widgets/instance-view';
import { FileViewerModal } from '@/features/files';
import { apiFetchBlob } from '@/shared/api';

import { OrgFile } from '@/shared/types/api';
import { CardSize } from '@/entities/organization';
import {
  Search, Filter, ArrowUpDown, ArrowUp, ArrowDown,
  LayoutGrid, List, Download, FileText, Image, Video, Music, File,
  Sparkles, CloudDownload, Upload, Check, X, Eye, Trash2, AlertTriangle, Square, CheckSquare,
  Grid3X3, Plus
} from 'lucide-react';
import {
  Pagination,
  LoadingState,
  ErrorState,
  EmptyState,
  ResourceTable,
  StatusBadge,
  type ResourceColumnConfig,
} from '@/shared/ui';
import { PAGE_SIZE_OPTIONS } from '@/shared/lib/pagination';
import { formatFileSize, formatDuration } from '@/shared/lib/format-utils';
import { useFileManager } from './hooks/useFileManager';
import { useFileFiltering, SortField } from './hooks/useFileFiltering';
import { useFileSelection } from './hooks/useFileSelection';
import {
  isVideoFile,
  isAudioFile,
  isImageFile,
  getDisplayFilename,
  getSourceLabel,
  getSourceColor,
  getSourceDescription,
  getSourceProvenance,
  getFileStatus,
} from './lib/fileTypeDetector';
import { formatDate } from '@/shared/lib/dateFormatter';

function getFileIconComponent(resource: OrgFile) {
  if (isImageFile(resource)) return Image;
  if (isVideoFile(resource)) return Video;
  if (isAudioFile(resource)) return Music;
  if (resource.mime_type.startsWith('text/') || resource.mime_type.startsWith('application/')) return FileText;
  return File;
}

function getSourceIcon(source: string) {
  switch (source) {
    case 'job_generated': return Sparkles;
    case 'job_download': return CloudDownload;
    case 'user_upload': return Upload;
    default: return File;
  }
}

const VIEWABLE = (resource: OrgFile) =>
  isImageFile(resource) || isVideoFile(resource) || isAudioFile(resource) || resource.mime_type === 'application/pdf';

const SORT_FIELD_BY_COLUMN: Record<string, SortField> = {
  preview: 'type',
  name: 'name',
  size: 'size',
  date: 'date',
  source: 'source',
  thumb: 'thumb',
  status: 'status',
};

const COLUMN_BY_SORT_FIELD: Partial<Record<SortField, string>> = {
  type: 'preview',
  name: 'name',
  size: 'size',
  date: 'date',
  source: 'source',
  thumb: 'thumb',
  status: 'status',
};

// Grid sort buttons, also shown on phones in table view where the column headers are hidden.
const SORT_BUTTON_FIELDS: SortField[] = ['name', 'date', 'size', 'type', 'source', 'status'];

// Preview cell that loads the image thumbnail as a blob
function FileThumbnail({
  resource,
  showThumbnails,
  cardSize = 'medium',
}: {
  resource: OrgFile;
  showThumbnails: boolean;
  cardSize?: CardSize;
}) {
  const [thumbnailBlobUrl, setThumbnailBlobUrl] = useState<string | null>(null);
  const [thumbnailError, setThumbnailError] = useState(false);

  const isImageType = isImageFile(resource);
  const shouldLoadThumbnail = showThumbnails && isImageType && resource.preview_url && !thumbnailError;

  useEffect(() => {
    if (!shouldLoadThumbnail || !resource.preview_url) return;

    let cancelled = false;

    const loadThumbnail = async () => {
      try {
        const blob = await apiFetchBlob(resource.preview_url!);
        if (!cancelled) {
          setThumbnailBlobUrl(URL.createObjectURL(blob));
        }
      } catch {
        if (!cancelled) setThumbnailError(true);
      }
    };

    loadThumbnail();

    return () => {
      cancelled = true;
      if (thumbnailBlobUrl) URL.revokeObjectURL(thumbnailBlobUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cleanup uses stale thumbnailBlobUrl intentionally
  }, [resource.preview_url, shouldLoadThumbnail]);

  useEffect(() => {
    return () => {
      if (thumbnailBlobUrl) URL.revokeObjectURL(thumbnailBlobUrl);
    };
  }, [thumbnailBlobUrl]);

  return (
    <div className={`inline-flex items-center justify-center bg-surface rounded overflow-hidden ${
      cardSize === 'small' ? 'w-12 h-12' : cardSize === 'large' ? 'w-24 h-24' : 'w-16 h-16'
    }`}>
      {thumbnailBlobUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- blob URLs not supported by Next.js Image
        <img
          src={thumbnailBlobUrl}
          alt={resource.display_name}
          className="w-full h-full object-cover"
          onError={() => setThumbnailError(true)}
        />
      ) : (
        createElement(getFileIconComponent(resource), {
          className: `text-muted ${
            cardSize === 'small' ? 'w-5 h-5' : cardSize === 'large' ? 'w-10 h-10' : 'w-7 h-7'
          }`,
        })
      )}
    </div>
  );
}

export default function FilesPage() {
  const filtering = useFileFiltering();
  const fm = useFileManager(filtering.query);
  const files = fm.files ?? [];
  const canDelete = fm.user?.role === 'admin' || fm.user?.role === 'super_admin';
  const selection = useFileSelection(
    files,
    {
      searchTerm: filtering.searchTerm,
      fileTypeFilter: filtering.fileTypeFilter,
      sourceFilter: filtering.sourceFilter,
      page: fm.page,
    },
    fm.refetch,
  );

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    await fm.handleFileUpload(files);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Wait for redirect or loading
  if (fm.authStatus === 'unauthenticated' ||
      (fm.authStatus === 'authenticated' && fm.user?.role === 'super_admin') ||
      fm.authStatus === 'loading' || fm.isLoading) {
    return (
      <>
        <LoadingState message="Loading files..." />
      </>
    );
  }

  if (fm.error) {
    return (
      <>
        <div className="p-6">
          <ErrorState
            title="Error Loading Files"
            message={(fm.error as Error).message}
            onRetry={() => fm.refetch()}
            retryLabel="Try Again"
          />
        </div>
      </>
    );
  }

  // Pagination calculations
  const totalCount = fm.totalCount;
  const totalPages = Math.ceil(totalCount / fm.pageSize) || 1;

  const renderSortIcon = (field: SortField) => {
    if (filtering.sortField !== field) return <ArrowUpDown className="w-3 h-3 text-muted" />;
    return filtering.sortDirection === 'asc'
      ? <ArrowUp className="w-3 h-3 text-info" />
      : <ArrowDown className="w-3 h-3 text-info" />;
  };

  const allSelected = selection.selectedIds.size === files.length && files.length > 0;

  const handleRowClick = (resource: OrgFile) => {
    if (selection.selectionMode) {
      selection.handleToggleSelect(resource.id);
    } else if (VIEWABLE(resource) && resource.status === 'available') {
      fm.handleView(resource);
    }
  };

  const selectColumn: ResourceColumnConfig<OrgFile>[] = canDelete ? [
    {
      key: 'select',
      priority: 'primary',
      header: (
        <div
          onClick={selection.handleSelectAll}
          className="w-5 h-5 flex items-center justify-center cursor-pointer"
          title={selection.selectedIds.size === files.length ? "Deselect all" : "Select all"}
        >
          {allSelected ? (
            <CheckSquare className="w-5 h-5 text-info" />
          ) : selection.selectedIds.size > 0 ? (
            <div className="w-5 h-5 border-2 border-info rounded flex items-center justify-center">
              <div className="w-2 h-2 bg-info rounded-sm" />
            </div>
          ) : (
            <Square className="w-5 h-5 text-muted hover:text-secondary" />
          )}
        </div>
      ),
      headerClassName: 'w-10',
      cellClassName: 'w-10',
      render: (resource) => (
        <div
          onClick={(e) => {
            e.stopPropagation();
            selection.handleToggleSelect(resource.id);
          }}
          className="w-5 h-5 flex items-center justify-center cursor-pointer"
        >
          {selection.selectedIds.has(resource.id) ? (
            <CheckSquare className="w-5 h-5 text-info" />
          ) : (
            <Square className="w-5 h-5 text-muted hover:text-secondary" />
          )}
        </div>
      ),
    },
  ] : [];

  const columns: ResourceColumnConfig<OrgFile>[] = [
    ...selectColumn,
    {
      key: 'preview',
      header: 'Preview',
      headerClassName: 'w-14',
      cellClassName: 'text-center',
      sortValue: (resource) => resource.mime_type,
      render: (resource) => (
        <FileThumbnail
          resource={resource}
          showThumbnails={fm.orgSettings.showThumbnails}
          cardSize={fm.orgSettings.resourceCardSize}
        />
      ),
    },
    {
      key: 'name',
      header: 'Name',
      sortValue: (resource) => getDisplayFilename(resource),
      render: (resource) => (
        <>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-primary min-w-0 wrap-anywhere" title={getDisplayFilename(resource)}>
              {getDisplayFilename(resource)}
            </span>
            {VIEWABLE(resource) && resource.status === 'available' && (
              <Eye className="w-3 h-3 text-muted flex-shrink-0" />
            )}
          </div>
          <div className="text-muted text-xs">
            {resource.mime_type}
          </div>
        </>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (resource) => resource.status,
      render: (resource) => {
        const { label, variant } = getFileStatus(resource.status);
        return <StatusBadge status={label} variant={variant} />;
      },
    },
    {
      key: 'size',
      header: 'Size',
      sortValue: (resource) => resource.file_size,
      render: (resource) => {
        const duration = resource.metadata?.duration as number | undefined;
        return (
          <span className="text-sm text-secondary">
            {formatFileSize(resource.file_size)}
            {duration != null && (
              <span className="ml-2 text-secondary dark:text-secondary">{formatDuration(duration)}</span>
            )}
          </span>
        );
      },
    },
    {
      key: 'date',
      header: 'Date',
      sortValue: (resource) => new Date(resource.created_at),
      render: (resource) => (
        <span className="text-sm text-secondary">
          {formatDate(resource.created_at)}
        </span>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      sortValue: (resource) => resource.source,
      render: (resource) => (
        <>
          <div
            className={`flex items-center gap-1 text-sm ${getSourceColor(resource.source)}`}
            title={getSourceDescription(resource.source)}
          >
            {createElement(getSourceIcon(resource.source), { className: 'w-4 h-4' })}
            <span>{getSourceLabel(resource.source)}</span>
          </div>
          {getSourceProvenance(resource) && (
            <div className="text-xs text-muted mt-0.5" title="Provenance">
              from {getSourceProvenance(resource)}
            </div>
          )}
        </>
      ),
    },
    {
      key: 'thumb',
      header: 'Thumbnail',
      align: 'center',
      headerClassName: 'w-24',
      sortValue: (resource) => (isImageFile(resource) ? (resource.has_thumbnail ? 0 : 1) : 2),
      render: (resource) => (isImageFile(resource) ? (
        resource.has_thumbnail ? (
          <Check className="w-4 h-4 text-success mx-auto" />
        ) : (
          <X className="w-4 h-4 text-muted mx-auto" />
        )
      ) : (
        <span className="text-muted">-</span>
      )),
    },
    {
      key: 'actions',
      header: '',
      headerClassName: 'w-16',
      render: (resource) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            fm.handleDownload(resource.id, getDisplayFilename(resource));
          }}
          disabled={resource.status !== 'available'}
          className="p-1.5 link rounded disabled:opacity-50 disabled:cursor-not-allowed"
          title="Download"
        >
          <Download className="w-4 h-4" />
        </button>
      ),
    },
  ];

  const emptyState = (
    <EmptyState
      icon={<File className="h-12 w-12" />}
      title={filtering.hasFilters
        ? 'No files found matching your filters'
        : 'No files available yet'}
      description="Files generated by workflows or uploaded by users will appear here."
    />
  );

  const fileCount = (
    <div className="text-sm text-secondary">
      {totalCount} {totalCount === 1 ? 'file' : 'files'}
    </div>
  );

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">Files</h1>
            <p className="section-subtitle mt-1">
              Browse all files generated by your workflows or uploaded by users
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              className="hidden"
              accept="image/*,video/*,audio/*,application/pdf,.pdf"
            />

            {/* Upload Button */}
            <button
              onClick={handleUploadClick}
              disabled={fm.isUploading}
              className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {fm.isUploading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  Upload Files
                </>
              )}
            </button>

            {/* View Toggle */}
            <div className="flex items-center gap-1 bg-card rounded-lg p-1">
              <button
                onClick={() => fm.handleViewModeChange('grid')}
                className={`p-2 rounded ${
                  fm.viewMode === 'grid'
                    ? 'bg-card shadow text-primary'
                    : 'text-secondary hover:text-secondary'
                }`}
                title="Grid view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => fm.handleViewModeChange('table')}
                className={`p-2 rounded ${
                  fm.viewMode === 'table'
                    ? 'bg-card shadow text-primary'
                    : 'text-secondary hover:text-secondary'
                }`}
                title="Table view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>

            {/* Card Size Toggle */}
            <div className="flex items-center gap-1 bg-card rounded-lg p-1">
              <button
                onClick={() => fm.updateSettings({ resourceCardSize: 'small' })}
                className={`p-2 rounded ${
                  fm.orgSettings.resourceCardSize === 'small'
                    ? 'bg-card shadow text-primary'
                    : 'text-secondary hover:text-secondary'
                }`}
                title="Small thumbnails"
              >
                <Grid3X3 className="w-4 h-4" />
              </button>
              <button
                onClick={() => fm.updateSettings({ resourceCardSize: 'medium' })}
                className={`p-2 rounded ${
                  fm.orgSettings.resourceCardSize === 'medium'
                    ? 'bg-card shadow text-primary'
                    : 'text-secondary hover:text-secondary'
                }`}
                title="Medium thumbnails"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => fm.updateSettings({ resourceCardSize: 'large' })}
                className={`p-2 rounded ${
                  fm.orgSettings.resourceCardSize === 'large'
                    ? 'bg-card shadow text-primary'
                    : 'text-secondary hover:text-secondary'
                }`}
                title="Large thumbnails"
              >
                <Square className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="filter-bar space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium text-secondary">
            <Filter className="w-4 h-4" />
            Filters <span className={fm.viewMode === 'grid' ? '' : 'md:hidden'}>&amp; Sort</span>
          </div>

          <div className={`grid grid-cols-1 md:grid-cols-2 ${fm.viewMode === 'grid' ? 'lg:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
            {/* Search */}
            <div>
              <label htmlFor="file-search" className="form-label">
                Search
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                <input
                  id="file-search"
                  type="text"
                  value={filtering.searchTerm}
                  onChange={(e) => filtering.setSearchTerm(e.target.value)}
                  placeholder="Search by filename..."
                  className="form-input-search"
                />
              </div>
            </div>

            {/* File Type */}
            <div>
              <label htmlFor="file-type-filter" className="form-label">
                File Type
              </label>
              <select
                id="file-type-filter"
                value={filtering.fileTypeFilter}
                onChange={(e) => filtering.setFileTypeFilter(e.target.value)}
                className="form-select w-full"
              >
                <option value="all">All Types</option>
                <option value="image">Images</option>
                <option value="video">Videos</option>
                <option value="audio">Audio</option>
                <option value="document">Documents</option>
                <option value="other">Other</option>
              </select>
            </div>

            {/* Source */}
            <div>
              <label htmlFor="file-source-filter" className="form-label">
                Source
              </label>
              <select
                id="file-source-filter"
                value={filtering.sourceFilter}
                onChange={(e) => filtering.setSourceFilter(e.target.value)}
                className="form-select w-full"
              >
                <option value="all">All Sources</option>
                <option value="job_generated" title="Created by a Studio worker">Generated</option>
                <option value="job_download" title="Retrieved by a Studio worker from an external provider">Downloaded</option>
                <option value="user_upload" title="Uploaded directly by a user">Uploaded</option>
              </select>
            </div>

            {/* Sort - grid view, and table view on phones */}
            <div className={fm.viewMode === 'grid' ? '' : 'md:hidden'}>
              <label className="form-label">
                Sort By
              </label>
              <div className="grid grid-cols-3 gap-1">
                {SORT_BUTTON_FIELDS.map((field) => (
                  <button
                    key={field}
                    onClick={() => filtering.handleSort(field)}
                    className={`px-2 py-2 text-xs border rounded-md flex items-center justify-center gap-1 transition-colors ${
                      filtering.sortField === field
                        ? 'border-info bg-info-subtle text-info'
                        : 'border-primary hover:bg-surface text-secondary'
                    }`}
                  >
                    <span className="capitalize">{field}</span>
                    {renderSortIcon(field)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Upload Error */}
        {fm.uploadError && (
          <div className="bg-danger-subtle border border-danger rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-danger flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-danger">Upload failed</p>
              <p className="text-sm text-danger mt-1">{fm.uploadError}</p>
            </div>
            <button
              onClick={() => fm.setUploadError(null)}
              className="text-danger hover:text-danger"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {fm.viewMode === 'table' ? (
          <ResourceTable<OrgFile>
            data={files}
            getItemId={(resource) => resource.id}
            columns={columns}
            nameColumn="name"
            sort={{
              field: COLUMN_BY_SORT_FIELD[filtering.sortField] ?? null,
              direction: filtering.sortDirection,
              onChange: (next) => {
                if (next.field) filtering.setSort(SORT_FIELD_BY_COLUMN[next.field], next.direction);
              },
              server: true,
            }}
            pagination={{
              itemLabel: 'file',
              server: {
                currentPage: fm.page,
                totalCount,
                pageSize: fm.pageSize,
                onPageChange: fm.setPage,
                onPageSizeChange: fm.handlePageSizeChange,
              },
            }}
            toolbar={fileCount}
            emptyState={emptyState}
            onRowClick={handleRowClick}
            rowClassName={(resource) => `${
              VIEWABLE(resource) && resource.status === 'available' && !selection.selectionMode ? 'cursor-pointer' : ''
            } ${selection.selectionMode ? 'cursor-pointer' : ''} ${selection.selectedIds.has(resource.id) ? 'bg-info-subtle' : ''}`}
            ariaLabel="Files"
          />
        ) : (
          <>
            {/* Pagination Controls - Top */}
            <div className="flex items-center justify-between">
              {fileCount}
              <Pagination
                currentPage={fm.page}
                totalPages={totalPages}
                totalCount={totalCount}
                pageSize={fm.pageSize}
                onPageChange={fm.setPage}
                onPageSizeChange={fm.handlePageSizeChange}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                position="top"
              />
            </div>

            {files.length === 0 ? emptyState : (
              <div className={`grid gap-4 items-start ${
                fm.orgSettings.resourceCardSize === 'small'
                  ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6'
                  : fm.orgSettings.resourceCardSize === 'large'
                  ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3'
                  : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
              }`}>
                {files.map((file) => (
                  <div key={file.id} className="relative group">
                    {/* Selection checkbox overlay - bottom-left to avoid the
                        Download/Regenerate/Delete cluster at top-left of ResourceCard */}
                    {canDelete && (
                    <div
                      className={`absolute bottom-2 left-2 z-10 transition-opacity ${
                        selection.selectionMode || selection.selectedIds.has(file.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                    >
                      <div
                        onClick={(e) => {
                          e.stopPropagation();
                          selection.handleToggleSelect(file.id);
                        }}
                        className="w-6 h-6 flex items-center justify-center cursor-pointer bg-card rounded shadow-sm"
                      >
                        {selection.selectedIds.has(file.id) ? (
                          <CheckSquare className="w-5 h-5 text-info" />
                        ) : (
                          <Square className="w-5 h-5 text-muted hover:text-secondary" />
                        )}
                      </div>
                    </div>
                    )}
                    {/* Selection highlight */}
                    {selection.selectedIds.has(file.id) && (
                      <div className="absolute inset-0 border-2 border-info rounded-lg pointer-events-none z-0" />
                    )}
                    <ResourceCard
                      resource={file}
                      onDownload={fm.handleDownload}
                      onView={selection.selectionMode ? undefined : fm.handleView}
                      showMetadata={true}
                      size={fm.orgSettings.resourceCardSize}
                      showThumbnails={fm.orgSettings.showThumbnails}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* Pagination Controls - Bottom */}
            {files.length > 0 && (
              <Pagination
                currentPage={fm.page}
                totalPages={totalPages}
                totalCount={totalCount}
                pageSize={fm.pageSize}
                onPageChange={fm.setPage}
                itemLabel="file"
                position="bottom"
              />
            )}
          </>
        )}
      </div>

      {/* Floating Action Bar - appears when items are selected */}
      {canDelete && selection.selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-gray-900 text-white rounded-lg shadow-xl px-4 py-3 flex items-center gap-4"> {/* css-check-ignore: floating action bar dark theme */}
            <span className="text-sm font-medium">
              {selection.selectedIds.size} {selection.selectedIds.size === 1 ? 'file' : 'files'} selected
            </span>
            <div className="h-4 w-px bg-gray-600" /> {/* css-check-ignore: divider in dark bar */}
            <button
              onClick={selection.handleDeleteSelected}
              disabled={selection.isDeleting}
              className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition-colors disabled:opacity-50" // css-check-ignore: danger button in dark bar
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
            <button
              onClick={selection.handleCancelSelection}
              className="btn-cancel flex items-center gap-2 text-sm"
            >
              <X className="w-4 h-4" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* File Viewer Modal */}
      {fm.viewingResource && (
        <FileViewerModal
          resource={fm.viewingResource}
          resources={files}
          onClose={() => fm.setViewingResource(null)}
          onDownload={fm.handleDownload}
          onNavigate={(resource) => fm.setViewingResource(resource)}
        />
      )}
    </>
  );
}
