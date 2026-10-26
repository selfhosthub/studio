// ui/features/files/hooks/useResources.ts

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getFiles } from '@/shared/api';
import type { FileListQuery } from '@/shared/api/files';
import { POLLING, PAGINATION } from '@/shared/lib/constants';

interface UseFilesOptions {
  page?: number;
  limit?: number;
  query?: FileListQuery;
}

export function useFiles(options: UseFilesOptions = {}) {
  const { page = 1, limit = PAGINATION.DEFAULT_PAGE_SIZE, query = {} } = options;

  return useQuery({
    queryKey: ['files', page, limit, query],
    queryFn: () => getFiles(page, limit, query),
    placeholderData: keepPreviousData,
    staleTime: POLLING.SLOW,
  });
}

// Legacy alias for backwards compatibility
export const useResources = useFiles;
