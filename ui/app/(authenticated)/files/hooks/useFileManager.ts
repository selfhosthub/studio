// ui/app/(authenticated)/files/hooks/useFileManager.ts

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { useOrgSettings } from '@/entities/organization';
import { useFiles } from '@/features/files';
import { downloadFile, uploadFiles } from '@/shared/api';
import { asOutputResources, type FileListQuery } from '@/shared/api/files';
import { OrgFile } from '@/shared/types/api';
import { DEFAULT_PAGE_SIZE } from '@/shared/lib/pagination';
import { useListPref, oneOf, isPageSize } from '@/shared/hooks/useListPref';

type ViewMode = 'grid' | 'table';

const VIEW_MODES: readonly ViewMode[] = ['grid', 'table'];
const EMPTY_QUERY: FileListQuery = {};

export function useFileManager(query: FileListQuery = EMPTY_QUERY) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();
  const { settings: orgSettings, updateSettings } = useOrgSettings();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useListPref<number>('files', 'pageSize', DEFAULT_PAGE_SIZE, isPageSize);
  const [viewMode, setViewMode] = useListPref<ViewMode>('files', 'viewMode', 'grid', oneOf(VIEW_MODES));
  const [viewingResource, setViewingResource] = useState<OrgFile | null>(null);

  // Upload state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Return to the first page whenever search, filters or sort change
  const queryKey = JSON.stringify(query);
  const [prevQueryKey, setPrevQueryKey] = useState(queryKey);
  if (queryKey !== prevQueryKey) {
    setPrevQueryKey(queryKey);
    setPage(1);
  }

  const { data: fileList, isLoading, error, refetch } = useFiles({ page, limit: pageSize, query });
  const files = fileList ? asOutputResources(fileList.items) : undefined;
  const totalCount = fileList?.total ?? 0;

  // Redirect in useEffect to avoid setState-during-render warnings
  useEffect(() => {
    if (authStatus === 'authenticated' && user?.role === 'super_admin') {
      router.push('/dashboard');
    } else if (authStatus === 'unauthenticated') {
      router.push('/login');
    }
  }, [authStatus, user?.role, router]);

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
  };

  const handleDownload = async (fileId: string, filename: string) => {
    try {
      const blob = await downloadFile(fileId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      toast({ title: 'Download failed', description: 'Failed to download file', variant: 'destructive' });
    }
  };

  const handleView = (resource: OrgFile) => {
    setViewingResource(resource);
  };

  const handleFileUpload = async (fileList: FileList) => {
    setIsUploading(true);
    setUploadError(null);

    try {
      await uploadFiles(Array.from(fileList));
      queryClient.invalidateQueries({ queryKey: ['files'] });
      refetch();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Failed to upload files');
    } finally {
      setIsUploading(false);
    }
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(1);
  };

  return {
    // Auth
    user,
    authStatus,
    // Data
    files,
    totalCount,
    isLoading,
    error,
    refetch,
    // Pagination
    page,
    setPage,
    pageSize,
    handlePageSizeChange,
    // View
    viewMode,
    handleViewModeChange,
    viewingResource,
    setViewingResource,
    handleView,
    // Settings
    orgSettings,
    updateSettings,
    // Download
    handleDownload,
    // Upload
    isUploading,
    uploadError,
    setUploadError,
    handleFileUpload,
    // Query client for selection hook
    queryClient,
  };
}
