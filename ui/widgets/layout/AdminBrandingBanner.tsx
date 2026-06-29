// ui/widgets/layout/AdminBrandingBanner.tsx

'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useUser } from '@/entities/user';
import { X, Settings } from 'lucide-react';

const DISMISSED_KEY = 'studio_branding_banner_dismissed';

function getInitialDismissed(): boolean {
  if (typeof window === 'undefined') return true; // SSR: hide to avoid flash
  return localStorage.getItem(DISMISSED_KEY) === 'true';
}

export default function AdminBrandingBanner() {
  const userContext = useUser();
  const [dismissed, setDismissed] = useState(getInitialDismissed);

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, 'true');
    setDismissed(true);
  };

  const role = userContext?.user?.role;
  const isAdmin = role === 'admin' || role === 'super_admin';

  if (!isAdmin || dismissed) return null;

  return (
    <div className="bg-info-subtle border-b border-info px-4 py-2">
      <div className="container mx-auto flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-info">
          <Settings size={14} className="flex-shrink-0" />
          <span>
            This is your default homepage. Customize it in{' '}
            <Link href="/settings/site" className="font-semibold underline hover:no-underline">
              Site Settings
            </Link>
            {' '}and{' '}
            <Link href="/organization/manage/branding" className="font-semibold underline hover:no-underline">
              Branding
            </Link>
            .
          </span>
        </div>
        <button
          onClick={handleDismiss}
          className="text-info hover:text-info p-1"
          aria-label="Dismiss banner"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
