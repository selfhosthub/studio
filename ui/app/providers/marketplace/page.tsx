// ui/app/providers/marketplace/page.tsx

"use client";

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function ProvidersMarketplaceRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/providers/list?tab=marketplace');
  }, [router]);
  return null;
}
