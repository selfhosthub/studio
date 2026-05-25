// ui/features/files/components/UserFilePicker.tsx

'use client';

import { useState, useEffect, useRef } from 'react';
import { getFiles, uploadFile, apiFetchBlob } from '@/shared/api';
import { asOutputResources } from '@/shared/api/files';
import { getApiUrl, API_VERSION } from '@/shared/lib/config';
import { OrgFile } from '@/shared/types/api';
import { Folder, Image as ImageIcon, Video, Music, File, X, ChevronDown, Upload, Loader2 } from 'lucide-react';

type MediaType = 'image' | 'video' | 'audio' | 'all';

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

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  if (blobUrl && !error) {
    // eslint-disable-next-line @next/next/no-img-element -- blob URL, not optimizable
    return <img src={blobUrl} alt={file.display_name} className="w-full h-full object-cover" />;
  }

  return <MediaIcon type={mediaType} className="h-5 w-5 text-muted" />;
}

interface UserFilePickerProps {
  value: string;
  onChange: (url: string) => void;
  mediaTypeFilter?: MediaType;
  placeholder?: string;
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

export default function UserFilePicker({
  value,
  onChange,
  mediaTypeFilter = 'all',
  placeholder = 'Select a file or enter URL...',
}: UserFilePickerProps) {
  const [files, setFiles] = useState<OrgFile[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<MediaType>(mediaTypeFilter);
  const [inputValue, setInputValue] = useState(value || '');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync input with external value
  useEffect(() => {
    setInputValue(value || '');
  }, [value]);

  // Sync filter when prop changes
  useEffect(() => {
    setFilter(mediaTypeFilter);
  }, [mediaTypeFilter]);

  // Fetch files when dropdown opens
  useEffect(() => {
    if (!isOpen) return;

    const fetchFiles = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getFiles(1, 100); // Get up to 100 files
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

  // Filter files by media type
  const filteredFiles = files.filter((file) => {
    if (filter === 'all') return true;
    return getMediaType(file.mime_type) === filter;
  });

  // Handle text input change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    onChange(newValue);
  };

  // Handle file selection
  const handleSelectFile = (file: OrgFile) => {
    // Ensure full URL for worker access (relative URLs don't work in Docker)
    // Use getApiUrl() to get the API base (port 8000), not the UI origin (port 3000)
    let url = file.download_url || '';
    if (url.startsWith('/')) {
      url = `${getApiUrl()}${url}`;
    }
    setInputValue(url);
    onChange(url);
    setIsOpen(false);
  };

  // Clear selection
  const handleClear = () => {
    setInputValue('');
    onChange('');
  };

  // Upload a file and auto-select it
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset so the same file can be re-selected
    e.target.value = '';
    setIsUploading(true);
    try {
      const result = await uploadFile(file);
      let url = result.download_url || '';
      if (url.startsWith('/')) {
        url = `${getApiUrl()}${url}`;
      }
      if (url) {
        setInputValue(url);
        onChange(url);
      }
    } catch (err) {
      console.error('Failed to upload file:', err);
    } finally {
      setIsUploading(false);
    }
  };

  // Map mediaTypeFilter to an accept attribute for the file input
  const acceptFilter = mediaTypeFilter === 'image' ? 'image/*'
    : mediaTypeFilter === 'video' ? 'video/*'
    : mediaTypeFilter === 'audio' ? 'audio/*'
    : undefined;

  // Get display name from URL or file
  const getDisplayName = () => {
    if (!inputValue) return null;
    // Check if it's a file from our list
    const file = files.find(f => f.download_url === inputValue);
    if (file) return file.display_name;
    // Otherwise extract filename from URL
    try {
      const url = new URL(inputValue);
      return url.pathname.split('/').pop() || inputValue;
    } catch {
      return inputValue.split('/').pop() || inputValue;
    }
  };

  const displayName = getDisplayName();

  return (
    <div className="relative">
      {/* Input with dropdown trigger */}
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <input
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            placeholder={placeholder}
            className="w-full px-3 py-2 pr-24 border border-primary rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-info text-sm"
          />
          <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-1">
            {inputValue && (
              <button
                type="button"
                onClick={handleClear}
                className="p-1 text-muted hover:text-secondary"
                title="Clear"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="p-1 text-muted hover:text-success disabled:opacity-50"
              title="Upload file"
            >
              {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={() => setIsOpen(!isOpen)}
              className="p-1 text-muted hover:text-info"
              title="Browse files"
            >
              <Folder className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Hidden file input for uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept={acceptFilter}
        onChange={handleUpload}
        className="hidden"
      />

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-card border border-primary rounded-lg shadow-lg max-h-80 overflow-hidden">
          {/* Filter tabs (only if showing all types) */}
          {mediaTypeFilter === 'all' && (
            <div className="flex border-b border-primary bg-surface">
              {(['all', 'image', 'video', 'audio'] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFilter(type)}
                  className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                    filter === type
                      ? 'text-info border-b-2 border-info bg-card'
                      : 'text-secondary hover:text-secondary'
                  }`}
                >
                  {type === 'all' ? 'All' : type.charAt(0).toUpperCase() + type.slice(1)}s
                </button>
              ))}
            </div>
          )}

          {/* File list */}
          <div className="max-h-60 overflow-y-auto">
            {isLoading ? (
              <div className="p-4 text-center">
                <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-info"></div>
                <p className="mt-2 text-xs text-secondary">Loading files...</p>
              </div>
            ) : error ? (
              <div className="p-4 text-center text-danger text-sm">{error}</div>
            ) : filteredFiles.length === 0 ? (
              <div className="p-4 text-center text-secondary text-sm">
                No {filter === 'all' ? '' : filter + ' '}files found
              </div>
            ) : (
              <ul className="divide-y divide-gray-100"> {/* css-check-ignore: no semantic token */}
                {filteredFiles.map((file) => {
                  const mediaType = getMediaType(file.mime_type);
                  const isSelected = inputValue === file.download_url;

                  return (
                    <li key={file.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectFile(file)}
                        className={`w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-surface transition-colors ${
                          isSelected ? 'bg-info-subtle' : ''
                        }`}
                      >
                        {/* Thumbnail or icon */}
                        <div className="w-10 h-10 rounded bg-card flex items-center justify-center overflow-hidden flex-shrink-0">
                          <FileThumbnail file={file} />
                        </div>

                        {/* File info */}
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-medium truncate ${
                            isSelected ? 'text-info' : 'text-primary'
                          }`}>
                            {file.display_name}
                          </p>
                          <p className="text-xs text-secondary truncate">
                            {file.virtual_path}
                          </p>
                        </div>

                        {/* Type badge */}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                          mediaType === 'image' ? 'bg-success-subtle text-success' :
                          mediaType === 'video' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' : // css-check-ignore: no semantic token
                          mediaType === 'audio' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' : // css-check-ignore: no semantic token
                          'bg-surface text-secondary'
                        }`}>
                          {file.file_extension}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-primary p-2 bg-surface flex justify-between items-center">
            <span className="text-muted text-xs">
              {filteredFiles.length} file{filteredFiles.length !== 1 ? 's' : ''}
            </span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="text-xs text-secondary hover:text-primary"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
