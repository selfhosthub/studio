// ui/app/instances/active/page.tsx

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function InstancesActivePage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to instances list with processing filter
    router.push('/instances/list?status=processing');
  }, [router]);

  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-center">
        <div className="spinner-md"></div>
        <p className="mt-2 text-sm text-secondary">Redirecting to processing instances...</p>
      </div>
    </div>
  );
}
