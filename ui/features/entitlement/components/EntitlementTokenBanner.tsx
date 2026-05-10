// ui/features/entitlement/components/EntitlementTokenBanner.tsx

'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useUser } from '@/entities/user';
import { getEntitlementTokenStatus } from '@/shared/api';
import { KeyRound, ExternalLink, X } from 'lucide-react';

const DISMISSED_KEY = 'studio_entitlement_banner_dismissed';

function getInitialDismissed(): boolean {
  if (typeof window === 'undefined') return true;
  return localStorage.getItem(DISMISSED_KEY) === 'true';
}

export default function EntitlementTokenBanner() {
  const userContext = useUser();
  const pathname = usePathname();
  const [dismissed, setDismissed] = useState(getInitialDismissed);
  const [configured, setConfigured] = useState<boolean | null>(null);

  const isSuperAdmin = userContext?.user?.role === 'super_admin';

  const checkStatus = useCallback(async () => {
    try {
      const status = await getEntitlementTokenStatus();
      setConfigured(status.configured);
      if (status.configured) {
        localStorage.removeItem(DISMISSED_KEY);
      }
    } catch {
      // If the check fails, don't show the banner
      setConfigured(true);
    }
  }, []);

  // Recheck on route change so configuring in another tab/page hides the banner
  useEffect(() => {
    if (isSuperAdmin && !configured) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch on mount/route change
      checkStatus();
    }
  }, [isSuperAdmin, configured, pathname, checkStatus]);

  const handleDismiss = () => {
    localStorage.setItem(DISMISSED_KEY, 'true');
    setDismissed(true);
  };

  if (!isSuperAdmin || dismissed || configured !== false) return null;

  return (
    <div className="bg-info-subtle border-b border-info px-4 py-2">
      <div className="container mx-auto flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-info">
          <KeyRound size={14} className="flex-shrink-0" />
          <span>
            Unlock advanced providers and workflows.{' '}
            <a
              href="https://skool.com/selfhostinnovators"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold underline hover:no-underline inline-flex items-center gap-1"
            >
              Join the Community
              <ExternalLink size={12} />
            </a>
            {' '}to get your Entitlement Token, then{' '}
            <Link href="/secrets" className="font-semibold underline hover:no-underline">
              configure it here
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
