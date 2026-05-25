// ui/features/roles/useRoleAccess.ts

/**
 * useRoleAccess Hook
 *
 * Provides role-based access control (RBAC) for pages and components.
 * Automatically redirects unauthorized users to the dashboard.
 */

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useUser } from '@/entities/user';

type UserRole = 'user' | 'admin' | 'super_admin';

export function useRoleAccess(allowedRoles: UserRole[]) {
  const { user, status } = useUser();
  const router = useRouter();

  useEffect(() => {
    // Wait for authentication to complete
    if (status === 'loading') {
      return;
    }

    // Redirect to login if not authenticated
    if (status === 'unauthenticated' || !user) {
      router.push('/login');
      return;
    }

    // Check if user's role is in the allowed roles list
    if (!allowedRoles.includes(user.role)) {
      router.push('/dashboard');
      return;
    }
  }, [user, status, router, allowedRoles]);

  return {
    hasAccess: user && allowedRoles.includes(user.role),
    user,
    status,
    isLoading: status === 'loading',
  };
}
