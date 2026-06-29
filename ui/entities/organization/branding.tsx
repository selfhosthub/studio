// ui/entities/organization/branding.tsx

// context/BrandingContext.tsx

'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useUser } from '@/entities/user';
import { getOrganization, getPublicBranding } from '@/shared/api';
import { useApiStatus } from '@/shared/hooks/useApiStatus';

export interface BrandingConfig {
  companyName: string;
  shortName: string;
  logoUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  tagline?: string;
  // Marketing page colors
  heroGradientStart?: string;
  heroGradientEnd?: string;
  headerBackground?: string;
  headerText?: string;
  sectionBackground?: string;
}

interface BrandingContextType {
  branding: BrandingConfig;
  isLoading: boolean;
  refreshBranding: () => Promise<void>;
}

// Empty defaults - no fallback text, only structural defaults for colors
const defaultBranding: BrandingConfig = {
  companyName: '',
  shortName: '',
  logoUrl: null,
  primaryColor: '#3B82F6', // blue-600
  secondaryColor: '#10B981', // green-500
  accentColor: '#F59E0B', // amber-500
  tagline: undefined,
  // Marketing page colors
  heroGradientStart: '#2563EB', // blue-600
  heroGradientEnd: '#4F46E5', // indigo-600
  headerBackground: '#FFFFFF', // white
  headerText: '#3B82F6', // blue-600
  sectionBackground: '#F9FAFB' // gray-50
};

const BrandingContext = createContext<BrandingContextType | undefined>(undefined);

interface BrandingProviderProps {
  children: ReactNode;
}

export const BrandingProvider: React.FC<BrandingProviderProps> = ({ children }) => {
  const apiStatus = useApiStatus();
  const [branding, setBranding] = useState<BrandingConfig>(defaultBranding);
  const [isLoading, setIsLoading] = useState(true);
  const userContext = useUser();

  const loadBranding = useCallback(async () => {
    try {
      let brandingData: BrandingConfig | null = null;

      // If user is logged in, try to load their organization's branding first
      if (userContext?.user?.org_id) {
        try {
          const org = await getOrganization(userContext.user.org_id);
          const orgBranding = org.settings?.branding;

          // Use org.name as primary source for companyName, with fallback to settings.branding.company_name
          const companyName = org.name || orgBranding?.company_name || '';

          if (companyName || orgBranding?.short_name || orgBranding?.logo_url) {
            // Org has custom branding configured
            brandingData = {
              companyName,
              shortName: orgBranding?.short_name || '',
              logoUrl: orgBranding?.logo_url || null,
              primaryColor: orgBranding?.primary_color || defaultBranding.primaryColor,
              secondaryColor: orgBranding?.secondary_color || defaultBranding.secondaryColor,
              accentColor: orgBranding?.accent_color || defaultBranding.accentColor,
              tagline: orgBranding?.tagline || undefined,
              heroGradientStart: orgBranding?.hero_gradient_start || defaultBranding.heroGradientStart,
              heroGradientEnd: orgBranding?.hero_gradient_end || defaultBranding.heroGradientEnd,
              headerBackground: orgBranding?.header_background || defaultBranding.headerBackground,
              headerText: orgBranding?.header_text || defaultBranding.headerText,
              sectionBackground: orgBranding?.section_background || defaultBranding.sectionBackground
            };
          }
        } catch {
          // Fall back to public API
        }
      }

      // If no org branding, load from public API (system org branding for public pages)
      if (!brandingData) {
        try {
          const data = await getPublicBranding();
          // Public API returns org_name (organization.name) and company_name (settings.branding.company_name)
          // Prefer org_name as the source of truth
          brandingData = {
            companyName: data.org_name || data.company_name || '',
            shortName: data.short_name || '',
            logoUrl: data.logo_url || null,
            primaryColor: data.primary_color || defaultBranding.primaryColor,
            secondaryColor: data.secondary_color || defaultBranding.secondaryColor,
            accentColor: data.accent_color || defaultBranding.accentColor,
            tagline: data.tagline || undefined,
            heroGradientStart: data.hero_gradient_start || defaultBranding.heroGradientStart,
            heroGradientEnd: data.hero_gradient_end || defaultBranding.heroGradientEnd,
            headerBackground: data.header_background || defaultBranding.headerBackground,
            headerText: data.header_text || defaultBranding.headerText,
            sectionBackground: data.section_background || defaultBranding.sectionBackground
          };
        } catch {
          // Public API unavailable - use defaults
        }
      }

      if (brandingData) {
        setBranding(brandingData);
        injectCSSVariables(brandingData);
      } else {
        setBranding(defaultBranding);
        injectCSSVariables(defaultBranding);
      }
    } finally {
      setIsLoading(false);
    }
  }, [userContext?.user?.org_id]);

  const injectCSSVariables = (_config: BrandingConfig) => {
    // Branding colors are no longer injected into global CSS variables.
    // Dashboard UI uses fixed semantic colors from NEXT_PUBLIC_DASHBOARD_* env vars
    // (injected via dashboardColorScript in layout.tsx).
    // Marketing components consume branding via the useBranding() hook directly.
  };

  const refreshBranding = async () => {
    setIsLoading(true);
    await loadBranding();
  };

  useEffect(() => {
    if (apiStatus !== 'up') return;
    // Load branding once API is confirmed reachable:
    // - If user is authenticated: load from their organization
    // - If unauthenticated: load based on domain (public API)
    loadBranding();
  }, [apiStatus, loadBranding]);

  return (
    <BrandingContext.Provider value={{ branding, isLoading, refreshBranding }}>
      {children}
    </BrandingContext.Provider>
  );
};

export const useBranding = (): BrandingContextType => {
  const context = useContext(BrandingContext);
  if (context === undefined) {
    throw new Error('useBranding must be used within a BrandingProvider');
  }
  return context;
};
