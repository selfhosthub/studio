// ui/entities/page-visibility/context.tsx

// context/PageVisibilityContext.tsx

'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { getPublicPageVisibility } from '@/shared/api';

export interface PageVisibility {
  about: boolean;
  blueprints: boolean;
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
  blueprints: false,
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
  const [isLoading, setIsLoading] = useState(true);

  const loadVisibility = async () => {
    try {
      const data = await getPublicPageVisibility();
      setVisibility({
        about: data.about ?? false,
        blueprints: data.blueprints ?? false,
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
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (apiStatus === 'up') {
      loadVisibility();
    } else if (apiStatus === 'down') {
      // API unreachable - stop loading, use defaults (all true) so pages
      // render instead of showing an infinite spinner.
      setIsLoading(false);
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
