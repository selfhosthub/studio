// ui/widgets/instance-view/MediaViewerModal.tsx

'use client';

import { useState, useEffect } from 'react';
import { X, Download, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { OrgFile } from '@/shared/types/api';
import { downloadResource } from '@/shared/api';
import { Modal } from '@/shared/ui';

interface MediaViewerModalProps {
  resource: OrgFile | null;
  resources?: OrgFile[]; // All resources for navigation
  onClose: () => void;
  onDownload: (resourceId: string, filename: string) => void;
  onNavigate?: (resource: OrgFile) => void;
}

export default function MediaViewerModal({
  resource,
  resources = [],
  onClose,
  onDownload,
  onNavigate
}: MediaViewerModalProps) {
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Find current index for navigation
  const currentIndex = resources.findIndex(r => r.id === resource?.id);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < resources.length - 1;

  // Filter to viewable resources only
  const viewableResources = resources.filter(r =>
    r.mime_type.startsWith('image/') ||
    r.mime_type.startsWith('video/') ||
    r.mime_type.startsWith('audio/')
  );

  useEffect(() => {
    if (!resource) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setMediaUrl(null);

    const loadMedia = async () => {
      try {
        // Use the same downloadResource function that the Download button uses
        const blob = await downloadResource(resource.id);
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          setMediaUrl(url);
          setLoading(false);
        }
      } catch (err) {
        console.error('Error loading media:', err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load media');
          setLoading(false);
        }
      }
    };

    loadMedia();

    return () => {
      cancelled = true;
      if (mediaUrl) {
        URL.revokeObjectURL(mediaUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cleanup uses stale mediaUrl intentionally, resource accessed via resource?.id
  }, [resource?.id]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (mediaUrl) {
        URL.revokeObjectURL(mediaUrl);
      }
    };
  }, [mediaUrl]);

  // Handle keyboard navigation for arrow keys (Escape is handled by Dialog)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' && hasPrev && onNavigate) {
        onNavigate(viewableResources[viewableResources.findIndex(r => r.id === resource?.id) - 1]);
      } else if (e.key === 'ArrowRight' && hasNext && onNavigate) {
        onNavigate(viewableResources[viewableResources.findIndex(r => r.id === resource?.id) + 1]);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [resource?.id, hasPrev, hasNext, onNavigate, viewableResources]);

  if (!resource) return null;

  const isImage = resource.mime_type.startsWith('image/');
  const isVideo = resource.mime_type.startsWith('video/');
  const isAudio = resource.mime_type.startsWith('audio/');

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      fullScreen
      panelClassName="fixed inset-0 flex items-center justify-center bg-black/80 backdrop-blur-sm transition duration-200 ease-out data-[closed]:opacity-0"
    >
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-4 bg-gradient-to-b from-black/60 to-transparent">
        <div className="text-white">
          <h3 className="font-medium truncate max-w-md">{resource.display_name}</h3>
          <p className="text-sm text-muted">
            {resource.mime_type} • {(resource.file_size / 1024).toFixed(1)} KB
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDownload(resource.id, resource.display_name);
            }}
            className="p-2 rounded-full bg-card/10 hover:bg-card/20 text-white transition-colors"
            title="Download"
          >
            <Download className="w-5 h-5" />
          </button>
          <button
            onClick={onClose}
            className="p-2 rounded-full bg-card/10 hover:bg-card/20 text-white transition-colors"
            title="Close (ESC)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Navigation arrows */}
      {viewableResources.length > 1 && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
              const viewableIndex = viewableResources.findIndex(r => r.id === resource.id);
              if (viewableIndex > 0 && onNavigate) {
                onNavigate(viewableResources[viewableIndex - 1]);
              }
            }}
            disabled={viewableResources.findIndex(r => r.id === resource.id) === 0}
            className="absolute left-4 p-2 rounded-full bg-card/10 hover:bg-card/20 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Previous (Left Arrow)"
          >
            <ChevronLeft className="w-8 h-8" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              const viewableIndex = viewableResources.findIndex(r => r.id === resource.id);
              if (viewableIndex < viewableResources.length - 1 && onNavigate) {
                onNavigate(viewableResources[viewableIndex + 1]);
              }
            }}
            disabled={viewableResources.findIndex(r => r.id === resource.id) === viewableResources.length - 1}
            className="absolute right-4 p-2 rounded-full bg-card/10 hover:bg-card/20 text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Next (Right Arrow)"
          >
            <ChevronRight className="w-8 h-8" />
          </button>
        </>
      )}

      {/* Media content */}
      <div
        className="max-w-[90vw] max-h-[80vh] flex items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex flex-col items-center gap-4 text-white">
            <Loader2 className="w-12 h-12 animate-spin" />
            <p>Loading...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-4 text-white bg-danger/20 p-8 rounded-lg">
            <p className="text-danger">{error}</p>
            <button
              onClick={() => onDownload(resource.id, resource.display_name)}
              className="px-4 py-2 bg-card/20 hover:bg-card/30 rounded-lg transition-colors"
            >
              Download instead
            </button>
          </div>
        ) : mediaUrl ? (
          <>
            {isImage && (
              // eslint-disable-next-line @next/next/no-img-element -- blob URLs not supported by Next.js Image
              <img
                src={mediaUrl}
                alt={resource.display_name}
                className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-2xl"
              />
            )}
            {isVideo && (
              <video
                src={mediaUrl}
                controls
                autoPlay
                className="max-w-full max-h-[80vh] rounded-lg shadow-2xl"
              />
            )}
            {isAudio && (
              <div className="bg-gray-900 p-8 rounded-lg shadow-2xl"> {/* css-check-ignore */}
                <audio
                  src={mediaUrl}
                  controls
                  autoPlay
                  className="w-[400px]"
                />
              </div>
            )}
          </>
        ) : null}
      </div>

      {/* Footer with navigation hint */}
      {viewableResources.length > 1 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/60 text-sm">
          {viewableResources.findIndex(r => r.id === resource.id) + 1} of {viewableResources.length} • Use arrow keys to navigate
        </div>
      )}
    </Modal>
  );
}
