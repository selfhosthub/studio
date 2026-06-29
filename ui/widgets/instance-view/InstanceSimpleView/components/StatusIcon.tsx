// ui/widgets/instance-view/InstanceSimpleView/components/StatusIcon.tsx

'use client';

import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Play,
  Octagon,
} from "lucide-react";

interface StatusIconProps {
  status: string;
  className?: string;
}

/**
 * Render status icon based on status string
 */
export function StatusIcon({ status, className = "w-4 h-4" }: StatusIconProps) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className={`${className} text-success`} />;
    case 'failed':
      return <XCircle className={`${className} text-danger`} />;
    case 'running':
      return <Loader2 className={`${className} text-info animate-spin`} data-status-indicator />;
    case 'queued':
      // Queued = claimed (or about-to-be) by a worker but not actively
      // executing yet. Same color family as running (in-flight), but a
      // non-spinning icon so the difference from RUNNING is visible.
      return <Clock className={`${className} text-info`} />;
    case 'stopped':
      return <Octagon className={`${className} text-danger`} />;
    case 'waiting_for_approval':
      return <Clock className={`${className} text-warning`} />;
    case 'waiting_for_manual_trigger':
      return <Play className={`${className} text-info`} />;
    case 'pending':
    default:
      return <Clock className={`${className} text-muted`} />;
  }
}

/**
 * Helper function to get status icon (for backward compatibility)
 */
export function getStatusIcon(status: string, className: string = "w-4 h-4") {
  return <StatusIcon status={status} className={className} />;
}

export default StatusIcon;
