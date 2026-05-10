// ui/widgets/instance-view/ResourceCard.tsx

'use client';

import React, { useState, useEffect } from 'react';
import { Download, FileText, Image, Video, AudioLines, File, Calendar, Eye, Upload, CloudDownload, Sparkles, Check, Trash2, RotateCw } from 'lucide-react';
import { OrgFile } from '@/shared/types/api';
import { downloadResource, apiFetchBlob } from '@/shared/api';
import { formatFileSize, formatDuration } from '@/shared/lib/format-utils';

export type CardSize = 'small' | 'medium' | 'large';

interface ResourceCardProps {
  resource: OrgFile;
  onDownload: (resourceId: string, filename: string) => void;
  onDelete?: (resourceId: string) => void; // Callback to delete the resource
  onRegenerate?: (resourceId: string) => void; // Callback to regenerate this resource
  onView?: (resource: OrgFile) => void; // Click to view in modal
  showMetadata?: boolean; // Show workflow/instance info
  size?: CardSize; // Card size: small, medium, large
  showThumbnails?: boolean; // Whether to display thumbnails (org setting)
  selectable?: boolean; // Show selection checkbox
  selected?: boolean; // Whether checkbox is checked
  onSelect?: (resourceId: string) => void; // Callback when checkbox toggled
}

// Get filename from resource - prefer virtual_path filename which already has unique ID
function getDownloadFilename(resource: OrgFile): string {
  // Extract filename from virtual_path (e.g., "generated_images_d8f06d83.png")
  if (resource.virtual_path) {
    const parts = resource.virtual_path.split('/');
    const filename = parts[parts.length - 1];
    if (filename && filename.includes('.')) return filename;
  }
  // Fallback: construct from display_name + short ID
  let baseName = resource.display_name || 'file';
  const lastDot = baseName.lastIndexOf('.');
  if (lastDot > 0) {
    baseName = baseName.substring(0, lastDot);
  }
  baseName = baseName.replace(/[^a-zA-Z0-9]/g, '_').replace(/_+/g, '_');
  const shortId = resource.id.slice(-8);
  const ext = resource.file_extension || '.bin';
  return `${baseName}_${shortId}${ext.startsWith('.') ? ext : '.' + ext}`;
}

function getFileIcon(mimeType: string) {
  if (mimeType.startsWith('image/')) return Image;
  if (mimeType.startsWith('video/')) return Video;
  if (mimeType.startsWith('audio/')) return AudioLines;
  if (mimeType.startsWith('text/') || mimeType.startsWith('application/')) return FileText;
  return File;
}


function getStatusBadge(status: string) {
  switch (status) {
    case 'available':
      return <span className="text-xs px-2 py-1 rounded bg-success-subtle text-success">Ready</span>;
    case 'pending':
      return <span className="text-xs px-2 py-1 rounded bg-card text-secondary">Pending</span>;
    case 'generating':
      return (
        <span className="text-xs px-2 py-1 rounded bg-info-subtle text-info flex items-center gap-1">
          <span className="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full" />
          Generating...
        </span>
      );
    case 'failed':
      return <span className="text-xs px-2 py-1 rounded bg-danger-subtle text-danger">Failed</span>;
    default:
      return <span className="text-xs px-2 py-1 rounded bg-card text-secondary">{status}</span>;
  }
}

function getSourceIcon(source: string) {
  switch (source) {
    case 'job_generated': return Sparkles;
    case 'job_download': return CloudDownload;
    case 'user_upload': return Upload;
    default: return File;
  }
}

function getSourceLabel(source: string): string {
  switch (source) {
    case 'job_generated': return 'Generated';
    case 'job_download': return 'Downloaded';
    case 'user_upload': return 'Uploaded';
    default: return source;
  }
}

function getSourceColor(source: string): string {
  switch (source) {
    case 'job_generated': return 'text-success';
    case 'job_download': return 'text-info';
    case 'user_upload': return 'text-purple-600 dark:text-purple-400'; // css-check-ignore: no semantic token
    default: return 'text-secondary';
  }
}

const ResourceCard = React.memo(function ResourceCard({ resource, onDownload, onDelete, onRegenerate, onView, showMetadata = false, size = 'medium', showThumbnails = true, selectable = false, selected = false, onSelect }: ResourceCardProps) {
  const isSmall = size === 'small';
  const isLarge = size === 'large';
  const [thumbnailError, setThumbnailError] = useState(false);
  const [thumbnailBlobUrl, setThumbnailBlobUrl] = useState<string | null>(null);
  const [audioBlobUrl, setAudioBlobUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const SourceIcon = getSourceIcon(resource.source);
  const createdDate = new Date(resource.created_at).toLocaleDateString();

  // Helper to detect file type by extension when mime_type is octet-stream
  const getFileExtension = (filename: string): string => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
  };

  // Extract actual filename from virtual_path (e.g., "/path/to/file.mp3" -> "file.mp3")
  const getFilenameFromPath = (path: string): string => {
    if (!path) return '';
    const parts = path.split('/').filter(Boolean);
    return parts[parts.length - 1] || '';
  };

  const actualFilename = getFilenameFromPath(resource.virtual_path) || resource.display_name;

  const isAudioExtension = (filename: string): boolean => {
    const ext = getFileExtension(filename);
    return ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma'].includes(ext);
  };

  const isVideoExtension = (filename: string): boolean => {
    const ext = getFileExtension(filename);
    return ['mp4', 'webm', 'mov', 'avi', 'mkv', 'flv', 'wmv'].includes(ext);
  };

  const isImageExtension = (filename: string): boolean => {
    const ext = getFileExtension(filename);
    return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext);
  };

  // Check file types with fallback to extension-based detection
  const isImageType = resource.mime_type.startsWith('image/') ||
                      (resource.mime_type === 'application/octet-stream' && isImageExtension(actualFilename));
  const isAudioType = resource.mime_type.startsWith('audio/') ||
                      (resource.mime_type === 'application/octet-stream' && isAudioExtension(actualFilename));
  const isVideoType = resource.mime_type.startsWith('video/') ||
                      (resource.mime_type === 'application/octet-stream' && isVideoExtension(actualFilename));

  // Pick icon based on detected type (extension-aware), not just mime_type
  const IconComponent = isImageType ? Image : isVideoType ? Video : isAudioType ? AudioLines : getFileIcon(resource.mime_type);

  // Check if file is viewable
  const isViewable = isImageType || isVideoType || isAudioType || resource.mime_type === 'application/pdf';

  // Fetch thumbnail with auth and create blob URL (only if showThumbnails is enabled)
  const shouldLoadThumbnail = showThumbnails && isImageType && resource.preview_url && !thumbnailError;

  useEffect(() => {
    if (!shouldLoadThumbnail || !resource.preview_url) return;

    let cancelled = false;

    const loadThumbnail = async () => {
      try {
        const blob = await apiFetchBlob(resource.preview_url!);
        if (!cancelled) {
          const blobUrl = URL.createObjectURL(blob);
          setThumbnailBlobUrl(blobUrl);
        }
      } catch {
        if (!cancelled) {
          setThumbnailError(true);
        }
      }
    };

    loadThumbnail();

    return () => {
      cancelled = true;
      if (thumbnailBlobUrl) {
        URL.revokeObjectURL(thumbnailBlobUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cleanup uses stale thumbnailBlobUrl intentionally
  }, [resource.preview_url, shouldLoadThumbnail]);

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (thumbnailBlobUrl) {
        URL.revokeObjectURL(thumbnailBlobUrl);
      }
    };
  }, [thumbnailBlobUrl]);

  // Load audio file for inline player
  useEffect(() => {
    if (!isAudioType || resource.status !== 'available' || audioBlobUrl) return;

    let cancelled = false;
    setAudioLoading(true);

    const loadAudio = async () => {
      try {
        const blob = await downloadResource(resource.id);
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          setAudioBlobUrl(url);
          setAudioLoading(false);
        }
      } catch (error) {
        console.error('Error loading audio:', error);
        if (!cancelled) {
          setAudioLoading(false);
        }
      }
    };

    loadAudio();

    return () => {
      cancelled = true;
    };
  }, [isAudioType, resource.status, resource.id, audioBlobUrl]);

  // Cleanup audio blob URL on unmount
  useEffect(() => {
    return () => {
      if (audioBlobUrl) {
        URL.revokeObjectURL(audioBlobUrl);
      }
    };
  }, [audioBlobUrl]);

  // Parse workflow name and run number from virtual_path (e.g., "/Workflow Name/Run 3/")
  const parseVirtualPath = (path: string) => {
    if (!path) return { workflowName: null, runNumber: null };
    const parts = path.split('/').filter(Boolean);
    if (parts.length >= 2) {
      const workflowName = parts[0];
      const runMatch = parts[1].match(/Run (\d+)/);
      const runNumber = runMatch ? runMatch[1] : null;
      return { workflowName, runNumber };
    }
    return { workflowName: parts[0] || null, runNumber: null };
  };

  const { workflowName, runNumber } = parseVirtualPath(resource.virtual_path);

  // Show thumbnail if we have a loaded blob URL
  const showThumbnail = thumbnailBlobUrl && !thumbnailError;

  // Size-based styling with significant differentiation for accessibility
  // Small: compact, Medium: default readable, Large: accessibility-friendly
  const containerPadding = isSmall ? 'p-2' : isLarge ? 'p-4' : 'p-3';
  const thumbnailHeight = isSmall ? 'h-24' : isLarge ? 'h-56' : 'h-36';
  const thumbnailMargin = isSmall ? 'mb-1' : isLarge ? 'mb-3' : 'mb-2';
  const iconSize = isSmall ? 'w-6 h-6' : isLarge ? 'w-14 h-14' : 'w-10 h-10';
  const spinnerSize = isSmall ? 'w-6 h-6' : isLarge ? 'w-12 h-12' : 'w-8 h-8';
  const titleSize = isSmall ? 'text-xs' : isLarge ? 'text-lg' : 'text-sm';
  const metaSize = isSmall ? 'text-[10px]' : isLarge ? 'text-base' : 'text-xs';
  // Button sizes for controls - larger on large cards for easier clicking
  const buttonSize = isSmall ? 'p-1' : isLarge ? 'p-2.5' : 'p-1.5';
  const buttonIconSize = isSmall ? 'w-3.5 h-3.5' : isLarge ? 'w-5 h-5' : 'w-4 h-4';
  const checkboxSize = isSmall ? 'w-5 h-5' : isLarge ? 'w-8 h-8' : 'w-6 h-6';
  const checkboxIconSize = isSmall ? 'w-3 h-3' : isLarge ? 'w-5 h-5' : 'w-4 h-4';

  // Get seed from metadata if available (for ComfyUI generated images)
  const seed = resource.metadata?.seed as number | undefined;
  const duration = resource.metadata?.duration as number | undefined;

  const handleClick = () => {
    if (onView && isViewable && resource.status === 'available') {
      onView(resource);
    }
  };

  const handleSelectClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onSelect) {
      onSelect(resource.id);
    }
  };

  return (
    <div className={`border rounded-lg bg-card hover:shadow-md transition-shadow ${containerPadding} ${
      selected
        ? 'border-info ring-2 ring-[var(--theme-primary)]/30'
        : 'border-primary'
    }`}>
      {/* Thumbnail or Icon - clickable if viewable */}
      <div
        className={`relative flex items-center justify-center bg-surface rounded ${thumbnailHeight} ${thumbnailMargin} ${
          onView && isViewable && resource.status === 'available' ? 'cursor-pointer group' : ''
        }`}
        onClick={handleClick}
      >
        {showThumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URLs not supported by Next.js Image
          <img
            src={thumbnailBlobUrl}
            alt={resource.display_name}
            className="max-h-full max-w-full object-contain rounded"
            onError={() => setThumbnailError(true)}
          />
        ) : shouldLoadThumbnail && !thumbnailError ? (
          // Loading state
          <div className={`border-2 border-primary border-t-[var(--theme-primary)] rounded-full animate-spin ${spinnerSize}`} />
        ) : (
          <IconComponent className={`text-muted dark:text-secondary ${iconSize}`} />
        )}

        {/* Action buttons - top left corner */}
        {resource.status === 'available' && (
          <div className="absolute top-1.5 left-1.5 flex gap-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDownload(resource.id, getDownloadFilename(resource));
              }}
              className={`${buttonSize} bg-black/60 hover:bg-black/80 rounded transition-colors`}
              title="Download"
            >
              <Download className={`${buttonIconSize} text-white`} />
            </button>
            {onRegenerate && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRegenerate(resource.id);
                }}
                className={`${buttonSize} bg-black/60 hover:bg-[var(--theme-primary)] rounded transition-colors`}
                title="Regenerate"
              >
                <RotateCw className={`${buttonIconSize} text-white`} />
              </button>
            )}
            {onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(resource.id);
                }}
                className={`${buttonSize} bg-black/60 hover:bg-[var(--theme-danger)] rounded transition-colors`}
                title="Delete"
              >
                <Trash2 className={`${buttonIconSize} text-white`} />
              </button>
            )}
          </div>
        )}

        {/* Selection checkbox - bottom left corner */}
        {selectable && (
          <button
            onClick={handleSelectClick}
            className={`absolute bottom-1.5 left-1.5 ${checkboxSize} rounded border-2 flex items-center justify-center transition-colors ${
              selected
                ? 'bg-info border-info text-white shadow-md'
                : 'bg-card border-secondary hover:border-[var(--theme-primary)] shadow-md'
            }`}
            title={selected ? 'Deselect for regeneration' : 'Select for regeneration'}
          >
            {selected && <Check className={checkboxIconSize} />}
          </button>
        )}

        {/* Status badge - top right corner */}
        <div className="absolute top-1 right-1">
          {getStatusBadge(resource.status)}
        </div>

        {/* Hover overlay for viewable files */}
        {onView && isViewable && resource.status === 'available' && (
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors rounded flex items-center justify-center pointer-events-none">
            <Eye className="w-6 h-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        )}
      </div>

      {/* File Info */}
      <div className={isSmall ? 'space-y-0.5' : 'space-y-1'}>
        <div className={`font-medium break-all text-primary ${titleSize}`} title={getDownloadFilename(resource)}>
          {getDownloadFilename(resource)}
        </div>
        <div className={`text-secondary ${metaSize}`}>
          {formatFileSize(resource.file_size)}{duration != null && ` • ${formatDuration(duration)}`} • {resource.mime_type.split('/')[1]?.toUpperCase() || 'FILE'}
        </div>

        {/* Seed display for AI-generated images */}
        {seed !== undefined && (
          <div className={`text-secondary ${metaSize}`} title={`Seed: ${seed}`}>
            <span>Seed: </span>
            <span className="font-mono">{seed}</span>
          </div>
        )}

        {/* Metadata for Resources page - show date and source */}
        {showMetadata && !isSmall && (
          <div className="mt-2 pt-2 border-t border-primary space-y-1">
            <div className={`flex items-center gap-1 text-secondary ${metaSize}`}>
              <Calendar className="w-3 h-3 flex-shrink-0" />
              <span>{createdDate}</span>
            </div>
            <div className={`flex items-center gap-1 ${getSourceColor(resource.source)} ${metaSize}`}>
              <SourceIcon className="w-3 h-3 flex-shrink-0" />
              <span>{getSourceLabel(resource.source)}</span>
            </div>
          </div>
        )}

        {/* Inline Audio Player */}
        {isAudioType && resource.status === 'available' && (
          <div className={`mt-2 pt-2 border-t border-primary ${isSmall ? 'mt-1 pt-1' : ''}`}>
            {audioLoading ? (
              <div className="flex items-center justify-center py-2 text-secondary">
                <div className="w-4 h-4 border-2 border-primary border-t-[var(--theme-primary)] rounded-full animate-spin" />
                <span className={`ml-2 ${metaSize}`}>Loading audio...</span>
              </div>
            ) : audioBlobUrl ? (
              <audio
                src={audioBlobUrl}
                controls
                className="w-full"
                preload="metadata"
              />
            ) : null}
          </div>
        )}
      </div>


      {/* Error Message (if failed) */}
      {resource.status === 'failed' && resource.metadata?.error && (
        <div className="mt-2 text-xs text-danger truncate" title={resource.metadata.error}>
          {resource.metadata.error}
        </div>
      )}
    </div>
  );
});

export default ResourceCard;
