// ui/app/files/page.tsx

"use client";

import { useState, useEffect, useRef } from 'react';
import { DashboardLayout } from '@/widgets/layout';
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
  Modal,
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
} from './lib/fileTypeDetector';

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

// Table row component with thumbnail loading
function FileTableRow({
  resource,
  onView,
  onDownload,
  showThumbnails,
  isSelected,
  onToggleSelect,
  selectionMode,
  cardSize = 'medium',
}: {
  resource: OrgFile;
  onView: (resource: OrgFile) => void;
  onDownload: (id: string, name: string) => void;
  showThumbnails: boolean;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  selectionMode: boolean;
  cardSize?: CardSize;
}) {
  const [thumbnailBlobUrl, setThumbnailBlobUrl] = useState<string | null>(null);
  const [thumbnailError, setThumbnailError] = useState(false);

  const IconComponent = getFileIconComponent(resource);
  const SourceIcon = getSourceIcon(resource.source);
  const isImageType = isImageFile(resource);
  const isViewable = isImageFile(resource) || isVideoFile(resource) || isAudioFile(resource) || resource.mime_type === 'application/pdf';
  const duration = resource.metadata?.duration as number | undefined;

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

  const handleRowClick = () => {
    if (selectionMode) {
      onToggleSelect(resource.id);
    } else if (isViewable && resource.status === 'available') {
      onView(resource);
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleSelect(resource.id);
  };

  return (
    <tr
      className={`border-b border-primary hover:bg-surface ${
        isViewable && resource.status === 'available' && !selectionMode ? 'cursor-pointer' : ''
      } ${selectionMode ? 'cursor-pointer' : ''} ${isSelected ? 'bg-info-subtle' : ''}`}
      onClick={handleRowClick}
    >
      {/* Checkbox */}
      <td className="px-3 py-2 w-10">
        <div
          onClick={handleCheckboxClick}
          className="w-5 h-5 flex items-center justify-center cursor-pointer"
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-info" />
          ) : (
            <Square className="w-5 h-5 text-muted hover:text-secondary" />
          )}
        </div>
      </td>

      {/* Preview/Icon */}
      <td className="px-3 py-2 text-center">
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
            <IconComponent className={`text-muted ${
              cardSize === 'small' ? 'w-5 h-5' : cardSize === 'large' ? 'w-10 h-10' : 'w-7 h-7'
            }`} />
          )}
        </div>
      </td>

      {/* Filename */}
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-primary break-all" title={getDisplayFilename(resource)}>
            {getDisplayFilename(resource)}
          </span>
          {isViewable && resource.status === 'available' && (
            <Eye className="w-3 h-3 text-muted flex-shrink-0" />
          )}
        </div>
        <div className="text-muted text-xs">
          {resource.mime_type}
        </div>
      </td>

      {/* Size */}
      <td className="px-3 py-2">
        <span className="text-sm text-secondary">
          {formatFileSize(resource.file_size)}
          {duration != null && (
            <span className="ml-2 text-secondary dark:text-secondary">{formatDuration(duration)}</span>
          )}
        </span>
      </td>

      {/* Date */}
      <td className="px-3 py-2">
        <span className="text-sm text-secondary">
          {new Date(resource.created_at).toLocaleString()}
        </span>
      </td>

      {/* Source */}
      <td className="px-3 py-2">
        <div className={`flex items-center gap-1 text-sm${getSourceColor(resource.source)}`}>
          <SourceIcon className="w-4 h-4" />
          <span>{getSourceLabel(resource.source)}</span>
        </div>
      </td>

      {/* Thumbnail exists */}
      <td className="px-3 py-2 text-center">
        {isImageType ? (
          resource.has_thumbnail ? (
            <Check className="w-4 h-4 text-success mx-auto" />
          ) : (
            <X className="w-4 h-4 text-muted mx-auto" />
          )
        ) : (
          <span className="text-muted">-</span>
        )}
      </td>

      {/* Actions */}
      <td className="px-3 py-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDownload(resource.id, resource.display_name);
          }}
          disabled={resource.status !== 'available'}
          className="p-1.5 link rounded disabled:opacity-50 disabled:cursor-not-allowed"
          title="Download"
        >
          <Download className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}

export default function FilesPage() {
  const fm = useFileManager();
  const filtering = useFileFiltering(fm.files);
  const selection = useFileSelection(
    filtering.filteredAndSortedFiles,
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
      <DashboardLayout>
        <LoadingState message="Loading files..." />
      </DashboardLayout>
    );
  }

  if (fm.error) {
    return (
      <DashboardLayout>
        <div className="p-6">
          <ErrorState
            title="Error Loading Files"
            message={(fm.error as Error).message}
            onRetry={() => fm.refetch()}
            retryLabel="Try Again"
          />
        </div>
      </DashboardLayout>
    );
  }

  // Pagination calculations
  const totalCount = filtering.filteredAndSortedFiles.length;
  const totalPages = Math.ceil(totalCount / fm.pageSize) || 1;

  const renderSortIcon = (field: SortField) => {
    if (filtering.sortField !== field) return <ArrowUpDown className="w-3 h-3 text-muted" />;
    return filtering.sortDirection === 'asc'
      ? <ArrowUp className="w-3 h-3 text-info" />
      : <ArrowDown className="w-3 h-3 text-info" />;
  };

  return (
    <DashboardLayout>
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
            Filters {fm.viewMode === 'grid' && '& Sort'}
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
                <option value="job_generated">Generated</option>
                <option value="job_download">Downloaded</option>
                <option value="user_upload">Uploaded</option>
              </select>
            </div>

            {/* Sort - only show in grid view */}
            {fm.viewMode === 'grid' && (
              <div>
                <label className="form-label">
                  Sort By
                </label>
                <div className="flex gap-1">
                  {(['name', 'date', 'size', 'type', 'source'] as SortField[]).map((field) => (
                    <button
                      key={field}
                      onClick={() => filtering.handleSort(field)}
                      className={`flex-1 px-2 py-2 text-xs border rounded-md flex items-center justify-center gap-1 transition-colors ${
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
            )}
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

        {/* Pagination Controls - Top */}
        <div className="flex items-center justify-between">
          <div className="text-sm text-secondary">
            {totalCount} {totalCount === 1 ? 'file' : 'files'}
          </div>
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

        {/* Files Display */}
        {filtering.filteredAndSortedFiles.length === 0 ? (
          <EmptyState
            icon={<File className="h-12 w-12" />}
            title={filtering.searchTerm || filtering.fileTypeFilter !== 'all' || filtering.sourceFilter !== 'all'
              ? 'No files found matching your filters'
              : 'No files available yet'}
            description="Files generated by workflows or uploaded by users will appear here."
          />
        ) : fm.viewMode === 'table' ? (
          /* Table View */
          <div className="bg-card rounded-lg shadow border border-primary overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-primary">
                <thead className="bg-surface">
                  <tr>
                    {/* Select All Checkbox */}
                    <th className="px-3 py-2 w-10">
                      <div
                        onClick={selection.handleSelectAll}
                        className="w-5 h-5 flex items-center justify-center cursor-pointer"
                        title={selection.selectedIds.size === filtering.filteredAndSortedFiles.length ? "Deselect all" : "Select all"}
                      >
                        {selection.selectedIds.size === filtering.filteredAndSortedFiles.length && filtering.filteredAndSortedFiles.length > 0 ? (
                          <CheckSquare className="w-5 h-5 text-info" />
                        ) : selection.selectedIds.size > 0 ? (
                          <div className="w-5 h-5 border-2 border-info rounded flex items-center justify-center">
                            <div className="w-2 h-2 bg-info rounded-sm" />
                          </div>
                        ) : (
                          <Square className="w-5 h-5 text-muted hover:text-secondary" />
                        )}
                      </div>
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider w-14">
                      Preview
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider cursor-pointer hover:bg-card select-none" onClick={() => filtering.handleSort('name')}>
                      <div className="flex items-center gap-1">Filename{renderSortIcon('name')}</div>
                    </th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-secondary uppercase tracking-wider cursor-pointer hover:bg-card select-none" onClick={() => filtering.handleSort('size')}>
                      <div className="flex items-center gap-1">Size{renderSortIcon('size')}</div>
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider cursor-pointer hover:bg-card select-none" onClick={() => filtering.handleSort('date')}>
                      <div className="flex items-center gap-1">Date{renderSortIcon('date')}</div>
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider cursor-pointer hover:bg-card select-none" onClick={() => filtering.handleSort('source')}>
                      <div className="flex items-center gap-1">Source{renderSortIcon('source')}</div>
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-medium text-secondary uppercase tracking-wider w-20">
                      Thumb
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-secondary uppercase tracking-wider w-16">

                    </th>
                  </tr>
                </thead>
                <tbody className="bg-card divide-y divide-primary">
                  {filtering.filteredAndSortedFiles.map((file) => (
                    <FileTableRow
                      key={file.id}
                      resource={file}
                      onView={fm.handleView}
                      onDownload={fm.handleDownload}
                      showThumbnails={fm.orgSettings.showThumbnails}
                      isSelected={selection.selectedIds.has(file.id)}
                      onToggleSelect={selection.handleToggleSelect}
                      selectionMode={selection.selectionMode}
                      cardSize={fm.orgSettings.resourceCardSize}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          /* Grid View */
          <div className={`grid gap-4 ${
            fm.orgSettings.resourceCardSize === 'small'
              ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6'
              : fm.orgSettings.resourceCardSize === 'large'
              ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3'
              : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
          }`}>
            {filtering.filteredAndSortedFiles.map((file) => (
              <div key={file.id} className="relative group">
                {/* Selection checkbox overlay */}
                <div
                  className={`absolute top-2 left-2 z-10 transition-opacity ${
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
        {filtering.filteredAndSortedFiles.length > 0 && (
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
      </div>

      {/* Floating Action Bar - appears when items are selected */}
      {selection.selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-gray-900 text-white rounded-lg shadow-xl px-4 py-3 flex items-center gap-4"> {/* css-check-ignore: floating action bar dark theme */}
            <span className="text-sm font-medium">
              {selection.selectedIds.size} {selection.selectedIds.size === 1 ? 'file' : 'files'} selected
            </span>
            <div className="h-4 w-px bg-gray-600" /> {/* css-check-ignore: divider in dark bar */}
            <button
              onClick={() => selection.setShowDeleteConfirm(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm font-medium transition-colors" // css-check-ignore: danger button in dark bar
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
            <button
              onClick={selection.handleCancelSelection}
              className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors" // css-check-ignore: button in dark bar
            >
              <X className="w-4 h-4" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={selection.showDeleteConfirm}
        onClose={() => { selection.setShowDeleteConfirm(false); selection.setDeleteError(null); }}
        title={`Delete ${selection.selectedIds.size} ${selection.selectedIds.size === 1 ? 'file' : 'files'}?`}
        size="sm"
      >
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-danger-subtle flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-danger" />
            </div>
            <div className="flex-1">
              <p className="mt-2 text-sm text-secondary">
                This will permanently delete the selected files and their associated thumbnails. This action cannot be undone.
              </p>
              {selection.deleteError && (
                <div className="mt-3 p-2 bg-danger-subtle border border-danger rounded text-sm text-danger">
                  {selection.deleteError}
                </div>
              )}
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <button
              onClick={() => {
                selection.setShowDeleteConfirm(false);
                selection.setDeleteError(null);
              }}
              disabled={selection.isDeleting}
              className="px-4 py-2 text-sm font-medium text-secondary bg-card hover:bg-input rounded-md transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={selection.handleDeleteSelected}
              disabled={selection.isDeleting}
              className="btn-danger flex items-center gap-2 disabled:opacity-50"
            >
              {selection.isDeleting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="w-4 h-4" />
                  Delete
                </>
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* File Viewer Modal */}
      {fm.viewingResource && (
        <FileViewerModal
          resource={fm.viewingResource}
          resources={filtering.filteredAndSortedFiles}
          onClose={() => fm.setViewingResource(null)}
          onDownload={fm.handleDownload}
          onNavigate={(resource) => fm.setViewingResource(resource)}
        />
      )}
    </DashboardLayout>
  );
}
