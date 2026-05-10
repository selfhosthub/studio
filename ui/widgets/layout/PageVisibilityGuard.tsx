// ui/widgets/layout/PageVisibilityGuard.tsx

'use client';

import { notFound } from 'next/navigation';
import { usePageVisibility, PageVisibility } from '@/entities/page-visibility';

interface PageVisibilityGuardProps {
  page: keyof PageVisibility;
  children: React.ReactNode;
}

/**
 * Client component that guards a page based on visibility settings.
 * Wraps page content and shows 404 if the page is disabled.
 */
export function PageVisibilityGuard({ page, children }: PageVisibilityGuardProps) {
  const { visibility, isLoading } = usePageVisibility();

  // Show loading state while checking visibility
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="spinner-md"></div>
      </div>
    );
  }

  // If page is not visible, trigger 404
  if (!visibility[page]) {
    notFound();
  }

  return <>{children}</>;
}
