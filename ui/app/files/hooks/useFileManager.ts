// ui/app/files/hooks/useFileManager.ts

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useUser } from '@/entities/user';
import { useToast } from '@/features/toast';
import { useOrgSettings } from '@/entities/organization';
import { useFiles } from '@/features/files';
import { downloadFile, uploadFiles } from '@/shared/api';
import { asOutputResources } from '@/shared/api/files';
import { OrgFile } from '@/shared/types/api';
import { getStoredPageSize } from '@/shared/lib/pagination';

type ViewMode = 'grid' | 'table';

const PAGE_SIZE_KEY = 'files-pageSize';

export function useFileManager() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, status: authStatus } = useUser();
  const { toast } = useToast();
  const { settings: orgSettings, updateSettings } = useOrgSettings();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(() => getStoredPageSize(PAGE_SIZE_KEY));
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [viewingResource, setViewingResource] = useState<OrgFile | null>(null);

  // Upload state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: rawFiles, isLoading, error, refetch } = useFiles({ page, limit: pageSize });
  const files = rawFiles ? asOutputResources(rawFiles) : undefined;

  // Load view mode preference from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('files-view-mode');
    if (saved === 'grid' || saved === 'table') {
      setViewMode(saved);
    }
  }, []);

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
    localStorage.setItem('files-view-mode', mode);
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
    localStorage.setItem(PAGE_SIZE_KEY, String(size));
  };

  return {
    // Auth
    user,
    authStatus,
    // Data
    files,
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
