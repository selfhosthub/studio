// ui/features/files/hooks/useResources.ts

import { useQuery } from '@tanstack/react-query';
import { getFiles } from '@/shared/api';
import { POLLING, PAGINATION } from '@/shared/lib/constants';

interface UseFilesOptions {
  page?: number;
  limit?: number;
}

export function useFiles(options: UseFilesOptions = {}) {
  const { page = 1, limit = PAGINATION.DEFAULT_PAGE_SIZE } = options;

  return useQuery({
    queryKey: ['files', page, limit],
    queryFn: () => getFiles(page, limit),
    staleTime: POLLING.SLOW,
  });
}

// Legacy alias for backwards compatibility
export const useResources = useFiles;
