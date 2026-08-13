// ui/entities/user/context.tsx

'use client';

import { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
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
  mustChangePassword: boolean;
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
  mustChangePassword: false,
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
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { toast } = useToast();

  // Fires exactly once when the client mounts. localStorage isn't available
  // during SSR, so this can't move into a useState initializer; the ref guard
  // keeps the synchronous auth-resolve setState off every subsequent render.
  const didInitRef = useRef(false);

  // Check if user is logged in on initial load, but only on the client side
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;

    // The token is a pure session pointer - it carries no role/identity.
    // Compute first, then set state directly (no setState buried in branches).
    // With a token we go to 'loading' and hydrate the user from /users/me (the
    // DB source of truth); without one we're unauthenticated.
    const hasToken = apiClient.isAuthenticated();
    setUser(null);
    setStatus(hasToken ? 'loading' : 'unauthenticated');

    if (!hasToken) return;

    void (async () => {
      try {
        const profile = await apiClient.getCurrentUserProfile();
        const hydrated = apiClient.profileToUser(profile);
        apiClient.cacheUser(hydrated);
        setUser(hydrated);
        setStatus('authenticated');
      } catch (err) {
        const errStatus = (err as { status?: number } | null)?.status;
        // 404 (user deleted) / 401 (token rejected): session is dead.
        if (errStatus === 404 || errStatus === 401) {
          apiClient.clearAuth();
          setUser(null);
          setStatus('unauthenticated');
          if (errStatus === 404) {
            toast({
              title: 'Session expired',
              description: 'Your session is no longer valid. Please sign in again.',
              variant: 'destructive',
              duration: 4000,
            });
            router.push('/login');
          }
          return;
        }
        // Transient failure (network/5xx): fall back to the last cached profile
        // so a blip doesn't log the user out. core.ts handles real 401s.
        const cached = apiClient.getCurrentUser();
        setUser(cached);
        setStatus(cached ? 'authenticated' : 'unauthenticated');
      }
    })();
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

      // Store the session-pointer token, then hydrate the user from /users/me
      // (the DB source of truth) - the token carries no role/identity claims.
      apiClient.storeAuth(response.access_token, response.refresh_token);
      const profile = await apiClient.getCurrentUserProfile();
      const userData = apiClient.profileToUser(profile);
      apiClient.cacheUser(userData);

      setUser(userData);
      setStatus('authenticated');

      // An admin-set one-time password must be changed before anything else;
      // the API refuses all other endpoints until it is. The flag also feeds
      // the login page's authenticated-redirect so it cannot race this push.
      if (response.must_change_password) {
        setMustChangePassword(true);
        toast({
          title: 'Password change required',
          description: 'Your password was reset by an administrator. Please set a new one.',
          variant: 'destructive',
          duration: 6000,
        });
        router.push('/settings/account');
      } else {
        setMustChangePassword(false);
        router.push('/dashboard');
      }
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

      // Store the session-pointer token, then hydrate from /users/me (DB truth).
      apiClient.storeAuth(response.access_token, response.refresh_token);
      const profile = await apiClient.getCurrentUserProfile();
      const userData = apiClient.profileToUser(profile);
      apiClient.cacheUser(userData);

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
      // Fetch fresh user data from the API (DB source of truth) and re-cache it.
      const profile = await apiClient.getCurrentUserProfile();
      const hydrated = apiClient.profileToUser(profile);
      apiClient.cacheUser(hydrated);
      setUser(hydrated);
    } catch {
      // Silently fail if refresh fails
    }
  };

  return (
    <UserContext.Provider value={{ user, status, mustChangePassword, login, register, logout, refreshUser, isLoading, error }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => {
  const context = useContext(UserContext);
  return context;
};