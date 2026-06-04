// ui/app/settings/page.tsx

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function SettingsPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to the profile tab by default
    router.push('/settings/profile');
  }, [router]);

  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-center">
        <div className="spinner-md"></div>
        <p className="mt-2 text-sm text-secondary">Redirecting to settings...</p>
      </div>
    </div>
  );
}
