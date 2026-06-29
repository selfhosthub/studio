// ui/shared/lib/pagination.ts

export const PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100];

/**
 * Retrieve the stored page size from localStorage, falling back to `defaultSize`.
 * Only returns a value that is present in PAGE_SIZE_OPTIONS.
 */
export function getStoredPageSize(key: string, defaultSize: number = 20): number {
  if (typeof window === 'undefined') return defaultSize;
  const stored = localStorage.getItem(key);
  if (stored) {
    const parsed = parseInt(stored, 10);
    if (PAGE_SIZE_OPTIONS.includes(parsed)) return parsed;
  }
  return defaultSize;
}
