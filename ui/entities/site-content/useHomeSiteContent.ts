// ui/entities/site-content/useHomeSiteContent.ts

'use client';

import { useState, useEffect } from 'react';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { getPublicSiteContent } from '@/shared/api';

export interface HeroConfig {
  visible: boolean;
  headline: string | null;
  subtext: string | null;
  cta_text: string | null;
  cta_link: string | null;
}

export interface FeatureBlock {
  id: string;
  title: string;
  description: string;
  thumbnail?: string | null;
  media_type?: 'image' | 'video';
  workflow_id?: string | null;
  sort_order: number;
  icon?: string | null;
  visible?: boolean;
}

interface HomeSiteContent {
  hero: HeroConfig;
  features: FeatureBlock[];
}

const DEFAULT_HERO: HeroConfig = {
  visible: true,
  headline: null,
  subtext: null,
  cta_text: null,
  cta_link: null,
};

export function useHomeSiteContent() {
  const apiStatus = useApiStatus();
  const [content, setContent] = useState<HomeSiteContent>({
    hero: DEFAULT_HERO,
    features: [],
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (apiStatus !== 'up') return;

    const fetchContent = async () => {
      try {
        const data = await getPublicSiteContent('home');
        const hero = data.content?.hero
          ? { ...DEFAULT_HERO, ...(data.content.hero as Partial<HeroConfig>) }
          : DEFAULT_HERO;

        const features = data.content?.features
          ? [...(data.content.features as FeatureBlock[])].sort(
              (a: FeatureBlock, b: FeatureBlock) => a.sort_order - b.sort_order
            )
          : [];

        setContent({ hero, features });
      } catch {
        // Silently fail - API may be unreachable
      } finally {
        setIsLoading(false);
      }
    };

    fetchContent();
  }, [apiStatus]);

  return { ...content, isLoading };
}
