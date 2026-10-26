// ui/app/(authenticated)/files/hooks/useFileFiltering.ts

'use client';

import { useEffect, useMemo, useState } from 'react';
import { useListPref, oneOf, isString } from '@/shared/hooks/useListPref';
import type { FileListQuery, FileSortField } from '@/shared/api/files';

export type SortField = FileSortField;
export type SortDirection = 'asc' | 'desc';

const SORT_FIELDS: readonly SortField[] = ['name', 'date', 'size', 'type', 'source', 'thumb', 'status'];
const SORT_DIRECTIONS: readonly SortDirection[] = ['asc', 'desc'];
const FILE_TYPES = ['all', 'image', 'video', 'audio', 'document', 'other'] as const;
const SOURCES = ['all', 'job_generated', 'job_download', 'user_upload'] as const;
const SEARCH_DELAY_MS = 300;

// Search, filter and sort choices for the files list, sent to the server as one query
export function useFileFiltering() {
  const [searchTerm, setSearchTerm] = useListPref<string>('files', 'search', '', isString);
  const [fileTypeFilter, setFileTypeFilter] = useListPref<string>('files', 'fileType', 'all', oneOf(FILE_TYPES));
  const [sourceFilter, setSourceFilter] = useListPref<string>('files', 'source', 'all', oneOf(SOURCES));
  const [sortField, setSortField] = useListPref<SortField>('files', 'sortField', 'date', oneOf(SORT_FIELDS));
  const [sortDirection, setSortDirection] = useListPref<SortDirection>('files', 'sortDirection', 'desc', oneOf(SORT_DIRECTIONS));
  const [debouncedSearch, setDebouncedSearch] = useState(searchTerm);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  const query = useMemo<FileListQuery>(() => ({
    search: debouncedSearch,
    fileType: fileTypeFilter,
    source: sourceFilter,
    sortBy: sortField,
    sortDir: sortDirection,
  }), [debouncedSearch, fileTypeFilter, sourceFilter, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection(field === 'date' ? 'desc' : 'asc');
    }
  };

  const setSort = (field: SortField, direction: SortDirection) => {
    setSortField(field);
    setSortDirection(direction);
  };

  const hasFilters = searchTerm.trim() !== '' || fileTypeFilter !== 'all' || sourceFilter !== 'all';

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
    setSort,
    hasFilters,
    query,
  };
}
