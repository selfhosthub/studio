// ui/entities/page-visibility/context.tsx

// context/PageVisibilityContext.tsx

'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { getPublicPageVisibility } from '@/shared/api';

export interface PageVisibility {
  about: boolean;
  compliance: boolean;
  contact: boolean;
  docs: boolean;
  privacy: boolean;
  support: boolean;
  terms: boolean;
  // Note: pricing visibility is controlled by useBillingAvailable (whether plans exist)
}

interface PageVisibilityContextType {
  visibility: PageVisibility;
  isLoading: boolean;
  isPageVisible: (page: keyof PageVisibility) => boolean;
  refetch: () => Promise<void>;
}

// Defaults to true so pages render when the API is unreachable (matches
// server-side defaultVisibility in page-visibility.ts). Hiding pages on
// API failure is worse UX than showing them with potentially stale content.
const defaultVisibility: PageVisibility = {
  about: true,
  compliance: true,
  contact: true,
  docs: true,
  privacy: true,
  support: true,
  terms: true,
};

const PageVisibilityContext = createContext<PageVisibilityContextType | undefined>(undefined);

interface PageVisibilityProviderProps {
  children: ReactNode;
}

export const PageVisibilityProvider: React.FC<PageVisibilityProviderProps> = ({ children }) => {
  const apiStatus = useApiStatus();
  const [visibility, setVisibility] = useState<PageVisibility>(defaultVisibility);
  const [loaded, setLoaded] = useState(false);

  // Derived rather than set in the effect: still loading until either the fetch
  // settles or the API is known to be down (in which case we keep defaults).
  const isLoading = !loaded && apiStatus !== 'down';

  const loadVisibility = async () => {
    try {
      const data = await getPublicPageVisibility();
      setVisibility({
        about: data.about ?? false,
        compliance: data.compliance ?? false,
        contact: data.contact ?? false,
        docs: data.docs ?? false,
        privacy: data.privacy ?? false,
        support: data.support ?? false,
        terms: data.terms ?? false,
      });
    } catch {
      // API unavailable - keep defaults (all true, pages visible)
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    if (apiStatus === 'up') {
      // IIFE so the deferred setState inside loadVisibility isn't read as a
      // synchronous set within the effect body.
      void (async () => { await loadVisibility(); })();
    }
  }, [apiStatus]);

  const isPageVisible = (page: keyof PageVisibility): boolean => {
    return visibility[page];
  };

  const refetch = async () => {
    await loadVisibility();
  };

  return (
    <PageVisibilityContext.Provider value={{ visibility, isLoading, isPageVisible, refetch }}>
      {children}
    </PageVisibilityContext.Provider>
  );
};

export const usePageVisibility = (): PageVisibilityContextType => {
  const context = useContext(PageVisibilityContext);
  if (context === undefined) {
    throw new Error('usePageVisibility must be used within a PageVisibilityProvider');
  }
  return context;
};
