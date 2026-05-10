// ui/app/files/hooks/useFileSelection.ts

'use client';

import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { deleteFile } from '@/shared/api';
import { OrgFile } from '@/shared/types/api';

export function useFileSelection(
  filteredFiles: OrgFile[],
  deps: { searchTerm: string; fileTypeFilter: string; sourceFilter: string; page: number },
  refetch: () => void,
) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Clear selection when changing pages or filters
  useEffect(() => {
    setSelectedIds(new Set());
    setSelectionMode(false);
  }, [deps.page, deps.searchTerm, deps.fileTypeFilter, deps.sourceFilter]);

  const handleToggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      if (newSet.size > 0 && !selectionMode) {
        setSelectionMode(true);
      }
      return newSet;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === filteredFiles.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredFiles.map(f => f.id)));
    }
  };

  const handleCancelSelection = () => {
    setSelectedIds(new Set());
    setSelectionMode(false);
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      const deletePromises = Array.from(selectedIds).map(id => deleteFile(id));
      await Promise.all(deletePromises);

      setSelectedIds(new Set());
      setSelectionMode(false);
      setShowDeleteConfirm(false);

      queryClient.invalidateQueries({ queryKey: ['files'] });
      refetch();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete some files');
    } finally {
      setIsDeleting(false);
    }
  };

  return {
    selectedIds,
    selectionMode,
    showDeleteConfirm,
    setShowDeleteConfirm,
    isDeleting,
    deleteError,
    setDeleteError,
    handleToggleSelect,
    handleSelectAll,
    handleCancelSelection,
    handleDeleteSelected,
  };
}
