// ui/next.config.mjs

const nextConfig = {
  reactStrictMode: false,
  allowedDevOrigins: process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS
    ? process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS.split(',')
    : [],
  // Enable output tracing for debugging (but not for E2E tests)
  // Standalone mode doesn't work with `npm run start`, so disable for E2E
  ...(process.env.NEXT_PUBLIC_API_ENV !== 'e2e' && { output: 'standalone' }),

  // Disable TypeScript errors during builds (temporary - fix type errors later)
  typescript: {
    ignoreBuildErrors: true,
  },

  // Server external packages (moved from experimental in Next.js 16)
  serverExternalPackages: [],

  // Turbopack config (required for Next.js 16 when webpack config was present)
  // Path aliases are handled by tsconfig.json
  turbopack: {},

  // Optional: Add security headers
  headers: async () => {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
