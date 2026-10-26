// ui/shared/lib/pagination.ts

export const PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100];

/** Page size a list starts at; always a member of PAGE_SIZE_OPTIONS. */
export const DEFAULT_PAGE_SIZE = 25;

/**
 * Retrieve the stored page size from localStorage, falling back to `defaultSize`.
 * Only returns a value that is present in PAGE_SIZE_OPTIONS.
 */
export function getStoredPageSize(key: string, defaultSize: number = DEFAULT_PAGE_SIZE): number {
  const fallback = PAGE_SIZE_OPTIONS.includes(defaultSize) ? defaultSize : DEFAULT_PAGE_SIZE;
  if (typeof window === 'undefined') return fallback;
  const stored = localStorage.getItem(key);
  if (stored) {
    const parsed = parseInt(stored, 10);
    if (PAGE_SIZE_OPTIONS.includes(parsed)) return parsed;
  }
  return fallback;
}
