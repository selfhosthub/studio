// ui/app/(authenticated)/files/hooks/useFileSelection.ts

'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { deleteFile, getFilesUsage, type FileRunUsage } from '@/shared/api';
import { useConfirm } from '@/shared/ui/ConfirmDialog';
import { useToast } from '@/features/toast';
import { OrgFile } from '@/shared/types/api';
import { getDisplayFilename } from '../lib/fileTypeDetector';

const LIST_CAP = 10;

// Bulleted list of up to LIST_CAP lines, then a count of the rest.
function bulletList(lines: string[]): string {
  const shown = lines.slice(0, LIST_CAP).map((line) => `• ${line}`);
  const rest = lines.length - shown.length;
  return [...shown, ...(rest > 0 ? [`and ${rest} more`] : [])].join('\n');
}

// Confirm text naming the files and the run steps that lose them.
export function deleteFilesMessage(names: string[], runs: FileRunUsage[] | null): string {
  const plural = names.length > 1 ? 's' : '';
  const parts = [`Delete ${names.length} selected file${plural}? This cannot be undone.`, bulletList(names)];
  if (runs === null) {
    parts.push('Runs that hold these files lose them.');
  } else if (runs.length > 0) {
    const lines = runs.map((run) => {
      const step = run.step_name ? `, node ${run.step_name}` : '';
      const count = `${run.file_count} file${run.file_count > 1 ? 's' : ''}`;
      return `${run.instance_name}${step} (${count})`;
    });
    parts.push(`These runs lose the files they hold:\n${bulletList(lines)}`);
  }
  return parts.join('\n\n');
}

export function useFileSelection(
  filteredFiles: OrgFile[],
  deps: { searchTerm: string; fileTypeFilter: string; sourceFilter: string; page: number },
  refetch: () => void,
) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { toast } = useToast();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Clear selection when changing pages or filters (Pattern C: adjust during render keyed on composite filter key)
  const filterKey = `${deps.page}|${deps.searchTerm}|${deps.fileTypeFilter}|${deps.sourceFilter}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setSelectedIds(new Set());
    setSelectionMode(false);
  }

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
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const plural = ids.length > 1 ? 's' : '';
    const byId = new Map(filteredFiles.map((f) => [f.id, f]));
    const names = ids.map((id) => {
      const file = byId.get(id);
      return file ? getDisplayFilename(file) : id;
    });
    const runs = await getFilesUsage(ids).catch(() => null);

    if (!(await confirm({
      title: 'Delete files',
      message: deleteFilesMessage(names, runs),
      confirmLabel: 'Delete',
      variant: 'danger',
    }))) {
      return;
    }

    setIsDeleting(true);
    try {
      await Promise.all(ids.map(id => deleteFile(id)));
      setSelectedIds(new Set());
      setSelectionMode(false);
      toast({ title: `Deleted ${ids.length} file${plural}`, variant: 'success' });
      queryClient.invalidateQueries({ queryKey: ['files'] });
      refetch();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast({ title: `Failed to delete files: ${message}`, variant: 'destructive' });
    } finally {
      setIsDeleting(false);
    }
  };

  return {
    selectedIds,
    selectionMode,
    isDeleting,
    handleToggleSelect,
    handleSelectAll,
    handleCancelSelection,
    handleDeleteSelected,
  };
}
