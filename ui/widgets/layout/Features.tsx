// ui/widgets/layout/Features.tsx

'use client';

import dynamic from 'next/dynamic';
import Image from 'next/image';
import { useState, useSyncExternalStore } from 'react';
import { useHomeSiteContent } from '@/entities/site-content';
import type { FeatureBlock } from '@/entities/site-content';
import {
  Workflow,
  Brain,
  Image as ImageIcon,
  Video,
  Music,
  Mic,
  Bot,
  Sparkles,
  Zap,
  Settings,
  Shield,
  Globe,
  Layers,
  GitBranch,
  Database,
  Cloud,
  Lock,
  Monitor,
  Cpu,
  Plug,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

// Dynamically import ReactPlayer to avoid hydration issues
const ReactPlayer = dynamic(() => import('react-player'), {
  ssr: false,
  loading: () => (
    <div className="bg-input rounded-md h-56 animate-pulse"></div>
  ),
});

// Curated icon map - static imports only, no dynamic lookups
const ICON_MAP: Record<string, LucideIcon> = {
  'workflow': Workflow,
  'brain': Brain,
  'image': ImageIcon,
  'video': Video,
  'music': Music,
  'mic': Mic,
  'bot': Bot,
  'sparkles': Sparkles,
  'zap': Zap,
  'settings': Settings,
  'shield': Shield,
  'globe': Globe,
  'layers': Layers,
  'git-branch': GitBranch,
  'database': Database,
  'cloud': Cloud,
  'lock': Lock,
  'monitor': Monitor,
  'cpu': Cpu,
  'plug': Plug,
};

function FeatureIcon({ name }: { name: string }) {
  const IconComponent = ICON_MAP[name];
  if (!IconComponent) return null;

  return (
    <div className="flex items-center justify-center w-16 h-16 mx-auto mb-4 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/30 dark:to-indigo-900/30">
      <IconComponent size={32} className="text-info" />
    </div>
  );
}

const emptySubscribe = () => () => {};
function useIsClient() {
  return useSyncExternalStore(emptySubscribe, () => true, () => false);
}

function FeatureCard({ feature }: { feature: FeatureBlock }) {
  const isClient = useIsClient();
  const [imageError, setImageError] = useState(false);

  const hasThumbnail = feature.thumbnail && !imageError;
  const hasIcon = !!(feature.icon && ICON_MAP[feature.icon]);

  return (
    <div className="p-6 border border-primary rounded-lg shadow-sm bg-card">
      {/* Icon fallback when no working thumbnail */}
      {!hasThumbnail && hasIcon && (
        <FeatureIcon name={feature.icon!} />
      )}

      <h3 className="text-2xl font-semibold mb-2 text-primary">{feature.title}</h3>
      <p className="text-secondary mb-4">{feature.description}</p>

      {/* Image/video when thumbnail is set and loads successfully */}
      {isClient && feature.thumbnail && !imageError && (
        <>
          {feature.media_type === 'image' && (
            <div className="image-container">
              <Image
                src={feature.thumbnail}
                alt={feature.title}
                width={500}
                height={300}
                className="w-full h-auto rounded-md"
                priority={feature.sort_order === 0}
                onError={() => setImageError(true)}
              />
            </div>
          )}
          {feature.media_type === 'video' && (
            <div className="video-container mt-4">
              <ReactPlayer
                url={feature.thumbnail}
                controls
                width="100%"
                height="auto"
                className="rounded-md"
              />
            </div>
          )}
        </>
      )}

      {/* Placeholder during server rendering (only for features with thumbnails) */}
      {!isClient && feature.thumbnail && !imageError && (
        <div className="bg-input rounded-md h-56 animate-pulse"></div>
      )}
    </div>
  );
}

const Features = () => {
  const { features, isLoading } = useHomeSiteContent();

  // Filter out hidden features
  const visibleFeatures = features.filter(f => f.visible !== false);

  // Don't render section if loading or no visible features
  if (isLoading || visibleFeatures.length === 0) {
    return null;
  }

  return (
    <section className="py-10">
      <div className="container mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          {visibleFeatures.map((feature) => (
            <FeatureCard key={feature.id} feature={feature} />
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;
