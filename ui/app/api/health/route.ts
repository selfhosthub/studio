// ui/app/api/health/route.ts

import { NextResponse } from 'next/server';

import { VERSION } from '@/shared/lib/version';

/**
 * Health/Status Endpoint
 *
 * Exposes frontend configuration and environment information.
 * Used for:
 * - Debugging: Quickly see which environment the frontend is running in
 * - E2E Test Safety: Tests can validate they're hitting the correct environment
 * - Monitoring: DevOps can verify environment configuration
 *
 * @returns Health check response with environment information
 */
export async function GET() {
  const apiEnv = process.env.NEXT_PUBLIC_API_ENV;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'not-configured';
  const nodeEnv = process.env.NODE_ENV || 'development';

  let environment = apiEnv || 'development';

  const warnings: string[] = [];

  if (!apiEnv) {
    warnings.push('NEXT_PUBLIC_API_ENV not set - defaulting to development');
  }

  if (nodeEnv === 'production' && environment !== 'production') {
    warnings.push('Running in production mode but environment is not production');
  }

  const healthResponse = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: VERSION,

    environment: {
      env: environment,
      nodeEnv: nodeEnv,
      apiEnv: apiEnv || 'not-set',
    },

    configuration: {
      apiUrl,
      analyticsEnabled: process.env.NEXT_PUBLIC_ANALYTICS_ENABLED === 'true',
    },

    // Safety indicator for E2E tests
    safety: {
      isProduction: environment === 'production',
      isE2E: environment === 'e2e',
      isDevelopment: environment === 'development',
      warnings: warnings.length > 0 ? warnings : undefined,
    },
  };

  return NextResponse.json(healthResponse, {
    status: 200,
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Content-Type': 'application/json',
    },
  });
}
