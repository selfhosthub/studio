// ui/app/(authenticated)/infrastructure/components/ProbeStatus.tsx

'use client';

import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import type { ProbeStatus } from '@/shared/api';

export const PROBE_LABELS: Record<ProbeStatus, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  down: 'Down',
};

export function ProbeStatusIcon({ status }: { status: ProbeStatus }) {
  const label = PROBE_LABELS[status];
  if (status === 'healthy') return <CheckCircle className="w-4 h-4 text-success flex-shrink-0" aria-label={label} />;
  if (status === 'degraded') return <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" aria-label={label} />;
  return <XCircle className="w-4 h-4 text-danger flex-shrink-0" aria-label={label} />;
}
