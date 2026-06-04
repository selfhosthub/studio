// ui/widgets/layout/HomeContent.tsx

'use client';

import { useBranding } from '@/entities/organization';
import { useMaintenance } from '@/features/maintenance';
import { useApiStatus } from '@/shared/hooks/useApiStatus';
import { AdminBrandingBanner, Features, Hero, Testimonials } from '@/widgets/layout';

function MaintenancePage({ reason }: { reason?: string | null }) {
  return (
    <section
      className="flex-1 flex items-center justify-center text-white"
      style={{
        background: `linear-gradient(135deg, var(--theme-hero-gradient-start) 0%, var(--theme-hero-gradient-end) 100%)`
      }}
    >
      <div className="text-center px-4">
        <svg
          className="w-24 h-24 mx-auto mb-6 text-white/90"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </svg>
        <h1 className="text-4xl font-bold mb-4">Scheduled Maintenance</h1>
        <p className="text-xl text-white/80 mb-2">
          {reason || "We're performing scheduled maintenance."}
        </p>
        <p className="text-lg text-white/60">
          We&apos;ll be back shortly. Thank you for your patience.
        </p>
      </div>
    </section>
  );
}

function ApiUnavailablePage() {
  return (
    <section
      className="flex-1 flex items-center justify-center text-white"
      style={{
        background: `linear-gradient(135deg, var(--theme-hero-gradient-start) 0%, var(--theme-hero-gradient-end) 100%)`
      }}
    >
      <div className="text-center px-4">
        <svg
          className="w-24 h-24 mx-auto mb-6 text-white/90"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <h1 className="text-4xl font-bold mb-4">We&apos;re working on it</h1>
        <p className="text-xl text-white/80">
          The site is temporarily down. We&apos;ll be back shortly.
        </p>
      </div>
    </section>
  );
}

export default function HomeContent() {
  const apiStatus = useApiStatus();
  const { branding, isLoading: brandingLoading } = useBranding();
  const { maintenanceMode, reason, isLoading: maintenanceLoading } = useMaintenance();

  if (apiStatus === 'down') {
    return <ApiUnavailablePage />;
  }

  if (apiStatus !== 'up') {
    return null;
  }

  if (!maintenanceLoading && maintenanceMode) {
    return <MaintenancePage reason={reason} />;
  }

  if (!brandingLoading && !branding.companyName) {
    return <ApiUnavailablePage />;
  }

  return (
    <>
      <AdminBrandingBanner />
      <Hero />
      <Features />
      <Testimonials />
    </>
  );
}
