// ui/shared/lib/provider-docs.ts

export function getProviderDocUrl(slug: string): string {
  return `/docs/providers/${slug}`;
}

/** Reads the primary slug, falling back to the one nested in client metadata. */
export function getProviderDocSlug(
  provider: { slug?: string; client_metadata?: Record<string, unknown> }
): string | null {
  if (provider.slug) {
    return provider.slug;
  }
  const metaSlug = provider.client_metadata?.slug;
  if (typeof metaSlug === 'string' && metaSlug) {
    return metaSlug;
  }
  return null;
}
