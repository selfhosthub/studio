// ui/widgets/layout/ProtectedRoute.tsx

'use client';

import { useUser } from '@/entities/user';
import { Loader2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  
  // Use the UserContext which now has default values so it will never be undefined
  const { user, status, isLoading } = useUser();
  
  // Set mounted state after hydration
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // Handle authentication state and redirects
  useEffect(() => {
    if (mounted && status === 'unauthenticated') {
      router.push('/login');
    }
  }, [status, router, mounted]);

  // During server-side rendering or initial mounting, show loading state
  if (!mounted || status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div data-testid="loading-spinner">
          <Loader2 data-testid="loading-spinner-icon" className="h-8 w-8 animate-spin text-info" />
        </div>
      </div>
    );
  }

  // Handle unauthenticated state - this should briefly show before redirect happens
  if (status === 'unauthenticated' || !user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-secondary">Redirecting to login...</p>
      </div>
    );
  }

  // User is authenticated, render children with a testid for testing
  return <div data-testid="protected-content">{children}</div>;
}