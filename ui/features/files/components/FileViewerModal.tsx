// ui/features/files/components/FileViewerModal.tsx

'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, Download, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RotateCw, Maximize2, Image, Video, Music, FileText } from 'lucide-react';
import { OrgFile } from '@/shared/types/api';
import { apiFetchBlob } from '@/shared/api';
import { formatFileSize } from '@/shared/lib/format-utils';
import { Modal } from '@/shared/ui';

interface FileViewerModalProps {
  resource: OrgFile;
  resources?: OrgFile[]; // Optional list for prev/next navigation
  onClose: () => void;
  onDownload: (resourceId: string, filename: string) => void;
  onNavigate?: (resource: OrgFile) => void;
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
    case 'job_generated': return 'bg-success-subtle text-success'; // css-check-ignore
    case 'job_download': return 'bg-info-subtle text-info'; // css-check-ignore
    case 'user_upload': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400';
    default: return 'bg-surface text-secondary'; // css-check-ignore
  }
}

export default function FileViewerModal({
  resource,
  resources = [],
  onClose,
  onDownload,
  onNavigate
}: FileViewerModalProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);

  const isImage = resource.mime_type.startsWith('image/');
  const isVideo = resource.mime_type.startsWith('video/');
  const isAudio = resource.mime_type.startsWith('audio/');
  const isPdf = resource.mime_type === 'application/pdf';
  const isViewable = isImage || isVideo || isAudio || isPdf;

  // Find current index for navigation
  const currentIndex = resources.findIndex(r => r.id === resource.id);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < resources.length - 1 && currentIndex !== -1;

  // Fetch file with auth
  useEffect(() => {
    if (!isViewable) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    const loadFile = async () => {
      try {
        setLoading(true);
        setError(null);

        const blob = await apiFetchBlob(resource.download_url);
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          setBlobUrl(url);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load file');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadFile();

    return () => {
      cancelled = true;
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cleanup uses stale blobUrl intentionally
  }, [resource.id, resource.download_url, isViewable]);

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  // Keyboard navigation for arrow keys (Escape is handled by Dialog)
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' && hasPrev && onNavigate) {
      onNavigate(resources[currentIndex - 1]);
    } else if (e.key === 'ArrowRight' && hasNext && onNavigate) {
      onNavigate(resources[currentIndex + 1]);
    }
  }, [hasPrev, hasNext, onNavigate, resources, currentIndex]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleZoomIn = () => setZoom(z => Math.min(z + 0.25, 3));
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.25, 0.5));
  const handleRotate = () => setRotation(r => (r + 90) % 360);
  const handleResetView = () => { setZoom(1); setRotation(0); };
  const handleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen();
    }
  };

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white" />
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-white">
          <p className="text-danger mb-4">{error}</p>
          <button
            onClick={() => onDownload(resource.id, resource.display_name)}
            className="btn-primary flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download Instead
          </button>
        </div>
      );
    }

    if (!isViewable) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-white">
          <FileText className="w-16 h-16 text-muted mb-4" />
          <p className="text-muted mb-4">Preview not available for this file type</p>
          <button
            onClick={() => onDownload(resource.id, resource.display_name)}
            className="btn-primary flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download File
          </button>
        </div>
      );
    }

    if (isImage && blobUrl) {
      return (
        <div className="flex items-center justify-center h-full overflow-auto p-4">
          {/* eslint-disable-next-line @next/next/no-img-element -- blob URLs not supported by Next.js Image */}
          <img
            src={blobUrl}
            alt={resource.display_name}
            className="max-w-none transition-transform duration-200"
            style={{
              transform: `scale(${zoom}) rotate(${rotation}deg)`,
              maxHeight: zoom === 1 ? '100%' : 'none',
              maxWidth: zoom === 1 ? '100%' : 'none',
            }}
          />
        </div>
      );
    }

    if (isVideo && blobUrl) {
      return (
        <div className="flex items-center justify-center h-full p-4">
          <video
            src={blobUrl}
            controls
            autoPlay
            className="max-h-full max-w-full"
          >
            Your browser does not support video playback.
          </video>
        </div>
      );
    }

    if (isAudio && blobUrl) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-4">
          <Music className="w-24 h-24 text-muted mb-8" />
          <audio
            src={blobUrl}
            controls
            autoPlay
            className="w-full max-w-md"
          >
            Your browser does not support audio playback.
          </audio>
        </div>
      );
    }

    if (isPdf && blobUrl) {
      return (
        <div className="h-full w-full p-4">
          <iframe
            src={blobUrl}
            className="w-full h-full rounded-lg"
            title={resource.display_name}
          />
        </div>
      );
    }

    return null;
  };

  return (
    <Modal isOpen={true} onClose={onClose} fullScreen>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/50">
        <div className="flex items-center gap-4">
          <h2 className="text-white font-medium break-all">{resource.display_name}</h2>
          <span className={`text-xs px-2 py-1 rounded${getSourceColor(resource.source)}`}>
            {getSourceLabel(resource.source)}
          </span>
          {resource.has_thumbnail && (
            <span className="text-xs px-2 py-1 rounded bg-gray-700 text-muted"> {/* css-check-ignore */}
              {/* eslint-disable-next-line jsx-a11y/alt-text -- lucide-react icon, not img */}
              <Image className="w-3 h-3 inline mr-1" />
              Thumbnail
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted text-sm">{formatFileSize(resource.file_size)}</span>
          <span className="text-secondary">•</span>
          <span className="text-muted text-sm">{resource.mime_type}</span>
          <button
            onClick={() => onDownload(resource.id, resource.display_name)}
            className="ml-4 p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors"
            title="Download"
          >
            <Download className="w-5 h-5" />
          </button>
          <button
            onClick={onClose}
            className="p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors"
            title="Close (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 relative overflow-hidden">
        {renderContent()}

        {/* Navigation arrows */}
        {hasPrev && onNavigate && (
          <button
            onClick={() => onNavigate(resources[currentIndex - 1])}
            className="absolute left-4 top-1/2 -translate-y-1/2 p-3 bg-black/50 hover:bg-black/70 text-white rounded-full transition-colors"
            title="Previous (←)"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
        )}
        {hasNext && onNavigate && (
          <button
            onClick={() => onNavigate(resources[currentIndex + 1])}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-3 bg-black/50 hover:bg-black/70 text-white rounded-full transition-colors"
            title="Next (→)"
          >
            <ChevronRight className="w-6 h-6" />
          </button>
        )}
      </div>

      {/* Footer with image controls */}
      {isImage && !loading && !error && (
        <div className="flex items-center justify-center gap-2 px-4 py-3 bg-black/50">
          <button
            onClick={handleZoomOut}
            disabled={zoom <= 0.5}
            className="p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Zoom Out"
          >
            <ZoomOut className="w-5 h-5" />
          </button>
          <span className="text-muted text-sm w-16 text-center">{Math.round(zoom * 100)}%</span>
          <button
            onClick={handleZoomIn}
            disabled={zoom >= 3}
            className="p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Zoom In"
          >
            <ZoomIn className="w-5 h-5" />
          </button>
          <div className="w-px h-6 bg-gray-600 mx-2" /> {/* css-check-ignore */}
          <button
            onClick={handleRotate}
            className="p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors"
            title="Rotate"
          >
            <RotateCw className="w-5 h-5" />
          </button>
          <button
            onClick={handleFullscreen}
            className="p-2 text-muted hover:text-white hover:bg-card/10 rounded-lg transition-colors"
            title="Toggle Fullscreen"
          >
            <Maximize2 className="w-5 h-5" />
          </button>
          {resources.length > 1 && (
            <>
              <div className="w-px h-6 bg-gray-600 mx-2" /> {/* css-check-ignore */}
              <span className="text-muted text-sm">
                {currentIndex + 1} / {resources.length}
              </span>
            </>
          )}
        </div>
      )}

      {/* Footer for non-image viewable files */}
      {(isVideo || isAudio || isPdf) && !loading && !error && resources.length > 1 && (
        <div className="flex items-center justify-center gap-2 px-4 py-3 bg-black/50">
          <span className="text-muted text-sm">
            {currentIndex + 1} / {resources.length}
          </span>
        </div>
      )}
    </Modal>
  );
}
