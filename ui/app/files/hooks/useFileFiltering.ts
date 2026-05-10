// ui/app/files/hooks/useFileFiltering.ts

'use client';

import { useState, useMemo } from 'react';
import { OrgFile } from '@/shared/types/api';
import {
  isImageFile,
  isVideoFile,
  isAudioFile,
  getDisplayFilename,
} from '../lib/fileTypeDetector';

export type SortField = 'name' | 'date' | 'size' | 'type' | 'source';
export type SortDirection = 'asc' | 'desc';

export function useFileFiltering(files: OrgFile[] | undefined) {
  const [searchTerm, setSearchTerm] = useState('');
  const [fileTypeFilter, setFileTypeFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<SortField>('date');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const filteredAndSortedFiles = useMemo(() => {
    let result = files?.filter((resource) => {
      const filename = getDisplayFilename(resource);
      const matchesSearch = filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            resource.virtual_path?.toLowerCase().includes(searchTerm.toLowerCase());

      const isImage = isImageFile(resource);
      const isVideo = isVideoFile(resource);
      const isAudio = isAudioFile(resource);
      const isDocument = !isImage && !isVideo && !isAudio &&
        (resource.mime_type.startsWith('text/') || resource.mime_type.startsWith('application/'));
      const isOther = !isImage && !isVideo && !isAudio && !isDocument;

      const matchesFileType = fileTypeFilter === 'all' ||
                             (fileTypeFilter === 'image' && isImage) ||
                             (fileTypeFilter === 'video' && isVideo) ||
                             (fileTypeFilter === 'audio' && isAudio) ||
                             (fileTypeFilter === 'document' && isDocument) ||
                             (fileTypeFilter === 'other' && isOther);

      const matchesSource = sourceFilter === 'all' || resource.source === sourceFilter;

      return matchesSearch && matchesFileType && matchesSource;
    }) || [];

    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'name':
          comparison = getDisplayFilename(a).localeCompare(getDisplayFilename(b));
          break;
        case 'date':
          comparison = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
        case 'size':
          comparison = a.file_size - b.file_size;
          break;
        case 'type':
          comparison = a.mime_type.localeCompare(b.mime_type);
          break;
        case 'source':
          comparison = a.source.localeCompare(b.source);
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [files, searchTerm, fileTypeFilter, sourceFilter, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection(field === 'date' ? 'desc' : 'asc');
    }
  };

  return {
    searchTerm,
    setSearchTerm,
    fileTypeFilter,
    setFileTypeFilter,
    sourceFilter,
    setSourceFilter,
    sortField,
    sortDirection,
    handleSort,
    filteredAndSortedFiles,
  };
}
