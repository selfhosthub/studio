// ui/shared/hooks/useReturnTo.ts

'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

// Return an editor to the list view (incl. sub-tab) it was opened from.
// Lists tag edit links with `?from=<url>` via withReturnTo; editors read it here.
export function useReturnTo(fallback: string) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const raw = searchParams.get('from');
  // Same-origin, root-relative paths only — never an absolute/external URL.
  const returnTo = raw && raw.startsWith('/') && !raw.startsWith('//') ? raw : fallback;

  const goBack = useCallback(() => {
    router.push(returnTo);
  }, [router, returnTo]);

  return { returnTo, goBack };
}

// The current page's root-relative URL (path + query), for use as `from`.
export function useCurrentUrl(): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const qs = searchParams.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

// Append `?from=<url>` to an editor link.
export function withReturnTo(href: string, from: string): string {
  const sep = href.includes('?') ? '&' : '?';
  return `${href}${sep}from=${encodeURIComponent(from)}`;
}
