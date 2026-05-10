// ui/entities/user/context.tsx

'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import * as apiClient from '@/shared/api';
import { useToast } from '@/features/toast';

// Re-export User type from shared layer (canonical definition lives there
// to avoid FSD layer violations where shared/ imports from entities/).
export type { User } from '@/shared/types/user';
import type { User } from '@/shared/types/user';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

type UserContextType = {
  user: User | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  register: (firstName: string, lastName: string, email: string, password: string, planSlug?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
};

// Create a context with default values to avoid undefined checks
export const UserContext = createContext<UserContextType>({
  user: null,
  status: 'unauthenticated',
  login: async () => {},
  register: async () => {},
  logout: async () => {},
  refreshUser: async () => {},
  isLoading: false,
  error: null
});

export const UserProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { toast } = useToast();

  // Check if user is logged in on initial load, but only on the client side
  useEffect(() => {
    // Decode the locally-stored JWT so the tree can render without waiting on the network.
    let hasLocalUser = false;
    try {
      const userData = apiClient.getCurrentUser();
      if (userData) {
        setUser(userData);
        setStatus('authenticated');
        hasLocalUser = true;
      } else {
        setStatus('unauthenticated');
      }
    } catch {
      setStatus('unauthenticated');
    }

    // Fire-and-forget server-side validation: if the JWT references a user/org that
    // no longer exists (e.g. dev DB was rebuilt), core.ts will emit 'session-expired'
    // which is handled below. We still await it so 404 (user deleted) is also caught.
    if (hasLocalUser) {
      void (async () => {
        try {
          await apiClient.getCurrentUserProfile();
        } catch (err) {
          const errStatus = (err as { status?: number } | null)?.status;
          // 401 is handled by core.ts via the session-expired event.
          // Handle 404 here (user deleted from DB while token was still valid).
          if (errStatus === 404) {
            apiClient.clearAuth();
            setUser(null);
            setStatus('unauthenticated');
            toast({
              title: 'Session expired',
              description: 'Your session is no longer valid. Please sign in again.',
              variant: 'destructive',
              duration: 4000,
            });
            router.push('/login');
          }
        }
      })();
    }
    // Deliberately run only on mount - toast identity may change but we don't
    // want to re-validate on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Listen for session-expired events dispatched by core.ts when any API call
  // returns 401 and the refresh token is also exhausted. Handles mid-session
  // expiry that the mount-time check above would miss.
  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
      setStatus('unauthenticated');
      toast({
        title: 'Session expired',
        description: 'Your session is no longer valid. Please sign in again.',
        variant: 'destructive',
        duration: 4000,
      });
      router.push('/login');
    };

    window.addEventListener('session-expired', handleSessionExpired);
    return () => window.removeEventListener('session-expired', handleSessionExpired);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // Use real API
      const response = await apiClient.login(email, password);

      // Store tokens (access and refresh) and decode user info
      apiClient.storeAuth(response.access_token, response.refresh_token);
      const userData = apiClient.decodeToken(response.access_token);

      setUser(userData);
      setStatus('authenticated');

      router.push('/dashboard');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed. Please try again.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (firstName: string, lastName: string, email: string, password: string, planSlug?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // Call registration API with optional plan
      const response = await apiClient.register(firstName, lastName, email, password, planSlug);

      // Store tokens (access and refresh) and decode user info
      apiClient.storeAuth(response.access_token, response.refresh_token);
      const userData = apiClient.decodeToken(response.access_token);

      setUser(userData);
      setStatus('authenticated');

      // Redirect to branding setup for new organization
      router.push('/organization/manage/branding?welcome=true');
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Registration failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    // Call backend logout for security audit logging, then clear local auth
    await apiClient.logout();
    setUser(null);
    setStatus('unauthenticated');
    router.push('/login');
  };

  const refreshUser = async () => {
    try {
      // Fetch fresh user data from the API
      const profile = await apiClient.getCurrentUserProfile();
      if (profile && user) {
        // Merge API profile data with existing user data
        setUser({
          ...user,
          first_name: profile.first_name,
          last_name: profile.last_name,
          username: profile.username || user.username,
          email: profile.email || user.email,
          avatar_url: profile.avatar_url ?? undefined,
        });
      }
    } catch {
      // Silently fail if refresh fails
    }
  };

  return (
    <UserContext.Provider value={{ user, status, login, register, logout, refreshUser, isLoading, error }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => {
  const context = useContext(UserContext);
  return context;
};