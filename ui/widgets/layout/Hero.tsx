// ui/widgets/layout/Hero.tsx

'use client';

import Link from 'next/link';
import { useBranding } from '@/entities/organization';
import { useHomeSiteContent } from '@/entities/site-content';
import { useRegistrationSettings } from '@/entities/registration';

const Hero = () => {
  const { branding } = useBranding();
  const { hero, isLoading: contentLoading } = useHomeSiteContent();
  const { allowRegistration } = useRegistrationSettings();

  // Don't render while loading (prevents flash of default content) or when admin toggles off
  if (contentLoading || hero.visible === false) return null;

  // Smart CTA link: admin override > registration > login
  const defaultCtaHref = allowRegistration
    ? '/register'
    : '/login';
  const ctaHref = hero.cta_link || defaultCtaHref;
  const defaultCtaText = allowRegistration ? 'Get Started' : 'Sign In';
  const ctaText = hero.cta_text || defaultCtaText;

  // Hero text: admin override > branding > neutral defaults
  const headline = hero.headline || branding.companyName || 'Your AI Workflow Platform';
  const subtext = hero.subtext || branding.tagline || 'Build, run, and manage automated workflows.';

  return (
    <section
      className="text-white py-20"
      style={{
        background: `linear-gradient(135deg, ${branding.heroGradientStart || '#2563EB'} 0%, ${branding.heroGradientEnd || '#4F46E5'} 100%)`
      }}
    >
      <div className="container mx-auto text-center px-4">
        <h1 className="text-5xl font-bold mb-6">{headline}</h1>
        <p className="text-xl mb-10 max-w-3xl mx-auto opacity-90">
          {subtext}
        </p>
        <div className="flex justify-center">
          <Link
            href={ctaHref}
            className="px-8 py-4 rounded-md text-lg font-semibold transition-colors hover:opacity-90"
            style={{
              backgroundColor: branding.primaryColor,
              color: '#FFFFFF',
            }}
          >
            {ctaText}
          </Link>
        </div>
      </div>
    </section>
  );
};

export default Hero;
