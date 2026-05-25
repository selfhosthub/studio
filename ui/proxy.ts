// ui/proxy.ts

// Renamed from middleware.ts per Next.js 16 migration guide

import { NextRequest, NextResponse } from 'next/server';

/**
 * Next.js Proxy for Custom Domain Detection
 *
 * This proxy runs on every request and detects the incoming domain.
 * It sets a custom header `x-custom-domain` that downstream components
 * (like BrandingContext) can use to fetch organization-specific branding.
 *
 * Flow:
 * 1. Extract domain from request headers
 * 2. Add x-custom-domain header to request
 * 3. BrandingContext reads header and fetches appropriate branding from API
 *
 * Note: In Next.js 16+, proxy runs on Node.js runtime only (not edge).
 */
export function proxy(request: NextRequest) {
  // Get the hostname from the request
  const hostname = request.headers.get('host') || '';

  // Remove port if present
  const domain = hostname.split(':')[0];

  // Create response with custom header
  const response = NextResponse.next();

  // Add custom domain header for downstream use
  response.headers.set('x-custom-domain', domain);

  return response;
}

/**
 * Configure which routes the proxy should run on.
 *
 * We run on all routes to ensure branding is always detected,
 * but you can customize this to exclude specific paths if needed.
 */
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
