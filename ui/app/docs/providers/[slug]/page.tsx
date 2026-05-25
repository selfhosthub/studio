// ui/app/docs/providers/[slug]/page.tsx

'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

/**
 * Redirects /docs/providers/{slug} to /docs/providers with the provider pre-selected.
 * The index page handles rendering via query param or default selection.
 */
export default function ProviderDocRedirectPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  useEffect(() => {
    router.replace(`/docs/providers?provider=${slug}`);
  }, [slug, router]);

  return null;
}
