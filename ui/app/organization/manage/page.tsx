// ui/app/organization/manage/page.tsx

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function OrganizationManagePage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to the details tab by default
    router.push('/organization/manage/details');
  }, [router]);

  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-center">
        <div className="spinner-md"></div>
        <p className="mt-2 text-sm text-secondary">Redirecting to organization details...</p>
      </div>
    </div>
  );
}
