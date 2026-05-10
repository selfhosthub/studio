// ui/features/files/components/MediaPicker.tsx

'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';

/** Next.js BFF route for listing static media files */
const STATIC_FILES_ENDPOINT = '/api/static-files';

interface StaticFileInfo {
  path: string;
  filename: string;
  extension: string;
  media_type: 'image' | 'video';
}

interface MediaPickerProps {
  value: string;
  onChange: (path: string, mediaType: 'image' | 'video') => void;
  label?: string;
  mediaTypeFilter?: 'image' | 'video' | 'all';
}

export default function MediaPicker({
  value,
  onChange,
  label = 'Select Media',
  mediaTypeFilter = 'all',
}: MediaPickerProps) {
  const [files, setFiles] = useState<StaticFileInfo[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'image' | 'video'>(mediaTypeFilter);

  // Sync filter when mediaTypeFilter prop changes
  useEffect(() => {
    setFilter(mediaTypeFilter);
  }, [mediaTypeFilter]);

  useEffect(() => {
    const fetchFiles = async () => {
      if (!isOpen) return;

      setIsLoading(true);
      setError(null);
      try {
        // Fetch from frontend's own API route (not backend)
        const response = await fetch(STATIC_FILES_ENDPOINT);
        if (!response.ok) {
          throw new Error('Failed to fetch static files');
        }
        const data = await response.json();
        setFiles(data.files || []);
      } catch (err) {
        console.error('Failed to fetch static files:', err);
        setError('Failed to load media files');
      } finally {
        setIsLoading(false);
      }
    };

    fetchFiles();
  }, [isOpen]);

  const filteredFiles = files.filter(
    (file) => filter === 'all' || file.media_type === filter
  );

  const selectedFile = files.find((f) => f.path === value);
  const isVideo = selectedFile?.media_type === 'video' || value?.includes('/videos/');

  return (
    <div className="space-y-2">
      <label className="form-label">
        {label}
      </label>

      {/* Current Selection Preview */}
      <div className="flex items-center gap-4">
        {value ? (
          <div className="relative w-24 h-24 rounded-lg overflow-hidden border border-primary bg-card">
            {isVideo ? (
              <div className="w-full h-full flex items-center justify-center bg-gray-900"> {/* css-check-ignore */}
                <video
                  src={value}
                  className="max-w-full max-h-full object-contain"
                  muted
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="bg-black/50 rounded-full p-2">
                    <svg
                      className="w-6 h-6 text-white"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                    </svg>
                  </div>
                </div>
              </div>
            ) : (
              <Image
                src={value}
                alt="Selected media"
                fill
                className="object-cover"
              />
            )}
          </div>
        ) : (
          <div className="w-24 h-24 rounded-lg border-2 border-dashed border-primary flex items-center justify-center">
            <span className="text-muted text-xs text-center px-2">No media selected</span>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className="btn-primary text-sm"
          >
            {value ? 'Change' : 'Select'} Media
          </button>
          {value && (
            <span className="text-xs text-secondary truncate max-w-[150px]">
              {value.split('/').pop()}
            </span>
          )}
        </div>
      </div>

      {/* Media Grid Picker */}
      {isOpen && (
        <div className="mt-4 p-4 border border-primary rounded-lg bg-surface">
          {/* Filter Tabs */}
          {mediaTypeFilter === 'all' && (
            <div className="flex gap-2 mb-4">
              {(['all', 'image', 'video'] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFilter(type)}
                  className={`px-3 py-1 text-sm rounded-md transition-colors ${
                    filter === type
                      ? 'bg-info text-white'
                      : 'bg-input text-secondary hover:bg-surface'
                  }`}
                >
                  {type === 'all' ? 'All' : type === 'image' ? 'Images' : 'Videos'}
                </button>
              ))}
            </div>
          )}

          {isLoading ? (
            <div className="text-center py-8">
              <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-info"></div>
              <p className="mt-2 text-sm text-secondary">Loading media files...</p>
            </div>
          ) : error ? (
            <div className="text-center py-8 text-danger">{error}</div>
          ) : filteredFiles.length === 0 ? (
            <div className="text-center py-8 text-secondary">
              No {filter === 'all' ? 'media' : filter} files found in public folder
            </div>
          ) : (
            <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-3 max-h-64 overflow-y-auto">
              {filteredFiles.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  onClick={() => {
                    onChange(file.path, file.media_type);
                    setIsOpen(false);
                  }}
                  className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                    value === file.path
                      ? 'border-info ring-2 ring-info/30'
                      : 'border-primary hover:border-info'
                  }`}
                  title={file.filename}
                >
                  {file.media_type === 'video' ? (
                    <div className="w-full h-full flex items-center justify-center bg-gray-900"> {/* css-check-ignore */}
                      <video
                        src={file.path}
                        className="max-w-full max-h-full object-contain"
                        muted
                      />
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="bg-black/50 rounded-full p-1">
                          <svg
                            className="w-4 h-4 text-white"
                            fill="currentColor"
                            viewBox="0 0 20 20"
                          >
                            <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                          </svg>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <Image
                      src={file.path}
                      alt={file.filename}
                      fill
                      className="object-cover"
                    />
                  )}
                </button>
              ))}
            </div>
          )}

          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="px-4 py-2 text-sm text-secondary hover:text-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
