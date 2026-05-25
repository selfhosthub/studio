// ui/features/files/components/FileLibraryModal.tsx

'use client';

import { useState, useEffect } from 'react';
import { getFiles, apiFetchBlob } from '@/shared/api';
import { asOutputResources } from '@/shared/api/files';
import { OrgFile } from '@/shared/types/api';
import { X, Image as ImageIcon, Video, Music, File, Check, Loader2 } from 'lucide-react';
import { Modal } from '@/shared/ui';

type MediaType = 'image' | 'video' | 'audio' | 'all';

interface FileLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (resourceIds: string[]) => void;
  mediaTypeFilter?: MediaType;
  title?: string;
  maxSelection?: number;
}

// Determine media type from mime_type
function getMediaType(mimeType: string): MediaType {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';
  if (mimeType.startsWith('audio/')) return 'audio';
  return 'all';
}

// Get icon for media type
function MediaIcon({ type, className }: { type: MediaType; className?: string }) {
  switch (type) {
    case 'image': return <ImageIcon className={className} />;
    case 'video': return <Video className={className} />;
    case 'audio': return <Music className={className} />;
    default: return <File className={className} />;
  }
}

// Component to load thumbnail with auth
function FileThumbnail({ file }: { file: OrgFile }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const mediaType = getMediaType(file.mime_type);

  useEffect(() => {
    if (!file.preview_url) return;

    let cancelled = false;

    const loadThumbnail = async () => {
      try {
        const blob = await apiFetchBlob(file.preview_url!);
        if (!cancelled) {
          const url = URL.createObjectURL(blob);
          setBlobUrl(url);
        }
      } catch {
        if (!cancelled) setError(true);
      }
    };

    loadThumbnail();

    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- blobUrl excluded to avoid refetching when blob URL is set; cleanup handles revocation separately
  }, [file.preview_url]);

  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  if (blobUrl && !error) {
    // eslint-disable-next-line @next/next/no-img-element -- blob URL, not optimizable
    return <img src={blobUrl} alt={file.display_name} className="w-full h-full object-cover" />;
  }

  return <MediaIcon type={mediaType} className="h-8 w-8 text-muted" />;
}

export default function FileLibraryModal({
  isOpen,
  onClose,
  onSelect,
  mediaTypeFilter = 'all',
  title = 'Select Files from Library',
  maxSelection = 10,
}: FileLibraryModalProps) {
  const [files, setFiles] = useState<OrgFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<MediaType>(mediaTypeFilter);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Fetch files when modal opens
  useEffect(() => {
    if (!isOpen) {
      setSelectedIds(new Set());
      return;
    }

    const fetchFiles = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getFiles(1, 100);
        setFiles(asOutputResources(data || []));
      } catch (err) {
        console.error('Failed to fetch user files:', err);
        setError('Failed to load files');
      } finally {
        setIsLoading(false);
      }
    };

    fetchFiles();
  }, [isOpen]);

  // Sync filter when prop changes
  useEffect(() => {
    setFilter(mediaTypeFilter);
  }, [mediaTypeFilter]);

  // Filter files by media type
  const filteredFiles = files.filter((file) => {
    if (filter === 'all') return true;
    return getMediaType(file.mime_type) === filter;
  });

  // Toggle file selection
  const toggleSelection = (fileId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) {
        next.delete(fileId);
      } else if (next.size < maxSelection) {
        next.add(fileId);
      }
      return next;
    });
  };

  // Handle add selected
  const handleAddSelected = () => {
    onSelect(Array.from(selectedIds));
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <div className="max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-primary">
          <h2 className="text-lg font-semibold text-primary">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-secondary hover:text-secondary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Filter tabs */}
        {mediaTypeFilter === 'all' && (
          <div className="flex border-b border-primary bg-surface px-4">
            {(['all', 'image', 'video', 'audio'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setFilter(type)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  filter === type
                    ? 'text-info border-b-2 border-info'
                    : 'text-secondary hover:text-secondary'
                }`}
              >
                {type === 'all' ? 'All' : type.charAt(0).toUpperCase() + type.slice(1)}s
              </button>
            ))}
          </div>
        )}

        {/* File grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-info" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-danger">{error}</div>
          ) : filteredFiles.length === 0 ? (
            <div className="text-center py-12 text-secondary">
              No {filter === 'all' ? '' : filter + ' '}files found in library
            </div>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3">
              {filteredFiles.map((file) => {
                const isSelected = selectedIds.has(file.id);
                return (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => toggleSelection(file.id)}
                    className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                      isSelected
                        ? 'border-info ring-2 ring-info/30'
                        : 'border-primary hover:border-primary'
                    }`}
                  >
                    {/* Thumbnail */}
                    <div className="absolute inset-0 bg-card flex items-center justify-center">
                      <FileThumbnail file={file} />
                    </div>

                    {/* Selection indicator */}
                    <div
                      className={`absolute top-1 right-1 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                        isSelected
                          ? 'bg-info border-info'
                          : 'bg-card/80 /80 border-primary'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3 text-white" />}
                    </div>

                    {/* Filename tooltip */}
                    <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-1 py-0.5">
                      <p className="text-[10px] text-white truncate">
                        {file.display_name}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-primary bg-surface">
          <span className="text-sm text-secondary">
            {selectedIds.size} of {maxSelection} selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-secondary hover:bg-card rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAddSelected}
              disabled={selectedIds.size === 0}
              className="px-4 py-2 text-sm btn-primary rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add {selectedIds.size > 0 ? `(${selectedIds.size})` : 'Selected'}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
