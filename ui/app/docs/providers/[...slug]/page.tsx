// ui/app/docs/providers/[...slug]/page.tsx

'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

/**
 * Redirects /docs/providers/{namespace}/{slug} to /docs/providers with the
 * provider pre-selected. Slug is namespaced (e.g. shs/openai), so the route is
 * a catch-all and the segments are rejoined into the provider id.
 */
export default function ProviderDocRedirectPage() {
  const params = useParams();
  const router = useRouter();
  const slug = Array.isArray(params.slug) ? params.slug.join('/') : (params.slug as string);

  useEffect(() => {
    router.replace(`/docs/providers?provider=${encodeURIComponent(slug)}`);
  }, [slug, router]);

  return null;
}
