// ui/app/providers/error.tsx

'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Providers error:', error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-card" role="alert" aria-live="assertive">
      <div className="text-center max-w-md">
        <h1 className="text-2xl font-bold text-primary mb-4">
          Something went wrong loading providers
        </h1>
        <p className="text-secondary mb-6">
          An unexpected error occurred. Please try again.
        </p>
        <div className="flex gap-4 justify-center">
          <button
            onClick={reset}
            className="btn-primary"
          >
            Try again
          </button>
          <Link href="/dashboard" className="btn-primary">
            Go to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
